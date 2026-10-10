"""Independent offline W4 E09H fixture tests; no I02 or external secrets."""

from dataclasses import replace

import pytest

from knowledge_engine.m27_w4_ar09_independent_harness_v1_experimental import (
    Artifact,
    Assignment,
    Candidate,
    Citation,
    Effect,
    Grade,
    IndependentOutcomeHarnessV1,
    Invoice,
    Permit,
    Recovery,
    ResearchProof,
    RunnerProof,
    Source,
    Stream,
    TrustContext,
    fixture_seal,
    sha,
)

ROLES = ("source", "verifier", "grader", "client", "reviewer", "runner",
         "permit", "observer", "billing", "recovery")
KEY = b"OFFLINE-ONLY-E09H-NEVER-A-REAL-SIGNER"
ROOTS = {
    (role, "fixture-" + role, "offline-" + role): KEY
    for role in ROLES
}
NOW = 1000


def sign(obj, role):
    return replace(
        obj,
        seal=fixture_seal(
            obj, role, "fixture-" + role, "offline-" + role, KEY,
        ),
    )


def context(**changes):
    return replace(TrustContext(ROOTS, now_ms=NOW), **changes)


def fixture(workload="QA", suffix="1"):
    case, task = workload + suffix, "task-" + workload + suffix
    a = Assignment(case, task, "tenant-a", 1, workload)
    src_content = b"Earth is round; other evidence was reviewed."
    source = sign(Source(
        "source-" + suffix, "tenant-a", "rev-1", src_content,
        sha(src_content), ("tenant-a",), True, False, 0, 2000,
    ), "source")
    art_bytes = b"Evidence says Earth is round. Confirmed by citation."
    citation = Citation(source.source_id, "rev-1", sha(src_content),
                        0, 14, b"Earth is round")
    artifact = sign(Artifact(task, "tenant-a", art_bytes, sha(art_bytes),
                             (citation,)), "verifier")
    grade = sign(Grade(task, sha(art_bytes), True, 95, True,
                       "offline-rubric"), "grader")
    stream = sign(Stream(
        task, sha(art_bytes), b"Evidence says", (source.source_id,),
        200, 250, 300, 900,
    ), "client")
    research = sign(ResearchProof(
        task, sha(art_bytes), sha(b"checkpoint"), True, 0,
        (source.source_id,),
    ), "reviewer")
    runner = sign(RunnerProof(
        task, sha(art_bytes), "external-fixture-runner", 0, 6, True,
    ), "runner")
    permit = sign(Permit(task, "tenant-a", "action-" + suffix, 0, 2000),
                  "permit")
    effect = sign(Effect(task, "action-" + suffix, True, False, "revision-2"),
                  "observer")
    bill = sign(Invoice(
        task, "attempt-" + case, "charge-" + case,
        2, 3, 10, 20, 80, True, 950,
    ), "billing")
    c = Candidate(
        case, task, "tenant-a", 1, workload, "executor-model", "ACCEPTED",
        ("attempt-" + case,), 200, 900,
        artifact=artifact, sources=(source,), grade=grade,
        stream=stream if workload == "QA" else None,
        research=research if workload == "RESEARCH" else None,
        runner=runner if workload == "CODING" else None,
        permit=permit if workload in ("CODING", "ACTION") else None,
        effect=effect if workload in ("CODING", "ACTION") else None,
        recovery=sign(Recovery(True, True, True, False, False, 1), "recovery"),
        invoices=(bill,),
    )
    return a, c


@pytest.mark.parametrize("workload", sorted(("QA", "RESEARCH", "CODING", "ACTION")))
def test_positive_signed_offline_only(workload):
    a, c = fixture(workload)
    output = IndependentOutcomeHarnessV1(context()).evaluate((a,), (c,))
    assert output.eligible == output.assigned == output.accepted == 1
    assert output.receipts[0].outcome == "ACCEPTED"
    assert output.receipts[0].verified
    assert output.cost_micros == 80
    assert output.cost_per_verified_outcome_micros == 80
    assert output.release_certification == "NOT_CERTIFIED"
    assert output.latency_authority == "SYNTHETIC_NOT_PRODUCT_P95"
    assert output.receipts[0].manifest is not None
    assert len(output.receipts[0].receipt_sha256) == 64
    if workload == "QA":
        assert output.qa_interactive_p95_ms == 100
        assert output.receipts[0].server_first_flush_ms == 50
    else:
        assert output.long_task_p95_ms == 700


