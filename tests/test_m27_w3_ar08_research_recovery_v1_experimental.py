"""Real local SQLite restart, cross-connection, provenance and fault cases for S08R."""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import replace

import pytest

from knowledge_engine.m27_ar02_durable_writer_v1_experimental import (
    DurableWriterV1,
    RunIdentity,
)
from knowledge_engine.m27_w3_ar08_research_recovery_v1_experimental import (
    PASS,
    ResearchDenied,
    ResearchPlan,
    ResearchRecoveryV1,
    ReviewReceipt,
    SourcePin,
)

IDENT = RunIdentity("tenant-a", "run-a", "research-a", 1, "research-actor")
SUPPORT = b"Offline snapshot: hypothesis may hold.\n"
COUNTER = b"Offline snapshot: a competing explanation exists.\n"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def make_plan(**override):
    pins = (
        SourcePin("support-1", "rev-1", sha(SUPPORT), "tenant-a", 200, 1, 1,
                  ("research-actor",), ("scoped-research",), 0,
                  len(SUPPORT), "support", "h1"),
        SourcePin("counter-1", "rev-1", sha(COUNTER), "tenant-a", 200, 1, 1,
                  ("research-actor",), ("scoped-research",), 0,
                  len(COUNTER), "counter", "h1"),
    )
    plan = ResearchPlan(
        IDENT, "scoped-research", 1, sha(b"immutable research brief"), ("h1",),
        ("collect", "review", "draft"), pins, "research-budget-a", 15, 190,
    )
    return replace(plan, **override)


def review(pin, **override):
    return replace(ReviewReceipt(
        pin.source_id, pin.source_revision, pin.original_sha256,
        "independent-reviewer", 20, "ACCEPTED", "fixture-review:" + pin.source_id,
    ), **override)


@pytest.fixture
def case(tmp_path):
    file = tmp_path / "real_wal.sqlite"
    writer = DurableWriterV1(file)
    writer.create_run(
        IDENT, budget=100, source_revision="rev-1",
        consent_generation=1, exclusion_generation=1,
    )
    return writer, ResearchRecoveryV1(writer), make_plan(), file


def setup(case, *, checkpoint=True, reviewed=True):
    writer, research, plan, _ = case
    research.admit(plan, now=10)
    research.reserve_budget(plan, now=10)
    for pin, data in zip(plan.source_pins, (SUPPORT, COUNTER), strict=True):
        research.register_source(plan, source_id=pin.source_id,
                                 original_bytes=data, now=20)
        if reviewed:
            research.record_review(plan, review(pin), now=20)
    if checkpoint:
        for milestone in plan.milestones:
            research.checkpoint(plan, milestone=milestone,
                                cursor="after-" + milestone, now=21)
    return writer, research, plan


def test_complete_positive_two_connections_restart_and_real_bytes(case):
    writer, research, plan = setup(case)
    old_head = writer.read_head(IDENT)
    head, digest = research.propose_artifact(plan, now=25, quoted_cost=15)
    assert head.seq == old_head.seq + 1
    assert digest == sha(research.read_artifact(plan))
    assert b"competing explanation" in research.read_artifact(plan)
    assert b"Hypothesis" not in research.read_artifact(plan)
    assert PASS == "RESEARCH_LOCAL_RECOVERY_PASS"
    assert research.resume(plan, now=26)["checkpoint_count"] == 3
    restarted = ResearchRecoveryV1(DurableWriterV1(case[3]))
    assert restarted.read_artifact(plan) == research.read_artifact(plan)
    assert restarted.resume(plan, now=26)["cursor"] == "after-draft"
    assert restarted.reserve_budget(plan, now=26) == head
    with sqlite3.connect(case[3]) as db:
        assert db.execute("SELECT COUNT(*) FROM reservations").fetchone()[0] == 1
        assert db.execute("SELECT original FROM research_artifacts").fetchone()[0] == (
            research.read_artifact(plan)
        )
        assert db.execute(
            "SELECT COUNT(*) FROM events WHERE kind='RESEARCH_CHECKPOINT'"
        ).fetchone()[0] == 3
    with pytest.raises(ResearchDenied, match="ARTIFACT_SUPERSESSION"):
        restarted.propose_artifact(plan, now=26, quoted_cost=15)


