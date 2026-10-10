"""W3 C07I offline AR07 -> AR02 SQLite CAS monetary budget bridge.

TEST FIXTURES ONLY. No Provider, dispatch, authentic pricing, model invocation,
remote billing, stream delivery, or economic certification. AR02 writes are the
budget authority; the sidecar binds route/quote/usage and fails closed on gaps.
AR02 reserve/claim/T3 are successive durable transactions, NOT one transaction:
a failure between them leaves a non-replayable unresolved reservation.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from knowledge_engine.m27_ar02_durable_writer_v1_experimental import (
    DurableWriterV1,
    FenceError,
    Head,
    RunIdentity,
)
from knowledge_engine.m27_ar07_compute_policy_experimental import (
    ComputeDecisionInput,
    PriceSnapshotFixture,
    ProviderCatalogFixture,
    propose_compute,
)

VERSION = "W3_C07I_LOCAL_CAS_v1"
PASS = "AR07_LOCAL_CAS_ROUTING_PASS"
OPEN = "ECONOMIC_AND_PROVIDER_INTEGRATION_OPEN"


class BudgetFence(FenceError):
    """Fail-closed local budget / quote / binding / invoice error."""


@dataclass(frozen=True, slots=True)
class Attempt:
    identity: RunIdentity
    head: Head
    decision_input: ComputeDecisionInput
    providers: tuple[ProviderCatalogFixture, ...]
    prices: tuple[PriceSnapshotFixture, ...]
    snapshot_id: str
    consent_generation: int
    exclusion_generation: int
    request_key: str
    reserve_id: str
    approval_id: str
    intent_id: str
    claim_id: str


@dataclass(frozen=True, slots=True)
class InvoiceFixture:
    usage_id: str
    snapshot_id: str
    model_version: str
    currency: str
    source_revision: str
    consent_generation: int
    actual_cost_microunits: int
    actual_tokens: int
    evidence_ref: str


@dataclass(frozen=True, slots=True)
class BudgetReceipt:
    status: str
    head: Head
    requested_microunits: int
    corrected_spent_microunits: int
    route_id: str | None
    snapshot_id: str | None
    economically_certified: bool = False
    provider_calls: int = 0
    client_delivered: bool = False


def _valid(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 128
        and all(c.isascii() and (c.isalnum() or c in "-_./") for c in value)
    )


def _number(value: object) -> bool:
    return type(value) is int and value >= 0


def _fingerprint(attempt: Attempt, quote: PriceSnapshotFixture, route: str) -> str:
    item = attempt.decision_input
    payload = {
        "version": VERSION,
        "identity": [
            attempt.identity.tenant_id, attempt.identity.run_id,
            attempt.identity.task_id, attempt.identity.task_version,
            attempt.identity.principal_id,
        ],
        "request": attempt.request_key,
        "ids": [attempt.reserve_id, attempt.approval_id, attempt.intent_id, attempt.claim_id],
        "epoch": attempt.head.epoch,
        "route": route,
        "price": [
            quote.snapshot_id, quote.provider_id, quote.model_id,
            quote.model_version, quote.currency, quote.cost_per_token_microunits,
            quote.observed_at_ms, quote.expires_at_ms,
        ],
        "workload": item.workload_kind,
        "tokens": item.request_tokens * item.agent_count,
        "wall": item.request_wall_ms,
        "source": item.source_revision,
        "consent": attempt.consent_generation,
        "exclusion": attempt.exclusion_generation,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class LocalComputeBudget:
    """Local-only AR02 budget owner with append/reconciliation sidecar.

    Does NOT expose a provider dispatch method. Every new attempt is CAS-fenced
    to a verified AR02 head; a possible-send fence only records uncertainty.
    """

    def __init__(self, writer: DurableWriterV1):
        if not writer.fixture_approval_mode:
            raise BudgetFence("TEST_FIXTURE_APPROVAL_REQUIRED")
        self.writer = writer
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS w3_compute_contracts(
              tenant TEXT NOT NULL, run TEXT NOT NULL, request_key TEXT NOT NULL,
              reserve_id TEXT NOT NULL, claim_id TEXT NOT NULL,
              charge_id TEXT, usage_id TEXT, fingerprint TEXT NOT NULL,
              route_id TEXT NOT NULL, snapshot_id TEXT NOT NULL,
              model_version TEXT NOT NULL, currency TEXT NOT NULL,
              source_revision TEXT NOT NULL, consent_generation INTEGER NOT NULL,
              tokens INTEGER NOT NULL, wall_ms INTEGER NOT NULL,
              quote_cost INTEGER NOT NULL, actual_cost INTEGER,
              state TEXT NOT NULL,
              PRIMARY KEY(tenant,run,request_key),
              UNIQUE(reserve_id), UNIQUE(claim_id), UNIQUE(charge_id),
              UNIQUE(usage_id)
            )""")

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(str(self.writer.path), isolation_level=None, timeout=8)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=8000")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            yield db
        finally:
            db.close()

    def _rows(self, identity: RunIdentity) -> list[sqlite3.Row]:
        with self._db() as db:
            return db.execute(
                "SELECT * FROM w3_compute_contracts WHERE tenant=? AND run=?",
                (identity.tenant_id, identity.run_id),
            ).fetchall()

    def _contract(self, identity: RunIdentity, request_key: str) -> sqlite3.Row:
        with self._db() as db:
            row = db.execute(
                "SELECT * FROM w3_compute_contracts "
                "WHERE tenant=? AND run=? AND request_key=?",
                (identity.tenant_id, identity.run_id, request_key),
            ).fetchone()
        if row is None:
            raise BudgetFence("UNKNOWN_REQUEST_KEY")
        return row

    def _change(self, identity: RunIdentity, key: str, state: str, **fields: object) -> None:
        if not set(fields) <= {"charge_id", "usage_id", "actual_cost"}:
            raise BudgetFence("SIDECAR_UPDATE_SCOPE")
        parts = ["state=?"] + [f"{field}=?" for field in fields]
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                cur = db.execute(
                    f"UPDATE w3_compute_contracts SET {','.join(parts)} "
                    "WHERE tenant=? AND run=? AND request_key=?",
                    (state, *fields.values(), identity.tenant_id, identity.run_id, key),
                )
                if cur.rowcount != 1:
                    raise BudgetFence("SIDECAR_LOST")
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def _safe_read(self, identity: RunIdentity) -> tuple[Head, dict, list[sqlite3.Row]]:
        rec = self.writer.recover(identity)
        head = rec["head"]
        rows = self._rows(identity)
        with self._db() as db:
            pending = db.execute(
                "SELECT COUNT(*) AS n FROM reservations "
                "WHERE tenant=? AND run=? AND charged=0",
                (identity.tenant_id, identity.run_id),
            ).fetchone()["n"]
            orphan = db.execute(
                "SELECT COUNT(*) AS n FROM reservations r "
                "LEFT JOIN w3_compute_contracts c "
                "ON r.tenant=c.tenant AND r.run=c.run AND r.reserve_id=c.reserve_id "
                "WHERE r.tenant=? AND r.run=? AND c.reserve_id IS NULL",
                (identity.tenant_id, identity.run_id),
            ).fetchone()["n"]
        if pending or orphan:
            # Reserve and sidecar are separate commits. Crash means no new spend.
            rec["w3_pending_or_orphan"] = True
        else:
            rec["w3_pending_or_orphan"] = False
        return head, rec, rows

    def reserve_and_fence(
        self, attempt: Attempt, *,
        fault: Callable[[str], None] | None = None,
    ) -> BudgetReceipt:
        """Reserve then durably claim/T3-fence; never invoke any model or tool."""
        item, identity = attempt.decision_input, attempt.identity
        identifiers = (
            attempt.request_key, attempt.reserve_id, attempt.approval_id,
            attempt.intent_id, attempt.claim_id, attempt.snapshot_id,
        )
        if not all(_valid(v) for v in identifiers):
            raise BudgetFence("INVALID_ATTEMPT_ID")
        if (
            (item.tenant_id, item.run_id, item.task_id, item.task_version)
            != (identity.tenant_id, identity.run_id, identity.task_id, identity.task_version)
            or item.lease_epoch != attempt.head.epoch
        ):
            raise BudgetFence("IDENTITY_OR_LEASE_MISMATCH")
        head, rec, rows = self._safe_read(identity)
        if rec["revoked"] or head.state != "OPEN":
            raise BudgetFence("REVOKED_OR_TERMINAL")
        if (
            attempt.head != head or item.budget_version != head.seq
            or item.max_cost_microunits != head.budget
            or item.spent_cost_microunits != head.spent
            or item.reserved_cost_microunits != head.reserved
        ):
            raise BudgetFence("STALE_BUDGET_CAS")
        if (
            item.source_revision != rec["source_revision"]
            or item.authorized_revision != rec["source_revision"]
            or attempt.consent_generation != rec["consent_generation"]
            or attempt.exclusion_generation != rec["exclusion_generation"]
        ):
            raise BudgetFence("SOURCE_CONSENT_OR_ACL_DRIFT")
        if rec["corrected_spent"] != head.spent or rec["w3_pending_or_orphan"]:
            raise BudgetFence("ECONOMIC_RECONCILIATION_REQUIRED")
        if any(o["state"] != "SETTLED" for o in rows):
            raise BudgetFence("UNRESOLVED_ATTEMPT")
        if any(x["state"] in {"PENDING", "CLAIMED", "POSSIBLY_SENT"}
               for x in rec["outbox"]):
            raise BudgetFence("UNRESOLVED_EFFECT")
        if (
            item.spent_tokens != sum(x["tokens"] for x in rows if x["state"] == "SETTLED")
            or item.reserved_tokens != 0
            or item.spent_wall_ms != sum(
                x["wall_ms"] for x in rows if x["state"] == "SETTLED"
            )
            or item.reserved_wall_ms != 0
            or item.attempts_used != len(rows)
        ):
            raise BudgetFence("SIDE_CAR_METER_MISMATCH")
        decision = propose_compute(item, attempt.providers, attempt.prices)
        if decision.status != "RESERVATION_REQUIRED":
            raise BudgetFence("POLICY_" + decision.trace.reason_codes[0])
        quote_matches = [
            p for p in attempt.prices
            if isinstance(p, PriceSnapshotFixture) and p.snapshot_id == attempt.snapshot_id
        ]
        if len(quote_matches) != 1 or decision.trace.price_snapshot_id != attempt.snapshot_id:
            raise BudgetFence("UNKNOWN_OR_AMBIGUOUS_PRICE_SNAPSHOT")
        quote = quote_matches[0]
        if decision.reservation_cost_microunits <= 0 or (
            quote.model_version != decision.trace.model_version
            or quote.currency != item.currency
        ):
            raise BudgetFence("PRICE_VERSION_OR_CURRENCY_MISMATCH")
        route_id = decision.trace.selected_route_id
        if route_id is None:
            raise BudgetFence("NO_COMPUTE_ROUTE")
        fingerprint = _fingerprint(attempt, quote, route_id)
        # CAS is owned by AR02. There is no runnable Provider adapter.
        next_head = self.writer.reserve(
            identity, head, reserve_id=attempt.reserve_id,
            amount=decision.reservation_cost_microunits,
        )
        with self._db() as db:
            db.execute(
                "INSERT INTO w3_compute_contracts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identity.tenant_id, identity.run_id, attempt.request_key,
                    attempt.reserve_id, attempt.claim_id, None, None,
                    fingerprint, route_id, quote.snapshot_id,
                    quote.model_version, item.currency, item.source_revision,
                    attempt.consent_generation, decision.reservation_tokens,
                    decision.reservation_wall_ms, decision.reservation_cost_microunits,
                    None, "RESERVED",
                ),
            )
        if fault:
            fault("after_reserve")
        next_head = self.writer.provision_fixture_approval(
            identity, next_head, approval_id=attempt.approval_id,
            intent_digest=fingerprint, expires_at=item.deadline_at_ms,
        )
        if fault:
            fault("after_approval")
        next_head = self.writer.commit_intent_and_claim(
            identity, next_head, intent_id=attempt.intent_id,
            intent_digest=fingerprint, approval_id=attempt.approval_id,
            claim_id=attempt.claim_id, reserve_id=attempt.reserve_id,
            idempotency_key=attempt.request_key, now=item.now_ms,
        )
        if fault:
            fault("after_claim")
        next_head, ack = self.writer.claim_outbox(
            identity, next_head, claim_id=attempt.claim_id,
        )
        if fault:
            fault("after_ack")
        next_head = self.writer.mark_possible_send(
            identity, next_head, claim_id=attempt.claim_id, local_ack_token=ack,
        )
        self._change(identity, attempt.request_key, "FENCED")
        if fault:
            fault("after_fence")
        rec = self.writer.recover(identity)
        if (
            rec["head"] != next_head
            or not any(o["claim_id"] == attempt.claim_id and o["state"] == "POSSIBLY_SENT"
                       for o in rec["outbox"])
        ):
            raise BudgetFence("DURABLE_T3_FENCE_MISSING")
        return BudgetReceipt(
            "RESERVED_FENCED_NO_PROVIDER", next_head,
            decision.reservation_cost_microunits, rec["corrected_spent"],
            route_id, quote.snapshot_id,
        )

    def recover(self, identity: RunIdentity, request_key: str) -> BudgetReceipt:
        """Read-only fresh-connection proof; never redispatch or auto-release."""
        row = self._contract(identity, request_key)
        head, rec, _ = self._safe_read(identity)
        if rec["corrected_spent"] > head.budget or rec["corrected_spent"] != head.spent:
            status = "ECONOMIC_QUALIFICATION_OPEN"
        elif row["state"] == "SETTLED":
            status = PASS
        else:
            status = "RECOVERY_PAUSE_NO_RETRY"
        return BudgetReceipt(
            status, head, row["quote_cost"], rec["corrected_spent"],
            row["route_id"], row["snapshot_id"],
        )

    def settle(self, identity: RunIdentity, request_key: str,
               invoice: InvoiceFixture, *, charge_id: str) -> BudgetReceipt:
        """A synthetic usage receipt settles AR02 once. Not remote invoice truth."""
        if not _valid(charge_id) or not all(
            _valid(v) for v in (
                invoice.usage_id, invoice.snapshot_id, invoice.model_version,
                invoice.currency, invoice.source_revision, invoice.evidence_ref,
            )
        ) or not _number(invoice.actual_cost_microunits) or not _number(
            invoice.actual_tokens
        ):
            raise BudgetFence("INVALID_INVOICE")
        row = self._contract(identity, request_key)
        head, rec, _ = self._safe_read(identity)
        if (
            invoice.snapshot_id != row["snapshot_id"]
            or invoice.model_version != row["model_version"]
            or invoice.currency != row["currency"]
            or invoice.source_revision != row["source_revision"]
            or invoice.consent_generation != row["consent_generation"]
        ):
            raise BudgetFence("INVOICE_PRICE_SOURCE_CONSENT_MISMATCH")
        if rec["revoked"] or head.state != "OPEN":
            raise BudgetFence("NO_BILLING_ON_REVOKED_OR_TERMINAL")
        if (
            not any(o["claim_id"] == row["claim_id"] and o["state"] == "POSSIBLY_SENT"
                    for o in rec["outbox"])
        ):
            raise BudgetFence("NO_FENCED_ATTEMPT")
        if row["state"] == "SETTLED":
            if (
                row["usage_id"] == invoice.usage_id
                and row["charge_id"] == charge_id
                and row["actual_cost"] == invoice.actual_cost_microunits
            ):
                return self.recover(identity, request_key)
            raise BudgetFence("DUPLICATE_OR_CONFLICTING_USAGE")
        if row["state"] != "FENCED":
            raise BudgetFence("INCOMPLETE_RESERVATION_RECOVERY_REQUIRED")
        if invoice.actual_tokens > row["tokens"]:
            raise BudgetFence("UNPLANNED_TOKEN_USAGE")
        if rec["corrected_spent"] != head.spent:
            raise BudgetFence("ECONOMIC_RECONCILIATION_REQUIRED")
        # After process failure following AR02 charge but before sidecar status,
        # refuse replay rather than double-charge a previously consumed reserve.
        with self._db() as db:
            exists = db.execute(
                "SELECT 1 FROM charges WHERE tenant=? AND run=? AND reserve_id=?",
                (identity.tenant_id, identity.run_id, row["reserve_id"]),
            ).fetchone()
        if exists is not None:
            raise BudgetFence("CHARGE_COMMITTED_RECOVERY_REQUIRED")
        bounded = min(invoice.actual_cost_microunits, row["quote_cost"])
        next_head = self.writer.charge(
            identity, head, reserve_id=row["reserve_id"], charge_id=charge_id,
            amount=bounded,
        )
        self._change(
            identity, request_key, "SETTLED", charge_id=charge_id,
            usage_id=invoice.usage_id, actual_cost=invoice.actual_cost_microunits,
        )
        excess = invoice.actual_cost_microunits - bounded
        if excess:
            self.writer.audit_charge_adjustment(
                adjustment_id="overrun-" + invoice.usage_id,
                charge_id=charge_id, delta=excess, evidence_ref=invoice.evidence_ref,
            )
        rec = self.writer.recover(identity)
        return BudgetReceipt(
            "ECONOMIC_QUALIFICATION_OPEN" if excess else PASS,
            next_head, row["quote_cost"], rec["corrected_spent"],
            row["route_id"], row["snapshot_id"],
        )

    def late_invoice(self, identity: RunIdentity, request_key: str,
                     *, adjustment_id: str, evidence_ref: str,
                     delta_microunits: int) -> BudgetReceipt:
        """Record a unique positive late correction. Never reopen spending."""
        if not all(_valid(v) for v in (adjustment_id, evidence_ref)) or (
            not _number(delta_microunits) or delta_microunits == 0
        ):
            raise BudgetFence("INVALID_LATE_INVOICE")
        row = self._contract(identity, request_key)
        if row["state"] != "SETTLED" or row["charge_id"] is None:
            raise BudgetFence("LATE_INVOICE_WITHOUT_SETTLEMENT")
        self.writer.audit_charge_adjustment(
            adjustment_id=adjustment_id, charge_id=row["charge_id"],
            delta=delta_microunits, evidence_ref=evidence_ref,
        )
        return self.recover(identity, request_key)
