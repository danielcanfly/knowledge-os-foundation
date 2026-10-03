from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

from .m27_context_runtime_contracts import STAGE1_UNAVAILABLE
from .m27_decision_trace import GuardObservation, GuardOutcome, TraceGuard
from .m27_legacy_m26_adapters import (
    LegacyM26ContextCompilerAdapter,
    LegacyM26DeadlineBudgetAdapter,
    LegacyM26SemanticRoutingAdapter,
    LegacyM26VerifierAdapter,
)

MISSING_SIGNAL = "missing_signal"
MissingSignal = Literal["missing_signal"]

_CASE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
_REQUIRED_GUARDS = (
    TraceGuard.BAD_TEMPLATE,
    TraceGuard.UNSUPPORTED_MATERIAL_CLAIM,
    TraceGuard.GENERIC_EXTRACTIVE_FALLBACK,
)
_SAFE_CITATION_SHAPE_FIELDS = frozenset(
    {
        "citation_id",
        "claim_id",
        "evidence_id",
        "locator_id",
        "source_identity",
        "evidence_type",
        "runtime_owned_locator",
    }
)


class ResponseStatusClass(StrEnum):
    CITED_ANSWER = "CITED_ANSWER"
    SAFE_ABSTENTION = "SAFE_ABSTENTION"
    ERROR = "ERROR"
    OTHER = "OTHER"
    UNAVAILABLE = "UNAVAILABLE"


class EquivalenceClassification(StrEnum):
    EQUIVALENT = "EQUIVALENT"
    EXPECTED_UNAVAILABLE_STAGE1 = "EXPECTED_UNAVAILABLE_STAGE1"
    LEGACY_EXPECTATION_DRIFT = "LEGACY_EXPECTATION_DRIFT"
    NORMALIZATION_DRIFT = "NORMALIZATION_DRIFT"
    MISSING_SIGNAL = "MISSING_SIGNAL"
    UNSAFE_DRIFT = "UNSAFE_DRIFT"


ReplayValue = str | int | bool | None | tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RoutingSnapshot:
    route: ReplayValue = MISSING_SIGNAL
    reason: ReplayValue = MISSING_SIGNAL
    deadline_remaining_ms: ReplayValue = MISSING_SIGNAL
    minimum_budget_ms: ReplayValue = MISSING_SIGNAL
    provider_attempts_remaining: ReplayValue = MISSING_SIGNAL
    affordable: ReplayValue = MISSING_SIGNAL
    compute_tier: ReplayValue = MISSING_SIGNAL
    provider_budget_class: ReplayValue = MISSING_SIGNAL


@dataclass(frozen=True, slots=True)
class ContextCompilerSnapshot:
    status: ReplayValue = MISSING_SIGNAL
    selected_evidence_ids: ReplayValue = MISSING_SIGNAL
    selected_evidence_count: ReplayValue = MISSING_SIGNAL
    citation_count: ReplayValue = MISSING_SIGNAL
    citation_shape: ReplayValue = MISSING_SIGNAL


@dataclass(frozen=True, slots=True)
class VerificationSnapshot:
    status: ReplayValue = MISSING_SIGNAL
    terminal_status: ReplayValue = MISSING_SIGNAL
    safe_abstention: ReplayValue = MISSING_SIGNAL
    provider_call_count: ReplayValue = MISSING_SIGNAL
    material_claim_support_verified: ReplayValue = MISSING_SIGNAL
    citation_locator_valid: ReplayValue = MISSING_SIGNAL
    unsupported_accepted_claims: ReplayValue = MISSING_SIGNAL
    repair_attempted: ReplayValue = MISSING_SIGNAL
    citation_count: ReplayValue = MISSING_SIGNAL
    citation_shape: ReplayValue = MISSING_SIGNAL
    answer_source: ReplayValue = MISSING_SIGNAL