# Every vector corrupts a different evidence or accounting assumption.
# Mutations are executed through the public evaluator, not just asserted labels.
NEGATIVE_VECTORS = (
    "wrong_case", "wrong_task", "wrong_tenant", "wrong_version",
    "wrong_workload", "executor_status_invalid", "model_claims_not_eligible",
    "holdout_contaminated", "time_reversed", "future_finish",
    "negative_start", "source_bytes_corrupt", "source_sha_corrupt",
    "source_acl_expired", "source_consent_revoked", "source_revoked",
    "source_wrong_tenant", "source_future_issued", "source_wrong_revision",
    "source_duplicate", "source_bad_signature", "source_self_signed",
    "source_signer_revoked", "artifact_bytes_corrupt", "artifact_sha_corrupt",
    "artifact_wrong_tenant", "artifact_unsigned", "artifact_self_signed",
    "artifact_missing", "fake_citation_quote", "citation_out_of_range",
    "citation_stale_revision", "citation_wrong_sha", "citation_no_source",
    "duplicate_citation", "grade_missing", "grade_model_self_score",
    "grade_wrong_digest", "grade_wrong_task", "grade_84",
    "grade_fact_wrong", "grade_grounding_false", "invalid_grade_signature",
    "stream_missing_ack", "stream_ack_after_terminal",
    "stream_flush_after_ack", "stream_missing_citations",
    "stream_wrong_payload", "stream_progress_only",
    "stream_wrong_signature", "stream_terminal_only",
    "missing_recovery", "checkpoint_lost", "duplicate_accounted",
    "unknown_effect", "replay_negative", "billing_delayed",
    "invoice_missing", "invoice_wrong_total", "invoice_unsigned",
    "invoice_wrong_task", "invoice_duplicate", "invoice_unknown_attempt",
    "invoice_bool_tokens", "invoice_negative_price", "attempt_duplicate",
    "research_counterevidence_missing", "research_unfinished",
    "research_checkpoint_missing", "research_sources_missing",
    "research_signature_invalid", "coding_fake_runner", "coding_tests_none",
    "coding_exit_nonzero", "coding_wrong_artifact", "coding_runner_unsigned",
    "permit_missing", "permit_expired", "permit_other_tenant",
    "effect_missing", "effect_unknown", "effect_no_observation",
    "effect_mismatch", "effect_signature_invalid",
    "claimed_partial", "claimed_abstain", "claimed_unknown",
    "claimed_rejected",
)


