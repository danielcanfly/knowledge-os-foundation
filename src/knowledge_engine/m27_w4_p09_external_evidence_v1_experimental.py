"""W4 P09: offline, read-only authority and FinOps evidence admission.

Only independently provisioned external Ed25519 trust anchors can establish
external authenticity. HMAC keys/signatures exist solely for offline fixtures.
Nothing in this module calls providers, reads confidential corpus bytes, or
authorizes release/side effects.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

REQUIRED_ROLES = frozenset({
    "source", "consent", "retention", "reviewer", "verifier", "ci",
    "observer", "price", "usage", "invoice", "client", "route",
    "build", "outcome",
})
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")
VALID_STATUSES = frozenset({"OK", "FAILED", "RETRIED", "TIMEOUT", "LATE", "REJECTED"})
REAL_ALGORITHM = "ed25519"
FIXTURE_ALGORITHM = "fixture-hmac-sha256"
REFUSAL = "P09_AUTHORITY_EVIDENCE_NOT_ADMITTED"


def canonical(value: Any) -> bytes:
    """Unique JSON bytes; NaN/Inf and non-JSON objects fail closed."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def is_sha(value: object) -> bool:
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def has_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


@dataclass(frozen=True)
class FrozenCandidate:
    """Expected separately accepted Git source, not a mutable tag."""

    commit: str
    tree: str
    image_digest: str | None
    build_digest: str | None


@dataclass(frozen=True)
class Identity:
    tenant: str
    run: str
    request: str
    attempt: str
    revision: str
    clock_domain: str
    event_ms: int
    source_commit: str
    source_tree: str
    image_digest: str | None
    build_digest: str | None
    provider: str
    model: str
    model_version: str
    native_route: str
    executor: str


@dataclass(frozen=True)
class Anchor:
    """Externally injected trust context; never supplied by evidence packet."""

    role: str
    signer: str
    key_id: str
    public_or_fixture_key: bytes
    algorithm: str
    tier: str  # AUTHORIZED_EXTERNAL or FIXTURE
    issuer: str


@dataclass(frozen=True)
class SignedRecord:
    role: str
    signer: str
    key_id: str
    algorithm: str
    tenant: str
    run: str
    request: str
    attempt: str
    revision: str
    issued_ms: int
    expires_ms: int
    previous_digest: str | None
    body: Mapping[str, Any]
    digest: str
    signature: str


def record_claim(record: SignedRecord) -> dict[str, Any]:
    return {
        "role": record.role, "signer": record.signer,
        "key_id": record.key_id, "algorithm": record.algorithm,
        "tenant": record.tenant, "run": record.run,
        "request": record.request, "attempt": record.attempt,
        "revision": record.revision, "issued_ms": record.issued_ms,
        "expires_ms": record.expires_ms,
        "previous_digest": record.previous_digest, "body": record.body,
    }


def test_only_seal(record: SignedRecord, fixture_key: bytes) -> str:
    """Test helper only; never produces real issuer authority."""
    return hmac.new(fixture_key, canonical(record_claim(record)), "sha256").hexdigest()


@dataclass(frozen=True)
class AdmissionPacket:
    identity: Identity
    records: tuple[SignedRecord, ...]
    assigned_attempts: tuple[str, ...]
    phase_b_independent_outcome: bool = False


@dataclass(frozen=True)
class Admission:
    verdict: str
    reasons: tuple[str, ...]
    classifications: Mapping[str, str]
    cost_micros: int | None
    accepted_outcome: bool
    evidence_digest: str | None
    attempt_id: str | None = None


@dataclass(frozen=True)
class EconomicRollup:
    status: str
    attempted: int
    eligible: int
    verified_outcomes: int
    total_cost_micros: int | None
    currency: str | None
    cost_per_verified_outcome_micros: Decimal | None
    reasons: tuple[str, ...]


