"""E15 metadata-only original-523 evaluator admission, deliberately non-production.

The candidate cannot read sealed case bodies. This module neither fetches corpora nor
executes a provider, evaluator, or external service. Trust roots and source registry
must arrive through an *independently authenticated* evaluator-side integration.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

VERSION = "m27-w5-e15-original523-admission-v1"
ORIGINAL = "ORIGINAL_523"
PHASE_B = "AR09_PHASE_B_200"
HISTORICAL = "HISTORICAL_REPLAY_FIXTURE"
REJECT_523 = "ORIGINAL523_EVIDENCE_NOT_ADMITTED"
REJECT_B = "AR09_PHASE_B_BLOCKED"
RIGHTS_FAIL = "REAL_SOURCE_RIGHTS_NOT_VERIFIED"
MECHANICS = "E15_LOCAL_EVALUATOR_MECHANICS_PASS"
ROLES = (
    "custodian", "rights_issuer", "source_verifier", "builder",
    "runner", "grader", "client", "observer",
)
HEX = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,95}$")
OUTCOMES = frozenset({"ANSWER", "ABSTAIN", "ERROR", "TIMEOUT", "REJECTED"})


def digest(value: Any) -> str:
    """Stable JSON SHA256 with NaN/Inf rejected. No hidden question text accepted."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def is_sha(value: object) -> bool:
    return isinstance(value, str) and HEX.fullmatch(value) is not None


def is_id(value: object) -> bool:
    return isinstance(value, str) and IDENT.fullmatch(value) is not None


def is_int(value: object, *, minimum: int = 0) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


@dataclass(frozen=True, slots=True)
class SourcePin:
    source_id: str
    revision: str
    document_id: str
    family_id: str
    origin_id: str
    source_sha256: str
    span_index_sha256: str
    consent_until_ms: int
    acl_until_ms: int


@dataclass(frozen=True, slots=True)
class OpaqueCase:
    case_id: str
    intent_digest: str
    lexical_dedup_digest: str
    source_id: str
    source_revision: str
    exposed_before: bool = False


@dataclass(frozen=True, slots=True)
class FrozenImage:
    commit: str
    tree: str
    image_sha256: str
    build_sha256: str
    runner_sha256: str
    instrumentation_sha256: str


@dataclass(frozen=True, slots=True)
class SealedManifest:
    version: str
    cohort: str
    dataset_id: str
    sealed_dataset_sha256: str
    nonce: str
    custodian_id: str
    evaluator_id: str
    implementer_ids: tuple[str, ...]
    reviewer_ids: tuple[str, ...]
    license_id: str
    license_scope: str
    issued_ms: int
    expires_ms: int
    rubric_id: str
    rubric_version: str
    candidate: FrozenImage
    sources: tuple[SourcePin, ...]
    cases: tuple[OpaqueCase, ...]


@dataclass(frozen=True, slots=True)
class ScoredCase:
    case_id: str
    outcome: str
    answerable: bool
    grade: int | float | None
    cited: bool
    final_answer_sha256: str | None
    final_text_bytes: int | None
    cited_span_bytes: int | None
    cited_source_id: str | None
    cited_source_revision: str | None
    cited_span_start: int | None
    cited_span_end: int | None
    citation_span_sha256: str | None
    client_payload_sha256: str | None
    first_client_text_ms: int | None
    terminal_ms: int | None


@dataclass(frozen=True, slots=True)
class SignedClaim:
    role: str
    signer_id: str
    key_id: str
    algorithm: str
    scope: str
    issued_ms: int
    expires_ms: int
    payload_sha256: str
    signature: str


@dataclass(frozen=True, slots=True)
class RunPacket:
    run_id: str
    manifest_sha256: str
    candidate_image_sha256: str
    rubric_id: str
    rubric_version: str
    results: tuple[ScoredCase, ...]
    claims: tuple[SignedClaim, ...]


@dataclass(frozen=True, slots=True)
class TrustRoot:
    role: str
    signer_id: str
    key_id: str
    issuer_id: str
    ed25519_public_key: bytes
    tier: str  # AUTHORIZED_EXTERNAL or FIXTURE. Fixture never grants product authority.