@dataclass(frozen=True, slots=True)
class SanitizedReplayInput:
    case_id: str
    routing: RoutingSnapshot
    context_compiler: ContextCompilerSnapshot
    verification: VerificationSnapshot
    guard_outcomes: tuple[GuardObservation, ...] = ()
    legacy_expected_status_class: ResponseStatusClass | None = None

    def __post_init__(self) -> None:
        if not _CASE_ID_RE.fullmatch(self.case_id):
            raise ValueError(
                "case_id must be a short sanitized identifier, not free-form query text"
            )
        guards = [item.guard for item in self.guard_outcomes]
        if len(set(guards)) != len(guards):
            raise ValueError("guard_outcomes must not contain duplicate guards")
        if any(item.guard not in _REQUIRED_GUARDS for item in self.guard_outcomes):
            raise ValueError("guard_outcomes contains a guard outside Stage 2 replay scope")


@dataclass(frozen=True, slots=True)
class FieldComparison:
    field: str
    legacy_value: ReplayValue
    normalized_value: ReplayValue
    classification: EquivalenceClassification
    safety_critical: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "field": self.field,
            "classification": self.classification.value,
            "safety_critical": self.safety_critical,
        }


@dataclass(frozen=True, slots=True)
class ReplayCaseResult:
    case_id: str
    overall_classification: EquivalenceClassification
    comparisons: tuple[FieldComparison, ...]

    @property
    def available_signals_equivalent(self) -> bool:
        return all(
            item.classification
            not in {
                EquivalenceClassification.NORMALIZATION_DRIFT,
                EquivalenceClassification.UNSAFE_DRIFT,
            }
            for item in self.comparisons
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "overall_classification": self.overall_classification.value,
            "available_signals_equivalent": self.available_signals_equivalent,
            "comparisons": [item.as_dict() for item in self.comparisons],
        }


def capture_sanitized_replay_input(
    *,
    case_id: str,
    routing_signal: object | None = None,
    compiled_output: Mapping[str, object] | None = None,
    verification_output: Mapping[str, object] | None = None,
    guard_outcomes: Mapping[TraceGuard | str, GuardOutcome | str] | None = None,
    compute_tier: str | MissingSignal = MISSING_SIGNAL,
    provider_budget_class: str | MissingSignal = MISSING_SIGNAL,
    legacy_expected_status_class: ResponseStatusClass | None = None,
) -> SanitizedReplayInput:
    """Capture only replay-safe fields from already-produced M26 outputs.

    The returned object cannot contain raw query text, answer text, evidence/source
    bodies, provider prompts, credentials, environment values, or private payloads.
    """

    routing = _capture_routing(
        routing_signal,
        compute_tier=compute_tier,
        provider_budget_class=provider_budget_class,
    )
    context = _capture_context_compiler(compiled_output)
    verification = _capture_verification(verification_output)
    guards = _capture_guards(guard_outcomes)
    return SanitizedReplayInput(
        case_id=case_id,
        routing=routing,
        context_compiler=context,
        verification=verification,
        guard_outcomes=guards,
        legacy_expected_status_class=legacy_expected_status_class,
    )