@pytest.mark.parametrize("override,code", [
    ({"plan_version": 0}, "PLAN_VERSION"),
    ({"plan_version": 2}, "PLAN_VERSION"),
    ({"purpose_id": ""}, "PLAN_VERSION"),
    ({"brief_sha256": "0"}, "PLAN_VERSION"),
    ({"reserve_id": ""}, "BUDGET"),
    ({"reserved_microunits": 0}, "BUDGET"),
    ({"reserved_microunits": -1}, "BUDGET"),
    ({"deadline_at": 0}, "BUDGET"),
    ({"hypotheses": ()}, "HYPOTHESIS"),
    ({"hypotheses": ("h1", "h1")}, "HYPOTHESIS"),
    ({"milestones": ()}, "MILESTONES"),
    ({"milestones": ("a", "a")}, "MILESTONES"),
    ({"source_pins": ()}, "SOURCES"),
])
def test_negative_admission_bad_schema(case, override, code):
    _, research, plan, _ = case
    with pytest.raises(ResearchDenied, match=code):
        research.admit(replace(plan, **override), now=10)


@pytest.mark.parametrize("pin_change,code", [
    ({"tenant_id": "tenant-b"}, "TENANT"),
    ({"source_revision": ""}, "REVISION"),
    ({"original_sha256": "fake"}, "REVISION"),
    ({"source_id": ""}, "REVISION"),
    ({"quote_start": -1}, "CITATION"),
    ({"quote_end": 0}, "CITATION"),
    ({"kind": "invented"}, "CITATION"),
    ({"hypothesis_id": "other"}, "CITATION"),
    ({"valid_until": 0}, "CITATION"),
])
def test_negative_source_pin_validation(case, pin_change, code):
    _, research, plan, _ = case
    pin = replace(plan.source_pins[0], **pin_change)
    with pytest.raises(ResearchDenied, match=code):
        research.admit(replace(plan, source_pins=(pin, plan.source_pins[1])),
                       now=10)


@pytest.mark.parametrize("modify,code", [
    ("duplicate", "SOURCES"),
    ("no-counter", "COUNTEREVIDENCE"),
    ("no-support", "SUPPORT"),
])
def test_negative_evidence_checklist(case, modify, code):
    _, research, plan, _ = case
    sources = {
        "duplicate": (plan.source_pins[0], plan.source_pins[0]),
        "no-counter": (plan.source_pins[0],),
        "no-support": (plan.source_pins[1],),
    }[modify]
    with pytest.raises(ResearchDenied, match=code):
        research.admit(replace(plan, source_pins=sources), now=10)


@pytest.mark.parametrize("kind", [
    "wrong-bytes", "fake-source", "nonbytes", "bad-span",
])
def test_negative_source_material_is_not_model_evidence(case, kind):
    _, research, plan, _ = case
    if kind == "bad-span":
        p = replace(plan.source_pins[0], quote_end=len(SUPPORT) + 10)
        plan = replace(plan, source_pins=(p, plan.source_pins[1]))
    research.admit(plan, now=10)
    kwargs = {
        "source_id": "support-1", "original_bytes": SUPPORT, "now": 10,
    }
    if kind == "wrong-bytes":
        kwargs["original_bytes"] = b"model claims source says so"
    elif kind == "fake-source":
        kwargs["source_id"] = "model-only-reference"
    elif kind == "nonbytes":
        kwargs["original_bytes"] = "literal hallucination"
    with pytest.raises(ResearchDenied):
        research.register_source(plan, **kwargs)


@pytest.mark.parametrize("changes,code", [
    ({"reviewer_id": "research-actor"}, "INDEPENDENT_REVIEW"),
    ({"reviewer_id": ""}, "INDEPENDENT_REVIEW"),
    ({"review_ref": ""}, "INDEPENDENT_REVIEW"),
    ({"verdict": "REJECTED"}, "INDEPENDENT_REVIEW"),
    ({"reviewed_at": 99}, "INDEPENDENT_REVIEW"),
    ({"source_revision": "rev-old"}, "DISAGREEMENT"),
    ({"original_sha256": "0" * 64}, "DISAGREEMENT"),
    ({"source_id": "fake"}, "DISAGREEMENT"),
])
def test_negative_review_receipts(case, changes, code):
    _, research, plan, _ = case
    research.admit(plan, now=10)
    research.register_source(plan, source_id="support-1",
                             original_bytes=SUPPORT, now=10)
    with pytest.raises(ResearchDenied, match=code):
        research.record_review(plan, review(plan.source_pins[0], **changes),
                               now=20)


