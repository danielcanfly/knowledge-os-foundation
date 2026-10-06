from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

TELEMETRY_SCHEMA_VERSION = "m27-runtime-telemetry/v1"
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/-]{0,255}$")
_SAFE_CODE = re.compile(r"^[A-Z0-9_:.+-]{1,128}$")
_STAGE_KEYS = (
    "tool_ms",
    "evidence_binding_ms",
    "compiler_ms",
    "provider_ms",
    "verifier_ms",
    "round_total_ms",
)


def opaque_identifier(value: object) -> str:
    text = str(value or "")
    if _SAFE_IDENTIFIER.fullmatch(text):
        return text
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def sanitized_code(value: object, fallback: str = "UNSPECIFIED") -> str:
    text = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    return text if _SAFE_CODE.fullmatch(text) else fallback


def elapsed_ms(start_ns: int, end_ns: int) -> float:
    return round(max(0, end_ns - start_ns) / 1000000, 3)


def _ms(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) < 0:
        raise ValueError("latency must be non-negative numeric")
    return round(float(value), 3)


@dataclass(frozen=True, slots=True)
class ProviderCallTelemetry:
    call_index: int
    call_class: str
    latency_ms: float
    success: bool
    reason_code: str

    def __post_init__(self):
        if self.call_index < 1:
            raise ValueError("call_index")
        object.__setattr__(self, "call_class", sanitized_code(self.call_class))
        object.__setattr__(self, "reason_code", sanitized_code(self.reason_code))
        object.__setattr__(self, "latency_ms", _ms(self.latency_ms))

    def as_dict(self):
        return {
            "call_index": self.call_index,
            "call_class": self.call_class,
            "latency_ms": self.latency_ms,
            "success": self.success,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True, slots=True)
class M27RoundTelemetry:
    round_index: int
    continuation_reason: str
    route: str
    task_kind: str
    compute_tier: str
    budget_class: str
    stage_latency_ms: Mapping[str, float]
    tool_calls: tuple[str, ...]
    retrieval_evidence_count: int
    evidence_delta: int
    compiler_status: str
    provider_calls: tuple[ProviderCallTelemetry, ...]
    verifier_status: str
    continuation_allowed: bool
    continuation_decision: str
    terminal_reason: str
    estimated_cost_usd: float | None = None
    cost_reason_code: str = "COST_UNAVAILABLE"

    def __post_init__(self):
        if self.round_index < 0 or self.retrieval_evidence_count < 0 or self.evidence_delta < 0:
            raise ValueError("negative count")
        for name in (
            "continuation_reason",
            "route",
            "task_kind",
            "compute_tier",
            "budget_class",
            "compiler_status",
            "verifier_status",
            "continuation_decision",
            "terminal_reason",
            "cost_reason_code",
        ):
            object.__setattr__(self, name, sanitized_code(getattr(self, name)))
        d = {}
        for k in _STAGE_KEYS:
            if k not in self.stage_latency_ms:
                raise ValueError("missing stage latency " + k)
            d[k] = _ms(self.stage_latency_ms[k])
        object.__setattr__(self, "stage_latency_ms", d)
        object.__setattr__(
            self,
            "tool_calls",
            tuple(sanitized_code(x, "UNSPECIFIED_TOOL") for x in self.tool_calls),
        )

    @property
    def provider_latency_ms(self):
        return round(sum(x.latency_ms for x in self.provider_calls), 3)

    def as_dict(self):
        return {
            "round_index": self.round_index,
            "continuation_reason": self.continuation_reason,
            "route": self.route,
            "task_kind": self.task_kind,
            "compute_tier": self.compute_tier,
            "budget_class": self.budget_class,
            "stage_latency_ms": dict(self.stage_latency_ms),
            "tool_calls": list(self.tool_calls),
            "tool_call_count": len(self.tool_calls),
            "retrieval_evidence_count": self.retrieval_evidence_count,
            "evidence_delta": self.evidence_delta,
            "compiler_status": self.compiler_status,
            "provider_calls": [x.as_dict() for x in self.provider_calls],
            "provider_call_count": len(self.provider_calls),
            "provider_latency_ms": self.provider_latency_ms,
            "model_call_count": len(self.provider_calls),
            "model_latency_ms": self.provider_latency_ms,
            "verifier_status": self.verifier_status,
            "verifier_latency_ms": self.stage_latency_ms["verifier_ms"],
            "continuation_allowed": self.continuation_allowed,
            "continuation_decision": self.continuation_decision,
            "terminal_reason": self.terminal_reason,
            "estimated_cost_usd": self.estimated_cost_usd,
            "cost_reason_code": self.cost_reason_code,
        }