def run_replay_equivalence(replay_input: SanitizedReplayInput) -> ReplayCaseResult:
    """Compare sanitized legacy M26 signals with Stage 1 adapter normalization."""

    routing_mapping = _routing_mapping(replay_input.routing)
    context_mapping = _context_mapping(replay_input.context_compiler)
    verification_mapping = _verification_mapping(replay_input.verification)

    context_plan = LegacyM26SemanticRoutingAdapter().normalize(routing_mapping)
    compute = LegacyM26DeadlineBudgetAdapter().normalize(routing_mapping)
    compiled = LegacyM26ContextCompilerAdapter().normalize(context_mapping)
    verified = LegacyM26VerifierAdapter().normalize(verification_mapping)

    legacy_status_class = classify_response_status(replay_input.verification)
    normalized_status_class = classify_response_status(
        VerificationSnapshot(
            status=_coerce_adapter_value(verified.status),
            terminal_status=_coerce_adapter_value(verified.terminal_status),
            safe_abstention=_coerce_adapter_value(verified.safe_abstention),
            provider_call_count=_coerce_adapter_value(verified.provider_call_count),
            material_claim_support_verified=_coerce_adapter_value(
                verified.material_claim_support_verified
            ),
            citation_locator_valid=_coerce_adapter_value(verified.citation_locator_valid),
            unsupported_accepted_claims=_coerce_adapter_value(
                verified.unsupported_accepted_claims
            ),
            repair_attempted=_coerce_adapter_value(verified.repair_attempted),
            citation_count=_coerce_adapter_value(verified.citation_count),
            citation_shape=STAGE1_UNAVAILABLE,
            answer_source=_coerce_adapter_value(verified.answer_source),
        )
    )

    comparisons: list[FieldComparison] = [
        _comparison(
            "response_status_class",
            legacy_status_class.value,
            normalized_status_class.value,
            safety_critical=True,
        ),
        _comparison(
            "safe_abstention",
            replay_input.verification.safe_abstention,
            _coerce_adapter_value(verified.safe_abstention),
            safety_critical=True,
        ),
        _comparison(
            "route",
            replay_input.routing.route,
            _coerce_adapter_value(context_plan.route),
        ),
        _comparison(
            "route_reason",
            replay_input.routing.reason,
            _coerce_adapter_value(context_plan.reason),
        ),
        _comparison(
            "deadline_remaining_ms",
            replay_input.routing.deadline_remaining_ms,
            _coerce_adapter_value(compute.deadline_remaining_ms),
        ),
        _comparison(
            "minimum_budget_ms",
            replay_input.routing.minimum_budget_ms,
            _coerce_adapter_value(compute.minimum_budget_ms),
        ),
        _comparison(
            "provider_attempts_remaining",
            replay_input.routing.provider_attempts_remaining,
            _coerce_adapter_value(compute.provider_attempts_remaining),
        ),
        _comparison(
            "deadline_affordable",
            replay_input.routing.affordable,
            _coerce_adapter_value(compute.affordable),
        ),
        _comparison(
            "compute_tier",
            replay_input.routing.compute_tier,
            _coerce_adapter_value(compute.compute_tier),
        ),
        _comparison(
            "provider_budget_class",
            replay_input.routing.provider_budget_class,
            STAGE1_UNAVAILABLE,
        ),
        _comparison(
            "selected_evidence_count",
            replay_input.context_compiler.selected_evidence_count,
            _selected_count(compiled.selected_passage_ids),
        ),
        _comparison(
            "selected_evidence_ids",
            replay_input.context_compiler.selected_evidence_ids,
            _coerce_adapter_value(compiled.selected_passage_ids),
        ),
        _comparison(
            "context_compiler_citation_count",
            replay_input.context_compiler.citation_count,
            _coerce_adapter_value(compiled.citation_count),
        ),
        _comparison(
            "citation_shape",
            replay_input.verification.citation_shape,
            STAGE1_UNAVAILABLE,
        ),
        _comparison(
            "provider_call_count",
            replay_input.verification.provider_call_count,
            _coerce_adapter_value(verified.provider_call_count),
        ),
        _comparison(
            "context_compiler_status",
            replay_input.context_compiler.status,
            _coerce_adapter_value(compiled.status),
        ),
        _comparison(
            "verification_status",
            replay_input.verification.status,
            _coerce_adapter_value(verified.status),
            safety_critical=True,
        ),
        _comparison(
            "terminal_status",
            replay_input.verification.terminal_status,
            _coerce_adapter_value(verified.terminal_status),
            safety_critical=True,
        ),
        _comparison(
            "verification_citation_count",
            replay_input.verification.citation_count,
            _coerce_adapter_value(verified.citation_count),
            safety_critical=True,
        ),
        _comparison(
            "material_claim_support_verified",
            replay_input.verification.material_claim_support_verified,
            _coerce_adapter_value(verified.material_claim_support_verified),
            safety_critical=True,
        ),
        _comparison(
            "unsupported_accepted_claims",
            replay_input.verification.unsupported_accepted_claims,
            _coerce_adapter_value(verified.unsupported_accepted_claims),
            safety_critical=True,
        ),
    ]

    guard_lookup = {item.guard: item.outcome for item in replay_input.guard_outcomes}
    for guard in _REQUIRED_GUARDS:
        legacy_guard = guard_lookup.get(guard, MISSING_SIGNAL)
        comparisons.append(
            _comparison(
                f"guard.{guard.value}",
                legacy_guard.value if isinstance(legacy_guard, GuardOutcome) else legacy_guard,
                STAGE1_UNAVAILABLE,
                safety_critical=True,
            )
        )

    if replay_input.legacy_expected_status_class is not None:
        expected = replay_input.legacy_expected_status_class
        classification = (
            EquivalenceClassification.EQUIVALENT
            if expected is legacy_status_class
            else EquivalenceClassification.LEGACY_EXPECTATION_DRIFT
        )
        comparisons.append(
            FieldComparison(
                field="legacy_expectation.response_status_class",
                legacy_value=expected.value,
                normalized_value=legacy_status_class.value,
                classification=classification,
                safety_critical=False,
            )
        )

    return ReplayCaseResult(
        case_id=replay_input.case_id,
        overall_classification=_overall_classification(comparisons),
        comparisons=tuple(comparisons),
    )