def test_missing_counterevidence_review_blocks_proposal(case):
    _, research, plan = setup(case, reviewed=False)
    research.record_review(plan, review(plan.source_pins[0]), now=20)
    with pytest.raises(ResearchDenied, match="SOURCE_OR_COUNTEREVIDENCE_MISSING"):
        research.propose_artifact(plan, now=25, quoted_cost=15)


@pytest.mark.parametrize("scenario", [
    "wrong-cost", "missing-reservation", "missing-checkpoint", "wrong-milestone",
    "cursor-empty", "cursor-conflict", "cursor-out-of-order",
])
def test_negative_checkpoint_and_cost(case, scenario):
    _, research, plan, _ = case
    research.admit(plan, now=10)
    if scenario != "missing-reservation":
        research.reserve_budget(plan, now=10)
    if scenario == "wrong-cost":
        for milestone in plan.milestones:
            research.checkpoint(plan, milestone=milestone,
                                cursor=milestone, now=11)
        with pytest.raises(ResearchDenied, match="COST"):
            research.propose_artifact(plan, now=15, quoted_cost=13)
    elif scenario in {"missing-reservation", "missing-checkpoint"}:
        with pytest.raises(ResearchDenied, match="MILESTONES"):
            research.propose_artifact(plan, now=15, quoted_cost=15)
    else:
        if scenario == "wrong-milestone":
            call = {"milestone": "draft", "cursor": "x"}
        elif scenario == "cursor-empty":
            call = {"milestone": "collect", "cursor": ""}
        else:
            research.checkpoint(plan, milestone="collect", cursor="cursor-1",
                                now=11)
            if scenario == "cursor-conflict":
                call = {"milestone": "collect", "cursor": "different"}
            else:
                call = {"milestone": "draft", "cursor": "cursor-3"}
        with pytest.raises(ResearchDenied):
            research.checkpoint(plan, **call, now=12)


def test_identical_checkpoint_idempotence_and_stale_replay(case):
    _, research, plan, _ = case
    research.admit(plan, now=10)
    head, digest = research.checkpoint(
        plan, milestone="collect", cursor="once", now=12,
    )
    head2, digest2 = research.checkpoint(
        plan, milestone="collect", cursor="once", now=13,
    )
    assert (head, digest) == (head2, digest2)
    with pytest.raises(ResearchDenied, match="IMMUTABLE_PLAN_MISMATCH"):
        research.resume(replace(plan, purpose_id="other-purpose"), now=14)


@pytest.mark.parametrize("change", [
    {"valid_until": 10},
    {"consent_generation": 2},
    {"exclusion_generation": 2},
    {"acl_principals": ("someone-else",)},
    {"purposes": ("wrong-purpose",)},
    {"tainted": True},
])
def test_negative_acl_consent_and_taint(case, change):
    _, research, plan, _ = case
    pin = replace(plan.source_pins[0], **change)
    altered = replace(plan, source_pins=(pin, plan.source_pins[1]))
    if "valid_until" in change:
        research.admit(altered, now=5)
        with pytest.raises(ResearchDenied, match="SOURCE_EXPIRED_ACL_CONSENT_OR_TAINT"):
            research.resume(altered, now=12)
    else:
        with pytest.raises(ResearchDenied, match="SOURCE_EXPIRED_ACL_CONSENT_OR_TAINT"):
            research.admit(altered, now=5)


