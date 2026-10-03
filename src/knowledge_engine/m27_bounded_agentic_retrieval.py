from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

M27_BOUNDED_AGENTIC_RETRIEVAL_ENABLED = "M27_BOUNDED_AGENTIC_RETRIEVAL_ENABLED"
M27_ISOLATED_RUNTIME = "M27_ISOLATED_RUNTIME"

MAX_RETRIEVAL_ROUNDS = 2
SECOND_ROUND_RETRIEVAL_RESERVE_MS = 1_500
MAX_GAP_REQUIREMENTS_PER_ROUND = 3
MAX_TERMS_PER_REQUIREMENT = 6
MAX_GAP_QUERY_CHARS = 768

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_MATERIAL_SUPPORT_STATES = frozenset({"UNSUPPORTED", "UNKNOWN"})
_STRUCTURAL_REQUIREMENT_IDS = frozenset({"explanatory_answer"})
_SAFE_REQUIREMENT_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")


class SecondRoundDecisionCode(StrEnum):
    DISABLED = "DISABLED"
    NOT_ISOLATED_RUNTIME = "NOT_ISOLATED_RUNTIME"
    NO_MATERIAL_GAP = "NO_MATERIAL_GAP"
    MAX_ROUNDS_REACHED = "MAX_ROUNDS_REACHED"
    DEADLINE_BUDGET_BLOCKED = "DEADLINE_BUDGET_BLOCKED"
    PROVIDER_BUDGET_BLOCKED = "PROVIDER_BUDGET_BLOCKED"
    READY = "READY"


@dataclass(frozen=True, slots=True)
class BoundedRetrievalFlags:
    requested: bool = False
    isolated_runtime: bool = False

    @property
    def enabled(self) -> bool:
        return self.requested and self.isolated_runtime


@dataclass(frozen=True, slots=True)
class SecondRoundPlan:
    should_run: bool
    decision_code: SecondRoundDecisionCode
    missing_requirement_ids: tuple[str, ...]
    rounds_completed: int
    max_rounds: int
    deadline_remaining_ms: int
    minimum_required_ms: int
    provider_attempts_remaining: int

    def as_safe_dict(self) -> dict[str, object]:
        return {
            "should_run": self.should_run,
            "decision_code": self.decision_code.value,
            "missing_requirement_ids": self.missing_requirement_ids,
            "rounds_completed": self.rounds_completed,
            "max_rounds": self.max_rounds,
            "deadline_remaining_ms": self.deadline_remaining_ms,
            "minimum_required_ms": self.minimum_required_ms,
            "provider_attempts_remaining": self.provider_attempts_remaining,
        }


def load_bounded_retrieval_flags(
    *,
    environ: Mapping[str, str] | None = None,
    isolated_runtime: bool | None = None,
) -> BoundedRetrievalFlags:
    """Resolve Stage 6 flags without retaining raw environment values."""

    values = os.environ if environ is None else environ
    requested = (
        values.get(M27_BOUNDED_AGENTIC_RETRIEVAL_ENABLED, "").strip().casefold()
        in _TRUE_VALUES
    )
    isolated = (
        values.get(M27_ISOLATED_RUNTIME, "").strip().casefold() in _TRUE_VALUES
        if isolated_runtime is None
        else bool(isolated_runtime)
    )
    return BoundedRetrievalFlags(requested=requested, isolated_runtime=isolated)