def damaged(vector):
    workload = (
        "RESEARCH" if vector.startswith("research_") else
        "CODING" if vector.startswith("coding_") else
        "ACTION" if vector.startswith(("permit_", "effect_")) else "QA"
    )
    a, c = fixture(workload)
    options = {}
    src = c.sources[0]
    art = c.artifact
    assert art is not None
    grade = c.grade
    assert grade is not None
    stream = c.stream
    bill = c.invoices[0]
    recovery = c.recovery
    assert recovery is not None
    if vector == "wrong_case":
        options["case_id"] = "other"
    elif vector == "wrong_task":
        options["task_id"] = "other"
    elif vector == "wrong_tenant":
        options["tenant_id"] = "tenant-b"
    elif vector == "wrong_version":
        options["version"] = 2
    elif vector == "wrong_workload":
        options["workload"] = "ACTION"
    elif vector == "executor_status_invalid":
        options["claimed_status"] = "SUCCESS_I_SAY_SO"
    elif vector == "model_claims_not_eligible":
        options["claimed_status"] = "NOT_ELIGIBLE"
    elif vector == "holdout_contaminated":
        options["dataset_provenance"] = "I02_WORKER_TEST_ANSWERS"
    elif vector == "time_reversed":
        options["started_ms"] = 901
    elif vector == "future_finish":
        options["finished_ms"] = 1100
    elif vector == "negative_start":
        options["started_ms"] = -1
    elif vector == "source_bytes_corrupt":
        src = replace(src, content=b"modified")
    elif vector == "source_sha_corrupt":
        src = replace(src, content_sha256="0" * 64)
    elif vector == "source_acl_expired":
        src = sign(replace(src, expires_ms=1000), "source")
    elif vector == "source_consent_revoked":
        src = sign(replace(src, consent=False), "source")
    elif vector == "source_revoked":
        src = sign(replace(src, revoked=True), "source")
    elif vector == "source_wrong_tenant":
        src = sign(replace(src, tenant_id="tenant-b"), "source")
    elif vector == "source_future_issued":
        src = sign(replace(src, issued_ms=500), "source")
    elif vector == "source_wrong_revision":
        src = sign(replace(src, revision="rev-2"), "source")
    elif vector == "source_duplicate":
        options["sources"] = (src, src)
    elif vector == "source_bad_signature":
        src = replace(src, seal=replace(src.seal, signature="0" * 64))
    elif vector == "source_self_signed":
        src = replace(src, seal=replace(src.seal, signer="executor-model"))
    elif vector == "source_signer_revoked":
        pass
    elif vector == "artifact_bytes_corrupt":
        art = replace(art, content=b"changed answer")
    elif vector == "artifact_sha_corrupt":
        art = replace(art, content_sha256="0" * 64)
    elif vector == "artifact_wrong_tenant":
        art = sign(replace(art, tenant_id="tenant-b"), "verifier")
    elif vector == "artifact_unsigned":
        art = replace(art, seal=None)
    elif vector == "artifact_self_signed":
        art = replace(art, seal=replace(art.seal, signer="executor-model"))
    elif vector == "artifact_missing":
        art = None
    elif vector in ("fake_citation_quote", "citation_out_of_range",
                    "citation_stale_revision", "citation_wrong_sha",
                    "citation_no_source", "duplicate_citation"):
        cite = art.citations[0]
        if vector == "fake_citation_quote":
            cite = replace(cite, quoted=b"unrelated string")
        elif vector == "citation_out_of_range":
            cite = replace(cite, end=400)
        elif vector == "citation_stale_revision":
            cite = replace(cite, revision="old")
        elif vector == "citation_wrong_sha":
            cite = replace(cite, source_sha256="f" * 64)
        elif vector == "citation_no_source":
            cite = replace(cite, source_id="not-found")
        citations = (cite, cite) if vector == "duplicate_citation" else (cite,)
        art = sign(replace(art, citations=citations), "verifier")
    elif vector == "grade_missing":
        grade = None
    elif vector == "grade_model_self_score":
        grade = replace(grade, seal=replace(grade.seal, signer="executor-model"))
    elif vector == "grade_wrong_digest":
        grade = sign(replace(grade, artifact_sha256="e" * 64), "grader")
    elif vector == "grade_wrong_task":
        grade = sign(replace(grade, task_id="other"), "grader")
    elif vector == "grade_84":
        grade = sign(replace(grade, quality_score=84), "grader")
    elif vector == "grade_fact_wrong":
        grade = sign(replace(grade, fact_correct=False), "grader")
    elif vector == "grade_grounding_false":
        grade = sign(replace(grade, grounding_ok=False), "grader")
    elif vector == "invalid_grade_signature":
        grade = replace(grade, seal=replace(grade.seal, signature="x" * 64))
    elif vector.startswith("stream_"):
        assert stream is not None
        if vector == "stream_missing_ack":
            stream = sign(replace(stream, client_ack_ms=None), "client")
        elif vector == "stream_ack_after_terminal":
            stream = sign(replace(stream, client_ack_ms=901), "client")
        elif vector == "stream_flush_after_ack":
            stream = sign(replace(stream, server_flush_ms=350), "client")
        elif vector == "stream_missing_citations":
            stream = sign(replace(stream, cited_source_ids=()), "client")
        elif vector == "stream_wrong_payload":
            stream = sign(replace(stream, payload=b"not in artifact"), "client")
        elif vector == "stream_progress_only":
            stream = sign(replace(stream, payload=b"[progress]"), "client")
        elif vector == "stream_wrong_signature":
            stream = replace(stream, seal=replace(stream.seal, signature="0" * 64))
        elif vector == "stream_terminal_only":
            stream = sign(replace(stream, server_flush_ms=900,
                                  client_ack_ms=900), "client")
    elif vector == "missing_recovery":
        recovery = None
    elif vector == "checkpoint_lost":
        recovery = replace(recovery, checkpoint_preserved=False)
    elif vector == "duplicate_accounted":
        recovery = replace(recovery, duplicate_accounting=True)
    elif vector == "unknown_effect":
        recovery = replace(recovery, unknown_effect=True)
    elif vector == "replay_negative":
        recovery = replace(recovery, replay_count=-1)
    elif vector == "billing_delayed":
        bill = sign(replace(bill, received_ms=2000), "billing")
    elif vector == "invoice_missing":
        options["invoices"] = ()
    elif vector == "invoice_wrong_total":
        bill = sign(replace(bill, billed_micros=79), "billing")
    elif vector == "invoice_unsigned":
        bill = replace(bill, seal=None)
    elif vector == "invoice_wrong_task":
        bill = sign(replace(bill, task_id="other"), "billing")
    elif vector == "invoice_duplicate":
        options["invoices"] = (bill, bill)
    elif vector == "invoice_unknown_attempt":
        bill = sign(replace(bill, attempt_id="unplanned"), "billing")
    elif vector == "invoice_bool_tokens":
        bill = sign(replace(bill, input_tokens=True), "billing")
    elif vector == "invoice_negative_price":
        bill = sign(replace(bill, input_unit_micros=-1), "billing")
    elif vector == "attempt_duplicate":
        options["attempts"] = c.attempts + c.attempts
    elif vector.startswith("research_"):
        r = c.research
        assert r is not None
        if vector == "research_counterevidence_missing":
            r = sign(replace(r, counterevidence_checked=False), "reviewer")
        elif vector == "research_unfinished":
            r = sign(replace(r, tasks_unfinished=1), "reviewer")
        elif vector == "research_checkpoint_missing":
            r = sign(replace(r, checkpoint_sha256=None), "reviewer")
        elif vector == "research_sources_missing":
            r = sign(replace(r, source_ids_reviewed=()), "reviewer")
        else:
            r = replace(r, seal=None)
        options["research"] = r
    elif vector.startswith("coding_"):
        r = c.runner
        assert r is not None
        if vector == "coding_fake_runner":
            r = sign(replace(r, real_subprocess=False), "runner")
        elif vector == "coding_tests_none":
            r = sign(replace(r, test_count=0), "runner")
        elif vector == "coding_exit_nonzero":
            r = sign(replace(r, exit_code=1), "runner")
        elif vector == "coding_wrong_artifact":
            r = sign(replace(r, artifact_sha256="a" * 64), "runner")
        else:
            r = replace(r, seal=None)
        options["runner"] = r
    elif vector.startswith("permit_"):
        p = c.permit
        assert p is not None
        if vector == "permit_missing":
            p = None
        elif vector == "permit_expired":
            p = sign(replace(p, expires_ms=1000), "permit")
        else:
            p = sign(replace(p, tenant_id="wrong"), "permit")
        options["permit"] = p
    elif vector.startswith("effect_"):
        e = c.effect
        assert e is not None
        if vector == "effect_missing":
            e = None
        elif vector == "effect_unknown":
            e = sign(replace(e, unknown_effect=True), "observer")
        elif vector == "effect_no_observation":
            e = sign(replace(e, observed=False), "observer")
        elif vector == "effect_mismatch":
            e = sign(replace(e, action_id="wrong"), "observer")
        else:
            e = replace(e, seal=None)
        options["effect"] = e
    elif vector.startswith("claimed_"):
        options["claimed_status"] = vector.removeprefix("claimed_").upper()
    else:
        raise AssertionError(f"Unimplemented negative vector: {vector}")
    if vector.startswith("source_") and vector not in ("source_duplicate",
                                                      "source_signer_revoked"):
        options["sources"] = (src,)
    if (
        vector.startswith(("artifact_", "citation_"))
        or vector in ("fake_citation_quote", "duplicate_citation")
    ):
        options["artifact"] = art
    if vector.startswith("grade_") or vector in ("invalid_grade_signature",):
        options["grade"] = grade
    if vector.startswith("stream_"):
        options["stream"] = stream
    if vector.startswith(("billing_", "invoice_")) and vector not in (
        "invoice_missing", "invoice_duplicate",
    ):
        options["invoices"] = (bill,)
    if vector in ("missing_recovery", "checkpoint_lost", "duplicate_accounted",
                  "unknown_effect", "replay_negative"):
        options["recovery"] = recovery
    return a, replace(c, **options)