@pytest.mark.parametrize("mutation", [
    {"source_revision": "rev-2"},
    {"consent_generation": 2},
    {"exclusion_generation": 2},
    {"revoked": True},
])
def test_negative_authority_drift_after_checkpoint(case, mutation):
    writer, research, plan = setup(case)
    head = writer.read_head(IDENT)
    writer.update_authority(
        IDENT, head, **({"source_revision": "rev-1",
                        "consent_generation": 1, "exclusion_generation": 1,
                        "revoked": False} | mutation),
    )
    with pytest.raises(ResearchDenied):
        research.propose_artifact(plan, now=25, quoted_cost=15)


def test_deadline_and_plan_identity_and_budget(case):
    _, research, plan, _ = case
    research.admit(plan, now=10)
    with pytest.raises(ResearchDenied, match="RESEARCH_DEADLINE"):
        research.resume(plan, now=plan.deadline_at)
    with pytest.raises(ResearchDenied, match="IMMUTABLE_PLAN_MISMATCH"):
        research.admit(replace(plan, reserve_id="a-new-reserve"), now=11)
    with pytest.raises(ResearchDenied, match="IMMUTABLE_PLAN_MISMATCH"):
        research.resume(replace(plan, identity=replace(IDENT, principal_id="attacker")),
                        now=11)


def test_at_most_once_claim_no_remote_dispatch_and_unknown_fence(case):
    _, research, plan = setup(case)
    research.claim_job(plan, job_id="one", intent_sha=sha(b"bounded job"), now=22)
    again = ResearchRecoveryV1(DurableWriterV1(case[3]))
    with pytest.raises(ResearchDenied, match="UNKNOWN_REMOTE_EFFECT"):
        again.resume(plan, now=23)
    with pytest.raises(ResearchDenied):
        again.claim_job(plan, job_id="one", intent_sha=sha(b"bounded job"), now=23)
    with pytest.raises(ResearchDenied):
        again.propose_artifact(plan, now=23, quoted_cost=15)
    with sqlite3.connect(case[3]) as db:
        assert db.execute("SELECT COUNT(*) FROM research_jobs").fetchone()[0] == 1


@pytest.mark.parametrize("stage", [
    "after_plan_insert", "after_source_insert",
    "after_journal_before_checkpoint", "after_checkpoint_before_commit",
    "after_writer_reserve_committed", "after_artifact_journal_before_blob",
    "after_artifact_insert_before_commit", "after_unknown_marker_before_commit",
])
def test_fault_injection_atomicity_and_recovery(tmp_path, stage):
    path = tmp_path / "fault-wal.sqlite"
    writer = DurableWriterV1(path)
    writer.create_run(
        IDENT, budget=100, source_revision="rev-1",
        consent_generation=1, exclusion_generation=1,
    )
    plan = make_plan()

    def crash(where):
        if where == stage:
            raise RuntimeError("SIMULATED_CRASH_" + where)

    test = ResearchRecoveryV1(writer, fault=crash)
    if stage == "after_plan_insert":
        with pytest.raises(RuntimeError, match="SIMULATED_CRASH"):
            test.admit(plan, now=10)
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT COUNT(*) FROM research_plans").fetchone()[0] == 0
        ResearchRecoveryV1(writer).admit(plan, now=10)
    else:
        test.admit(plan, now=10)
        if stage == "after_writer_reserve_committed":
            with pytest.raises(RuntimeError, match="SIMULATED_CRASH"):
                test.reserve_budget(plan, now=10)
            recovered = ResearchRecoveryV1(DurableWriterV1(path))
            recovered.reserve_budget(plan, now=11)
            with sqlite3.connect(path) as db:
                assert db.execute("SELECT COUNT(*) FROM reservations").fetchone()[0] == 1
            return
        test.reserve_budget(plan, now=10)
        if stage == "after_source_insert":
            with pytest.raises(RuntimeError, match="SIMULATED_CRASH"):
                test.register_source(plan, source_id="support-1",
                                     original_bytes=SUPPORT, now=15)
            with sqlite3.connect(path) as db:
                assert db.execute("SELECT COUNT(*) FROM research_sources").fetchone()[0] == 0
            ResearchRecoveryV1(writer).register_source(
                plan, source_id="support-1", original_bytes=SUPPORT, now=15,
            )
            return
        if stage.startswith("after_") and "checkpoint" in stage or stage == (
            "after_journal_before_checkpoint"
        ):
            before = writer.read_head(IDENT)
            with pytest.raises(RuntimeError, match="SIMULATED_CRASH"):
                test.checkpoint(plan, milestone="collect", cursor="first", now=15)
            assert writer.read_head(IDENT) == before
            ResearchRecoveryV1(writer).checkpoint(
                plan, milestone="collect", cursor="first", now=15,
            )
            return
        if stage == "after_unknown_marker_before_commit":
            with pytest.raises(RuntimeError, match="SIMULATED_CRASH"):
                test.claim_job(plan, job_id="j", intent_sha=sha(b"j"), now=15)
            with sqlite3.connect(path) as db:
                assert db.execute("SELECT COUNT(*) FROM research_jobs").fetchone()[0] == 0
            return
        safe = ResearchRecoveryV1(writer)
        for pin, data in zip(plan.source_pins, (SUPPORT, COUNTER), strict=True):
            safe.register_source(plan, source_id=pin.source_id,
                                 original_bytes=data, now=15)
            safe.record_review(plan, review(pin), now=20)
        for milestone in plan.milestones:
            safe.checkpoint(plan, milestone=milestone, cursor=milestone, now=20)
        before = writer.read_head(IDENT)
        with pytest.raises(RuntimeError, match="SIMULATED_CRASH"):
            test.propose_artifact(plan, now=25, quoted_cost=15)
        assert writer.read_head(IDENT) == before
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT COUNT(*) FROM research_artifacts").fetchone()[0] == 0
        assert ResearchRecoveryV1(writer).propose_artifact(
            plan, now=25, quoted_cost=15,
        )[1] == sha(ResearchRecoveryV1(writer).read_artifact(plan))