def classify_response_status(snapshot: VerificationSnapshot) -> ResponseStatusClass:
    status = _string_or_empty(snapshot.status).casefold()
    terminal = _string_or_empty(snapshot.terminal_status).casefold()
    source = _string_or_empty(snapshot.answer_source).casefold()

    if (
        snapshot.safe_abstention is True
        or status == "owner_only_safe_abstention"
        or terminal == "safe_abstention"
        or source == "safe_abstention"
    ):
        return ResponseStatusClass.SAFE_ABSTENTION

    if "cited_answer" in status:
        return ResponseStatusClass.CITED_ANSWER
    if terminal in {
        "answered",
        "verified_answer",
        "verified_answer_ready_candidate",
        "fast_answer_ready",
    }:
        return ResponseStatusClass.CITED_ANSWER

    failure_tokens = ("error", "denied", "failed", "failure")
    if any(token in status or token in terminal for token in failure_tokens):
        return ResponseStatusClass.ERROR

    if (
        snapshot.status == MISSING_SIGNAL
        and snapshot.terminal_status == MISSING_SIGNAL
        and snapshot.safe_abstention == MISSING_SIGNAL
    ):
        return ResponseStatusClass.UNAVAILABLE
    return ResponseStatusClass.OTHER


def classify_equivalence(
    legacy_value: ReplayValue,
    normalized_value: ReplayValue,
    *,
    safety_critical: bool = False,
) -> EquivalenceClassification:
    if legacy_value == MISSING_SIGNAL:
        return EquivalenceClassification.MISSING_SIGNAL
    if normalized_value == STAGE1_UNAVAILABLE and legacy_value != STAGE1_UNAVAILABLE:
        return EquivalenceClassification.EXPECTED_UNAVAILABLE_STAGE1
    if legacy_value == normalized_value:
        return EquivalenceClassification.EQUIVALENT
    if safety_critical:
        return EquivalenceClassification.UNSAFE_DRIFT
    return EquivalenceClassification.NORMALIZATION_DRIFT


def _comparison(
    field: str,
    legacy_value: ReplayValue,
    normalized_value: ReplayValue,
    *,
    safety_critical: bool = False,
) -> FieldComparison:
    return FieldComparison(
        field=field,
        legacy_value=legacy_value,
        normalized_value=normalized_value,
        classification=classify_equivalence(
            legacy_value,
            normalized_value,
            safety_critical=safety_critical,
        ),
        safety_critical=safety_critical,
    )