class EvidenceIntake:
    """Validate externally furnished metadata only, never fetch source text."""

    def __init__(
        self,
        frozen: FrozenCandidate,
        anchors: Sequence[Anchor] = (),
        *,
        authorized_external_custodian: bool = False,
        now_ms: int = 1000,
        invoice_close_ms: int = 1000,
    ) -> None:
        self.frozen = frozen
        self.anchors = {
            (x.role, x.signer, x.key_id): x for x in anchors
        }
        self.authorized_external_custodian = authorized_external_custodian
        self.now_ms = now_ms
        self.invoice_close_ms = invoice_close_ms

    def _verify_signature(self, rec: SignedRecord) -> tuple[bool, bool]:
        anchor = self.anchors.get((rec.role, rec.signer, rec.key_id))
        if anchor is None or not anchor.issuer or rec.algorithm != anchor.algorithm:
            return False, False
        try:
            message = canonical(record_claim(rec))
        except (TypeError, ValueError):
            return False, False
        if rec.algorithm == FIXTURE_ALGORITHM and anchor.tier == "FIXTURE":
            expected = hmac.new(
                anchor.public_or_fixture_key, message, "sha256"
            ).hexdigest()
            return hmac.compare_digest(rec.signature, expected), False
        if rec.algorithm == REAL_ALGORITHM and anchor.tier == "AUTHORIZED_EXTERNAL":
            try:
                from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                    Ed25519PublicKey,
                )

                Ed25519PublicKey.from_public_bytes(
                    anchor.public_or_fixture_key
                ).verify(bytes.fromhex(rec.signature), message)
                return True, self.authorized_external_custodian
            except Exception:  # Missing crypto or invalid independent signature fails closed.
                return False, False
        return False, False

    def inspect(self, packet: AdmissionPacket) -> Admission:
        reasons: set[str] = set()
        classes: dict[str, str] = {r: "MISSING" for r in sorted(REQUIRED_ROLES)}
        ident = packet.identity
        if not all(has_text(x) for x in (
            ident.tenant, ident.run, ident.request, ident.attempt,
            ident.revision, ident.clock_domain, ident.provider, ident.model,
            ident.model_version, ident.executor, ident.native_route,
        )):
            reasons.add("INCOMPLETE_IDENTITY")
        if (
            not isinstance(ident.event_ms, int)
            or isinstance(ident.event_ms, bool)
            or not 0 <= ident.event_ms <= self.now_ms
        ):
            reasons.add("BAD_CLOCK")
        if not HEX40.fullmatch(ident.source_commit or ""):
            reasons.add("BAD_SOURCE_COMMIT")
        if not HEX40.fullmatch(ident.source_tree or ""):
            reasons.add("BAD_SOURCE_TREE")
        if (
            ident.source_commit != self.frozen.commit
            or ident.source_tree != self.frozen.tree
        ):
            reasons.add("I02_FROZEN_REVISION_CONFLICT")
        if (
            not self.frozen.image_digest or not self.frozen.build_digest
            or not ident.image_digest or not ident.build_digest
        ):
            reasons.add("IMMUTABLE_IMAGE_OR_BUILD_MISSING")
        elif (
            ident.image_digest != self.frozen.image_digest
            or ident.build_digest != self.frozen.build_digest
            or not ident.image_digest.startswith("sha256:")
            or not is_sha(ident.image_digest.removeprefix("sha256:"))
            or not is_sha(ident.build_digest)
        ):
            reasons.add("IMMUTABLE_IMAGE_OR_BUILD_CONFLICT")
        if not isinstance(packet.assigned_attempts, tuple) or (
            not packet.assigned_attempts
            or ident.attempt not in packet.assigned_attempts
            or not all(has_text(x) for x in packet.assigned_attempts)
            or len(set(packet.assigned_attempts)) != len(packet.assigned_attempts)
        ):
            reasons.add("ASSIGNMENT_DENOMINATOR_INVALID")

        by_role: dict[str, SignedRecord] = {}
        externally_verified: set[str] = set()
        seen_digests: set[str] = set()
        previous: str | None = None
        for rec in packet.records:
            if rec.role not in REQUIRED_ROLES:
                reasons.add("UNEXPECTED_ROLE")
                continue
            if rec.role in by_role:
                reasons.add("DUPLICATE_ROLE_" + rec.role.upper())
                classes[rec.role] = "NOT_VERIFIED"
                continue
            if not isinstance(rec.body, Mapping):
                reasons.add("MALFORMED_BODY_" + rec.role.upper())
                continue
            by_role[rec.role] = rec
            classes[rec.role] = "NOT_VERIFIED"
            if (
                not rec.signer or rec.signer == ident.executor
                or not rec.key_id or rec.tenant != ident.tenant
                or rec.run != ident.run or rec.request != ident.request
                or rec.attempt != ident.attempt or rec.revision != ident.revision
            ):
                reasons.add("IDENTITY_OR_ISSUER_MISMATCH_" + rec.role.upper())
                continue
            if (
                not isinstance(rec.issued_ms, int)
                or not isinstance(rec.expires_ms, int)
                or rec.issued_ms > ident.event_ms
                or rec.issued_ms > self.now_ms
                or rec.expires_ms <= self.now_ms
                or rec.expires_ms <= rec.issued_ms
            ):
                reasons.add("EXPIRED_FUTURE_OR_BAD_CLOCK_" + rec.role.upper())
                continue
            try:
                digest = sha256(canonical(record_claim(rec)))
            except (TypeError, ValueError):
                reasons.add("UNCANONICAL_RECORD_" + rec.role.upper())
                continue
            if not is_sha(rec.digest) or rec.digest != digest:
                reasons.add("RECORD_DIGEST_CONFLICT_" + rec.role.upper())
                continue
            if rec.digest in seen_digests or rec.previous_digest != previous:
                reasons.add("CHAIN_OR_DUPLICATE_DIGEST_" + rec.role.upper())
                continue
            seen_digests.add(rec.digest)
            previous = rec.digest
            signature_valid, external = self._verify_signature(rec)
            if not signature_valid:
                reasons.add("SIGNATURE_OR_ROOT_INVALID_" + rec.role.upper())
                continue
            if external:
                externally_verified.add(rec.role)
                classes[rec.role] = "PRESENT_VERIFIED"
            else:
                reasons.add("FIXTURE_NOT_EXTERNAL_AUTHORITY_" + rec.role.upper())

        missing_roles = REQUIRED_ROLES - by_role.keys()
        if missing_roles:
            reasons.add("REQUIRED_ROLES_MISSING")
        # Roles must be independent: do not allow evaluator, issuer and client
        # to be the same signer even if different role keys exist.
        signer_roles: dict[str, set[str]] = {}
        for role, rec in by_role.items():
            signer_roles.setdefault(rec.signer, set()).add(role)
        if any(len(v) > 1 for v in signer_roles.values()):
            reasons.add("SIGNER_ROLE_COLLUSION")
        if by_role.get("source") is not None:
            s = by_role["source"].body
            if (
                s.get("tenant") != ident.tenant
                or not has_text(s.get("source_id"))
                or not has_text(s.get("revision"))
                or not is_sha(s.get("native_sha256"))
                or not isinstance(s.get("acl_tenants"), (list, tuple))
                or ident.tenant not in s["acl_tenants"]
                or not isinstance(s.get("acl_valid_until_ms"), int)
                or s["acl_valid_until_ms"] <= self.now_ms
                or not has_text(s.get("license"))
                or s.get("license") == "UNKNOWN"
                or s.get("revoked") is not False
            ):
                reasons.add("SOURCE_ACL_LICENSE_OR_REVISION_UNVERIFIED")
        if by_role.get("consent") is not None:
            c = by_role["consent"].body
            if (
                c.get("granted") is not True
                or c.get("tenant") != ident.tenant
                or c.get("source_revision") != (
                    by_role.get("source").body.get("revision")
                    if by_role.get("source") else None
                )
                or not isinstance(c.get("expires_ms"), int)
                or c["expires_ms"] <= self.now_ms
            ):
                reasons.add("CONSENT_INVALID")
        if by_role.get("retention") is not None:
            t = by_role["retention"].body
            if not has_text(t.get("policy_id")) or (
                not isinstance(t.get("permitted_until_ms"), int)
                or t["permitted_until_ms"] <= self.now_ms
                or t.get("revoked") is not False
            ):
                reasons.add("RETENTION_INVALID")
        for role in ("reviewer", "verifier", "ci", "observer", "outcome"):
            if role in by_role:
                body = by_role[role].body
                if (
                    body.get("decision") != "PASS"
                    or body.get("candidate_commit") != ident.source_commit
                    or body.get("task_attempt") != ident.attempt
                    or (role == "outcome" and (
                        body.get("effect_state") != "RESOLVED"
                        or body.get("independently_verified") is not True
                    ))
                ):
                    reasons.add("INDEPENDENT_PROOF_INVALID_" + role.upper())
        if "client" in by_role:
            c = by_role["client"].body
            if (
                c.get("ack") is not True
                or c.get("request") != ident.request
                or c.get("clock_domain") != ident.clock_domain
                or not is_sha(c.get("wire_payload_sha256"))
                or not isinstance(c.get("received_ms"), int)
                or c.get("received_ms") < ident.event_ms
                or c.get("received_ms") > self.now_ms
            ):
                reasons.add("CLIENT_ACK_NOT_VERIFIED")
        if "route" in by_role:
            r = by_role["route"].body
            if (
                r.get("instrumented_native_route") != ident.native_route
                or r.get("candidate_commit") != ident.source_commit
                or r.get("client_ack_request") != ident.request
            ):
                reasons.add("NATIVE_ROUTE_NOT_VERIFIED")
        if "build" in by_role:
            b = by_role["build"].body
            if (
                b.get("source_commit") != ident.source_commit
                or b.get("source_tree") != ident.source_tree
                or b.get("image_digest") != ident.image_digest
                or b.get("build_digest") != ident.build_digest
            ):
                reasons.add("BUILD_PROVENANCE_NOT_VERIFIED")

        amount, cost_errors = self._reconcile(packet, by_role)
        reasons.update(cost_errors)
        if not packet.phase_b_independent_outcome:
            reasons.add("PHASE_B_INDEPENDENT_OUTCOME_MISSING")
        if externally_verified != REQUIRED_ROLES:
            reasons.add("EXTERNAL_ROOT_OR_RECEIPT_MISSING")
        if not self.authorized_external_custodian:
            reasons.add("EXTERNAL_CUSTODIAN_AUTHORIZATION_MISSING")
        if amount is None or externally_verified != REQUIRED_ROLES:
            reasons.add("ACTUAL_COST_UNKNOWN")
        try:
            manifest = sha256(canonical({
                "identity": vars(ident),
                "record_digests": [r.digest for r in packet.records],
                "assigned_attempts": packet.assigned_attempts,
            }))
        except (ValueError, TypeError):
            manifest = None
            reasons.add("MANIFEST_NOT_CANONICAL")
        success = not reasons
        return Admission(
            verdict="P09_EXTERNAL_EVIDENCE_ADMITTED" if success else REFUSAL,
            reasons=tuple(sorted(reasons)),
            classifications=classes,
            cost_micros=amount if success else None,
            accepted_outcome=success,
            evidence_digest=manifest,
            attempt_id=ident.attempt,
        )

    def _reconcile(
        self, packet: AdmissionPacket, by_role: Mapping[str, SignedRecord]
    ) -> tuple[int | None, set[str]]:
        errors: set[str] = set()
        usage = by_role.get("usage")
        invoice = by_role.get("invoice")
        price = by_role.get("price")
        if usage is None or invoice is None or price is None:
            return None, {"PRICE_USAGE_OR_INVOICE_MISSING"}
        u = usage.body
        inv = invoice.body
        p = price.body
        currency = p.get("currency")
        if not has_text(currency) or not re.fullmatch(r"[A-Z]{3}", str(currency)):
            errors.add("CURRENCY_INVALID")
        if (
            p.get("provider") != packet.identity.provider
            or p.get("model") != packet.identity.model
            or p.get("model_version") != packet.identity.model_version
            or not isinstance(p.get("effective_ms"), int)
            or not isinstance(p.get("until_ms"), int)
            or p["effective_ms"] > packet.identity.event_ms
            or p["until_ms"] <= packet.identity.event_ms
        ):
            errors.add("PRICE_VERSION_OR_INTERVAL_MISMATCH")
        calls = u.get("calls")
        bills = inv.get("bills")
        if (
            not isinstance(calls, list) or not calls
            or not isinstance(bills, list) or not bills
        ):
            return None, errors | {"INCOMPLETE_CALL_OR_INVOICE_LEDGER"}
        call_ids: set[str] = set()
        invoice_ids: set[str] = set()
        expected = 0
        expected_by_id: dict[str, int] = {}
        call_times: dict[str, int] = {}
        actual = 0
        for call in calls:
            if not isinstance(call, dict):
                errors.add("BAD_USAGE_CALL")
                continue
            cid = call.get("call_id")
            if not has_text(cid) or cid in call_ids:
                errors.add("DUPLICATE_USAGE_OR_CALL_ID")
                continue
            call_ids.add(cid)
            if (
                call.get("attempt") not in packet.assigned_attempts
                or call.get("provider") != packet.identity.provider
                or call.get("model_version") != packet.identity.model_version
                or call.get("status") not in VALID_STATUSES
                or not has_text(call.get("provider_request_id"))
                or call.get("clock_domain") != packet.identity.clock_domain
                or not isinstance(call.get("time_ms"), int)
                or call["time_ms"] < packet.identity.event_ms
                or call["time_ms"] > self.invoice_close_ms
                or not isinstance(p.get("effective_ms"), int)
                or not isinstance(p.get("until_ms"), int)
                or not p["effective_ms"] <= call["time_ms"] < p["until_ms"]
            ):
                errors.add("USAGE_IDENTITY_METER_OR_CLOCK_INVALID")
            if isinstance(call.get("time_ms"), int):
                call_times[cid] = call["time_ms"]
            if call.get("retry_of") is not None and (
                not has_text(call["retry_of"])
                or call["retry_of"] not in call_ids
                or call["retry_of"] == cid
            ):
                errors.add("RETRY_CHAIN_INVALID")
            for k in ("input_tokens", "output_tokens", "reasoning_tokens", "cached_tokens"):
                v = call.get(k)
                if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                    errors.add("TOKEN_METER_INVALID")
            if call.get("cached_tokens", 0) > call.get("input_tokens", 0):
                errors.add("CACHE_METER_INVALID")
            if not errors:
                try:
                    q_input = Decimal(str(p["input_micros_per_token"]))
                    q_output = Decimal(str(p["output_micros_per_token"]))
                    q_reasoning = Decimal(str(p["reasoning_micros_per_token"]))
                    q_cached = Decimal(str(p["cached_micros_per_token"]))
                    if any(not x.is_finite() or x < 0 for x in (
                        q_input, q_output, q_reasoning, q_cached
                    )):
                        raise InvalidOperation
                    line = (
                        Decimal(call["input_tokens"] - call["cached_tokens"]) * q_input
                        + Decimal(call["cached_tokens"]) * q_cached
                        + Decimal(call["output_tokens"]) * q_output
                        + Decimal(call["reasoning_tokens"]) * q_reasoning
                    )
                    if line != line.to_integral_value() or line < 0:
                        errors.add("PRICE_PRECISION_UNRECONCILED")
                    else:
                        expected += int(line)
                        expected_by_id[cid] = int(line)
                except (InvalidOperation, ValueError, TypeError, KeyError):
                    errors.add("PRICE_RATE_INVALID")
        for bill in bills:
            if not isinstance(bill, dict):
                errors.add("BAD_INVOICE_LINE")
                continue
            bid = bill.get("call_id")
            if not has_text(bid) or bid in invoice_ids:
                errors.add("DUPLICATE_OR_FORGED_INVOICE")
                continue
            invoice_ids.add(bid)
            if (
                bill.get("currency") != currency
                or bill.get("attempt") not in packet.assigned_attempts
                or bill.get("model_version") != packet.identity.model_version
                or not isinstance(bill.get("issued_ms"), int)
                or bill["issued_ms"] > self.invoice_close_ms
                or (bid in call_times and bill["issued_ms"] < call_times[bid])
                or not isinstance(bill.get("micros"), int)
                or isinstance(bill.get("micros"), bool)
                or bill["micros"] < 0
                or not has_text(bill.get("external_invoice_id"))
            ):
                errors.add("INVOICE_CURRENCY_METER_OR_CUTOFF_INVALID")
            else:
                actual += bill["micros"]
                if bid in expected_by_id and bill["micros"] != expected_by_id[bid]:
                    errors.add("INVOICE_LINE_MISMATCH")
        if call_ids != invoice_ids:
            errors.add("INVOICE_COVERAGE_MISSING")
        if expected != actual:
            errors.add("INVOICE_TOTAL_MISMATCH")
        if not calls or set(packet.assigned_attempts) - {
            call.get("attempt") for call in calls if isinstance(call, dict)
        }:
            errors.add("ASSIGNED_FAILURE_OR_ATTEMPT_NOT_METERED")
        if not (
            p.get("issued_by_provider") is True
            and u.get("boundary_complete") is True
            and inv.get("billing_complete") is True
        ):
            errors.add("PROVIDER_BOUNDARY_OR_BILLING_COMPLETENESS_UNKNOWN")
        return (actual if not errors else None), errors


