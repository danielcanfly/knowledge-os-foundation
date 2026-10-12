"""N25 portable client receive-loop instrument. Not a product attestation.

Call from a *genuine* client's actual receive loop. This wrapper never issues
requests, opens endpoints, fetches credentials or asserts external ownership.
It preserves both successful completion and every failed outcome in receipts.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from .m27_w5_c24_client_observation_v1_experimental import (
    CasePlan,
    ClientCapture,
    ObservationDenied,
    SourcePin,
    independent_custody,
)

N25_SCHEMA = "m27.w5.n25.native_client_trial.v1"
OUTCOMES = frozenset({"COMPLETE", "TIMEOUT", "DISCONNECT", "CANCELLED", "REJECTED",
                      "ERROR"})
HEX = frozenset("0123456789abcdef")


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _sha64(v: str) -> bool:
    return isinstance(v, str) and len(v) == 64 and all(c in HEX for c in v)


@dataclass(frozen=True)
class AppAttachment:
    """Immutable metadata, NOT credentials, endpoint access or legal consent."""

    app_id: str
    app_build_sha256: str
    instrumentation_sha256: str
    endpoint_id: str
    controller_grant_sha256: str | None = None
    independent_client_ack_sha256: str | None = None
    signed_source_roster_sha256: str | None = None

    def validate(self) -> None:
        if (not self.app_id or len(self.app_id) > 128 or
                not all(c.isascii() and (c.isalnum() or c in "-_.")
                        for c in self.app_id)):
            raise ObservationDenied("APP_ID_INVALID")
        if not self.endpoint_id or len(self.endpoint_id) > 128:
            raise ObservationDenied("ENDPOINT_ID_MISSING")
        if any(x in self.endpoint_id for x in ("@", "/", ":", "\\", "?", "#")):
            raise ObservationDenied("ENDPOINT_SECRET_OR_URL_FORBIDDEN")
        for x in (self.app_build_sha256, self.instrumentation_sha256):
            if not _sha64(x):
                raise ObservationDenied("APP_IMAGE_UNPINNED")
        for x in (self.controller_grant_sha256,
                  self.independent_client_ack_sha256,
                  self.signed_source_roster_sha256):
            if x is not None and not _sha64(x):
                raise ObservationDenied("EXTERNAL_REFERENCE_UNPINNED")

    def as_dict(self) -> dict:
        self.validate()
        return {
            "app_id": self.app_id,
            "app_build_sha256": self.app_build_sha256,
            "instrumentation_sha256": self.instrumentation_sha256,
            "endpoint_id": self.endpoint_id,
            "controller_grant_sha256": self.controller_grant_sha256,
            "independent_client_ack_sha256": self.independent_client_ack_sha256,
            "signed_source_roster_sha256": self.signed_source_roster_sha256,
        }


class NativeTrial:
    """Captures only bytes supplied from the actual client's recv callback.

    Neither a Plan(synthetic=False) nor this wrapper grants provider authority.
    External signatures and independent rights are a separate trust boundary.
    """

    def __init__(
        self, case: CasePlan, sources: Iterable[SourcePin],
        attachment: AppAttachment, *,
        clock_ns: Callable[[], int],
        source_current: Callable[[SourcePin], bool] | None = None,
        client_pid: int | None = None,
        client_process_nonce: str | None = None,
    ) -> None:
        self.attachment = attachment
        attachment.validate()
        self.capture = ClientCapture(
            case, sources, clock_ns=clock_ns,
            client_pid=client_pid,
            client_process_nonce=client_process_nonce,
            source_current=source_current,
        )
        self.finished = False
        self.started = False
        self.transport_fault: str | None = None

    def before_send(self) -> None:
        if self.started or self.finished:
            raise ObservationDenied("DUPLICATE_CLIENT_START")
        self.capture.admit()
        self.started = True

    def on_recv(self, raw_bytes: bytes) -> None:
        if not self.started or self.finished:
            raise ObservationDenied("CLIENT_NOT_OPEN")
        try:
            self.capture.feed(raw_bytes)
        except (ObservationDenied, TypeError, ValueError) as exc:
            self.transport_fault = "WIRE_VALIDATION:" + type(exc).__name__
            # Do not erase parser failures, or turn them into a success.
            self.capture.errors.append(str(exc)[:96])
            raise

    def close(self, reason: str = "disconnect") -> dict:
        if not self.started or self.finished:
            raise ObservationDenied("CLIENT_NOT_OPEN")
        if reason not in {"disconnect", "timeout", "cancelled", "rejected"}:
            raise ObservationDenied("INVALID_TRIAL_CLOSE_REASON")
        receipt = self.capture.close(reason)
        self.finished = True
        start = receipt["request_admitted_ns"]
        terminal = receipt["terminal_ns"]
        closed = receipt["client_closed_ns"]
        completed = receipt["status"] == "COMPLETE"
        end = terminal if completed else closed
        receipt["n25_schema"] = N25_SCHEMA
        receipt["app_attachment"] = self.attachment.as_dict()
        receipt["app_attachment_sha256"] = _digest(receipt["app_attachment"])
        receipt["outcome_latency_ms"] = (end - start) / 1_000_000
        receipt["full_final_answer_latency_ms"] = (
            (terminal - start) / 1_000_000 if completed else None
        )
        receipt["first_substantive_before_terminal"] = bool(
            completed and receipt["first_substantive_text_ns"] is not None
            and receipt["first_substantive_text_ns"] < terminal
        )
        receipt["client_transport_fault"] = self.transport_fault
        receipt["real_app_connected"] = False
        receipt["official_qualified"] = False
        receipt["product_p95_ms"] = None
        receipt["w5_full_complete"] = False
        if receipt["status"] not in OUTCOMES:
            raise ObservationDenied("TRIAL_OUTCOME_UNCLASSIFIED")
        if not math.isfinite(receipt["outcome_latency_ms"]):
            raise ObservationDenied("TRIAL_LATENCY_UNUSABLE")
        return receipt


def run_received_bytes(
    case: CasePlan, sources: Iterable[SourcePin], attachment: AppAttachment,
    wire_chunks: Iterable[bytes], *,
    clock_ns: Callable[[], int], close_reason: str = "disconnect",
    source_current: Callable[[SourcePin], bool] | None = None,
    client_pid: int | None = None, client_process_nonce: str | None = None,
) -> dict:
    """Bounded observer for an already-controlled iterable of client-received bytes.

    Caller owns networking, consent, timeout enforcement and transport.
    This method never contacts a server or certifies that the iterable is live.
    """
    trial = NativeTrial(
        case, sources, attachment, clock_ns=clock_ns,
        source_current=source_current, client_pid=client_pid,
        client_process_nonce=client_process_nonce,
    )
    trial.before_send()
    try:
        for part in wire_chunks:
            trial.on_recv(part)
            if trial.capture.status in ("COMPLETE", "ERROR"):
                break
    except (ObservationDenied, TypeError, ValueError, OSError) as exc:
        trial.transport_fault = "CLIENT_RECV_FAILURE:" + type(exc).__name__
        return trial.close("rejected")
    return trial.close(close_reason)


def review_independent_authority(
    receipt: dict, *, grant: dict | None = None,
    ack: dict | None = None,
    approved_trust_roots: dict[str, str] | None = None,
) -> dict:
    """Cryptographic check is never identical to external legal/grade admission."""
    try:
        if receipt.get("n25_schema") != N25_SCHEMA:
            raise ObservationDenied("WRONG_N25_RECEIPT")
        if receipt.get("synthetic") is not False:
            raise ObservationDenied("SYNTHETIC_NOT_REAL_APP")
        if receipt.get("status") != "COMPLETE":
            raise ObservationDenied("NO_COMPLETE_NATIVE_ANSWER")
        attachment = receipt.get("app_attachment")
        if not isinstance(attachment, dict):
            raise ObservationDenied("APP_NOT_BOUND")
        if receipt.get("app_attachment_sha256") != _digest(attachment):
            raise ObservationDenied("APP_TAMPER")
        for key in ("controller_grant_sha256", "independent_client_ack_sha256",
                    "signed_source_roster_sha256"):
            if not _sha64(attachment.get(key)):
                raise ObservationDenied("SIGNED_EXTERNAL_ARTIFACT_MISSING")
        if not (isinstance(grant, dict) and isinstance(ack, dict)
                and _digest(grant) == attachment["controller_grant_sha256"]
                and _digest(ack) == attachment["independent_client_ack_sha256"]):
            raise ObservationDenied("EXTERNAL_SIGNATURE_ARTIFACT_MISMATCH")
        custody = independent_custody(receipt, grant, ack, approved_trust_roots)
        return {
            "status": custody["status"],
            "reason": custody["reason"],
            "real_app_connected": False,  # Requires independent operator admission.
            "official_qualified": False,
            "product_p95_ms": None,
        }
    except (ObservationDenied, TypeError, ValueError, KeyError) as exc:
        return {
            "status": "UNKNOWN", "reason": str(exc)[:100],
            "real_app_connected": False,
            "official_qualified": False,
            "product_p95_ms": None,
        }