@pytest.mark.parametrize("target", ["checkpoint_digest", "checkpoint_cursor",
                                    "artifact_blob", "artifact_sha"])
def test_corruption_fail_closed(case, target):
    _, research, plan = setup(case)
    if target.startswith("artifact"):
        research.propose_artifact(plan, now=25, quoted_cost=15)
    with sqlite3.connect(case[3]) as db:
        if target == "checkpoint_digest":
            db.execute("UPDATE research_checkpoints SET digest='tampered' WHERE ordinal=2")
        elif target == "checkpoint_cursor":
            db.execute("UPDATE research_checkpoints SET cursor='tampered' WHERE ordinal=2")
        elif target == "artifact_blob":
            db.execute("UPDATE research_artifacts SET original=?",
                       (b"fake research",))
        else:
            db.execute("UPDATE research_artifacts SET artifact_sha='fake'")
    with pytest.raises(ResearchDenied):
        if target.startswith("artifact"):
            research.read_artifact(plan)
        else:
            research.resume(plan, now=26)


def test_postterminal_supersession_is_fenced_without_reopening(case):
    writer, research, plan = setup(case)
    research.propose_artifact(plan, now=25, quoted_cost=15)
    frozen = research.read_artifact(plan)
    # Simulated terminal-state fault, not a forged K02D verifier signature.
    with writer._write() as db:
        db.execute("UPDATE runs SET state='LOCAL_VERIFIED_APPLIED'"
                   " WHERE tenant=? AND run=?", ("tenant-a", "run-a"))
    with pytest.raises(ResearchDenied, match="REVOKED_OR_TERMINAL"):
        research.propose_artifact(plan, now=26, quoted_cost=15)
    with pytest.raises(ResearchDenied, match="REVOKED_OR_TERMINAL"):
        research.checkpoint(plan, milestone="draft", cursor="late", now=26)
    assert research.read_artifact(plan) == frozen


def test_duplicate_checkpoint_across_two_independent_connections(case):
    writer, research, plan, path = case
    research.admit(plan, now=10)
    other = ResearchRecoveryV1(DurableWriterV1(path))
    first = research.checkpoint(plan, milestone="collect",
                                cursor="persistent", now=11)
    assert other.checkpoint(plan, milestone="collect",
                            cursor="persistent", now=11) == first
    assert writer.read_head(IDENT) == first[0]
    with pytest.raises(ResearchDenied, match="MILESTONE_OUT_OF_ORDER"):
        other.checkpoint(plan, milestone="collect",
                         cursor="another", now=12)
