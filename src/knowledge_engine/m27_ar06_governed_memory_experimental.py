"""Deny-first, metadata-only AR06 simulation. TEST_ONLY. NOT a memory store.

No persisted bytes, real identities/consent, signed authority, provider deletion,
physical erasure, native citation, execution, network calls or production wiring.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
TEST_ONLY = "TEST_ONLY"
EXPERIMENTAL_NO_LIVE_PROVIDER = True


class GovernanceDenied(ValueError):
    """Synthetic negative: a proposal, read or effect is inadmissible."""


def _digest(value: str) -> bool:
    return bool(SHA256.fullmatch(value))


def may_consume(pinned_generation: int, current_generation: int) -> bool:
    """The current authoritative generation is required for every consumption."""
    return pinned_generation >= 0 and pinned_generation == current_generation


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    memory_id: str
    tenant: str
    subject: str
    purpose: str
    producer: str
    source_revision: str
    source_digest: str
    proposed_ref: str
    proposed_digest: str
    policy_version: str
    consent_version: str | None
    lawful_basis_ref: str | None
    residency: str
    expires_at: int
    taint_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewerDecisionFixture:
    candidate_id: str
    reviewer: str
    decision: str
    tenant: str
    subject: str
    purpose: str
    source_revision: str
    source_digest: str
    proposed_digest: str
    policy_version: str
    consent_version: str | None
    lawful_basis_ref: str | None
    residency: str
    approved_at: int
    expires_at: int
    fixture_kind: str = TEST_ONLY
    independently_reviewed: bool = False


@dataclass(frozen=True)
class AcceptedMemory:
    memory_id: str
    candidate_id: str
    tenant: str
    subject: str
    purpose: str
    source_revision: str
    source_digest: str
    value_ref: str
    value_digest: str
    policy_version: str
    consent_version: str | None
    lawful_basis_ref: str | None
    residency: str
    reviewer_ref: str
    review_expires_at: int
    expires_at: int
    version: int
    exclusion_generation: int
    taint_labels: tuple[str, ...]
    mock_only: bool = True
    native_citation_eligible: bool = False


@dataclass(frozen=True)
class Revocation:
    revocation_id: str
    tenant: str
    subject: str
    memory_id: str
    reason: str
    requested_at: int
    authenticated_subject_fixture: bool
    fixture_kind: str = TEST_ONLY
    legal_hold_ref: str | None = None


@dataclass(frozen=True)
class Tombstone:
    tenant: str
    memory_id: str
    exclusion_generation: int
    reason: str
    effective_at: int
    legal_hold_ref: str | None
    nonserving: bool = True


@dataclass(frozen=True)
class ReadFixture:
    tenant: str
    subject: str
    purpose: str
    principal: str
    now: int
    source_revision: str
    source_digest: str
    policy_version: str
    consent_version: str | None
    lawful_basis_ref: str | None
    residency: str
    source_acl_current: bool
    effective_principal_test_authorized: bool
    fixture_kind: str = TEST_ONLY
    ledger_available: bool = True
    tokens: int = 1
    cost: int = 1


@dataclass(frozen=True)
class ReadDecision:
    allowed: bool
    reason: str
    memory_id: str
    tenant: str
    purpose: str
    exclusion_generation: int
    value_ref: str | None
    mock_only: bool = True
    authorized_real: bool = False
    native_citation_eligible: bool = False


@dataclass(frozen=True)
class DeletionCascade:
    tenant: str
    memory_id: str
    generation: int
    descendant_id: str
    kind: str
    residency: str
    state: str = "PENDING"
    receipt_id: str | None = None


@dataclass(frozen=True)
class AuditReceipt:
    receipt_id: str
    tenant: str
    memory_id: str
    generation: int
    descendant_id: str
    observer: str
    executor: str
    verified_generation: int
    evidence_digest: str
    result: str
    observation_method: str
    independent_observed: bool
    observation_region: str
    fixture_kind: str = TEST_ONLY
    # Provider text alone can never satisfy independent observation.
    provider_text_only: bool = False


@dataclass(frozen=True)
class DeletionOutcome:
    accepted_requests: int
    pending: int
    partial: int
    exception_held: int
    simulated_verified: int
    actual_deletions_verified: int = 0
    no_real_deletion_guarantee: bool = True


class GovernanceBoundary:
    """Owned *in-process* simulated authority. Never persists user memory."""

    def __init__(self) -> None:
        self._accepted: dict[tuple[str, str], AcceptedMemory] = {}
        self._generation: dict[tuple[str, str], int] = {}
        self._tombstones: dict[tuple[str, str], Tombstone] = {}
        self._conflicts: set[tuple[str, str]] = set()
        self._descendants: dict[tuple[str, str], dict[str, tuple[str, str]]] = {}
        self._cascades: dict[tuple[str, str], dict[str, DeletionCascade]] = {}
        self._accepted_deletions: list[tuple[str, str, int]] = []

    def generation(self, tenant: str, memory_id: str) -> int:
        return self._generation.get((tenant, memory_id), 0)

    def propose(self, candidate: Candidate, review: ReviewerDecisionFixture,
                *, now: int) -> AcceptedMemory:
        key = (candidate.tenant, candidate.memory_id)
        if (not candidate.candidate_id or not candidate.memory_id or
                not candidate.tenant or not candidate.subject or
                not candidate.purpose or not candidate.source_revision or
                not candidate.policy_version or not candidate.residency or
                not candidate.producer or
                not candidate.proposed_ref.startswith("synthetic://") or
                not _digest(candidate.source_digest) or
                not _digest(candidate.proposed_digest) or
                not (candidate.consent_version or candidate.lawful_basis_ref)):
            raise GovernanceDenied("invalid_or_unconsented_candidate")
        if (review.fixture_kind != TEST_ONLY or
                not review.independently_reviewed or
                review.reviewer == candidate.producer or
                review.decision != "APPROVE" or
                review.candidate_id != candidate.candidate_id or
                review.tenant != candidate.tenant or
                review.subject != candidate.subject or
                review.purpose != candidate.purpose or
                review.source_revision != candidate.source_revision or
                review.source_digest != candidate.source_digest or
                review.proposed_digest != candidate.proposed_digest or
                review.policy_version != candidate.policy_version or
                review.consent_version != candidate.consent_version or
                review.lawful_basis_ref != candidate.lawful_basis_ref or
                review.residency != candidate.residency or
                not (review.approved_at <= now < review.expires_at) or
                candidate.expires_at <= now):
            raise GovernanceDenied("review_not_independently_exact_and_current")
        if key in self._tombstones:
            raise GovernanceDenied("tombstone_is_irreversible")
        if key in self._conflicts:
            raise GovernanceDenied("conflict_requires_independent_adjudication")
        existing = self._accepted.get(key)
        if existing is not None:
            if (existing.source_digest != candidate.source_digest or
                    existing.value_digest != candidate.proposed_digest or
                    existing.source_revision != candidate.source_revision):
                self._conflicts.add(key)
                raise GovernanceDenied("conflicting_versions_no_last_write_wins")
            raise GovernanceDenied("duplicate_approval_not_a_new_version")
        accepted = AcceptedMemory(
            candidate.memory_id, candidate.candidate_id, candidate.tenant,
            candidate.subject, candidate.purpose, candidate.source_revision,
            candidate.source_digest, candidate.proposed_ref,
            candidate.proposed_digest, candidate.policy_version,
            candidate.consent_version, candidate.lawful_basis_ref,
            candidate.residency, review.reviewer, review.expires_at,
            min(candidate.expires_at, review.expires_at), 1,
            self.generation(*key), candidate.taint_labels,
        )
        self._accepted[key] = accepted
        return accepted

    def read(self, memory_id: str, auth: ReadFixture, *,
             pinned_generation: int | None = None,
             for_native_citation: bool = False) -> ReadDecision:
        key = (auth.tenant, memory_id)
        generation = self.generation(*key)
        def deny(reason: str) -> ReadDecision:
            return ReadDecision(False, reason, memory_id, auth.tenant,
                                auth.purpose, generation, None)
        if not auth.ledger_available:
            return deny("exclusion_ledger_unavailable")
        if key in self._tombstones:
            return deny("tombstoned")
        if key in self._conflicts:
            return deny("conflicting_versions")
        if pinned_generation is not None and not may_consume(
                pinned_generation, generation):
            return deny("stale_generation")
        accepted = self._accepted.get(key)
        if accepted is None:
            return deny("not_eligible")
        if for_native_citation:
            return deny("native_citation_forbidden")
        if (auth.fixture_kind != TEST_ONLY or
                not auth.effective_principal_test_authorized or
                not auth.principal):
            return deny("mock_principal_not_authorized")
        if auth.tenant != accepted.tenant or auth.subject != accepted.subject:
            return deny("subject_or_tenant_denied")
        if auth.purpose != accepted.purpose:
            return deny("purpose_not_approved")
        if auth.policy_version != accepted.policy_version:
            return deny("policy_revision_stale")
        if not auth.source_acl_current:
            return deny("source_acl_stale")
        if (auth.source_revision != accepted.source_revision or
                auth.source_digest != accepted.source_digest):
            return deny("source_revision_stale")
        if (auth.consent_version != accepted.consent_version or
                auth.lawful_basis_ref != accepted.lawful_basis_ref):
            return deny("consent_or_lawful_basis_stale")
        if auth.residency != accepted.residency:
            return deny("residency_boundary")
        if auth.now >= accepted.expires_at or auth.now >= accepted.review_expires_at:
            return deny("expired")
        if auth.tokens <= 0 or auth.cost <= 0:
            return deny("budget_exhausted")
        return ReadDecision(True, "mock_metadata_only", memory_id,
                            auth.tenant, auth.purpose, generation,
                            accepted.value_ref)

    def consume(self, previous: ReadDecision, auth: ReadFixture) -> ReadDecision:
        if (not previous.allowed or not previous.mock_only or
                previous.tenant != auth.tenant or
                previous.purpose != auth.purpose):
            return ReadDecision(False, "not_a_valid_preapproval",
                                previous.memory_id, auth.tenant, auth.purpose,
                                self.generation(auth.tenant, previous.memory_id),
                                None)
        current = self.read(previous.memory_id, auth,
                            pinned_generation=previous.exclusion_generation)
        if not current.allowed or current.value_ref != previous.value_ref:
            return replace(current, allowed=False, value_ref=None)
        return current

    def add_descendant(self, tenant: str, memory_id: str,
                       descendant_id: str, kind: str, residency: str) -> None:
        key = (tenant, memory_id)
        accepted = self._accepted.get(key)
        if (not accepted or key in self._tombstones or key in self._conflicts or
                residency != accepted.residency or not descendant_id or
                descendant_id in self._descendants.get(key, {}) or
                kind not in {"vector", "graph", "summary", "cache",
                             "checkpoint", "backup", "index", "provider"}):
            raise GovernanceDenied("invalid_or_cross_region_descendant")
        self._descendants.setdefault(key, {})[descendant_id] = (kind, residency)

    def revoke(self, request: Revocation) -> Tombstone:
        key = (request.tenant, request.memory_id)
        accepted = self._accepted.get(key)
        if (request.fixture_kind != TEST_ONLY or
                not request.authenticated_subject_fixture or
                not request.revocation_id or
                request.reason not in {"CONSENT_WITHDRAWN", "SUBJECT_ERASURE",
                                       "SOURCE_REVOKED", "ACL_REVOKED",
                                       "EXPIRY", "PURPOSE_ENDED", "CORRECTION",
                                       "POLICY_CHANGE", "ADMIN_ORDER"} or
                accepted is None or accepted.subject != request.subject):
            raise GovernanceDenied("no_authenticated_subject_revocation_fixture")
        new_generation = self.generation(*key) + 1
        self._generation[key] = new_generation
        tombstone = Tombstone(request.tenant, request.memory_id,
                              new_generation, request.reason,
                              request.requested_at, request.legal_hold_ref)
        self._tombstones[key] = tombstone
        self._cascades[key] = {
            cid: DeletionCascade(request.tenant, request.memory_id,
                                 new_generation, cid, kind, zone,
                                 "EXCEPTION_HELD" if request.legal_hold_ref
                                 and kind in {"backup", "checkpoint"} else "PENDING")
            for cid, (kind, zone) in self._descendants.get(key, {}).items()
        }
        self._accepted_deletions.append((request.tenant, request.memory_id,
                                         new_generation))
        return tombstone

    def record_receipt(self, receipt: AuditReceipt) -> DeletionCascade:
        key = (receipt.tenant, receipt.memory_id)
        cascade = self._cascades.get(key, {}).get(receipt.descendant_id)
        if (cascade is None or receipt.fixture_kind != TEST_ONLY or
                receipt.generation != cascade.generation or
                receipt.verified_generation != cascade.generation or
                receipt.observation_region != cascade.residency or
                not receipt.receipt_id or not _digest(receipt.evidence_digest) or
                not receipt.independent_observed or
                not receipt.observer or receipt.observer == receipt.executor or
                receipt.provider_text_only or
                receipt.observation_method != "SIMULATED_READ_AFTER_DELETE" or
                receipt.result not in {"CONFIRMED_REMOVED",
                                       "CONFIRMED_QUARANTINED"}):
            raise GovernanceDenied("independent_simulated_deletion_proof_missing")
        if cascade.state == "EXCEPTION_HELD":
            raise GovernanceDenied("held_material_cannot_claim_purged")
        updated = replace(cascade, state="SIMULATED_VERIFIED",
                          receipt_id=receipt.receipt_id)
        self._cascades[key][receipt.descendant_id] = updated
        return updated

    def release_hold(self, tenant: str, memory_id: str, *,
                     authenticated_custodian_fixture: bool) -> None:
        key = (tenant, memory_id)
        if (not authenticated_custodian_fixture or
                key not in self._tombstones or
                not self._tombstones[key].legal_hold_ref):
            raise GovernanceDenied("hold_release_not_authenticated")
        for cid, c in self._cascades[key].items():
            if c.state == "EXCEPTION_HELD":
                self._cascades[key][cid] = replace(c, state="PENDING")
        self._tombstones[key] = replace(self._tombstones[key],
                                         legal_hold_ref=None)
        # Tombstone and exclusion_generation deliberately NEVER rolled back.

    def cascade_status(self, tenant: str, memory_id: str) -> str:
        key = (tenant, memory_id)
        if key not in self._tombstones:
            return "NOT_REQUESTED"
        states = [c.state for c in self._cascades.get(key, {}).values()]
        if "EXCEPTION_HELD" in states:
            return "EXCEPTION_HELD"
        if states and all(s == "SIMULATED_VERIFIED" for s in states):
            return "SIMULATED_VERIFIED"
        if "SIMULATED_VERIFIED" in states:
            return "PARTIAL"
        return "PENDING"

    def outcome_denominator(self) -> DeletionOutcome:
        statuses = [
            self.cascade_status(tenant, memory_id)
            for tenant, memory_id, _ in self._accepted_deletions
        ]
        return DeletionOutcome(
            len(statuses), statuses.count("PENDING"), statuses.count("PARTIAL"),
            statuses.count("EXCEPTION_HELD"),
            statuses.count("SIMULATED_VERIFIED"),
        )

    def restore_snapshot(self, tenant: str, memory_id: str,
                         snapshot_generation: int) -> bool:
        """Restored backup cannot ever bypass the authoritative exclusion map."""
        key = (tenant, memory_id)
        return (
            key in self._accepted and key not in self._tombstones and
            key not in self._conflicts and
            may_consume(snapshot_generation, self.generation(*key))
        )


def ar03a_metadata_probe(accepted: AcceptedMemory, *,
                         now: int, principal: str) -> object:
    """Call existing AR03A public select without manufacturing a real grant."""
    from knowledge_engine.m27_ar03_context_broker_experimental import (
        Candidate as ContextCandidate,
    )
    from knowledge_engine.m27_ar03_context_broker_experimental import (
        Request,
        select,
    )

    req = Request(accepted.tenant, principal, accepted.purpose,
                  frozenset({"memory"}), now, 1, 1, 30)
    metadata = ContextCandidate(
        scope="memory", source_id=accepted.memory_id,
        revision=str(accepted.version), digest=accepted.value_digest,
        tenant=accepted.tenant, principals=frozenset({principal}),
        purpose=accepted.purpose, expires=accepted.expires_at,
        retrieved=now, tokens=1, cost=1, trust="untrusted",
        tainted=bool(accepted.taint_labels), synthetic_native=False,
    )
    # No GrantFixture: AR03A must omit the candidate.
    return select(req, (metadata,), grant=None)