@dataclass(frozen=True, slots=True)
class IndependentContext:
    """Evaluator-side injection; caller MUST establish its provenance out of band.

    Boolean flags are merely prerequisites, not a substitute for signed receipts.
    An untrusted caller must not be allowed to construct this context.
    """
    roots: tuple[TrustRoot, ...] = ()
    externally_provisioned: bool = False
    independent_custodian_nominated: bool = False
    sealed_dataset_hashes: Mapping[str, str] = field(default_factory=dict)
    source_revisions: Mapping[str, tuple[str, str, str]] = field(
        default_factory=dict
    )  # source_id -> (revision, native_sha256, span_index_sha256)
    source_taxonomy: Mapping[str, tuple[str, str, str]] = field(
        default_factory=dict
    )  # source_id -> (document, independently originated family, origin)
    reviewed_cases: Mapping[str, frozenset[str]] = field(default_factory=dict)
    approved_reviewer_ids: frozenset[str] = frozenset()
    approved_licenses: frozenset[str] = frozenset()
    approved_rubrics: frozenset[tuple[str, str]] = frozenset()
    authorized_images: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    status: str
    mechanics: str
    authority: str
    independent_rights: str
    may_execute_official_evaluation: bool
    official_cited_gate_pass: bool
    total_assigned: int
    result_count: int
    cited_qualified: int
    missing: int
    rejected_or_failed: int
    p95_terminal_ms: int | None
    cited_fraction: float | None
    reasons: tuple[str, ...]


