"""B3-01 offline-only custom Gateway identity and client trace shape checks.

This module performs NO network/credential/provider calls and issues NO Product admission.
Positive unit fixtures check syntax and ordering, not provenance or real execution.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

ABI = "m27.b3.01.gateway-route-inventory/v1"
PRIMARY = "cloudflare_custom_worker_gateway"
FALLBACK = "minimax"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED = (
    "route_id", "gateway_hostname", "config_sha256", "deployment_label", "endpoint_class",
    "upstream_model_id", "request_schema_id", "response_schema_id",
    "sse_schema_id", "principal_propagation", "source_rights_check",
    "timeout_policy", "quota_policy", "rate_error_mapping",
    "owner_custodian", "config_authority_ref", "feature_flag",
)
HOLD_GATES = (
    "PRIMARY_GATEWAY_AUTHENTICATED", "PRIMARY_SOURCE_VERIFIED",
    "PRIMARY_FIRST_TEXT", "PRIMARY_RELEASE_QUALIFIED",
)


@dataclass(frozen=True)
class OfflineResult:
    shape_valid: bool
    problems: tuple[str, ...]
    evidence_scope: str = "OFFLINE_SHAPE_ONLY_NO_AUTHORIZATION"
    product_admitted: bool = False


def audit_route_registry(registry: Mapping[str, object]) -> OfflineResult:
    """Only validate *nonsecret* registry syntax; existence is NOT authentication."""
    errors: list[str] = []
    if registry.get("primary_kind") != PRIMARY:
        errors.append("PRIMARY_MUST_BE_OWNER_CUSTOM_WORKER_GATEWAY")
    if registry.get("fallback_kind") != FALLBACK:
        errors.append("FALLBACK_MUST_BE_MINIMAX")
    if registry.get("endpoint_class") != "owner_custom_worker_hostname":
        errors.append("NOT_OWNER_CUSTOM_WORKER_ENDPOINT")
    if registry.get("worker_gateway_deployed") is not True:
        errors.append("NO_DEPLOYMENT_EVIDENCE")
    hostname = str(registry.get("gateway_hostname", "")).lower().strip()
    if hostname and (not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,251}[a-z0-9]", hostname)
                     or hostname in {"api.cloudflare.com", "api.minimax.io", "localhost"}
                     or ".." in hostname):
        errors.append("GATEWAY_HOSTNAME_INVALID_OR_VENDOR_DIRECT")
    if registry.get("fallback_on_auth_failure") is not False:
        errors.append("AUTH_FAILURE_FALLBACK_FORBIDDEN")
    if registry.get("fallback_after_answer_text") is not False:
        errors.append("POST_ANSWER_FAILOVER_FORBIDDEN")
    for k in REQUIRED:
        v = registry.get(k)
        if not isinstance(v, str) or not v.strip() or v.lower() in {"unknown", "tbd", "assumed"}:
            errors.append(f"UNVERIFIED_OR_MISSING_{k.upper()}")
    h = registry.get("config_sha256")
    if h and not SHA256.fullmatch(str(h)):
        errors.append("CONFIG_SHA256_INVALID")
    if registry.get("credential_value") is not None:
        errors.append("CREDENTIAL_VALUE_MUST_NEVER_ENTER_REGISTRY")
    if registry.get("authorization_header") is not None:
        errors.append("AUTH_HEADER_MUST_NEVER_ENTER_REGISTRY")
    # @cf/... is allowed only as an independently confirmed upstream model;
    # Cloudflare branding or direct account URI cannot establish this fact.
    if registry.get("upstream_identity_origin") != "custodian_verified_nonsecret":
        errors.append("UPSTREAM_MODEL_NOT_CUSTODIAN_VERIFIED")
    return OfflineResult(not errors, tuple(errors))


def audit_client_trace_shape(
    events: Sequence[Mapping[str, object]], *,
    expected_claim_ids: tuple[str, ...],
    expected_upstream_model_id: str,
    expected_tenant: str,
    expected_principal: str,
) -> OfflineResult:
    """Order and label validation of nonsecret events. NEVER proves authenticity."""
    errors: list[str] = []
    if not expected_claim_ids or len(set(expected_claim_ids)) != len(expected_claim_ids):
        errors.append("INVALID_EXPECTED_OBLIGATIONS")
    if not expected_upstream_model_id:
        errors.append("NO_PINNED_UPSTREAM_ID")
    if not events:
        return OfflineResult(False, ("EMPTY_TRACE",))
    kinds = [str(e.get("kind", "")) for e in events]
    if kinds[0] != "provider_open" or kinds[-1] != "terminal":
        errors.append("INVALID_EVENT_BOUNDARIES")
    if any(not isinstance(e.get("t_ns"), int) for e in events):
        errors.append("TIMESTAMP_MISSING")
    else:
        ts = [int(e["t_ns"]) for e in events]
        if ts != sorted(ts) or len(ts) != len(set(ts)):
            errors.append("TIMESTAMPS_NOT_STRICT_MONOTONIC")
    if any(e.get("provider") != PRIMARY for e in events):
        errors.append("TRACE_WRONG_PRIMARY_ROUTE")
    if any(e.get("upstream_model_id") != expected_upstream_model_id for e in events):
        errors.append("ACTUAL_UPSTREAM_MISMATCH")
    if any(e.get("tenant") != expected_tenant or e.get("principal") != expected_principal for e in events):
        errors.append("TENANT_PRINCIPAL_MISMATCH")
    if "provider_text_delta" not in kinds:
        errors.append("NO_PROVIDER_TEXT_DELTA")
    if kinds.count("provider_open") != 1 or kinds.count("provider_done") != 1 or kinds.count("terminal") != 1:
        errors.append("PROVIDER_EVENT_CARDINALITY_INVALID")
    if "provider_done" in kinds and any(k == "provider_text_delta" for k in kinds[kinds.index("provider_done") + 1:]):
        errors.append("DELTA_AFTER_PROVIDER_DONE")
    if any(e.get("kind") == "provider_text_delta" and
           (not isinstance(e.get("text"), str) or not e["text"].strip()) for e in events):
        errors.append("NO_SUBSTANTIVE_PROVIDER_DELTA")
    if "provider_done" not in kinds:
        errors.append("NO_PROVIDER_DONE")
    terminal = events[-1]
    if terminal.get("answer_complete") is not True:
        errors.append("FULL_ANSWER_NOT_PROVEN")
    if terminal.get("status") != "answered":
        errors.append("TERMINAL_NOT_ANSWERED")
    actual_verified: list[str] = []
    actual_published: list[str] = []
    actual_acked: list[str] = []
    for i, e in enumerate(events):
        kind = e.get("kind")
        cid = e.get("claim_id")
        if kind in {"claim_verified", "answer_text", "client_ack"}:
            if not isinstance(cid, str) or cid not in expected_claim_ids:
                errors.append("UNKNOWN_CLAIM_ID")
                continue
            if kind == "claim_verified":
                if e.get("rights_valid") is not True or e.get("source_sha256_valid") is not True:
                    errors.append("UNVERIFIED_SOURCE_RIGHTS")
                if "provider_text_delta" not in kinds[:i]:
                    errors.append("VERIFIER_BEFORE_MODEL_DELTA")
                actual_verified.append(cid)
            if kind == "answer_text":
                if cid not in actual_verified:
                    errors.append("PUBLISH_BEFORE_VERIFICATION")
                if not SHA256.fullmatch(str(e.get("text_sha256", ""))):
                    errors.append("PUBLISHED_TEXT_SHA_MISSING")
                actual_published.append(cid)
            if kind == "client_ack":
                if cid not in actual_published or e.get("http_status") != 200:
                    errors.append("INVALID_CLIENT_ACK")
                actual_acked.append(cid)
    if tuple(actual_verified) != expected_claim_ids:
        errors.append("VERIFIED_OBLIGATIONS_INCOMPLETE_OR_OUT_OF_ORDER")
    if tuple(actual_published) != expected_claim_ids:
        errors.append("PUBLISHED_OBLIGATIONS_INCOMPLETE_OR_OUT_OF_ORDER")
    if tuple(actual_acked) != expected_claim_ids:
        errors.append("ACKED_OBLIGATIONS_INCOMPLETE_OR_OUT_OF_ORDER")
    if kinds.index("terminal") < kinds.index("provider_done") if "provider_done" in kinds else True:
        errors.append("TERMINAL_BEFORE_PROVIDER_DONE")
    return OfflineResult(not errors, tuple(dict.fromkeys(errors)))


def product_acceptance_matrix() -> dict[str, str]:
    """No fixture, unit test or local SHA may assert live or release admission."""
    return {key: "HOLD_AWAIT_INDEPENDENT_REAL_AUTHORITY" for key in HOLD_GATES}