@pytest.mark.parametrize("vector", NEGATIVE_VECTORS)
def test_negative_falsification(vector):
    a, c = damaged(vector)
    ctx = (context(revoked_keys=frozenset({"offline-source"}))
           if vector == "source_signer_revoked" else context())
    result = IndependentOutcomeHarnessV1(ctx).evaluate((a,), (c,))
    assert result.accepted == 0, vector
    assert result.receipts[0].outcome != "ACCEPTED", vector
    assert result.release_certification == "NOT_CERTIFIED"
    if vector in ("unknown_effect", "effect_unknown"):
        assert result.receipts[0].outcome == "UNKNOWN"
    if vector in ("invoice_missing", "billing_delayed"):
        assert result.cost_micros is None


def test_denominator_unknown_partial_abstain_and_not_eligible():
    a1, c1 = fixture("QA", "a")
    a2, c2 = fixture("RESEARCH", "b")
    a3, c3 = fixture("ACTION", "c")
    a4, c4 = fixture("QA", "d")
    a5, c5 = fixture("CODING", "e")
    a5 = replace(a5, eligible=False)
    result = IndependentOutcomeHarnessV1(context()).evaluate(
        (a1, a2, a3, a4, a5),
        (c1, replace(c2, claimed_status="PARTIAL"),
         replace(c3, claimed_status="ABSTAIN"), c5),
    )
    assert (result.assigned, result.eligible, result.not_eligible) == (5, 4, 1)
    assert (result.accepted, result.partial, result.abstain, result.unknown) == (1, 1, 1, 1)
    assert result.success_rate == .25
    assert result.missing_cases == (a4.case_id,)
    assert result.cost_micros is None


