from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

EXPLICIT_REFUSAL_TEXT = "此次工具調用已被 OpenAI 的安全檢查封鎖。請再次檢查你傳送的內容。"


class ExecutionOutcome(StrEnum):
    LIVE_PID_POLL = "LIVE_PID_POLL"
    TIMEOUT_WITHOUT_REFUSAL = "TIMEOUT_WITHOUT_REFUSAL"
    ORDINARY_TECHNICAL_ERROR = "ORDINARY_TECHNICAL_ERROR"
    AUTHORIZATION_PENDING = "AUTHORIZATION_PENDING"
    EXPLICIT_PLATFORM_REFUSAL = "EXPLICIT_PLATFORM_REFUSAL"
    UNKNOWN_UNCLASSIFIED = "UNKNOWN_UNCLASSIFIED"


@dataclass(frozen=True, slots=True)
class ExecutionObservation:
    pid: int | None
    pid_alive: bool
    timed_out: bool
    exit_code: int | None
    stdout: bytes = b""
    stderr: bytes = b""
    authorization_granted: bool | None = None
    principal: str | None = None
    command_known: bool = True


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def classify_execution_outcome(observation: ExecutionObservation) -> ExecutionOutcome:
    """Classify abnormal execution evidence with explicit, non-overlapping precedence."""
    combined = observation.stdout + b"\n" + observation.stderr
    refusal = EXPLICIT_REFUSAL_TEXT.encode("utf-8")
    if refusal in combined:
        return ExecutionOutcome.EXPLICIT_PLATFORM_REFUSAL
    if observation.timed_out:
        return ExecutionOutcome.TIMEOUT_WITHOUT_REFUSAL
    if observation.pid is not None and observation.pid_alive:
        return ExecutionOutcome.LIVE_PID_POLL
    if observation.authorization_granted is False:
        return ExecutionOutcome.AUTHORIZATION_PENDING
    if observation.exit_code is not None and observation.exit_code != 0:
        return ExecutionOutcome.ORDINARY_TECHNICAL_ERROR
    if observation.pid is None or not observation.command_known:
        return ExecutionOutcome.UNKNOWN_UNCLASSIFIED
    return ExecutionOutcome.UNKNOWN_UNCLASSIFIED


def observation_receipt(
    *,
    command_id: str,
    tool: str,
    host: str,
    scope: str,
    started_monotonic_ns: int,
    finished_monotonic_ns: int | None,
    observation: ExecutionObservation,
) -> dict[str, object]:
    combined = observation.stdout + b"\n" + observation.stderr
    return {
        "command_id": command_id,
        "tool": tool,
        "host": host,
        "scope": scope,
        "pid": observation.pid,
        "pid_alive_at_observation": observation.pid_alive,
        "started_monotonic_ns": started_monotonic_ns,
        "finished_monotonic_ns": finished_monotonic_ns,
        "duration_monotonic_ns": (
            finished_monotonic_ns - started_monotonic_ns
            if finished_monotonic_ns is not None
            else None
        ),
        "exit_code": observation.exit_code,
        "timed_out": observation.timed_out,
        "stdout_sha256": sha256_bytes(observation.stdout),
        "stdout_bytes": len(observation.stdout),
        "stderr_sha256": sha256_bytes(observation.stderr),
        "stderr_bytes": len(observation.stderr),
        "literal_denial_present": EXPLICIT_REFUSAL_TEXT.encode("utf-8") in combined,
        "principal": observation.principal,
        "authorization_granted": observation.authorization_granted,
        "final_state": classify_execution_outcome(observation).value,
    }
