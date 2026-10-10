"""W3 M06I: local-only, deny-first AR06 tombstone ledger over K02D SQLite.

Metadata only; never writes memory values, issues live grants, deletes physical bytes,
or performs external effects. Each admission is a revocable *fixture-only* pin.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path

from knowledge_engine.m27_ar02_durable_writer_v1_experimental import (
    DurableWriterV1,
    RunIdentity,
)
from knowledge_engine.m27_ar03_verified_rights_v1_experimental import (
    CHECKPOINT_VERSION,
    AuthorizedReadPlan,
    NativeCitationPinV1,
    ReadIntent,
    RunCheckpointV1,
    SourceAuthorityEvidenceV1,
    VerifiedRightsConsumer,
)
from knowledge_engine.m27_ar06_governed_memory_experimental import (
    AcceptedMemory,
    GovernanceBoundary,
    GovernanceDenied,
    ReadFixture,
    Revocation,
)

SCHEMA = "AR06_LOCAL_DURABLE_EXCLUSION_V1"
PASS = "AR06_LOCAL_DURABLE_EXCLUSION_PASS"


class DurableMemoryDenied(ValueError):
    """Fail-closed local metadata admission, never an actual authorization."""


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MemoryTicket:
    tenant: str
    memory_id: str
    subject: str
    purpose: str
    generation: int
    consent_generation: int
    source_revision: str
    source_digest: str
    source_pin: str
    event_seq: int
    event_digest: str
    value_ref: str
    mock_only: bool = True


@dataclass(frozen=True)
class ExclusionReceipt:
    tenant: str
    memory_id: str
    generation: int
    event_seq: int
    event_digest: str
    revocation_id: str
    ar02_synced: bool
    actual_physical_purge: bool = False
    local_only: bool = True


class DurableMemoryExclusion:
    """A monotonic receipt is durable before the optional AR02 mirror update.

    A crash after the local tombstone but before AR02 authority update is safe:
    this ledger denies first. A client cannot bypass the use-time ticket recheck.
    This is not a distributed atomic transaction with external readers/providers.
    """

    def __init__(self, writer: DurableWriterV1, boundary: GovernanceBoundary,
                 identity: RunIdentity):
        self.writer = writer
        self.boundary = boundary
        self.identity = identity
        self.path = Path(writer.path)
        writer.recover(identity)  # accepted K02D chain, run and identity check
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS m06_control (
                  tenant TEXT NOT NULL, memory TEXT NOT NULL,
                  subject TEXT NOT NULL, purpose TEXT NOT NULL,
                  source_rev TEXT NOT NULL, source_digest TEXT NOT NULL,
                  source_pin TEXT NOT NULL,
                  consent_version TEXT, consent_gen INTEGER NOT NULL,
                  reviewer TEXT NOT NULL, review_expiry INTEGER NOT NULL,
                  memory_expiry INTEGER NOT NULL,
                  generation INTEGER NOT NULL, state TEXT NOT NULL,
                  seq INTEGER NOT NULL, digest TEXT NOT NULL,
                  PRIMARY KEY(tenant,memory)
                );
                CREATE TABLE IF NOT EXISTS m06_receipts (
                  tenant TEXT NOT NULL, memory TEXT NOT NULL,
                  seq INTEGER NOT NULL, kind TEXT NOT NULL,
                  payload TEXT NOT NULL, prev TEXT NOT NULL, digest TEXT NOT NULL,
                  PRIMARY KEY(tenant,memory,seq),
                  FOREIGN KEY(tenant,memory) REFERENCES m06_control(tenant,memory)
                );
                CREATE TRIGGER IF NOT EXISTS m06_no_rewrite BEFORE UPDATE ON m06_receipts
                  BEGIN SELECT RAISE(ABORT,'append-only'); END;
                CREATE TRIGGER IF NOT EXISTS m06_no_remove BEFORE DELETE ON m06_receipts
                  BEGIN SELECT RAISE(ABORT,'append-only'); END;
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(str(self.path), timeout=8, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=8000")
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        return db

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _state(self, db: sqlite3.Connection, memory_id: str) -> tuple[sqlite3.Row, dict]:
        row = db.execute("SELECT * FROM m06_control WHERE tenant=? AND memory=?",
                         (self.identity.tenant_id, memory_id)).fetchone()
        if row is None:
            raise DurableMemoryDenied("UNKNOWN_OR_CROSS_TENANT_MEMORY")
        events = db.execute(
            "SELECT * FROM m06_receipts WHERE tenant=? AND memory=? ORDER BY seq",
            (self.identity.tenant_id, memory_id),
        ).fetchall()
        prev = _sha(_json([SCHEMA, row["tenant"], memory_id]))
        generation = -1
        state = "UNKNOWN"
        descendants: set[str] = set()
        tombstone = None
        for seq, event in enumerate(events, 1):
            try:
                payload = json.loads(event["payload"])
            except (ValueError, TypeError) as exc:
                raise DurableMemoryDenied("CORRUPT_CONTROL_CHAIN") from exc
            digest = _sha(prev + "|" + _json([seq, event["kind"], payload]))
            if (event["seq"] != seq or event["prev"] != prev
                    or event["digest"] != digest):
                raise DurableMemoryDenied("CORRUPT_CONTROL_CHAIN")
            if seq == 1 and event["kind"] == "REGISTER":
                generation = payload["generation"]
                state = "ACTIVE"
                if (row["subject"], row["purpose"], row["source_rev"],
                    row["source_digest"], row["source_pin"],
                    row["consent_gen"], row["reviewer"],
                    row["review_expiry"], row["memory_expiry"]) != (
                    payload["subject"], payload["purpose"], payload["source_rev"],
                    payload["source_digest"], payload["source_pin"],
                    payload["consent_gen"], payload["reviewer"],
                    payload["review_expiry"], payload["memory_expiry"]):
                    raise DurableMemoryDenied("CONTROL_METADATA_DRIFT")
            elif event["kind"] == "DESCENDANT" and state == "ACTIVE":
                if payload["id"] in descendants:
                    raise DurableMemoryDenied("DUPLICATE_DESCENDANT")
                descendants.add(payload["id"])
            elif event["kind"] == "REVOKE" and state == "ACTIVE":
                if payload["generation"] != generation + 1:
                    raise DurableMemoryDenied("GENERATION_NONMONOTONIC")
                generation = payload["generation"]
                state = "TOMBSTONED"
                tombstone = payload
            else:
                raise DurableMemoryDenied("INVALID_CONTROL_TRANSITION")
            prev = digest
        if (not events or row["seq"] != len(events) or row["digest"] != prev
                or row["generation"] != generation or row["state"] != state):
            raise DurableMemoryDenied("CONTROL_HEAD_MISMATCH")
        return row, {"generation": generation, "state": state,
                     "descendants": descendants, "tombstone": tombstone}

    def _append(self, db: sqlite3.Connection, row: sqlite3.Row, kind: str,
                payload: dict, *, generation: int, state: str) -> tuple[int, str]:
        seq = row["seq"] + 1
        digest = _sha(row["digest"] + "|" + _json([seq, kind, payload]))
        db.execute(
            "INSERT INTO m06_receipts VALUES(?,?,?,?,?,?,?)",
            (row["tenant"], row["memory"], seq, kind, _json(payload),
             row["digest"], digest),
        )
        db.execute(
            "UPDATE m06_control SET seq=?,digest=?,generation=?,state=?"
            " WHERE tenant=? AND memory=?",
            (seq, digest, generation, state, row["tenant"], row["memory"]),
        )
        return seq, digest

    def register_reviewed(self, accepted: AcceptedMemory, auth: ReadFixture,
                          *, consent_generation: int, source_pin: str) -> MemoryTicket:
        """Explicit reviewer-approved metadata registration, not agent suggestion write."""
        if (not accepted.mock_only or accepted.native_citation_eligible
                or not accepted.reviewer_ref or not source_pin
                or accepted.tenant != self.identity.tenant_id
                or auth.tenant != accepted.tenant or auth.subject != accepted.subject
                or consent_generation < 0):
            raise DurableMemoryDenied("REGISTRATION_SCOPE_OR_REVIEW")
        # The accepted object must actually be held by this accepted boundary.
        if self.boundary._accepted.get((accepted.tenant, accepted.memory_id)) is not accepted:
            raise DurableMemoryDenied("NOT_BOUNDARY_ACCEPTED")
        check = self.boundary.read(accepted.memory_id, auth,
                                   pinned_generation=accepted.exclusion_generation)
        if not check.allowed or check.value_ref != accepted.value_ref:
            raise DurableMemoryDenied("GOVERNANCE_REGISTRATION_DENIED")
        run = self.writer.recover(self.identity)
        if (run["revoked"] or run["source_revision"] != accepted.source_revision
                or run["consent_generation"] != consent_generation
                or run["exclusion_generation"] != accepted.exclusion_generation):
            raise DurableMemoryDenied("AR02_REGISTRATION_DRIFT")
        with self._transaction() as db:
            if db.execute("SELECT 1 FROM m06_control WHERE tenant=? AND memory=?",
                          (accepted.tenant, accepted.memory_id)).fetchone():
                raise DurableMemoryDenied("REGISTER_ONCE_ONLY")
            digest = _sha(_json([SCHEMA, accepted.tenant, accepted.memory_id]))
            db.execute(
                "INSERT INTO m06_control VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (accepted.tenant, accepted.memory_id, accepted.subject,
                 accepted.purpose, accepted.source_revision,
                 accepted.source_digest, source_pin,
                 accepted.consent_version, consent_generation,
                 accepted.reviewer_ref, accepted.review_expires_at,
                 accepted.expires_at, accepted.exclusion_generation,
                 "ACTIVE", 0, digest),
            )
            row = db.execute("SELECT * FROM m06_control WHERE tenant=? AND memory=?",
                             (accepted.tenant, accepted.memory_id)).fetchone()
            self._append(db, row, "REGISTER", {
                "generation": accepted.exclusion_generation,
                "subject": accepted.subject, "purpose": accepted.purpose,
                "source_rev": accepted.source_revision, "source_pin": source_pin,
                "consent_gen": consent_generation,
                "consent_version": accepted.consent_version,
                "source_digest": accepted.source_digest,
                "reviewer": accepted.reviewer_ref,
                "review_expiry": accepted.review_expires_at,
                "memory_expiry": accepted.expires_at,
            }, generation=accepted.exclusion_generation, state="ACTIVE")
        return self.admit(accepted.memory_id, auth,
                          expected_generation=accepted.exclusion_generation)

    def add_descendant(self, memory_id: str, descendant_id: str,
                       *, kind: str, residency: str) -> None:
        with self._transaction() as db:
            row, state = self._state(db, memory_id)
            if state["state"] != "ACTIVE":
                raise DurableMemoryDenied("DESCENDANT_TOMBSTONED")
            self.boundary.add_descendant(row["tenant"], memory_id,
                                         descendant_id, kind, residency)
            self._append(db, row, "DESCENDANT", {
                "id": descendant_id, "kind": kind, "residency": residency,
            }, generation=state["generation"], state="ACTIVE")

    def revoke(self, request: Revocation, *,
               consent_generation: int, expected_generation: int) -> ExclusionReceipt:
        if (request.tenant != self.identity.tenant_id
                or not request.authenticated_subject_fixture
                or request.fixture_kind != "TEST_ONLY"
                or not request.revocation_id or not request.reason
                or consent_generation < 0):
            raise DurableMemoryDenied("REVOCATION_NOT_FIXTURE_AUTHENTICATED")
        with self._transaction() as db:
            row, state = self._state(db, request.memory_id)
            if row["subject"] != request.subject:
                raise DurableMemoryDenied("REVOCATION_SUBJECT_MISMATCH")
            if state["state"] == "TOMBSTONED":
                old = state["tombstone"]
                if (old["revocation_id"] != request.revocation_id
                        or old["reason"] != request.reason
                        or old["legal_hold_ref"] != request.legal_hold_ref):
                    raise DurableMemoryDenied("DIFFERENT_REVOCATION_AFTER_TOMBSTONE")
                return ExclusionReceipt(row["tenant"], request.memory_id,
                                        row["generation"], row["seq"], row["digest"],
                                        request.revocation_id,
                                        self.writer.recover(self.identity)["revoked"])
            if (expected_generation != state["generation"]
                    or consent_generation < row["consent_gen"]
                    or request.reason not in {
                        "CONSENT_WITHDRAWN", "SUBJECT_ERASURE", "SOURCE_REVOKED",
                        "ACL_REVOKED", "EXPIRY", "PURPOSE_ENDED", "CORRECTION",
                        "POLICY_CHANGE", "ADMIN_ORDER",
                    }):
                raise DurableMemoryDenied("STALE_OR_INVALID_REVOCATION")
            next_generation = state["generation"] + 1
            seq, digest = self._append(db, row, "REVOKE", {
                "revocation_id": request.revocation_id,
                "reason": request.reason, "generation": next_generation,
                "consent_generation": consent_generation,
                "subject": request.subject, "requested_at": request.requested_at,
                "legal_hold_ref": request.legal_hold_ref,
                "external_erase_receipt": None,
                "actual_physical_purge": False,
            }, generation=next_generation, state="TOMBSTONED")
        # The hard fence is DURABLE before any in-process or AR02 propagation.
        # Missing ephemeral fixture cannot undo a durable revocation.
        with suppress(GovernanceDenied):
            self.boundary.revoke(request)
        synced = False
        try:
            recovered = self.writer.recover(self.identity)
            if not recovered["revoked"]:
                self.writer.update_authority(
                    self.identity, recovered["head"],
                    source_revision=recovered["source_revision"],
                    consent_generation=consent_generation,
                    exclusion_generation=next_generation, revoked=True,
                )
            synced = bool(self.writer.recover(self.identity)["revoked"])
        except (ValueError, sqlite3.Error):
            # Terminal/fenced AR02 cannot be rewritten; durable M06 denies anyway.
            pass
        return ExclusionReceipt(request.tenant, request.memory_id,
                                next_generation, seq, digest,
                                request.revocation_id, synced)

    def admit(self, memory_id: str, auth: ReadFixture, *,
              expected_generation: int, descendant_id: str | None = None
              ) -> MemoryTicket:
        # BEGIN IMMEDIATE serializes every local use gate against a concurrent revoke.
        with self._transaction() as db:
            row, state = self._state(db, memory_id)
            if (auth.tenant != row["tenant"] or auth.subject != row["subject"]
                    or auth.purpose != row["purpose"]
                    or state["state"] != "ACTIVE"
                    or expected_generation != state["generation"]
                    or auth.now >= row["review_expiry"]
                    or auth.now >= row["memory_expiry"]
                    or (descendant_id is not None
                        and descendant_id not in state["descendants"])):
                raise DurableMemoryDenied("TOMBSTONED_STALE_OR_SCOPE_DENIED")
            recovered = self.writer.recover(self.identity)
            if (recovered["revoked"] or recovered["source_revision"] != row["source_rev"]
                    or recovered["consent_generation"] != row["consent_gen"]
                    or recovered["exclusion_generation"] != state["generation"]):
                raise DurableMemoryDenied("AR02_PIN_OR_AUTHORITY_DRIFT")
            decision = self.boundary.read(memory_id, auth,
                                          pinned_generation=expected_generation)
            if not decision.allowed or not decision.value_ref:
                raise DurableMemoryDenied("AR06_IN_PROCESS_READ_DENIED")
            return MemoryTicket(row["tenant"], memory_id, row["subject"],
                                row["purpose"], state["generation"],
                                row["consent_gen"], row["source_rev"],
                                row["source_digest"], row["source_pin"],
                                row["seq"], row["digest"],
                                decision.value_ref)

    def consume(self, ticket: MemoryTicket, auth: ReadFixture, *,
                operation: str, descendant_id: str | None = None) -> MemoryTicket:
        if operation not in {"use", "read", "checkpoint", "replay", "cite"}:
            raise DurableMemoryDenied("UNKNOWN_USE_KIND")
        current = self.admit(ticket.memory_id, auth,
                             expected_generation=ticket.generation,
                             descendant_id=descendant_id)
        if current != ticket:
            raise DurableMemoryDenied("STALE_TICKET_REQUIRES_NEW_READ")
        prior = self.boundary.read(ticket.memory_id, auth,
                                   pinned_generation=ticket.generation)
        if not self.boundary.consume(prior, auth).allowed:
            raise DurableMemoryDenied("BOUNDARY_CONSUMPTION_DENIED")
        return current

    def fixture_citation_eligible(self, plan: AuthorizedReadPlan,
                                  ticket: MemoryTicket, auth: ReadFixture) -> bool:
        """Only local AR03 plan consistency. NEVER a native publication grant."""
        try:
            current = self.consume(ticket, auth, operation="cite")
        except (DurableMemoryDenied, GovernanceDenied):
            return False
        head = self.writer.read_head(self.identity)
        return bool(
            plan.checkpoint == RunCheckpointV1(
                CHECKPOINT_VERSION, self.identity.task_id, self.identity.run_id,
                head.seq, head.digest,
            )
            and plan.expires_at > auth.now
            and current.mock_only and plan.read_allowed and plan.citation_eligible
            and not plan.publication_authorized
            and plan.actor.tenant_id == current.tenant
            and plan.actor.subject_id == current.subject
            and plan.scope.purpose_id == current.purpose
            and plan.pin.source_id == current.source_pin
            and plan.pin.original_sha256 == current.source_digest
            and plan.pin.source_revision == current.source_revision
            and plan.scope.tenant_id == current.tenant
        )

    def authorize_fixture_read(
        self, rights: VerifiedRightsConsumer, memory_id: str,
        auth: ReadFixture, *, expected_generation: int,
        evidence: SourceAuthorityEvidenceV1, intent: ReadIntent,
        pin: NativeCitationPinV1, checkpoint: RunCheckpointV1,
    ) -> tuple[MemoryTicket, AuthorizedReadPlan]:
        """Invoke accepted K03V verification only AFTER local exclusion preflight."""
        ticket = self.admit(memory_id, auth,
                            expected_generation=expected_generation)
        plan = rights.authorize_read(evidence, intent, pin, checkpoint)
        if not self.fixture_citation_eligible(plan, ticket, auth):
            raise DurableMemoryDenied("AR03_PLAN_STALE_OR_EXCLUDED")
        return ticket, plan

    def restore_snapshot_allowed(self, memory_id: str, auth: ReadFixture, *,
                                 snapshot_generation: int) -> bool:
        try:
            self.admit(memory_id, auth, expected_generation=snapshot_generation)
        except (DurableMemoryDenied, GovernanceDenied):
            return False
        return self.boundary.restore_snapshot(auth.tenant, memory_id,
                                              snapshot_generation)

    def actual_physical_purge(self, *_args: object, **_kwargs: object) -> None:
        raise DurableMemoryDenied("EXTERNAL_INDEPENDENT_ERASURE_ATTESTATION_REQUIRED")