def reconcile_economics(
    assigned_attempts: Sequence[str],
    admissions: Sequence[Admission],
    currency: str | None,
) -> EconomicRollup:
    """Cost includes ALL attempts and failures, not just successful outputs."""
    reasons: set[str] = set()
    if (
        not assigned_attempts
        or not all(has_text(a) for a in assigned_attempts)
        or len(set(assigned_attempts)) != len(assigned_attempts)
        or len(admissions) != len(assigned_attempts)
        or {r.attempt_id for r in admissions} != set(assigned_attempts)
        or len({r.attempt_id for r in admissions}) != len(admissions)
    ):
        reasons.add("ELIGIBLE_DENOMINATOR_OR_COVERAGE_INVALID")
    known = all(x.cost_micros is not None for x in admissions)
    if not known:
        reasons.add("UNKNOWN_ACTUAL_COST")
    if not has_text(currency):
        reasons.add("UNKNOWN_CURRENCY")
    verified = sum(x.accepted_outcome for x in admissions)
    if verified == 0:
        reasons.add("ZERO_VERIFIED_OUTCOMES")
    if any(x.verdict != "P09_EXTERNAL_EVIDENCE_ADMITTED" for x in admissions):
        reasons.add("UNADMITTED_ATTEMPT")
    total = sum(x.cost_micros or 0 for x in admissions) if known else None
    ratio = Decimal(total) / Decimal(verified) if (
        total is not None and verified and not reasons
    ) else None
    return EconomicRollup(
        "VERIFIED" if not reasons else "UNKNOWN",
        len(admissions), len(assigned_attempts), verified,
        total, currency if has_text(currency) else None,
        ratio, tuple(sorted(reasons)),
    )