def claim_bytes(claim: SignedClaim) -> bytes:
    """Ed25519 signs exactly these metadata fields, excluding signature."""
    data = asdict(claim)
    del data["signature"]
    return json.dumps(data, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _verify(claim: SignedClaim, root: TrustRoot) -> bool:
    if (
        claim.algorithm != "ed25519" or root.tier not in
        {"AUTHORIZED_EXTERNAL", "FIXTURE"}
        or len(root.ed25519_public_key) != 32
        or not isinstance(claim.signature, str)
        or len(claim.signature) != 128
    ):
        return False
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
        Ed25519PublicKey.from_public_bytes(root.ed25519_public_key).verify(
            bytes.fromhex(claim.signature), claim_bytes(claim)
        )
        return True
    except (ImportError, ValueError, TypeError, Exception):
        return False


def _expected_payloads(
    manifest: SealedManifest, packet: RunPacket
) -> dict[str, str]:
    candidate = asdict(manifest.candidate)
    results_hash = digest([asdict(r) for r in packet.results])
    return {
        "custodian": digest(asdict(manifest)),
        "rights_issuer": digest({
            "dataset_id": manifest.dataset_id, "license_id": manifest.license_id,
            "license_scope": manifest.license_scope, "expires_ms": manifest.expires_ms,
        }),
        "source_verifier": digest([asdict(p) for p in manifest.sources]),
        "builder": digest(candidate),
        "runner": digest({
            "run_id": packet.run_id,
            "manifest_sha256": packet.manifest_sha256,
            "candidate_image_sha256": packet.candidate_image_sha256,
            "runner_sha256": manifest.candidate.runner_sha256,
            "instrumentation_sha256": manifest.candidate.instrumentation_sha256,
        }),
        "grader": results_hash,
        "client": results_hash,
        "observer": digest({
            "run_id": packet.run_id, "manifest_sha256": packet.manifest_sha256,
            "results_sha256": results_hash,
        }),
    }


def _manifest_reasons(
    m: SealedManifest, context: IndependentContext, now_ms: int
) -> set[str]:
    errors: set[str] = set()
    expected_count = {ORIGINAL: 523, PHASE_B: 200}.get(m.cohort)
    if m.version != VERSION or expected_count is None:
        errors.add("INVALID_COHORT_OR_SCHEMA")
    if m.cohort == HISTORICAL:
        errors.add("HISTORICAL_REPLAY_NEVER_ORIGINAL")
    if not all(is_id(x) for x in (
        m.dataset_id, m.nonce, m.custodian_id, m.evaluator_id,
        m.license_id, m.rubric_id, m.rubric_version
    )):
        errors.add("INVALID_IDENTIFIER")
    if (
        not isinstance(m.reviewer_ids, tuple)
        or len(set(m.reviewer_ids)) < 2
        or not all(is_id(x) for x in m.reviewer_ids)
        or any(x in (m.custodian_id, m.evaluator_id) or
               x in m.implementer_ids for x in m.reviewer_ids)
        or not set(m.reviewer_ids) <= context.approved_reviewer_ids
    ):
        errors.add("INDEPENDENT_REVIEWERS_NOT_VERIFIED")
    if (
        not isinstance(m.implementer_ids, tuple)
        or not m.implementer_ids
        or not all(is_id(x) for x in m.implementer_ids)
        or len(set(m.implementer_ids)) != len(m.implementer_ids)
        or m.custodian_id == m.evaluator_id
        or m.custodian_id in m.implementer_ids
        or m.evaluator_id in m.implementer_ids
    ):
        errors.add("CUSTODIAN_EVALUATOR_IMPLEMENTER_COLLUSION")
    if (
        not is_int(m.issued_ms) or not is_int(m.expires_ms)
        or not m.issued_ms <= now_ms < m.expires_ms
    ):
        errors.add("MANIFEST_EXPIRED_OR_FUTURE")
    if m.license_scope != "EVALUATION_ONLY" or not is_sha(m.sealed_dataset_sha256):
        errors.add("RIGHTS_SCOPE_OR_SEAL_INVALID")
    if (
        not isinstance(m.candidate, FrozenImage)
        or not COMMIT.fullmatch(m.candidate.commit or "")
        or not COMMIT.fullmatch(m.candidate.tree or "")
        or not all(is_sha(x) for x in (
            m.candidate.image_sha256, m.candidate.build_sha256,
            m.candidate.runner_sha256, m.candidate.instrumentation_sha256
        ))
    ):
        errors.add("IMMUTABLE_EXECUTED_IMAGE_PROVENANCE_INVALID")
    if (
        not isinstance(m.sources, tuple) or not m.sources
        or not isinstance(m.cases, tuple)
        or len(m.cases) != expected_count
    ):
        errors.add("FROZEN_DENOMINATOR_NOT_EXACT")
    pins: dict[str, SourcePin] = {}
    docs: set[str] = set()
    families: set[str] = set()
    origins: set[str] = set()
    for p in m.sources if isinstance(m.sources, tuple) else ():
        if not isinstance(p, SourcePin):
            errors.add("SOURCE_PIN_NOT_TYPED")
            continue
        if (
            not is_id(p.source_id) or not is_id(p.revision)
            or not is_id(p.document_id) or not is_id(p.family_id)
            or not is_id(p.origin_id)
            or not is_sha(p.source_sha256) or not is_sha(p.span_index_sha256)
            or not is_int(p.consent_until_ms)
            or not is_int(p.acl_until_ms)
            or min(p.consent_until_ms, p.acl_until_ms) <= now_ms
            or p.source_id in pins
        ):
            errors.add("SOURCE_SHA_REVISION_OR_RIGHTS_INVALID")
        pins[p.source_id] = p
        docs.add(p.document_id)
        families.add(p.family_id)
        origins.add(p.origin_id)
    if len(pins) < 100 or len(docs) < 20 or len(families) < 5 or len(origins) < 5:
        errors.add("INSUFFICIENT_INDEPENDENT_SOURCE_DIVERSITY")
    ids: set[str] = set()
    used_sources: set[str] = set()
    origin_family: dict[str, str] = {}
    for p in pins.values():
        if p.origin_id in origin_family and origin_family[p.origin_id] != p.family_id:
            errors.add("SOURCE_FAMILY_ORIGIN_COLLISION")
        origin_family[p.origin_id] = p.family_id
    lexical: set[str] = set()
    intents: set[str] = set()
    for case in m.cases if isinstance(m.cases, tuple) else ():
        if not isinstance(case, OpaqueCase):
            errors.add("CASE_NOT_TYPED_OR_PROTECTED_TEXT")
            continue
        if (
            not is_id(case.case_id) or not is_sha(case.intent_digest)
            or not is_sha(case.lexical_dedup_digest)
            or case.exposed_before is not False
            or case.case_id in ids
            or case.lexical_dedup_digest in lexical
        ):
            errors.add("DUPLICATE_EXPOSED_OR_UNVERIFIED_CASE")
        ids.add(case.case_id)
        lexical.add(case.lexical_dedup_digest)
        intents.add(case.intent_digest)
        pin = pins.get(case.source_id)
        if pin is None or case.source_revision != pin.revision:
            errors.add("CASE_SOURCE_REVISION_NOT_PINNED")
        else:
            used_sources.add(case.source_id)
        if context.reviewed_cases.get(case.case_id) != frozenset(m.reviewer_ids):
            errors.add("PER_CASE_INDEPENDENT_REVIEW_MISSING")
    if len(used_sources) < 100:
        errors.add("INSUFFICIENT_USED_SOURCE_DIVERSITY")
    if expected_count is not None and len(intents) < 140:
        errors.add("INSUFFICIENT_DISTINCT_INTENT_ATTESTATION")
    if context.sealed_dataset_hashes.get(m.dataset_id) != m.sealed_dataset_sha256:
        errors.add("SEALED_DATASET_NOT_INDEPENDENTLY_MATCHED")
    if m.license_id not in context.approved_licenses:
        errors.add("LICENSE_RIGHTS_NOT_INDEPENDENTLY_APPROVED")
    if (m.rubric_id, m.rubric_version) not in context.approved_rubrics:
        errors.add("RUBRIC_NOT_INDEPENDENTLY_APPROVED")
    if m.candidate.image_sha256 not in context.authorized_images:
        errors.add("EXECUTED_IMAGE_NOT_INDEPENDENTLY_ATTESTED")
    for sid, pin in pins.items():
        if context.source_revisions.get(sid) != (
            pin.revision, pin.source_sha256, pin.span_index_sha256
        ):
            errors.add("SOURCE_REVISION_OR_SPAN_SHA_INDEPENDENT_MISMATCH")
        if context.source_taxonomy.get(sid) != (
            pin.document_id, pin.family_id, pin.origin_id
        ):
            errors.add("SOURCE_ORIGIN_INDEPENDENCE_NOT_VERIFIED")
    return errors


def _score(m: SealedManifest, packet: RunPacket) -> tuple[
    set[str], int, int, int, int | None, float | None
]:
    """Score over sealed assignment, not supplied successes; fail unknown closed."""
    errors: set[str] = set()
    assigned = {
        c.case_id: c for c in m.cases if isinstance(c, OpaqueCase)
    }
    pins = {
        p.source_id: p for p in m.sources if isinstance(p, SourcePin)
    }
    seen: set[str] = set()
    durations: list[int] = []
    cited_qualified = 0
    failed = 0
    for rec in packet.results:
        if not isinstance(rec, ScoredCase):
            errors.add("UNTYPED_SCORING_RECEIPT")
            continue
        if rec.case_id in seen or rec.case_id not in assigned:
            errors.add("DUPLICATE_OR_UNASSIGNED_RESULT")
            continue
        seen.add(rec.case_id)
        valid_duration = is_int(rec.terminal_ms, minimum=1)
        if not valid_duration:
            errors.add("TERMINAL_DURATION_MISSING_OR_INVALID")
        else:
            durations.append(rec.terminal_ms)
        if rec.outcome not in OUTCOMES or not isinstance(rec.answerable, bool):
            errors.add("INVALID_RESULT_OUTCOME")
            failed += 1
            continue
        if rec.outcome != "ANSWER":
            failed += 1
            continue
        if (
            not isinstance(rec.grade, (float, int))
            or isinstance(rec.grade, bool)
            or not math.isfinite(rec.grade)
            or not 0 <= rec.grade <= 100
        ):
            errors.add("INVALID_INDEPENDENT_GRADE")
            failed += 1
            continue
        case = assigned[rec.case_id]
        pin = pins.get(case.source_id)
        span_ok = (
            is_int(rec.cited_span_start)
            and is_int(rec.cited_span_end, minimum=1)
            and rec.cited_span_end > rec.cited_span_start
        )
        proof = (
            rec.answerable is True
            and rec.grade >= 85
            and rec.cited is True
            and is_sha(rec.final_answer_sha256)
            and rec.final_answer_sha256 != hashlib.sha256(b"").hexdigest()
            and is_int(rec.final_text_bytes, minimum=1)
            and is_int(rec.cited_span_bytes, minimum=1)
            and is_sha(rec.client_payload_sha256)
            and is_sha(rec.citation_span_sha256)
            and pin is not None
            and rec.cited_source_id == case.source_id
            and rec.cited_source_revision == case.source_revision
            and span_ok
            and is_int(rec.first_client_text_ms, minimum=1)
            and valid_duration
            and rec.first_client_text_ms < rec.terminal_ms
        )
        if proof:
            cited_qualified += 1
        else:
            failed += 1
            errors.add("UNVERIFIED_CITED_FINAL_ANSWER_OR_CLIENT_FIRST_TEXT")
    missing = len(assigned) - len(seen)
    if missing:
        errors.add("ASSIGNED_CASE_OUTCOME_MISSING")
    if len(packet.results) != len(assigned):
        errors.add("FROZEN_DENOMINATOR_RESULT_COVERAGE_INCOMPLETE")
    if len(durations) != len(assigned):
        errors.add("P95_DENOMINATOR_INCOMPLETE")
    p95 = (
        sorted(durations)[math.ceil(len(assigned) * 0.95) - 1]
        if len(durations) == len(assigned) and len(assigned) else None
    )
    fraction = cited_qualified / len(assigned) if assigned else None
    return errors, cited_qualified, missing, failed, p95, fraction


def _claims(
    manifest: SealedManifest, packet: RunPacket,
    ctx: IndependentContext, now_ms: int
) -> set[str]:
    errors: set[str] = set()
    try:
        expected = _expected_payloads(manifest, packet)
    except (ValueError, TypeError, OverflowError):
        return {"NON_CANONICAL_SIGNED_PAYLOAD"}
    if len(packet.claims) != len(ROLES):
        errors.add("MISSING_OR_EXTRA_AUTHORITY_ROLES")
    trusted = {(r.role, r.signer_id, r.key_id): r for r in ctx.roots
               if isinstance(r, TrustRoot)}
    signers: set[str] = set()
    assigned_roles: set[str] = set()
    for c in packet.claims:
        if not isinstance(c, SignedClaim):
            errors.add("UNTYPED_AUTHORITY_CLAIM")
            continue
        if c.role not in ROLES or c.role in assigned_roles:
            errors.add("DUPLICATE_OR_UNEXPECTED_SIGNER_ROLE")
            continue
        assigned_roles.add(c.role)
        if c.signer_id in signers or c.signer_id in (
            manifest.implementer_ids + (manifest.evaluator_id,)
        ):
            errors.add("SIGNER_COLLUSION_OR_IMPLEMENTER_ISSUER")
        signers.add(c.signer_id)
        if (
            not is_id(c.signer_id) or not is_id(c.key_id)
            or c.scope != (manifest.cohort + ":EVALUATION_ONLY")
            or not is_int(c.issued_ms) or not is_int(c.expires_ms)
            or not c.issued_ms <= now_ms < c.expires_ms
            or c.payload_sha256 != expected[c.role]
        ):
            errors.add("SIGNER_SCOPE_EXPIRY_OR_DIGEST_INVALID")
        root = trusted.get((c.role, c.signer_id, c.key_id))
        if root is None or not root.issuer_id or not _verify(c, root):
            errors.add("SIGNATURE_OR_INDEPENDENT_TRUST_ROOT_INVALID")
        elif root.tier != "AUTHORIZED_EXTERNAL":
            errors.add("FIXTURE_SIGNATURE_NOT_REAL_AUTHORITY")
    if assigned_roles != set(ROLES):
        errors.add("REQUIRED_INDEPENDENT_AUTHORITY_MISSING")
    if not ctx.externally_provisioned or not ctx.independent_custodian_nominated:
        errors.add("EXTERNAL_CUSTODIAN_OR_TRUST_PROVISIONING_NOT_VERIFIED")
    return errors


def inspect(
    manifest: SealedManifest | None,
    packet: RunPacket | None = None,
    context: IndependentContext | None = None,
    *,
    now_ms: int = 1000,
) -> AdmissionDecision:
    """Evaluate typed metadata only. Never launch a protected or paid evaluation."""
    cohort = getattr(manifest, "cohort", None)
    original = cohort == ORIGINAL
    status = REJECT_523 if original or cohort != PHASE_B else REJECT_B
    errors: set[str] = set()
    rights = RIGHTS_FAIL
    total = 0
    results_count = 0
    cited = missing = failed = 0
    p95: int | None = None
    fraction: float | None = None
    ctx = context if isinstance(context, IndependentContext) else IndependentContext()
    mechanics = "E15_MECHANICS_NOT_VERIFIED"
    if not is_int(now_ms):
        errors.add("INVALID_CLOCK")
        now_ms = 0
    if not isinstance(manifest, SealedManifest):
        errors.add("NO_AUTHORIZED_SEALED_MANIFEST")
    else:
        total = len(manifest.cases) if isinstance(manifest.cases, tuple) else 0
        try:
            errors.update(_manifest_reasons(manifest, ctx, now_ms))
        except (ValueError, TypeError, AttributeError, OverflowError):
            errors.add("MALFORMED_MANIFEST_METADATA")
        if not isinstance(packet, RunPacket):
            errors.add("INDEPENDENT_SCORER_RESULTS_MISSING")
            missing = total
        else:
            results_count = (
                len(packet.results) if isinstance(packet.results, tuple) else 0
            )
            try:
                if (
                    not is_id(packet.run_id)
                    or packet.manifest_sha256 != digest(asdict(manifest))
                    or packet.candidate_image_sha256 != manifest.candidate.image_sha256
                ):
                    errors.add("MANIFEST_RUN_OR_EXECUTED_IMAGE_MISMATCH")
                if (
                    packet.rubric_id != manifest.rubric_id
                    or packet.rubric_version != manifest.rubric_version
                ):
                    errors.add("RUBRIC_OR_VERSION_CONFLICT")
                score_errors, cited, missing, failed, p95, fraction = _score(
                    manifest, packet
                )
                errors.update(score_errors)
                errors.update(_claims(manifest, packet, ctx, now_ms))
            except (ValueError, TypeError, AttributeError, OverflowError):
                errors.add("MALFORMED_SCORING_OR_SIGNATURE_METADATA")
    authority_errors = {
        "SEALED_DATASET_NOT_INDEPENDENTLY_MATCHED",
        "LICENSE_RIGHTS_NOT_INDEPENDENTLY_APPROVED",
        "SOURCE_REVISION_OR_SPAN_SHA_INDEPENDENT_MISMATCH",
        "SOURCE_ORIGIN_INDEPENDENCE_NOT_VERIFIED",
        "PER_CASE_INDEPENDENT_REVIEW_MISSING",
        "INDEPENDENT_REVIEWERS_NOT_VERIFIED",
        "RIGHTS_SCOPE_OR_SEAL_INVALID",
        "SOURCE_SHA_REVISION_OR_RIGHTS_INVALID",
        "MANIFEST_EXPIRED_OR_FUTURE",
        "EXTERNAL_CUSTODIAN_OR_TRUST_PROVISIONING_NOT_VERIFIED",
        "SIGNATURE_OR_INDEPENDENT_TRUST_ROOT_INVALID",
        "FIXTURE_SIGNATURE_NOT_REAL_AUTHORITY",
    }
    if not errors.intersection(authority_errors) and isinstance(manifest, SealedManifest):
        rights = "RIGHTS_METADATA_EXTERNALLY_VERIFIED"
    threshold_diagnostic = (
        not errors and total == 523 and original
        and cited >= math.ceil(total * 0.95)
        and p95 is not None and p95 <= 15000
    )
    if (
        isinstance(manifest, SealedManifest)
        and isinstance(packet, RunPacket)
        and total in (200, 523)
        and not ({"MALFORMED_SCORING_OR_SIGNATURE_METADATA",
                  "MALFORMED_MANIFEST_METADATA",
                  "INVALID_CLOCK"} & errors)
    ):
        mechanics = MECHANICS
    if not errors and original and threshold_diagnostic:
        status = "ORIGINAL523_METADATA_ACCEPTED_FOR_INDEPENDENT_REVIEW"
    elif not original and cohort == PHASE_B:
        status = REJECT_B
    else:
        status = REJECT_523
    return AdmissionDecision(
        status=status, mechanics=mechanics,
        authority=("EXTERNAL_AUTHORITY_VERIFIED" if not errors else
                   "INDEPENDENT_AUTHORITY_OR_EVIDENCE_NOT_VERIFIED"),
        independent_rights=rights,
        may_execute_official_evaluation=False,  # only external owner run gate can launch
        official_cited_gate_pass=False,  # no local metadata runner certifies product gates
        total_assigned=total, result_count=results_count,
        cited_qualified=cited, missing=missing,
        rejected_or_failed=failed, p95_terminal_ms=p95,
        cited_fraction=fraction, reasons=tuple(sorted(errors)),
    )