def test_duplicate_case_cannot_improve_success_rate():
    a, c = fixture()
    r = IndependentOutcomeHarnessV1(context()).evaluate((a,), (c, c))
    assert r.accepted == 0
    assert r.duplicate_cases == (a.case_id,)
    assert "DUPLICATE_CASE_ID" in r.receipts[0].reasons


def test_cross_task_duplicate_charge_is_rejected():
    a, c = fixture("QA", "a")
    b, d = fixture("QA", "b")
    dbill = sign(replace(d.invoices[0], charge_id=c.invoices[0].charge_id), "billing")
    d = replace(d, invoices=(dbill,))
    output = IndependentOutcomeHarnessV1(context()).evaluate((a, b), (c, d))
    assert output.accepted == 0
    assert all("DUPLICATE_CHARGE_ACROSS_TASKS" in r.reasons for r in output.receipts)


def test_duplicate_task_id_across_distinct_cases_fails_closed():
    a, c = fixture("QA", "a")
    b, d = fixture("QA", "b")
    b = replace(b, task_id=a.task_id)
    output = IndependentOutcomeHarnessV1(context()).evaluate((a, b), (c, d))
    assert output.duplicate_task_ids == (a.task_id,)
    assert output.accepted == 0
    assert all("DUPLICATE_TASK_ID" in r.reasons for r in output.receipts)


def test_extra_unassigned_cannot_increase_denominator_success():
    a, c = fixture()
    _, d = fixture("QA", "extra")
    result = IndependentOutcomeHarnessV1(context()).evaluate((a,), (c, d))
    assert result.unassigned_cases == ("QAextra",)
    assert result.accepted == 1
    assert result.cost_micros is None
    assert result.release_certification == "NOT_CERTIFIED"


def test_assignment_duplicate_fails_closed():
    a, c = fixture()
    with pytest.raises(ValueError, match="DUPLICATE_ASSIGNMENT"):
        IndependentOutcomeHarnessV1(context()).evaluate((a, a), (c,))


def test_zero_eligible_has_no_rate_or_cost_denominator():
    a, c = fixture()
    a = replace(a, eligible=False)
    output = IndependentOutcomeHarnessV1(context()).evaluate((a,), (c,))
    assert output.success_rate is None
    assert output.cost_per_verified_outcome_micros is None
    assert output.not_eligible == 1


def test_no_verified_outcome_has_unknown_cost_per_outcome():
    a, c = fixture()
    output = IndependentOutcomeHarnessV1(context()).evaluate(
        (a,), (replace(c, claimed_status="ABSTAIN"),),
    )
    assert output.cost_micros == 80
    assert output.cost_per_verified_outcome_micros is None


def test_fixture_can_never_be_unseen_holdout_or_release_proof():
    a, c = fixture()
    malicious_context = context(
        authority_tier="EXTERNALLY_AUTHENTICATED",
        i02_master_accepted_commit="f" * 40,
        externally_sealed_holdout=True,
        external_score_custodian=True,
        real_source_and_billing_authority=True,
    )
    local = IndependentOutcomeHarnessV1(malicious_context).evaluate((a,), (c,))
    assert local.release_certification == "NOT_CERTIFIED"
    assert local.latency_authority == "SYNTHETIC_NOT_PRODUCT_P95"
    assert local.assigned == 1  # 523 real unique cases are mandatory, not 1.


def test_receipts_deterministic_and_input_is_unmodified():
    a, c = fixture()
    h = IndependentOutcomeHarnessV1(context())
    one = h.evaluate((a,), (c,))
    two = h.evaluate((a,), (c,))
    assert one == two
    assert c.artifact is not None and c.artifact.seal is not None
    assert one.receipts[0].manifest.sha256 != one.receipts[0].receipt_sha256