def _overall_classification(
    comparisons: Sequence[FieldComparison],
) -> EquivalenceClassification:
    priority = (
        EquivalenceClassification.UNSAFE_DRIFT,
        EquivalenceClassification.NORMALIZATION_DRIFT,
        EquivalenceClassification.LEGACY_EXPECTATION_DRIFT,
        EquivalenceClassification.MISSING_SIGNAL,
        EquivalenceClassification.EXPECTED_UNAVAILABLE_STAGE1,
        EquivalenceClassification.EQUIVALENT,
    )
    classes = {item.classification for item in comparisons}
    return next(item for item in priority if item in classes)


def _capture_routing(
    signal: object | None,
    *,
    compute_tier: str | MissingSignal,
    provider_budget_class: str | MissingSignal,
) -> RoutingSnapshot:
    if signal is None:
        return RoutingSnapshot(
            compute_tier=compute_tier,
            provider_budget_class=provider_budget_class,
        )
    return RoutingSnapshot(
        route=_safe_signal_value(_read_signal(signal, "route")),
        reason=_safe_signal_value(_read_signal(signal, "reason")),
        deadline_remaining_ms=_safe_signal_value(
            _read_signal(signal, "deadline_remaining_ms")
        ),
        minimum_budget_ms=_safe_signal_value(_read_signal(signal, "minimum_budget_ms")),
        provider_attempts_remaining=_safe_signal_value(
            _read_signal(signal, "provider_attempts_remaining")
        ),
        affordable=_safe_affordable(signal),
        compute_tier=compute_tier,
        provider_budget_class=provider_budget_class,
    )


def _capture_context_compiler(
    output: Mapping[str, object] | None,
) -> ContextCompilerSnapshot:
    if output is None:
        return ContextCompilerSnapshot()
    manifest_value = output.get("context_manifest")
    manifest = manifest_value if isinstance(manifest_value, Mapping) else None
    ids = (
        _safe_string_tuple(manifest.get("selected_passage_ids"))
        if manifest is not None
        else MISSING_SIGNAL
    )
    citations = output.get("citations")
    return ContextCompilerSnapshot(
        status=_safe_signal_value(output.get("status", MISSING_SIGNAL)),
        selected_evidence_ids=ids,
        selected_evidence_count=len(ids) if isinstance(ids, tuple) else MISSING_SIGNAL,
        citation_count=_safe_sequence_count(citations),
        citation_shape=_safe_citation_shape(citations),
    )


def _capture_verification(
    output: Mapping[str, object] | None,
) -> VerificationSnapshot:
    if output is None:
        return VerificationSnapshot()
    citations = output.get("citations")
    return VerificationSnapshot(
        status=_safe_signal_value(output.get("status", MISSING_SIGNAL)),
        terminal_status=_safe_signal_value(output.get("terminal_status", MISSING_SIGNAL)),
        safe_abstention=_safe_signal_value(output.get("safe_abstention", MISSING_SIGNAL)),
        provider_call_count=_safe_signal_value(
            output.get("provider_call_count", MISSING_SIGNAL)
        ),
        material_claim_support_verified=_safe_signal_value(
            output.get("material_claim_support_verified", MISSING_SIGNAL)
        ),
        citation_locator_valid=_safe_signal_value(
            output.get("citation_locator_valid", MISSING_SIGNAL)
        ),
        unsupported_accepted_claims=_safe_signal_value(
            output.get("unsupported_accepted_claims", MISSING_SIGNAL)
        ),
        repair_attempted=_safe_signal_value(
            output.get("repair_attempted", MISSING_SIGNAL)
        ),
        citation_count=_safe_sequence_count(citations),
        citation_shape=_safe_citation_shape(citations),
        answer_source=_safe_signal_value(output.get("answer_source", MISSING_SIGNAL)),
    )


def _capture_guards(
    guard_outcomes: Mapping[TraceGuard | str, GuardOutcome | str] | None,
) -> tuple[GuardObservation, ...]:
    if not guard_outcomes:
        return ()
    observations: list[GuardObservation] = []
    for raw_guard, raw_outcome in guard_outcomes.items():
        guard = raw_guard if isinstance(raw_guard, TraceGuard) else TraceGuard(raw_guard)
        outcome = (
            raw_outcome
            if isinstance(raw_outcome, GuardOutcome)
            else GuardOutcome(raw_outcome)
        )
        observations.append(GuardObservation(guard=guard, outcome=outcome))
    return tuple(sorted(observations, key=lambda item: item.guard.value))