def material_gap_requirement_ids(
    *,
    requirements: Sequence[object],
    support_classification: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    """Return material requirement IDs that existing M26 support still lacks."""

    support_by_id: dict[str, str] = {}
    for item in support_classification:
        requirement_id = str(item.get("facet_id") or "").strip()
        if not requirement_id or not _SAFE_REQUIREMENT_ID_RE.fullmatch(requirement_id):
            continue
        support_by_id[requirement_id] = str(item.get("support_state") or "UNKNOWN").upper()

    missing: list[str] = []
    for requirement in requirements:
        requirement_id = _requirement_id(requirement)
        if (
            not requirement_id
            or requirement_id in _STRUCTURAL_REQUIREMENT_IDS
            or not _SAFE_REQUIREMENT_ID_RE.fullmatch(requirement_id)
        ):
            continue
        if support_by_id.get(requirement_id, "UNKNOWN") in _MATERIAL_SUPPORT_STATES:
            missing.append(requirement_id)
    return tuple(dict.fromkeys(missing))


def plan_second_retrieval_round(
    *,
    flags: BoundedRetrievalFlags,
    requirements: Sequence[object],
    support_classification: Sequence[Mapping[str, Any]],
    rounds_completed: int,
    deadline_remaining_ms: int,
    provider_attempts_remaining: int,
    post_retrieval_reserve_ms: int,
) -> SecondRoundPlan:
    """Decide whether exactly one additional evidence-gap retrieval is allowed."""

    missing_ids = material_gap_requirement_ids(
        requirements=requirements,
        support_classification=support_classification,
    )
    minimum_required_ms = max(0, int(post_retrieval_reserve_ms)) + (
        SECOND_ROUND_RETRIEVAL_RESERVE_MS
    )
    base = {
        "missing_requirement_ids": missing_ids,
        "rounds_completed": max(0, int(rounds_completed)),
        "max_rounds": MAX_RETRIEVAL_ROUNDS,
        "deadline_remaining_ms": max(0, int(deadline_remaining_ms)),
        "minimum_required_ms": minimum_required_ms,
        "provider_attempts_remaining": max(0, int(provider_attempts_remaining)),
    }

    if not flags.requested:
        return SecondRoundPlan(False, SecondRoundDecisionCode.DISABLED, **base)
    if not flags.isolated_runtime:
        return SecondRoundPlan(
            False,
            SecondRoundDecisionCode.NOT_ISOLATED_RUNTIME,
            **base,
        )
    if not missing_ids:
        return SecondRoundPlan(False, SecondRoundDecisionCode.NO_MATERIAL_GAP, **base)
    if base["rounds_completed"] >= MAX_RETRIEVAL_ROUNDS:
        return SecondRoundPlan(False, SecondRoundDecisionCode.MAX_ROUNDS_REACHED, **base)
    if base["provider_attempts_remaining"] <= 0:
        return SecondRoundPlan(
            False,
            SecondRoundDecisionCode.PROVIDER_BUDGET_BLOCKED,
            **base,
        )
    if base["deadline_remaining_ms"] < minimum_required_ms:
        return SecondRoundPlan(
            False,
            SecondRoundDecisionCode.DEADLINE_BUDGET_BLOCKED,
            **base,
        )
    return SecondRoundPlan(True, SecondRoundDecisionCode.READY, **base)


def build_gap_retrieval_query(
    *,
    base_query: str,
    requirements: Sequence[object],
    missing_requirement_ids: Sequence[str],
) -> str:
    """Build a deterministic internal query from existing requirement evidence terms.

    The returned query is runtime-internal. It must never be placed in a trace,
    report, response metadata, or persistence surface.
    """

    requirement_by_id = {
        requirement_id: requirement
        for requirement in requirements
        if (requirement_id := _requirement_id(requirement))
    }
    additions: list[str] = []
    seen: set[str] = set()
    for requirement_id in tuple(missing_requirement_ids)[:MAX_GAP_REQUIREMENTS_PER_ROUND]:
        requirement = requirement_by_id.get(str(requirement_id))
        if requirement is None:
            continue
        candidates = [
            _requirement_exact_phrase(requirement),
            *_requirement_evidence_terms(requirement),
        ]
        kept = 0
        for raw in candidates:
            term = _normalize_query_term(raw)
            key = term.casefold()
            if not term or key in seen:
                continue
            seen.add(key)
            additions.append(term)
            kept += 1
            if kept >= MAX_TERMS_PER_REQUIREMENT:
                break

    base = re.sub(r"\s+", " ", str(base_query or "")).strip()
    suffix = " ".join(additions).strip()
    if not suffix:
        return base[:MAX_GAP_QUERY_CHARS]

    suffix_budget = min(len(suffix), MAX_GAP_QUERY_CHARS // 2)
    suffix = suffix[:suffix_budget].rstrip()
    base_budget = max(0, MAX_GAP_QUERY_CHARS - len(suffix) - 1)
    anchored_base = base[:base_budget].rstrip()
    if not anchored_base:
        return suffix[:MAX_GAP_QUERY_CHARS]
    return f"{anchored_base} {suffix}"[:MAX_GAP_QUERY_CHARS].rstrip()


def merge_retrieval_round_mapping(
    primary: Mapping[str, Any],
    secondary: Mapping[str, Any],
    *,
    collection_field: str,
) -> dict[str, Any]:
    """Merge candidate/result lists while keeping primary round metadata authoritative."""

    merged = dict(primary)
    primary_items = _mapping_items(primary.get(collection_field))
    secondary_items = _mapping_items(secondary.get(collection_field))
    seen: set[tuple[str, str]] = set()
    combined: list[dict[str, Any]] = []
    for item in (*primary_items, *secondary_items):
        key = _retrieval_item_key(item)
        if key in seen:
            continue
        seen.add(key)
        combined.append(item)
    merged[collection_field] = combined

    if collection_field == "results":
        for optional_list_field in ("relation_expansions", "citations"):
            values = [
                *(_mapping_items(primary.get(optional_list_field))),
                *(_mapping_items(secondary.get(optional_list_field))),
            ]
            if values:
                merged[optional_list_field] = _dedupe_mappings(values)

    if "backend_identity" not in merged and isinstance(
        secondary.get("backend_identity"), Mapping
    ):
        merged["backend_identity"] = dict(secondary["backend_identity"])
    return merged


def _mapping_items(value: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, Mapping))


def _dedupe_mappings(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = _retrieval_item_key(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(item))
    return result


def _retrieval_item_key(item: Mapping[str, Any]) -> tuple[str, str]:
    for field in ("section_id", "passage_id", "evidence_id", "edge_id", "id"):
        value = str(item.get(field) or "").strip()
        if value:
            return field, value
    source = str(item.get("source_id") or item.get("source_identity") or "").strip()
    locator = str(item.get("locator_id") or item.get("uri") or "").strip()
    if source or locator:
        return "source_locator", f"{source}#{locator}"
    return "opaque", repr(sorted((str(k), type(v).__name__) for k, v in item.items()))


def _requirement_id(requirement: object) -> str:
    if isinstance(requirement, Mapping):
        return str(requirement.get("requirement_id") or "").strip()
    return str(getattr(requirement, "requirement_id", "") or "").strip()


def _requirement_exact_phrase(requirement: object) -> str:
    if isinstance(requirement, Mapping):
        return str(requirement.get("exact_phrase") or "")
    return str(getattr(requirement, "exact_phrase", "") or "")


def _requirement_evidence_terms(requirement: object) -> tuple[str, ...]:
    if isinstance(requirement, Mapping):
        raw = requirement.get("evidence_terms", ())
    else:
        raw = getattr(requirement, "evidence_terms", ())
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ()
    return tuple(str(item) for item in raw if str(item).strip())


def _normalize_query_term(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    return text[:160]


__all__ = [
    "M27_BOUNDED_AGENTIC_RETRIEVAL_ENABLED",
    "M27_ISOLATED_RUNTIME",
    "MAX_RETRIEVAL_ROUNDS",
    "SECOND_ROUND_RETRIEVAL_RESERVE_MS",
    "BoundedRetrievalFlags",
    "SecondRoundDecisionCode",
    "SecondRoundPlan",
    "load_bounded_retrieval_flags",
    "material_gap_requirement_ids",
    "plan_second_retrieval_round",
    "build_gap_retrieval_query",
    "merge_retrieval_round_mapping",
]
