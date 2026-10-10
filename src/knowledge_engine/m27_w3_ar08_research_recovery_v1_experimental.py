"""W3 S08R: fixture-only research checkpoint, provenance and crash recovery.

SQLite bytes, durable AR02 events and budget CAS are real LOCAL operations.
The local source/reviewer fixtures are NOT IdP, Provider, billing, publisher,
independent signatures, or evidence of an external research task.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from dataclasses import asdict, dataclass

from knowledge_engine.m27_ar02_durable_writer_v1_experimental import (
    DurableWriterV1,
    FenceError,
    Head,
    RunIdentity,
)

VERSION = "S08R/1.0/LOCAL_FIXTURE_ONLY"
PASS = "RESEARCH_LOCAL_RECOVERY_PASS"


class ResearchDenied(FenceError):
    """A fail-closed research-only admission, source, or recovery fence."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ResearchDenied(code)


def _hex64(value: str) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


@dataclass(frozen=True)
class SourcePin:
    source_id: str
    source_revision: str
    original_sha256: str
    tenant_id: str
    valid_until: int
    consent_generation: int
    exclusion_generation: int
    acl_principals: tuple[str, ...]
    purposes: tuple[str, ...]
    quote_start: int
    quote_end: int
    kind: str  # support | counter
    hypothesis_id: str
    tainted: bool = False


@dataclass(frozen=True)
class ResearchPlan:
    identity: RunIdentity
    purpose_id: str
    plan_version: int
    brief_sha256: str
    hypotheses: tuple[str, ...]
    milestones: tuple[str, ...]
    source_pins: tuple[SourcePin, ...]
    reserve_id: str
    reserved_microunits: int
    deadline_at: int


@dataclass(frozen=True)
class ReviewReceipt:
    source_id: str
    source_revision: str
    original_sha256: str
    reviewer_id: str
    reviewed_at: int
    verdict: str  # ACCEPTED | REJECTED
    review_ref: str


FaultHook = Callable[[str], None]