def _routing_mapping(snapshot: RoutingSnapshot) -> dict[str, object]:
    return _without_missing(
        {
            "route": snapshot.route,
            "reason": snapshot.reason,
            "deadline_remaining_ms": snapshot.deadline_remaining_ms,
            "minimum_budget_ms": snapshot.minimum_budget_ms,
            "provider_attempts_remaining": snapshot.provider_attempts_remaining,
            "affordable": snapshot.affordable,
        }
    )


def _context_mapping(snapshot: ContextCompilerSnapshot) -> dict[str, object]:
    output: dict[str, object] = {}
    if snapshot.status != MISSING_SIGNAL:
        output["status"] = snapshot.status
    if isinstance(snapshot.selected_evidence_ids, tuple):
        output["context_manifest"] = {
            "selected_passage_ids": list(snapshot.selected_evidence_ids)
        }
    if isinstance(snapshot.citation_count, int) and not isinstance(snapshot.citation_count, bool):
        output["citations"] = [{} for _ in range(snapshot.citation_count)]
    return output


def _verification_mapping(snapshot: VerificationSnapshot) -> dict[str, object]:
    output = _without_missing(
        {
            "status": snapshot.status,
            "terminal_status": snapshot.terminal_status,
            "safe_abstention": snapshot.safe_abstention,
            "provider_call_count": snapshot.provider_call_count,
            "material_claim_support_verified": snapshot.material_claim_support_verified,
            "citation_locator_valid": snapshot.citation_locator_valid,
            "unsupported_accepted_claims": snapshot.unsupported_accepted_claims,
            "repair_attempted": snapshot.repair_attempted,
            "answer_source": snapshot.answer_source,
        }
    )
    if isinstance(snapshot.citation_count, int) and not isinstance(snapshot.citation_count, bool):
        output["citations"] = [{} for _ in range(snapshot.citation_count)]
    return output


def _without_missing(values: Mapping[str, ReplayValue]) -> dict[str, object]:
    return {key: value for key, value in values.items() if value != MISSING_SIGNAL}


def _read_signal(signal: object, key: str) -> Any:
    if isinstance(signal, Mapping):
        return signal.get(key, MISSING_SIGNAL)
    return getattr(signal, key, MISSING_SIGNAL)


def _safe_affordable(signal: object) -> ReplayValue:
    value = _read_signal(signal, "affordable")
    if callable(value):
        try:
            value = value()
        except TypeError:
            return MISSING_SIGNAL
    return _safe_signal_value(value)


def _safe_signal_value(value: object) -> ReplayValue:
    if value == MISSING_SIGNAL:
        return MISSING_SIGNAL
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return MISSING_SIGNAL


def _safe_string_tuple(value: object) -> ReplayValue:
    if (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and all(isinstance(item, str) for item in value)
    ):
        return tuple(value)
    return MISSING_SIGNAL


def _safe_sequence_count(value: object) -> ReplayValue:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return len(value)
    return MISSING_SIGNAL


def _safe_citation_shape(value: object) -> ReplayValue:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return MISSING_SIGNAL
    present: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            continue
        present.update(str(key) for key in item if key in _SAFE_CITATION_SHAPE_FIELDS)
    return tuple(sorted(present))


def _selected_count(value: object) -> ReplayValue:
    if isinstance(value, tuple):
        return len(value)
    if value == STAGE1_UNAVAILABLE:
        return STAGE1_UNAVAILABLE
    return MISSING_SIGNAL


def _coerce_adapter_value(value: object) -> ReplayValue:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
        return value
    return MISSING_SIGNAL


def _string_or_empty(value: ReplayValue) -> str:
    return value if isinstance(value, str) else ""
