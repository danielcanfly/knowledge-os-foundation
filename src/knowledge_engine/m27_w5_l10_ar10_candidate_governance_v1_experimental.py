"""AR10 candidate-only governed learning. Offline, synthetic, fail-closed.

This module deliberately owns no Provider, ACL, tool, runtime, release, or
production adapter. Its SQLite database may contain only synthetic opaque IDs,
digests and immutable receipts, never original user content or hidden labels.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

NAMESPACE = "ar10.proposal/v1"
G09_BLOCK = "W4_ENGINEERING_LOCAL_ACCEPTED_PHASE_B_EXTERNAL_BLOCKED"
SHA = re.compile(r"[0-9a-f]{64}\Z")
ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.:/-]{0,119}\Z")
TYPES = frozenset({"routing", "prompt", "retrieval", "tool-policy", "evaluator", "skill", "code"})
TERMINAL = frozenset({"REJECTED", "QUARANTINED", "EXPIRED"})
LATER = frozenset(
    {
        "BLIND_EVAL",
        "SECURITY_PRIVACY_COST_APPROVAL",
        "SIGNED_IMMUTABLE_VERSION",
        "ISOLATED_CANARY",
        "RELEASE_PENDING_REL02",
        "RELEASED",
        "REL01",
        "REL02",
        "PRODUCTION",
        "GRANT",
        "ACL",
        "POLICY_ACTIVATION",
    }
)
ALLOWED_EFFECTS = frozenset(
    {
        "routing_rank_delta_only",
        "prompt_fixture_only",
        "retrieval_plan_fixture_only",
        "tighten_tool_permissions_only",
        "evaluator_design_only",
        "skill_recipe_fixture_only",
        "code_patch_fixture_only",
    }
)
BAD_CLASSIFICATIONS = frozenset(
    {"REAL", "USER_CONTENT", "HIDDEN_HOLDOUT", "SECRET", "CROSS_TENANT"}
)
ACCEPTED = frozenset({"ACCEPTED", "PASS"})
ADVERSE = frozenset({"UNKNOWN_EFFECT", "LEAK", "REVOCATION", "TAINT"})


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def _id(value: object) -> bool:
    return isinstance(value, str) and ID.fullmatch(value) is not None


def _sha(value: object) -> bool:
    return isinstance(value, str) and SHA.fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class ImprovementProposal:
    namespace: str
    proposal_id: str
    tenant_id: str
    principal_id: str
    origin_run_id: str
    origin_source_id: str
    origin_subject_id: str
    source_classification: str
    purpose: str
    consent_ref: str
    consent_generation: int
    exclusion_generation: int
    tombstone_generation: int
    retention_until_ms: int
    created_ms: int
    expires_ms: int
    source_revision: str
    source_sha256: str
    base_artifact_sha256: str
    control_artifact_sha256: str
    runner_sha256: str
    candidate_artifact_sha256: str
    candidate_type: str
    manifest_sha256: str
    rubric_sha256: str
    dataset_version: str
    version_tag: str
    rollback_ref: str
    reviewer_id: str
    proposed_effect: str
    derivative_of: str = ""
    tainted: bool = False
    contaminated: bool = False
    source_revoked: bool = False


@dataclass(frozen=True, slots=True)
class RightsSnapshot:
    tenant_id: str
    purpose: str
    source_id: str
    subject_id: str
    revision: str
    consent_generation: int
    exclusion_generation: int
    tombstone_generation: int
    consent_active: bool
    source_revoked: bool
    valid_until_ms: int
    fixture_only: bool = True


@dataclass(frozen=True, slots=True)
class OfflineCase:
    case_id: str
    stratum: str
    status: str
    cost_micros: int | None
    attempts: int = 1
    safety_incident: bool = False
    unknown_effect: bool = False
    rights_current: bool = True


@dataclass(frozen=True, slots=True)
class MatchedOfflineCohort:
    version: str
    rubric_sha256: str
    source_sha256: str
    control_sha256: str
    candidate_sha256: str
    assigned: tuple[str, ...]
    baseline: tuple[OfflineCase, ...]
    candidate: tuple[OfflineCase, ...]
    fixture_only: bool = True
    independent_external_custody: bool = False
    sealed_hidden_labels: bool = False
    changed_weights_after_outcome: bool = False
    self_scored: bool = False


@dataclass(frozen=True, slots=True)
class W4FixtureSeams:
    """Concrete W4 types, never a source of signed/external trust."""

    e09h: object
    d09: dict[str, object]
    t09: object
    p09: object
    e09b: object
    local_only: bool = True


@dataclass(frozen=True, slots=True)
class Comparison:
    status: str
    reasons: tuple[str, ...]
    denominator: int
    control_accepted: int
    candidate_accepted: int
    control_cost_micros: int | None
    candidate_cost_micros: int | None
    per_stratum: tuple[tuple[str, int, int, int], ...]
    promotion_eligible: bool = False


@dataclass(frozen=True, slots=True)
class Decision:
    state: str
    reason: str
    version: int
    head: str
    tool_effects: int = 0
    release_writes: int = 0


@dataclass(frozen=True, slots=True)
class Lease:
    proposal_id: str
    owner: str
    epoch: int
    until_ms: int
    version: int


class Denied(ValueError):
    """Deny-first admission or monotonic authority fence failure."""


def _validate_proposal(p: ImprovementProposal, now: int) -> str:
    if p.namespace != NAMESPACE or p.candidate_type not in TYPES:
        return "BAD_NAMESPACE_OR_TYPE"
    required = (
        p.proposal_id,
        p.tenant_id,
        p.principal_id,
        p.origin_run_id,
        p.origin_source_id,
        p.origin_subject_id,
        p.purpose,
        p.consent_ref,
        p.source_revision,
        p.dataset_version,
        p.version_tag,
        p.rollback_ref,
        p.reviewer_id,
    )
    if not all(_id(x) for x in required):
        return "BAD_IDENTITY"
    hashes = (
        p.source_sha256,
        p.base_artifact_sha256,
        p.control_artifact_sha256,
        p.runner_sha256,
        p.candidate_artifact_sha256,
        p.manifest_sha256,
        p.rubric_sha256,
    )
    if not all(_sha(x) for x in hashes):
        return "BAD_DIGEST"
    if p.derivative_of and not _id(p.derivative_of):
        return "BAD_DERIVATIVE"
    if min(p.consent_generation, p.exclusion_generation, p.tombstone_generation) < 0:
        return "BAD_GENERATION"
    if p.source_classification != "SYNTHETIC" or p.source_classification in BAD_CLASSIFICATIONS:
        return "SOURCE_CLASSIFICATION_DENIED"
    if p.proposed_effect not in ALLOWED_EFFECTS:
        return "FORBIDDEN_EFFECT"
    expected = {
        "routing": "routing_rank_delta_only",
        "prompt": "prompt_fixture_only",
        "retrieval": "retrieval_plan_fixture_only",
        "tool-policy": "tighten_tool_permissions_only",
        "evaluator": "evaluator_design_only",
        "skill": "skill_recipe_fixture_only",
        "code": "code_patch_fixture_only",
    }
    if p.proposed_effect != expected[p.candidate_type]:
        return "EFFECT_TYPE_MISMATCH"
    if p.principal_id == p.reviewer_id:
        return "SELF_REVIEW"
    if p.tainted or p.contaminated or p.source_revoked:
        return "TAINT"
    if not p.consent_ref or p.consent_ref == "none":
        return "NO_CONSENT"
    if p.created_ms > now or min(p.retention_until_ms, p.expires_ms) <= now:
        return "EXPIRED"
    if p.expires_ms <= p.created_ms or p.retention_until_ms <= p.created_ms:
        return "EXPIRED"
    return "OK"


def _rights_error(p: ImprovementProposal, rights: RightsSnapshot, now: int) -> str:
    if not rights.fixture_only:
        return "EXTERNAL_RIGHTS_NOT_ADMITTED"
    if (rights.tenant_id, rights.purpose, rights.source_id, rights.subject_id) != (
        p.tenant_id,
        p.purpose,
        p.origin_source_id,
        p.origin_subject_id,
    ):
        return "SCOPE_CROSSOVER"
    if rights.revision != p.source_revision:
        return "REVISION_CHANGED"
    if (rights.consent_generation, rights.exclusion_generation, rights.tombstone_generation) != (
        p.consent_generation,
        p.exclusion_generation,
        p.tombstone_generation,
    ):
        return "GENERATION_CHANGED"
    if not rights.consent_active:
        return "CONSENT_REVOKED"
    if rights.source_revoked:
        return "SOURCE_REVOKED"
    if rights.valid_until_ms <= now:
        return "SOURCE_EXPIRED"
    return "OK"


def evaluate_matched_offline(
    p: ImprovementProposal, cohort: MatchedOfflineCohort, seams: W4FixtureSeams
) -> Comparison:
    # Exact classes from accepted W4 source, *not* duck-typed claimed pass strings.
    from knowledge_engine.m27_w4_ar09_independent_harness_v1_experimental import (
        DenominatorLedger,
    )
    from knowledge_engine.m27_w4_e09b_blind_gate_v1_experimental import AdmissionDecision
    from knowledge_engine.m27_w4_p09_external_evidence_v1_experimental import Admission
    from knowledge_engine.m27_w4_t09_transport_evidence_v1_experimental import StreamVerdict

    reasons: set[str] = set()
    if not (
        isinstance(seams.e09h, DenominatorLedger)
        and isinstance(seams.t09, StreamVerdict)
        and isinstance(seams.p09, Admission)
        and isinstance(seams.e09b, AdmissionDecision)
    ):
        reasons.add("UNTRUSTED_W4_STRUCTURE")
    if not seams.local_only:
        reasons.add("EXTERNAL_FIXTURE_ASSERTION")
    if not isinstance(seams.d09, dict) or seams.d09.get("verdict") != "W4_D09_CORPUS_NOT_ADMITTED":
        reasons.add("D09_AUTHORITY_SPOOF")
    if isinstance(seams.e09b, AdmissionDecision):
        if seams.e09b.official_evaluation_ran or seams.e09b.release_certified:
            reasons.add("FORGED_PHASE_B")
        if seams.e09b.status != "E09B_PHASE_B_BLOCKED_EVIDENCE_DEBT":
            reasons.add("FORGED_PHASE_B")
    if (
        not cohort.fixture_only
        or cohort.independent_external_custody
        or cohort.sealed_hidden_labels
    ):
        reasons.add("EXTERNAL_OR_HIDDEN_COHORT_DENIED")
    if cohort.changed_weights_after_outcome or cohort.self_scored:
        reasons.add("CHERRY_PICKED_OR_SELF_SCORED")
    if (
        cohort.version != p.dataset_version
        or cohort.rubric_sha256 != p.rubric_sha256
        or cohort.source_sha256 != p.source_sha256
        or cohort.control_sha256 != p.control_artifact_sha256
        or cohort.candidate_sha256 != p.candidate_artifact_sha256
    ):
        reasons.add("UNMATCHED_FREEZE")
    assigned = cohort.assigned
    if not assigned or len(set(assigned)) != len(assigned) or not all(_id(x) for x in assigned):
        reasons.add("BAD_ASSIGNMENT")
    bases = {x.case_id: x for x in cohort.baseline}
    candidates = {x.case_id: x for x in cohort.candidate}
    if (
        len(bases) != len(cohort.baseline)
        or len(candidates) != len(cohort.candidate)
        or set(bases) != set(assigned)
        or set(candidates) != set(assigned)
    ):
        reasons.add("DENOMINATOR_CHANGED")
    strata: dict[str, list[int]] = {}
    for case_id in assigned:
        b, c = bases.get(case_id), candidates.get(case_id)
        if b is None or c is None:
            continue
        if not _id(b.stratum) or b.stratum != c.stratum:
            reasons.add("STRATUM_MISMATCH")
        counts = strata.setdefault(b.stratum, [0, 0, 0])
        counts[0] += 1
        counts[1] += b.status in ACCEPTED and not b.safety_incident
        counts[2] += c.status in ACCEPTED and not c.safety_incident
        if b.safety_incident is False and c.safety_incident:
            reasons.add("SAFETY_REGRESSION")
        if c.unknown_effect or b.unknown_effect or c.status in ADVERSE or b.status in ADVERSE:
            reasons.add("UNKNOWN_OR_ADVERSE_EFFECT")
        if not b.rights_current or not c.rights_current:
            reasons.add("REVOKED_SOURCE")
        if b.cost_micros is None or c.cost_micros is None:
            reasons.add("UNKNOWN_COST")
        if (
            b.cost_micros is not None
            and b.cost_micros < 0
            or c.cost_micros is not None
            and c.cost_micros < 0
            or b.attempts < 1
            or c.attempts < 1
        ):
            reasons.add("INVALID_COST_OR_ATTEMPTS")
        if b.status not in ACCEPTED | {
            "FAILED",
            "ABSTAIN",
            "PARTIAL",
            "UNKNOWN",
            "TIMEOUT",
            "REJECTED",
        } or c.status not in ACCEPTED | {
            "FAILED",
            "ABSTAIN",
            "PARTIAL",
            "UNKNOWN",
            "TIMEOUT",
            "REJECTED",
        }:
            reasons.add("INVALID_CASE_STATUS")
    if isinstance(seams.t09, StreamVerdict) and seams.t09.product_ttft not in {
        "UNVERIFIED",
        "PRODUCT_TTFT_UNVERIFIED",
        "FIXTURE_ONLY",
    }:
        reasons.add("PRODUCT_TTFT_SPOOF")
    if isinstance(seams.p09, Admission) and seams.p09.accepted_outcome:
        reasons.add("EXTERNAL_COST_AUTHORITY_SPOOF")
    if isinstance(seams.e09h, DenominatorLedger) and seams.e09h.release_certification not in {
        "NOT_CERTIFIED",
        "BLOCKED",
        "NO",
    }:
        reasons.add("RELEASE_SPOOF")

    def cost(items: tuple[OfflineCase, ...]) -> int | None:
        return (
            sum(x.cost_micros for x in items if x.cost_micros is not None)
            if all(x.cost_micros is not None for x in items)
            else None
        )

    return Comparison(
        "LOCAL_FIXTURE_REVIEW" if not reasons else "INELIGIBLE",
        tuple(sorted(reasons)),
        len(assigned),
        sum(x.status in ACCEPTED and not x.safety_incident for x in cohort.baseline),
        sum(x.status in ACCEPTED and not x.safety_incident for x in cohort.candidate),
        cost(cohort.baseline),
        cost(cohort.candidate),
        tuple((k, *v) for k, v in sorted(strata.items())),
        False,
    )


class AR10CandidateGovernanceV1:
    """Durable local intent-only CAS journal. No capability to mutate real state."""

    def __init__(self, db_path: str | Path) -> None:
        path = Path(db_path)
        if not path.parent.is_dir() or path.is_symlink():
            raise Denied("DISPOSABLE_LOCAL_DB_REQUIRED")
        self.db = sqlite3.connect(str(path), timeout=5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS proposals(
                id TEXT PRIMARY KEY, tenant TEXT NOT NULL, run TEXT NOT NULL,
                subject TEXT NOT NULL, source TEXT NOT NULL, purpose TEXT NOT NULL,
                proposal TEXT NOT NULL, state TEXT NOT NULL, version INTEGER NOT NULL,
                lease_owner TEXT NOT NULL DEFAULT '', lease_epoch INTEGER NOT NULL DEFAULT 0,
                lease_until INTEGER NOT NULL DEFAULT 0,
                UNIQUE(tenant, run)
            );
            CREATE TABLE IF NOT EXISTS fences(
                tenant TEXT NOT NULL, purpose TEXT NOT NULL, source TEXT NOT NULL,
                subject TEXT NOT NULL, revision TEXT NOT NULL,
                consent_generation INTEGER NOT NULL, exclusion_generation INTEGER NOT NULL,
                tombstone_generation INTEGER NOT NULL, revoked INTEGER NOT NULL,
                PRIMARY KEY(tenant,purpose,source,subject)
            );
            CREATE TABLE IF NOT EXISTS journal(
                seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL,
                request_id TEXT NOT NULL UNIQUE, version INTEGER NOT NULL,
                event TEXT NOT NULL, reason TEXT NOT NULL,
                previous TEXT NOT NULL, head TEXT NOT NULL
            );
        """)
        self._assert_chain()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> AR10CandidateGovernanceV1:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _assert_chain(self) -> None:
        previous = "0" * 64
        for row in self.db.execute("SELECT * FROM journal ORDER BY seq"):
            expected = digest(
                [
                    previous,
                    row["seq"],
                    row["id"],
                    row["request_id"],
                    row["version"],
                    row["event"],
                    row["reason"],
                ]
            )
            if row["previous"] != previous or row["head"] != expected:
                raise Denied("JOURNAL_TAMPER")
            previous = expected

    def _append(self, ident: str, key: str, version: int, event: str, reason: str) -> str:
        last = self.db.execute("SELECT head FROM journal ORDER BY seq DESC LIMIT 1").fetchone()
        previous = last["head"] if last else "0" * 64
        cur = self.db.execute(
            "INSERT INTO journal(id,request_id,version,event,reason,previous,head)"
            " VALUES(?,?,?,?,?,?,?)",
            (ident, key, version, event, reason, previous, ""),
        )
        head = digest([previous, cur.lastrowid, ident, key, version, event, reason])
        self.db.execute("UPDATE journal SET head=? WHERE seq=?", (head, cur.lastrowid))
        return head

    def _decision(self, ident: str, reason: str = "OK") -> Decision:
        row = self.db.execute("SELECT state,version FROM proposals WHERE id=?", (ident,)).fetchone()
        head = self.db.execute(
            "SELECT head FROM journal WHERE id=? ORDER BY seq DESC LIMIT 1", (ident,)
        ).fetchone()
        if row is None or head is None:
            raise Denied("UNKNOWN_PROPOSAL")
        return Decision(row["state"], reason, row["version"], head["head"])

    def _begin(self) -> None:
        self.db.execute("BEGIN IMMEDIATE")

    def _existing(self, key: str) -> bool:
        return (
            self.db.execute("SELECT 1 FROM journal WHERE request_id=?", (key,)).fetchone()
            is not None
        )

    def _fence(self, p: ImprovementProposal, r: RightsSnapshot) -> str:
        row = self.db.execute(
            "SELECT * FROM fences WHERE tenant=? AND purpose=? AND source=? AND subject=?",
            (p.tenant_id, p.purpose, p.origin_source_id, p.origin_subject_id),
        ).fetchone()
        if row is None:
            self.db.execute(
                "INSERT INTO fences VALUES(?,?,?,?,?,?,?, ?,?)",
                (
                    r.tenant_id,
                    r.purpose,
                    r.source_id,
                    r.subject_id,
                    r.revision,
                    r.consent_generation,
                    r.exclusion_generation,
                    r.tombstone_generation,
                    int(r.source_revoked or not r.consent_active),
                ),
            )
            return "OK"
        if row["revoked"]:
            return "PERSISTED_REVOCATION"
        if row["revision"] != r.revision:
            return "PERSISTED_REVISION"
        for field in ("consent_generation", "exclusion_generation", "tombstone_generation"):
            if row[field] != getattr(r, field):
                return "PERSISTED_GENERATION"
        return "OK"

    def _ancestor_error(self, p: ImprovementProposal, now: int) -> str:
        parent_id = p.derivative_of
        seen = {p.proposal_id}
        while parent_id:
            if parent_id in seen:
                return "DERIVATIVE_CYCLE"
            seen.add(parent_id)
            row = self.db.execute(
                "SELECT tenant,proposal,state FROM proposals WHERE id=?", (parent_id,)
            ).fetchone()
            if row is None:
                return "DERIVATIVE_PARENT_UNKNOWN"
            if row["tenant"] != p.tenant_id:
                return "DERIVATIVE_CROSS_TENANT"
            parent = ImprovementProposal(**json.loads(row["proposal"]))
            if row["state"] in TERMINAL:
                return "DERIVATIVE_PARENT_BLOCKED"
            if min(parent.expires_ms, parent.retention_until_ms) <= now:
                return "DERIVATIVE_PARENT_EXPIRED"
            parent_id = parent.derivative_of
        return "OK"

    def _fresh(self, p: ImprovementProposal, rights: RightsSnapshot, now: int) -> str:
        return next(
            (
                code
                for code in (
                    _validate_proposal(p, now),
                    _rights_error(p, rights, now),
                    self._ancestor_error(p, now),
                    self._fence(p, rights),
                )
                if code != "OK"
            ),
            "OK",
        )

    def register(
        self, p: ImprovementProposal, rights: RightsSnapshot, now_ms: int, request_id: str
    ) -> Decision:
        if not _id(request_id):
            raise Denied("BAD_REQUEST")
        self._begin()
        try:
            if self._existing(request_id):
                row = self.db.execute(
                    "SELECT id FROM journal WHERE request_id=?", (request_id,)
                ).fetchone()
                if row["id"] != p.proposal_id:
                    raise Denied("REPLAY_CROSS_PROPOSAL")
                answer = self._decision(p.proposal_id, "IDEMPOTENT")
            else:
                reason = self._fresh(p, rights, now_ms)
                state = (
                    "DRAFT"
                    if reason == "OK"
                    else (
                        "EXPIRED"
                        if reason == "EXPIRED"
                        else "QUARANTINED"
                        if reason
                        in {
                            "TAINT",
                            "PERSISTED_REVOCATION",
                            "SOURCE_REVOKED",
                            "PERSISTED_REVISION",
                            "REVISION_CHANGED",
                            "PERSISTED_GENERATION",
                            "GENERATION_CHANGED",
                            "DERIVATIVE_PARENT_BLOCKED",
                            "DERIVATIVE_PARENT_EXPIRED",
                        }
                        else "REJECTED"
                    )
                )
                self.db.execute(
                    "INSERT INTO proposals("
                    "id,tenant,run,subject,source,purpose,proposal,state,version)"
                    " VALUES(?,?,?,?,?,?,?,?,0)",
                    (
                        p.proposal_id,
                        p.tenant_id,
                        p.origin_run_id,
                        p.origin_subject_id,
                        p.origin_source_id,
                        p.purpose,
                        json.dumps(asdict(p)),
                        state,
                    ),
                )
                self._append(p.proposal_id, request_id, 0, state, reason)
                answer = self._decision(p.proposal_id, reason)
            self.db.execute("COMMIT")
            return answer
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def lease(
        self, proposal_id: str, owner: str, expected_version: int, now_ms: int, until_ms: int
    ) -> Lease:
        if not _id(owner) or until_ms <= now_ms or until_ms - now_ms > 60_000:
            raise Denied("BAD_LEASE")
        self._begin()
        try:
            row = self.db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
            if row is None or row["version"] != expected_version:
                raise Denied("STALE_CAS")
            if row["lease_until"] > now_ms and row["lease_owner"] != owner:
                raise Denied("LEASE_HELD")
            epoch = row["lease_epoch"] + 1
            self.db.execute(
                "UPDATE proposals SET lease_owner=?,lease_epoch=?,lease_until=? WHERE id=?",
                (owner, epoch, until_ms, proposal_id),
            )
            self.db.execute("COMMIT")
            return Lease(proposal_id, owner, epoch, until_ms, expected_version)
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def advance(
        self,
        proposal_id: str,
        lease: Lease,
        rights: RightsSnapshot,
        now_ms: int,
        request_id: str,
        target: str,
        comparison: Comparison | None = None,
        reviewer_id: str = "",
    ) -> Decision:
        if not _id(request_id):
            raise Denied("BAD_REQUEST")
        self._begin()
        try:
            if self._existing(request_id):
                existing = self.db.execute(
                    "SELECT id FROM journal WHERE request_id=?", (request_id,)
                ).fetchone()
                if existing["id"] != proposal_id:
                    raise Denied("REPLAY_CROSS_PROPOSAL")
                answer = self._decision(proposal_id, "IDEMPOTENT")
            else:
                row = self.db.execute(
                    "SELECT * FROM proposals WHERE id=?", (proposal_id,)
                ).fetchone()
                if row is None:
                    raise Denied("UNKNOWN_PROPOSAL")
                if (
                    lease.proposal_id != proposal_id
                    or lease.version != row["version"]
                    or lease.epoch != row["lease_epoch"]
                    or lease.owner != row["lease_owner"]
                    or lease.until_ms != row["lease_until"]
                    or lease.until_ms <= now_ms
                ):
                    raise Denied("STALE_CAS_OR_LEASE")
                p = ImprovementProposal(**json.loads(row["proposal"]))
                reason = self._fresh(p, rights, now_ms)
                if row["state"] in TERMINAL:
                    target_state, why = row["state"], "TERMINAL_IMMUTABLE"
                elif reason != "OK":
                    target_state, why = (
                        "EXPIRED" if reason == "EXPIRED" else "QUARANTINED",
                        reason,
                    )
                elif target in LATER or target not in {"ELIGIBILITY_REVIEW", "OFFLINE_REVIEW"}:
                    target_state, why = row["state"], "G09_EXTERNAL_BLOCKED"
                elif target == "ELIGIBILITY_REVIEW" and row["state"] == "DRAFT":
                    target_state, why = target, "LOCAL_ELIGIBLE_ONLY"
                elif target == "OFFLINE_REVIEW" and row["state"] == "ELIGIBILITY_REVIEW":
                    if reviewer_id != p.reviewer_id or reviewer_id == p.principal_id:
                        target_state, why = row["state"], "INDEPENDENT_REVIEWER_MISSING"
                    elif comparison is None or comparison.status != "LOCAL_FIXTURE_REVIEW":
                        target_state, why = row["state"], "MATCHED_FIXTURE_NOT_ADMITTED"
                    elif comparison.promotion_eligible:
                        target_state, why = row["state"], "FORGED_PROMOTION"
                    else:
                        target_state, why = target, "LOCAL_OFFLINE_REVIEW_ONLY"
                else:
                    target_state, why = row["state"], "INVALID_TRANSITION"
                version = row["version"] + 1
                self.db.execute(
                    "UPDATE proposals SET state=?,version=? WHERE id=?",
                    (target_state, version, proposal_id),
                )
                self._append(proposal_id, request_id, version, target_state, why)
                answer = self._decision(proposal_id, why)
            self.db.execute("COMMIT")
            return answer
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def record_fence(self, rights: RightsSnapshot, request_id: str, *, incident: str) -> int:
        """Monotonic local revocation/revision/tombstone; descendants auto-quarantine."""
        if incident not in {"REVOCATION", "LEAK", "TAINT", "UNKNOWN_EFFECT", "SOURCE_REVISION"}:
            raise Denied("BAD_INCIDENT")
        if not rights.fixture_only or not _id(request_id):
            raise Denied("EXTERNAL_RIGHTS_NOT_ADMITTED")
        self._begin()
        try:
            if self._existing(request_id):
                self.db.execute("COMMIT")
                return 0
            old = self.db.execute(
                "SELECT * FROM fences WHERE tenant=? AND purpose=? AND source=? AND subject=?",
                (rights.tenant_id, rights.purpose, rights.source_id, rights.subject_id),
            ).fetchone()
            if old is None:
                raise Denied("UNKNOWN_SOURCE")
            for field in ("consent_generation", "exclusion_generation", "tombstone_generation"):
                if getattr(rights, field) < old[field]:
                    raise Denied("GENERATION_ROLLBACK")
            if not (
                rights.revision != old["revision"]
                or rights.source_revoked
                or not rights.consent_active
                or incident in {"LEAK", "TAINT", "UNKNOWN_EFFECT"}
                or any(
                    getattr(rights, f) > old[f]
                    for f in ("consent_generation", "exclusion_generation", "tombstone_generation")
                )
            ):
                raise Denied("NO_FENCE_CHANGE")
            self.db.execute(
                "UPDATE fences SET revision=?,consent_generation=?,exclusion_generation=?,"
                "tombstone_generation=?,revoked=1 WHERE tenant=? AND purpose=?"
                " AND source=? AND subject=?",
                (
                    rights.revision,
                    rights.consent_generation,
                    rights.exclusion_generation,
                    rights.tombstone_generation,
                    rights.tenant_id,
                    rights.purpose,
                    rights.source_id,
                    rights.subject_id,
                ),
            )
            # Descendant closure is tenant-scoped, even when synthetic derivative
            # metadata points to a different local source, subject or purpose.
            rows = self.db.execute(
                "SELECT * FROM proposals WHERE tenant=?", (rights.tenant_id,)
            ).fetchall()
            marked = {
                row["id"]
                for row in rows
                if (row["purpose"], row["source"], row["subject"])
                == (rights.purpose, rights.source_id, rights.subject_id)
            }
            expanded = True
            while expanded:
                expanded = False
                for row in rows:
                    if row["id"] not in marked and (
                        json.loads(row["proposal"])["derivative_of"] in marked
                    ):
                        marked.add(row["id"])
                        expanded = True
            affected = 0
            for row in rows:
                if row["id"] in marked and row["state"] != "QUARANTINED":
                    affected += 1
                    next_version = row["version"] + 1
                    self.db.execute(
                        "UPDATE proposals SET state='QUARANTINED',version=? WHERE id=?",
                        (next_version, row["id"]),
                    )
                    self._append(
                        row["id"],
                        request_id + ":" + row["id"],
                        next_version,
                        "QUARANTINED",
                        incident,
                    )
            self._append(
                "fence:" + rights.tenant_id + ":" + rights.source_id,
                request_id,
                0,
                "FENCE",
                incident,
            )
            self.db.execute("COMMIT")
            return affected
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def rollback_local(self, proposal_id: str, lease: Lease, now_ms: int, key: str) -> Decision:
        """Never rolls back/points a live runtime; only marks local review status."""
        self._begin()
        try:
            if self._existing(key):
                answer = self._decision(proposal_id, "IDEMPOTENT")
            else:
                row = self.db.execute(
                    "SELECT * FROM proposals WHERE id=?", (proposal_id,)
                ).fetchone()
                if (
                    row is None
                    or row["state"] != "OFFLINE_REVIEW"
                    or lease.proposal_id != proposal_id
                    or lease.owner != row["lease_owner"]
                    or lease.epoch != row["lease_epoch"]
                    or lease.version != row["version"]
                    or now_ms >= row["lease_until"]
                ):
                    raise Denied("UNSIGNED_OR_STALE_ROLLBACK")
                version = row["version"] + 1
                self.db.execute(
                    "UPDATE proposals SET state='ELIGIBILITY_REVIEW',version=? WHERE id=?",
                    (version, proposal_id),
                )
                self._append(proposal_id, key, version, "ELIGIBILITY_REVIEW", "LOCAL_STATUS_ONLY")
                answer = self._decision(proposal_id, "LOCAL_STATUS_ONLY")
            self.db.execute("COMMIT")
            return answer
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def inspect(self, proposal_id: str) -> Decision:
        self._assert_chain()
        return self._decision(proposal_id)

    def journal_rows(self) -> tuple[tuple[object, ...], ...]:
        self._assert_chain()
        return tuple(tuple(row) for row in self.db.execute("SELECT * FROM journal ORDER BY seq"))