class ResearchRecoveryV1:
    """Local-only protocol backed by the *same* SQLite file as DurableWriterV1.

    Checkpoints and their K02D journal events commit in a single transaction.
    K02D's public reserve() is reconciled after a crash without re-reserving.
    Claim markers are durable BEFORE any possible external effect; this module
    contains no remote dispatcher and UNKNOWN claims cannot be auto-retried.
    """

    def __init__(self, writer: DurableWriterV1, *, fault: FaultHook | None = None):
        self.writer = writer
        self.fault = fault
        with writer._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS research_plans (
                    tenant TEXT NOT NULL, run TEXT NOT NULL,
                    plan_sha TEXT NOT NULL, plan_json BLOB NOT NULL,
                    PRIMARY KEY(tenant,run));
                CREATE TABLE IF NOT EXISTS research_sources (
                    tenant TEXT NOT NULL, run TEXT NOT NULL,
                    source_id TEXT NOT NULL, original BLOB NOT NULL,
                    source_sha TEXT NOT NULL,
                    PRIMARY KEY(tenant,run,source_id));
                CREATE TABLE IF NOT EXISTS research_reviews (
                    tenant TEXT NOT NULL, run TEXT NOT NULL, source_id TEXT NOT NULL,
                    receipt BLOB NOT NULL, PRIMARY KEY(tenant,run,source_id));
                CREATE TABLE IF NOT EXISTS research_checkpoints (
                    tenant TEXT NOT NULL, run TEXT NOT NULL, ordinal INTEGER NOT NULL,
                    milestone TEXT NOT NULL, cursor TEXT NOT NULL, prior TEXT NOT NULL,
                    digest TEXT NOT NULL, journal_seq INTEGER NOT NULL,
                    journal_digest TEXT NOT NULL,
                    PRIMARY KEY(tenant,run,ordinal),
                    UNIQUE(tenant,run,milestone,cursor));
                CREATE TABLE IF NOT EXISTS research_jobs (
                    tenant TEXT NOT NULL, run TEXT NOT NULL,
                    job_id TEXT NOT NULL, intent_sha TEXT NOT NULL,
                    state TEXT NOT NULL, PRIMARY KEY(tenant,run,job_id));
                CREATE TABLE IF NOT EXISTS research_artifacts (
                    tenant TEXT NOT NULL, run TEXT NOT NULL,
                    original BLOB NOT NULL, artifact_sha TEXT NOT NULL,
                    journal_seq INTEGER NOT NULL, journal_digest TEXT NOT NULL,
                    PRIMARY KEY(tenant,run));
            """)

    def _probe(self, stage: str) -> None:
        if self.fault:
            self.fault(stage)

    @staticmethod
    def _key(plan: ResearchPlan) -> tuple[str, str]:
        return plan.identity.tenant_id, plan.identity.run_id

    @staticmethod
    def _validate_plan(plan: ResearchPlan) -> None:
        identity = plan.identity
        _require(bool(identity.tenant_id and identity.run_id
                      and identity.task_id and identity.principal_id)
                 and identity.task_version > 0, "INVALID_IDENTITY")
        _require(plan.plan_version == 1 and bool(plan.purpose_id)
                 and _hex64(plan.brief_sha256), "INVALID_PLAN_VERSION_OR_PURPOSE")
        _require(plan.reserved_microunits > 0 and bool(plan.reserve_id)
                 and plan.deadline_at > 0, "INVALID_RESEARCH_BUDGET")
        _require(bool(plan.hypotheses) and len(set(plan.hypotheses)) == len(plan.hypotheses)
                 and all(plan.hypotheses), "INVALID_HYPOTHESIS_SET")
        _require(bool(plan.milestones) and len(set(plan.milestones)) == len(plan.milestones)
                 and all(plan.milestones), "INVALID_MILESTONES")
        _require(bool(plan.source_pins)
                 and len({p.source_id for p in plan.source_pins}) == len(plan.source_pins),
                 "DUPLICATE_OR_MISSING_SOURCES")
        for pin in plan.source_pins:
            _require(bool(pin.source_id and pin.source_revision)
                     and _hex64(pin.original_sha256)
                     and pin.tenant_id == identity.tenant_id,
                     "SOURCE_ID_REVISION_OR_TENANT")
            _require(pin.kind in {"support", "counter"}
                     and pin.hypothesis_id in plan.hypotheses
                     and 0 <= pin.quote_start < pin.quote_end
                     and pin.valid_until > 0, "INVALID_CITATION_PIN")
        for hypothesis in plan.hypotheses:
            _require(any(p.hypothesis_id == hypothesis and p.kind == "support"
                         for p in plan.source_pins), "MISSING_SUPPORT_CHECKLIST")
            _require(any(p.hypothesis_id == hypothesis and p.kind == "counter"
                         for p in plan.source_pins), "MISSING_COUNTEREVIDENCE_CHECKLIST")

    def _plan_row(self, db: sqlite3.Connection, plan: ResearchPlan) -> sqlite3.Row:
        row = db.execute("SELECT * FROM research_plans WHERE tenant=? AND run=?",
                         self._key(plan)).fetchone()
        _require(row is not None, "PLAN_NOT_ADMITTED")
        _require(row["plan_sha"] == _sha(_canonical(asdict(plan)))
                 and row["plan_json"] == _canonical(asdict(plan)),
                 "IMMUTABLE_PLAN_MISMATCH")
        return row

    def _authority(self, db: sqlite3.Connection, plan: ResearchPlan,
                   now: int) -> Head:
        self._validate_plan(plan)
        self._plan_row(db, plan)
        row = self.writer._load(db, plan.identity)
        _require(row["state"] == "OPEN" and not row["revoked"],
                 "REVOKED_OR_TERMINAL")
        _require(now < plan.deadline_at, "RESEARCH_DEADLINE_EXPIRED")
        _require(not any(x["state"] in {"POSSIBLY_SENT", "CLAIMED"}
                         for x in db.execute(
                             "SELECT state FROM outbox WHERE tenant=? AND run=?",
                             self._key(plan))),
                 "UNKNOWN_OUTBOX_EFFECT")
        _require(not any(x["state"] == "UNKNOWN_REMOTE"
                         for x in db.execute(
                             "SELECT state FROM research_jobs WHERE tenant=? AND run=?",
                             self._key(plan))),
                 "UNKNOWN_REMOTE_EFFECT")
        revisions = {p.source_revision for p in plan.source_pins}
        _require(len(revisions) == 1 and row["source_rev"] in revisions,
                 "SOURCE_REVISION_DRIFT")
        for pin in plan.source_pins:
            _require(now < pin.valid_until and not pin.tainted
                     and pin.consent_generation == row["consent_gen"]
                     and pin.exclusion_generation == row["exclusion_gen"]
                     and plan.purpose_id in pin.purposes
                     and plan.identity.principal_id in pin.acl_principals,
                     "SOURCE_EXPIRED_ACL_CONSENT_OR_TAINT")
        return self.writer._head(row)

    def admit(self, plan: ResearchPlan, *, now: int) -> Head:
        self._validate_plan(plan)
        serialized = _canonical(asdict(plan))
        with self.writer._write() as db:
            current = db.execute(
                "SELECT * FROM research_plans WHERE tenant=? AND run=?",
                self._key(plan)).fetchone()
            if current:
                self._plan_row(db, plan)
                return self._authority(db, plan, now)
            row = self.writer._load(db, plan.identity)
            _require(row["seq"] >= 1 and row["state"] == "OPEN"
                     and row["budget"] >= plan.reserved_microunits,
                     "AR02_RUN_NOT_READY")
            _require(row["source_rev"] in {p.source_revision for p in plan.source_pins},
                     "SOURCE_REVISION_DRIFT")
            db.execute("INSERT INTO research_plans VALUES(?,?,?,?)",
                       (*self._key(plan), _sha(serialized), serialized))
            self._probe("after_plan_insert")
            self._authority(db, plan, now)
            return self.writer._append(db, row, "RESEARCH_PLAN_ADMITTED", {
                "plan_sha": _sha(serialized), "version": VERSION,
            })

    def reserve_budget(self, plan: ResearchPlan, *, now: int) -> Head:
        with self.writer._connect() as db:
            self._authority(db, plan, now)
            found = db.execute(
                "SELECT amount FROM reservations WHERE tenant=? AND run=?"
                " AND reserve_id=?", (*self._key(plan), plan.reserve_id),
            ).fetchone()
            if found:
                _require(found["amount"] == plan.reserved_microunits,
                         "RESERVATION_AMOUNT_DRIFT")
                return self.writer.read_head(plan.identity)
            head = self.writer.read_head(plan.identity)
        head = self.writer.reserve(plan.identity, head, reserve_id=plan.reserve_id,
                                   amount=plan.reserved_microunits)
        self._probe("after_writer_reserve_committed")
        return head

    def register_source(self, plan: ResearchPlan, *, source_id: str,
                        original_bytes: bytes, now: int) -> None:
        _require(type(original_bytes) is bytes and bool(original_bytes),
                 "SOURCE_BYTES_NOT_ACTUAL")
        with self.writer._write() as db:
            self._authority(db, plan, now)
            pin = next((p for p in plan.source_pins if p.source_id == source_id), None)
            _require(pin is not None and _sha(original_bytes) == pin.original_sha256,
                     "UNPINNED_OR_HALLUCINATED_EVIDENCE")
            _require(pin.quote_end <= len(original_bytes),
                     "QUOTE_OUT_OF_ORIGINAL_RANGE")
            old = db.execute(
                "SELECT original FROM research_sources WHERE tenant=? AND run=?"
                " AND source_id=?", (*self._key(plan), source_id),
            ).fetchone()
            if old:
                _require(old["original"] == original_bytes, "SOURCE_BYTES_CHANGED")
                return
            db.execute("INSERT INTO research_sources VALUES(?,?,?,?,?)",
                       (*self._key(plan), source_id, original_bytes,
                        _sha(original_bytes)))
            self._probe("after_source_insert")

    def record_review(self, plan: ResearchPlan, receipt: ReviewReceipt,
                      *, now: int) -> None:
        with self.writer._write() as db:
            self._authority(db, plan, now)
            pin = next((p for p in plan.source_pins
                        if p.source_id == receipt.source_id), None)
            _require(pin is not None and receipt.source_revision == pin.source_revision
                     and receipt.original_sha256 == pin.original_sha256,
                     "REVIEW_PIN_DISAGREEMENT")
            _require(bool(receipt.reviewer_id and receipt.review_ref)
                     and receipt.reviewer_id != plan.identity.principal_id
                     and 0 <= receipt.reviewed_at <= now
                     and receipt.verdict == "ACCEPTED",
                     "INDEPENDENT_REVIEW_MISSING_OR_REJECTED")
            source = db.execute(
                "SELECT original FROM research_sources WHERE tenant=? AND run=?"
                " AND source_id=?", (*self._key(plan), receipt.source_id),
            ).fetchone()
            _require(source is not None
                     and _sha(source["original"]) == pin.original_sha256,
                     "REVIEWED_SOURCE_UNAVAILABLE")
            serialized = _canonical(asdict(receipt))
            old = db.execute(
                "SELECT receipt FROM research_reviews WHERE tenant=? AND run=?"
                " AND source_id=?", (*self._key(plan), receipt.source_id),
            ).fetchone()
            if old:
                _require(old["receipt"] == serialized, "REVIEW_SUPERSESSION_DENIED")
                return
            db.execute("INSERT INTO research_reviews VALUES(?,?,?,?)",
                       (*self._key(plan), receipt.source_id, serialized))

    def _check_checkpoints(self, db: sqlite3.Connection,
                           plan: ResearchPlan) -> list[sqlite3.Row]:
        checkpoints = db.execute(
            "SELECT * FROM research_checkpoints WHERE tenant=? AND run=?"
            " ORDER BY ordinal", self._key(plan),
        ).fetchall()
        prior = _sha(_canonical({"domain": VERSION, "plan": _sha(
            _canonical(asdict(plan)))}))
        for index, item in enumerate(checkpoints, 1):
            payload = {"ordinal": index, "milestone": item["milestone"],
                       "cursor": item["cursor"], "prior": prior}
            _require(item["ordinal"] == index and item["prior"] == prior
                     and item["digest"] == _sha(_canonical(payload)),
                     "CHECKPOINT_CHAIN_CORRUPT")
            event = db.execute(
                "SELECT * FROM events WHERE tenant=? AND run=? AND seq=?",
                (*self._key(plan), item["journal_seq"]),
            ).fetchone()
            _require(event is not None and event["digest"] == item["journal_digest"]
                     and event["kind"] == "RESEARCH_CHECKPOINT"
                     and json.loads(event["payload"])["checkpoint_sha"]
                     == item["digest"], "CHECKPOINT_JOURNAL_DISAGREEMENT")
            prior = item["digest"]
        return checkpoints

    def checkpoint(self, plan: ResearchPlan, *, milestone: str,
                   cursor: str, now: int) -> tuple[Head, str]:
        _require(bool(cursor) and len(cursor) <= 256, "INVALID_CURSOR")
        with self.writer._write() as db:
            head = self._authority(db, plan, now)
            checks = self._check_checkpoints(db, plan)
            matches = [c for c in checks
                       if c["milestone"] == milestone and c["cursor"] == cursor]
            if matches:
                return head, matches[0]["digest"]
            _require(len(checks) < len(plan.milestones)
                     and milestone == plan.milestones[len(checks)],
                     "MILESTONE_OUT_OF_ORDER_OR_DUPLICATE")
            ordinal = len(checks) + 1
            prior = checks[-1]["digest"] if checks else _sha(_canonical({
                "domain": VERSION, "plan": _sha(_canonical(asdict(plan))),
            }))
            digest = _sha(_canonical({"ordinal": ordinal, "milestone": milestone,
                                      "cursor": cursor, "prior": prior}))
            row = self.writer._load(db, plan.identity)
            self.writer._cas(row, head)
            new_head = self.writer._append(db, row, "RESEARCH_CHECKPOINT", {
                "checkpoint_sha": digest, "cursor_sha": _sha(cursor.encode()),
                "milestone": milestone,
            })
            self._probe("after_journal_before_checkpoint")
            db.execute(
                "INSERT INTO research_checkpoints VALUES(?,?,?,?,?,?,?,?,?)",
                (*self._key(plan), ordinal, milestone, cursor, prior,
                 digest, new_head.seq, new_head.digest),
            )
            self._probe("after_checkpoint_before_commit")
            return new_head, digest

    def claim_job(self, plan: ResearchPlan, *, job_id: str,
                  intent_sha: str, now: int) -> None:
        """Durable at-most-once local claim; NEVER grants remote dispatch."""
        _require(bool(job_id) and _hex64(intent_sha), "INVALID_JOB_INTENT")
        with self.writer._write() as db:
            self._authority(db, plan, now)
            self._check_checkpoints(db, plan)
            old = db.execute(
                "SELECT intent_sha FROM research_jobs WHERE tenant=? AND run=?"
                " AND job_id=?", (*self._key(plan), job_id),
            ).fetchone()
            _require(old is None, "JOB_CLAIM_ALREADY_USED_NO_BLIND_RETRY")
            db.execute("INSERT INTO research_jobs VALUES(?,?,?,?,?)",
                       (*self._key(plan), job_id, intent_sha, "UNKNOWN_REMOTE"))
            self._probe("after_unknown_marker_before_commit")

    def resume(self, plan: ResearchPlan, *, now: int) -> dict:
        with self.writer._connect() as db:
            head = self._authority(db, plan, now)
            checkpoints = self._check_checkpoints(db, plan)
            return {"version": VERSION, "head": head,
                    "cursor": checkpoints[-1]["cursor"] if checkpoints else None,
                    "checkpoint_digest": checkpoints[-1]["digest"]
                    if checkpoints else None,
                    "checkpoint_count": len(checkpoints),
                    "dispatch_authorized": False,
                    "remote_job_replay_authorized": False}

    def propose_artifact(self, plan: ResearchPlan, *, now: int,
                         quoted_cost: int) -> tuple[Head, str]:
        """Store actual Markdown bytes; proposal only, never publish/terminal."""
        with self.writer._write() as db:
            head = self._authority(db, plan, now)
            checkpoints = self._check_checkpoints(db, plan)
            _require(len(checkpoints) == len(plan.milestones),
                     "RESEARCH_MILESTONES_INCOMPLETE")
            reserve = db.execute(
                "SELECT * FROM reservations WHERE tenant=? AND run=?"
                " AND reserve_id=?", (*self._key(plan), plan.reserve_id),
            ).fetchone()
            _require(reserve is not None and reserve["amount"] == quoted_cost
                     == plan.reserved_microunits and reserve["charged"] == 0,
                     "COST_QUOTE_OR_RESERVATION_MISMATCH")
            _require(db.execute(
                "SELECT 1 FROM research_artifacts WHERE tenant=? AND run=?",
                self._key(plan),
            ).fetchone() is None, "ARTIFACT_SUPERSESSION_DENIED")
            lines = ["# Local research evidence fixture", "",
                     "Status: PROPOSAL_LOCAL_FIXTURE_ONLY",
                     f"Task: {plan.identity.task_id}",
                     f"Purpose: {plan.purpose_id}",
                     f"Brief digest: {plan.brief_sha256}",
                     f"Checkpoint digest: {checkpoints[-1]['digest']}", "",
                     "## Source and counterevidence checklist", ""]
            for pin in plan.source_pins:
                source = db.execute(
                    "SELECT * FROM research_sources WHERE tenant=? AND run=?"
                    " AND source_id=?", (*self._key(plan), pin.source_id),
                ).fetchone()
                review = db.execute(
                    "SELECT receipt FROM research_reviews WHERE tenant=? AND run=?"
                    " AND source_id=?", (*self._key(plan), pin.source_id),
                ).fetchone()
                _require(source is not None and review is not None
                         and _sha(source["original"]) == pin.original_sha256
                         and source["source_sha"] == pin.original_sha256,
                         "SOURCE_OR_COUNTEREVIDENCE_MISSING")
                reviewed = json.loads(review["receipt"])
                _require(reviewed["source_id"] == pin.source_id
                         and reviewed["original_sha256"] == pin.original_sha256
                         and reviewed["source_revision"] == pin.source_revision
                         and reviewed["reviewer_id"] != plan.identity.principal_id
                         and reviewed["verdict"] == "ACCEPTED",
                         "COUNTEREVIDENCE_REVIEW_TAMPERED")
                quote = source["original"][pin.quote_start:pin.quote_end]
                _require(bool(quote), "EMPTY_CITED_ORIGINAL")
                lines.append(f"- {pin.kind.upper()} hypothesis={pin.hypothesis_id}"
                             f" source={pin.source_id}@{pin.source_revision}"
                             f" sha256={pin.original_sha256}"
                             f" span={pin.quote_start}:{pin.quote_end}"
                             f" reviewer={reviewed['reviewer_id']}"
                             f" review={reviewed['review_ref']}")
                lines.append("  - Quote from pinned original bytes (UTF-8): "
                             + quote.decode("utf-8", errors="backslashreplace"))
            lines += ["", "## Limitations", "",
                      "Synthetic, locally supplied bytes and review receipts only.",
                      "No external research result, validated publication, or actual billing.",
                      ""]
            artifact = "\n".join(lines).encode()
            digest = _sha(artifact)
            row = self.writer._load(db, plan.identity)
            self.writer._cas(row, head)
            new_head = self.writer._append(db, row, "RESEARCH_ARTIFACT_PROPOSAL", {
                "artifact_sha": digest, "checkpoint_sha": checkpoints[-1]["digest"],
            })
            self._probe("after_artifact_journal_before_blob")
            db.execute(
                "INSERT INTO research_artifacts VALUES(?,?,?,?,?,?)",
                (*self._key(plan), artifact, digest, new_head.seq, new_head.digest),
            )
            self._probe("after_artifact_insert_before_commit")
            return new_head, digest

    def read_artifact(self, plan: ResearchPlan) -> bytes:
        with self.writer._connect() as db:
            self._plan_row(db, plan)
            row = db.execute(
                "SELECT * FROM research_artifacts WHERE tenant=? AND run=?",
                self._key(plan),
            ).fetchone()
            _require(row is not None, "NO_LOCAL_ARTIFACT")
            event = db.execute(
                "SELECT kind,digest,payload FROM events WHERE tenant=? AND run=?"
                " AND seq=?", (*self._key(plan), row["journal_seq"]),
            ).fetchone()
            _require(_sha(row["original"]) == row["artifact_sha"]
                     and event is not None
                     and event["kind"] == "RESEARCH_ARTIFACT_PROPOSAL"
                     and event["digest"] == row["journal_digest"]
                     and json.loads(event["payload"])["artifact_sha"]
                     == row["artifact_sha"], "ARTIFACT_HASH_OR_JOURNAL_CORRUPT")
            return bytes(row["original"])
