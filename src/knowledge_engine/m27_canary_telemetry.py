from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Mapping

ALLOWED_CANARY_MODES = frozenset({"owner_only", "shadow", "tiny_percentage"})


@dataclass(frozen=True)
class CanaryIdentity:
    route_id: str
    candidate_id: str
    candidate_git_sha: str
    canary_mode: str
    candidate_runtime_identity: str | None = None

    def __post_init__(self) -> None:
        required = (self.route_id, self.candidate_id, self.candidate_git_sha, self.canary_mode)
        if any(not str(value).strip() for value in required):
            raise ValueError("M27_CANARY_IDENTITY_REQUIRED_FIELD_MISSING")
        if self.canary_mode not in ALLOWED_CANARY_MODES:
            raise ValueError("M27_CANARY_MODE_UNSUPPORTED")


@dataclass(frozen=True)
class CanaryTelemetryRecord:
    identity: CanaryIdentity
    request_id: str
    terminal_kind: str
    first_material_latency_ms: float | None
    final_latency_ms: float
    product_gate_outcome: str
    stop_condition_flags: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise ValueError("M27_CANARY_REQUEST_ID_REQUIRED")
        if not self.terminal_kind.strip():
            raise ValueError("M27_CANARY_TERMINAL_KIND_REQUIRED")
        if self.final_latency_ms < 0:
            raise ValueError("M27_CANARY_FINAL_LATENCY_INVALID")
        if self.first_material_latency_ms is not None and self.first_material_latency_ms < 0:
            raise ValueError("M27_CANARY_FIRST_MATERIAL_LATENCY_INVALID")
        if not self.product_gate_outcome.strip():
            raise ValueError("M27_CANARY_PRODUCT_GATE_OUTCOME_REQUIRED")

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        identity = payload.pop("identity")
        return {
            "schema_version": "m27-canary-telemetry/v1",
            **identity,
            **payload,
        }


def append_canary_telemetry(path: Path, record: CanaryTelemetryRecord) -> None:
    """Persist one redacted record to an explicit non-production sink.

    The caller owns sink selection. This helper never selects or opens a production
    datastore and has no network side effects.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.as_dict(), sort_keys=True, separators=(",", ":")))
        handle.write("\n")