@dataclass(frozen=True, slots=True)
class M27RuntimeTelemetry:
    request_id: str
    task_id: str
    route: str
    task_kind: str
    compute_tier: str
    budget_class: str
    rounds: tuple[M27RoundTelemetry, ...]
    terminal_reason: str
    feature_flags: Mapping[str, bool]
    reason_codes: tuple[str, ...]
    total_latency_ms: float
    estimated_cost_usd: float | None = None
    cost_reason_code: str = "COST_UNAVAILABLE"

    def __post_init__(self):
        object.__setattr__(self, "request_id", opaque_identifier(self.request_id))
        object.__setattr__(self, "task_id", opaque_identifier(self.task_id))
        for name in (
            "route",
            "task_kind",
            "compute_tier",
            "budget_class",
            "terminal_reason",
            "cost_reason_code",
        ):
            object.__setattr__(self, name, sanitized_code(getattr(self, name)))
        object.__setattr__(
            self, "reason_codes", tuple(sanitized_code(x) for x in self.reason_codes)
        )
        object.__setattr__(
            self,
            "feature_flags",
            {
                sanitized_code(k, "UNSPECIFIED_FLAG"): v
                for k, v in self.feature_flags.items()
                if isinstance(v, bool)
            },
        )
        object.__setattr__(self, "total_latency_ms", _ms(self.total_latency_ms))

    def as_dict(self):
        provider_calls = sum(len(r.provider_calls) for r in self.rounds)
        provider_ms = round(sum(r.provider_latency_ms for r in self.rounds), 3)
        return {
            "schema_version": TELEMETRY_SCHEMA_VERSION,
            "request_id": self.request_id,
            "task_id": self.task_id,
            "route": self.route,
            "task_kind": self.task_kind,
            "compute_tier": self.compute_tier,
            "budget_class": self.budget_class,
            "rounds": [r.as_dict() for r in self.rounds],
            "tool_call_count": sum(len(r.tool_calls) for r in self.rounds),
            "retrieval_evidence_count": self.rounds[-1].retrieval_evidence_count
            if self.rounds
            else 0,
            "compiler_latency_ms": round(
                sum(r.stage_latency_ms["compiler_ms"] for r in self.rounds), 3
            ),
            "provider_call_count": provider_calls,
            "provider_latency_ms": provider_ms,
            "model_call_count": provider_calls,
            "model_latency_ms": provider_ms,
            "verifier_latency_ms": round(
                sum(r.stage_latency_ms["verifier_ms"] for r in self.rounds), 3
            ),
            "continuation_rounds": max(0, len(self.rounds) - 1),
            "terminal_reason": self.terminal_reason,
            "feature_flags": dict(self.feature_flags),
            "reason_codes": list(self.reason_codes),
            "total_latency_ms": self.total_latency_ms,
            "estimated_cost_usd": self.estimated_cost_usd,
            "cost_reason_code": self.cost_reason_code,
        }


def assert_privacy_safe_telemetry(payload: Mapping[str, Any]) -> None:
    forbidden = {
        "question",
        "query",
        "prompt",
        "passage_text",
        "answer_text",
        "evidence_text",
        "raw_evidence",
        "raw_query",
        "raw_prompt",
        "provider_response",
        "model_response",
        "credentials",
        "secret",
    }

    def walk(v):
        if isinstance(v, Mapping):
            for k, c in v.items():
                n = str(k).strip().lower()
                if n in forbidden or n.startswith("raw_"):
                    raise ValueError("forbidden telemetry field: " + str(k))
                walk(c)
        elif isinstance(v, Sequence) and not isinstance(v, (str, bytes, bytearray)):
            for c in v:
                walk(c)

    walk(payload)
