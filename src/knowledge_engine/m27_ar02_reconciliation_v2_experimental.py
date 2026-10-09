"""Versioned in-memory AR02 successor, strictly MOCK_ONLY. No real authority or ACID.

Accepted AR02C Kernel remains byte-identical, UNKNOWN and nonterminal.
This owns only an isolated experimental post-T3 head, receipt and terminal;
it is NOT an adapter that commits terminal to the accepted AR02C Kernel.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
from dataclasses import asdict, dataclass, replace
from types import MappingProxyType
from typing import Literal

from knowledge_engine.m27_ar02_kernel_experimental import Denied, Kernel
from knowledge_engine.m27_ar03_context_broker_experimental import (
    Candidate,
    GrantFixture,
    Request,
    select,
)
from knowledge_engine.m27_ar04_safe_action_experimental import (
    ActionDenied,
    InertSafeActionBoundary,
    ObserverEvidence,
)
from knowledge_engine.m27_ar05_verification_experimental import (
    JournalSnapshot,
    PublicationCandidate,
    PublicationEligibility,
    VerificationPublicationGate,
    VerificationReceipt,
)

MOCK_ONLY_UNAUTHORIZED_FOR_REAL_EFFECT = True
TEST_TRUSTED_OBSERVER_FIXTURE = "TEST_TRUSTED_OBSERVER_FIXTURE"
REAL_ATTESTED_AUTHORITY = False


def digest_bytes(obj: object) -> bytes:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def hex_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class SourceState:
    source_id: str
    revision: str
    digest: str
    exclusion_generation: int
    consent_expires_at: int
    source_expires_at: int
    retrieved_at: int
    revoked: bool = False
    excluded: bool = False


class TestOnlyContextAuthority:
    """Manually controlled test fixture. NEVER claims independent Provider authority."""

    def __init__(self, state: SourceState):
        self._state = state

    def read(self) -> SourceState:
        return self._state

    def replace(self, **changes: object) -> None:
        self._state = replace(self._state, **changes)


@dataclass(frozen=True, slots=True)
class ObservationV2:
    observation_id: str
    run_id: str
    tenant_id: str
    intent_id: str
    original_t1_digest: str
    expected_head: int
    lease_epoch: int
    source_id: str
    source_revision: str
    source_digest: str
    exclusion_generation: int
    captured_at: int
    expires_at: int
    observer_key_id: str
    evidence: ObserverEvidence
    signature: str = ""

    def unsigned(self) -> ObservationV2:
        return replace(self, signature="")


def observation_message(observation: ObservationV2) -> bytes:
    return digest_bytes(asdict(observation.unsigned()))


@dataclass(frozen=True, slots=True)
class LedgerEvent:
    seq: int
    kind: str
    event_hash: str
    original_t1_digest: str
    observation_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReconciliationReceipt:
    observation_id: str
    effect: Literal["CONFIRMED_APPLIED", "CONFIRMED_NOT_APPLIED"]
    observer_id: str
    trust_grade: str
    head_seq: int
    head_hash: str
    lease_epoch: int
    original_t1_digest: str


@dataclass(frozen=True, slots=True)
class TerminalReceipt:
    head_seq: int
    head_hash: str
    prior_head_seq: int
    verification_id: str
    status: Literal["SUCCEEDED", "FAILED"]
    publication: PublicationEligibility


class ReconciliationKernelV2:
    """Single-process bounded successor CAS (no durability, no external I/O).

    The original accepted Kernel is used through public read and pre-T3 APIs
    only. A copied T3 boundary is guarded continuously against legacy drift.
    """

    def __init__(
        self,
        *,
        kernel: Kernel,
        run_id: str,
        tenant_id: str,
        intent_id: str,
        original_t1_digest: str,
        ar04: InertSafeActionBoundary,
        request: Request,
        candidate: Candidate,
        grant: GrantFixture,
        context_authority: TestOnlyContextAuthority,
        observer_keys: dict[str, bytes],
        verifier_keys: dict[str, bytes],
        signer_for_key: dict[str, str],
        generator_id: str,
        task_id: str,
        task_version: int,
        attempt: int,
        outcome_id: str,
        outcome_digest: str,
        now: int,
    ) -> None:
        original = kernel.read(run_id, tenant_id)
        if (
            not original_t1_digest
            or original["terminal"]
            or original["unknown"] != {intent_id}
            or intent_id not in original["claims"]
            or original["intents"].get(intent_id, (None,))[0] != original_t1_digest
            or original["head"] < 1
        ):
            raise Denied("V2_ORIGINAL_T3_NOT_PROVEN")
        if not observer_keys or not verifier_keys or not signer_for_key:
            raise Denied("V2_MISSING_FIXTURE_TRUST_ROOT")
        self._kernel = kernel
        self._original = original
        self.run_id, self.tenant_id = run_id, tenant_id
        self.intent_id, self.original_t1_digest = intent_id, original_t1_digest
        self._ar04 = ar04
        self._request, self._candidate, self._grant = request, candidate, grant
        self._authority = context_authority
        self._task_binding = (
            task_id, task_version, attempt, outcome_id, outcome_digest
        )
        if (not task_id or not outcome_id or len(outcome_digest) != 64
                or task_version < 1 or attempt < 1):
            raise Denied("V2_OUTCOME_BINDING_INVALID")
        self._pin = context_authority.read()
        self._observer_keys = MappingProxyType(dict(observer_keys))
        self._gate = VerificationPublicationGate(
            verifier_keys=verifier_keys,
            signer_for_key=signer_for_key,
            generator_id=generator_id,
        )
        self._lock = threading.RLock()
        self._head = original["head"]
        self._epoch = original["epoch"]
        self._hash = hex_digest(digest_bytes({
            "domain": "M27_C02_T3_V2",
            "run": run_id,
            "tenant": tenant_id,
            "head": self._head,
            "epoch": self._epoch,
            "t1": original_t1_digest,
            "unknown": sorted(original["unknown"]),
            "charges": sorted(original["charges"].items()),
        }))
        self._events = (LedgerEvent(
            self._head, "T3_UNKNOWN_EFFECT", self._hash, original_t1_digest
        ),)
        self._reconciliation: ReconciliationReceipt | None = None
        self._terminal: TerminalReceipt | None = None
        self._observation: ObservationV2 | None = None
        self._notices: tuple[object, ...] = ()
        self._now = now
        self._check_context(now)

    @property
    def head(self) -> int:
        return self._head

    @property
    def head_hash(self) -> str:
        return self._hash

    @property
    def epoch(self) -> int:
        return self._epoch

    @property
    def history(self) -> tuple[LedgerEvent, ...]:
        return self._events

    @property
    def terminal_receipt(self) -> TerminalReceipt | None:
        return self._terminal

    @property
    def notices(self) -> tuple[object, ...]:
        return self._notices

    def _check_legacy(self) -> None:
        if self._kernel.read(self.run_id, self.tenant_id) != self._original:
            raise Denied("V2_ACCEPTED_KERNEL_DRIFT")

    def _check_context(self, now: int) -> None:
        if now < self._now:
            raise Denied("V2_CLOCK_ROLLBACK")
        self._now = now
        pin = self._pin
        current = self._authority.read()
        if (
            current != pin or current.revoked or current.excluded
            or current.consent_expires_at <= now
            or current.source_expires_at <= now
            or current.retrieved_at > now
            or now - current.retrieved_at > self._request.freshness
            or self._candidate.source_id != pin.source_id
            or self._candidate.revision != pin.revision
            or self._candidate.digest != pin.digest
            or self._candidate.consent_expires != pin.consent_expires_at
            or self._candidate.expires != pin.source_expires_at
            or self._candidate.retrieved != pin.retrieved_at
            or self._request.tenant != self.tenant_id
            or self._grant.tenant != self.tenant_id
        ):
            raise Denied("V2_SOURCE_CONSENT_EXCLUSION_REVISION_STALE")
        req = replace(self._request, now=now)
        if select(req, (self._candidate,), self._grant).selected != (self._candidate,):
            raise Denied("V2_AR03_GRANT_OR_SOURCE_DENIED")

    def _cas(self, expected_head: int, epoch: int, now: int) -> None:
        self._check_legacy()
        if self._terminal is not None:
            raise Denied("V2_TERMINAL_IMMUTABLE")
        if expected_head != self._head or epoch != self._epoch:
            raise Denied("V2_STALE_HEAD_OR_EPOCH")
        self._check_context(now)

    def _append(self, kind: str, observation_id: str | None = None) -> None:
        self._hash = hex_digest(digest_bytes({
            "parent": self._hash,
            "seq": self._head + 1,
            "kind": kind,
            "intent": self.intent_id,
            "original_t1": self.original_t1_digest,
            "observation": observation_id,
        }))
        self._head += 1
        self._events += (LedgerEvent(
            self._head, kind, self._hash, self.original_t1_digest, observation_id
        ),)

    def record_verified_reconciliation(
        self, *, observation: ObservationV2, expected_head: int,
        epoch: int, now: int,
    ) -> ReconciliationReceipt:
        with self._lock:
            self._check_legacy()
            if self._observation is not None:
                if observation == self._observation:
                    if (expected_head != observation.expected_head
                            or epoch != self._epoch or now < self._now):
                        raise Denied("V2_DUPLICATE_STALE_REPLAY")
                    assert self._reconciliation is not None
                    return self._reconciliation
                raise Denied("V2_CONFLICTING_OBSERVATION")
            self._cas(expected_head, epoch, now)
            e = observation.evidence
            if (
                not observation.observation_id
                or observation.run_id != self.run_id
                or observation.tenant_id != self.tenant_id
                or observation.intent_id != self.intent_id
                or observation.original_t1_digest != self.original_t1_digest
                or observation.expected_head != expected_head
                or observation.lease_epoch != epoch
                or observation.source_id != self._pin.source_id
                or observation.source_revision != self._pin.revision
                or observation.source_digest != self._pin.digest
                or observation.exclusion_generation != self._pin.exclusion_generation
                or e.tenant_id != self.tenant_id
                or e.intent_id != self.intent_id
                or not e.independent
                or not e.observation_digest
                or observation.captured_at > now
                or now - observation.captured_at > self._request.freshness
                or now >= observation.expires_at
                or e.status not in ("applied", "not_applied")
            ):
                raise Denied("V2_OBSERVATION_BINDING_OR_FRESHNESS")
            secret = self._observer_keys.get(observation.observer_key_id)
            if secret is None or observation.observer_key_id != e.observer_id:
                raise Denied("V2_UNTRUSTED_OBSERVER")
            expected = hmac.new(
                secret, observation_message(observation), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(expected, observation.signature):
                raise Denied("V2_FORGED_OBSERVER")
            if e.status == "not_applied" and not (
                e.authoritative_negative and e.visibility_complete
            ):
                raise Denied("V2_UNCERTAIN_NEGATIVE")
            ar04_result = self._ar04.reconcile(evidence=e)
            expected_effect = (
                "CONFIRMED_APPLIED" if e.status == "applied"
                else "CONFIRMED_NOT_APPLIED"
            )
            if ar04_result.effect != expected_effect or ar04_result.observer_id != e.observer_id:
                raise Denied("V2_AR04_OBSERVER_REJECTED")
            self._append("T4_VERIFIED_" + expected_effect, observation.observation_id)
            result = ReconciliationReceipt(
                observation.observation_id, expected_effect, e.observer_id,
                TEST_TRUSTED_OBSERVER_FIXTURE, self._head, self._hash,
                self._epoch, self.original_t1_digest,
            )
            self._observation = observation
            self._reconciliation = result
            return result

    def current_snapshot(
        self, *, task_id: str, task_version: int, attempt: int,
        outcome_id: str, outcome_digest: str,
    ) -> JournalSnapshot:
        with self._lock:
            self._check_legacy()
            if (task_id, task_version, attempt, outcome_id, outcome_digest) != self._task_binding:
                raise Denied("V2_OUTCOME_BINDING_MISMATCH")
            return JournalSnapshot(
                self.tenant_id, task_id, task_version, self.run_id, attempt,
                self._head, self._hash, self._epoch, outcome_id, outcome_digest,
                unknown_effect=self._reconciliation is None,
                terminal=self._terminal is not None,
            )

    def terminal_cas(
        self, *, expected_head: int, epoch: int,
        receipt: VerificationReceipt, publication: PublicationCandidate,
        now: int, status: Literal["SUCCEEDED", "FAILED"],
    ) -> TerminalReceipt:
        with self._lock:
            self._cas(expected_head, epoch, now)
            reconciled = self._reconciliation
            if reconciled is None or self._observation is None:
                raise Denied("V2_UNRESOLVED_EFFECT")
            if now >= self._observation.expires_at:
                raise Denied("V2_OBSERVER_PROOF_EXPIRED_AT_TERMINAL")
            if status == "SUCCEEDED" and reconciled.effect != "CONFIRMED_APPLIED":
                raise Denied("V2_SUCCESS_WITHOUT_APPLIED_EFFECT")
            if status not in ("SUCCEEDED", "FAILED"):
                raise Denied("V2_INVALID_TERMINAL_STATUS")
            if not publication.claim_client_delivered:
                raise Denied("V2_CLIENT_ACK_REQUIRED_FOR_PUBLICATION")
            names = {g.name for g in receipt.hard_gates if g.result == "pass"}
            if not {"source", "policy", "effect", "approval", "client_ack"} <= names:
                raise Denied("V2_MANDATORY_HARD_GATES_MISSING")
            try:
                proposal = self._ar04.propose_verification(
                    intent_id=self.intent_id, verifier_id=receipt.signer_id,
                    verifier_key_id=receipt.key_id,
                )
            except ActionDenied as exc:
                raise Denied("V2_AR04_VERIFIER_DENIED") from exc
            if (
                proposal.effect != reconciled.effect
                or proposal.terminal_committed
            ):
                raise Denied("V2_AR04_PROPOSAL_CONFLICT")
            snapshot = self.current_snapshot(
                task_id=receipt.task_id, task_version=receipt.task_version,
                attempt=receipt.attempt, outcome_id=receipt.outcome_id,
                outcome_digest=receipt.outcome_digest,
            )
            eligibility = self._gate.evaluate(
                snapshot=snapshot, receipt=receipt, publication=publication, now=now
            )
            if not eligibility.client_delivery_proven:
                raise Denied("V2_CLIENT_ACK_UNPROVEN")
            prior = self._head
            self._append("TERMINAL_" + status, reconciled.observation_id)
            result = TerminalReceipt(
                self._head, self._hash, prior, receipt.verification_id, status,
                eligibility,
            )
            self._terminal = result
            self._publication = publication
            return result

    def append_postterminal_notice(
        self, *, kind: Literal["correction", "retraction"], content: bytes
    ) -> object:
        with self._lock:
            self._check_legacy()
            if self._terminal is None:
                raise Denied("V2_NOTICE_BEFORE_TERMINAL")
            prior = self._notices[-1] if self._notices else None
            notice = self._gate.append_terminal_notice(
                publication_id=self._publication.publication_id,
                prior_revision=prior.revision if prior else self._publication.revision,
                prior_cursor=prior.cursor if prior else 0,
                kind=kind, supersedes_segment_id=self._publication.segment_id,
                content=content,
            )
            self._notices += (notice,)
            return notice
