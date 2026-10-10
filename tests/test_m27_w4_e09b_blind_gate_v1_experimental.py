"""Adversarial offline tests for independently sealed Phase B admission only."""

from dataclasses import replace

import pytest

from knowledge_engine.m27_w4_e09b_blind_gate_v1_experimental import (
    BLOCKED,
    EXPECTED_I02,
    AdmissionGateV1,
    AuthorityClaim,
    CandidateFreeze,
    CaseReceipt,
    ClientTrace,
    IndependentCorpus,
    OpaqueCase,
    PhaseBPacket,
    SourceClearance,
    UpstreamReport,
    audit_opaque_offline,
)
from knowledge_engine.m27_w4_e09b_blind_gate_v1_experimental import (
    TestOnceLedger as OnceLedger,
)

H = "a" * 64
H2 = "b" * 64
H3 = "c" * 64


def clean_packet():
    corpus = IndependentCorpus(
        H, H2, H3, "unseen-v1", 200, 140, 100, 20, 5, 40, 60, 30, 20,
        0, 10.0, 20.0, 15.0, 20.0, True, H2, 523,
    )
    source = SourceClearance(
        H, H2, H3, "rights-id", "independent-custodian",
        2000, True, False, True, False, H,
    )
    upstream = tuple(
        UpstreamReport(k, "MASTER_ADMITTED", H, H2, True)
        for k in ("D09", "T09", "P09")
    )
    roles = (
        "holdout_custodian", "source_rights", "consent", "scorer",
        "independent_reviewer", "billing", "client_observer", "ci_runner",
        "effect_observer", "execution_approver",
    )
    authorities = tuple(
        AuthorityClaim(k, "role-" + k, "external-root", H3, True, H, 2000)
        for k in roles
    )
    return PhaseBPacket(
        CandidateFreeze(EXPECTED_I02, "a" * 40, H, H2, H3),
        corpus, source, upstream, authorities, ("reviewer-a", "reviewer-b"),
        "grader-v1", H, H2, H3, H, "independent-evaluator",
        "candidate-executor", 1000, H, H2,
    )


def external_gate():
    # Test-only proof port; never independent real-world attestation.
    return AdmissionGateV1(
        verifier=lambda claim: claim.key_id == "external-root",
        independently_operated=True, authorized_interface=lambda: None,
    )


def test_mocked_preconditions_are_not_official_run_or_release():
    d = external_gate().inspect(clean_packet())
    assert d.status == "PRECONDITIONS_SATISFIED_NOT_EXECUTED"
    assert d.reasons == ()
    assert d.official_evaluation_ran is False
    assert d.release_certified is False


def test_default_constructor_always_fail_closed():
    r = AdmissionGateV1().inspect(clean_packet())
    assert r.status == BLOCKED
    assert "AUTHORIZED_INDEPENDENT_RUN_INTERFACE_MISSING" in r.reasons
    assert "AUTHORITY_SCORER_UNVERIFIED" in r.reasons


# Each vector mutates a distinct trusted or cohort fact, then invokes inspect().
VECTORS = (
    "wrong_i02_commit", "short_commit", "wrong_tree", "bad_image",
    "bad_build", "bad_runner", "wrong_master_anchor",
    "unsigned_manifest", "bad_manifest", "bad_snapshot",
    "missing_dataset_version", "wrong_hidden_case_digest",
    "only_199_cases", "only_139_intents", "only_99_sources",
    "only_19_documents", "only_4_families", "only_39_longtail",
    "only_59_paraphrases", "only_29_controls", "only_19_positives",
    "reuse_intention", "legacy_182_replays", "direct100",
    "stage30p", "exposed_nine", "document_concentration",
    "family_concentration", "graphology_concentration",
    "historical_topic_concentration", "no_original_523",
    "historical_341_plus_182", "wrong_original_version",
    "source_rights_hash_missing", "acl_hash_missing",
    "consent_hash_missing", "access_log_missing",
    "missing_license", "missing_custodian", "expired_snapshot",
    "source_revoked", "no_retention", "no_evaluator_acl",
    "leaks_to_candidate", "missing_d09", "missing_t09",
    "missing_p09", "d09_not_admitted", "t09_not_admitted",
    "p09_not_admitted", "d09_no_master_signature",
    "d09_unverified_hash", "duplicated_upstream",
    "self_reviewer", "only_one_reviewer", "same_reviewer_twice",
    "candidate_evaluator", "no_grader_version",
    "missing_rubric", "missing_scorer_build", "missing_calibration",
    "unapproved_interface", "missing_approval",
    "missing_billing_authority", "missing_source_authority",
    "self_signed_scorer", "scorer_key_untrusted",
    "scorer_bad_signature", "scorer_expired", "scorer_wrong_corpus",
    "scorer_claims_not_independent", "duplicated_scorer",
    "no_original_benchmark_gate",
)


def corrupt(p, vector):
    c, h, s = p.candidate, p.corpus, p.source
    if vector == "wrong_i02_commit":
        c = replace(c, commit="f" * 40)
    elif vector == "short_commit":
        c = replace(c, commit="deadbeef")
    elif vector == "wrong_tree":
        c = replace(c, tree="foo")
    elif vector == "bad_image":
        c = replace(c, image_sha256="not-a-digest")
    elif vector == "bad_build":
        c = replace(c, build_sha256="0")
    elif vector == "bad_runner":
        c = replace(c, runner_sha256="")
    elif vector == "wrong_master_anchor":
        c = replace(c, master_accepted_commit="f" * 40)
    elif vector == "unsigned_manifest":
        h = replace(h, signed_manifest_sha256="")
    elif vector == "bad_manifest":
        h = replace(h, manifest_sha256="xyz")
    elif vector == "bad_snapshot":
        h = replace(h, snapshot_sha256="")
    elif vector == "missing_dataset_version":
        h = replace(h, dataset_version="")
    elif vector == "wrong_hidden_case_digest":
        return replace(p, frozen_case_ids_digest="wrong")
    elif vector == "only_199_cases":
        h = replace(h, cases=199)
    elif vector == "only_139_intents":
        h = replace(h, independent_intents=139)
    elif vector == "only_99_sources":
        h = replace(h, source_records=99)
    elif vector == "only_19_documents":
        h = replace(h, source_documents=19)
    elif vector == "only_4_families":
        h = replace(h, source_families=4)
    elif vector == "only_39_longtail":
        h = replace(h, long_tail=39)
    elif vector == "only_59_paraphrases":
        h = replace(h, paraphrase_probes=59)
    elif vector == "only_29_controls":
        h = replace(h, negative_controls=29)
    elif vector == "only_19_positives":
        h = replace(h, supported_positives=19)
    elif vector == "reuse_intention":
        h = replace(h, distinct_reused=1)
    elif vector == "legacy_182_replays":
        h = replace(h, includes_historical_182_replays=True)
    elif vector == "direct100":
        h = replace(h, contains_direct100=True)
    elif vector == "stage30p":
        h = replace(h, contains_stage30p=True)
    elif vector == "exposed_nine":
        h = replace(h, contains_exposed_nine=True)
    elif vector == "document_concentration":
        h = replace(h, max_document_share_pct=10.01)
    elif vector == "family_concentration":
        h = replace(h, max_family_share_pct=20.01)
    elif vector == "graphology_concentration":
        h = replace(h, graphology_share_pct=15.01)
    elif vector == "historical_topic_concentration":
        h = replace(h, historical_topic_share_pct=20.01)
    elif vector == "no_original_523":
        h = replace(h, separately_frozen_original_523=False)
    elif vector == "historical_341_plus_182":
        h = replace(h, original_523_distinct_questions=341)
    elif vector == "wrong_original_version":
        h = replace(h, original_523_version_sha256="unversioned")
    elif vector == "source_rights_hash_missing":
        s = replace(s, rights_manifest_sha256="")
    elif vector == "acl_hash_missing":
        s = replace(s, acl_manifest_sha256="")
    elif vector == "consent_hash_missing":
        s = replace(s, consent_manifest_sha256="")
    elif vector == "access_log_missing":
        s = replace(s, access_log_sha256="")
    elif vector == "missing_license":
        s = replace(s, license_id="")
    elif vector == "missing_custodian":
        s = replace(s, custodian_id="")
    elif vector == "expired_snapshot":
        s = replace(s, snapshot_expires_utc=1000)
    elif vector == "source_revoked":
        s = replace(s, revoked=True)
    elif vector == "no_retention":
        s = replace(s, retention_approved=False)
    elif vector == "no_evaluator_acl":
        s = replace(s, permitted_evaluator_only=False)
    elif vector == "leaks_to_candidate":
        s = replace(s, leaks_to_candidate=True)
    elif vector in {"missing_d09", "missing_t09", "missing_p09"}:
        return replace(
            p, upstream=tuple(
                x for x in p.upstream if x.task_id != vector[8:11].upper()
            ),
        )
    elif vector in {"d09_not_admitted", "t09_not_admitted", "p09_not_admitted"}:
        task = vector[:3].upper()
        return replace(
            p, upstream=tuple(
                replace(x, status="NOT_ADMITTED") if x.task_id == task else x
                for x in p.upstream
            ),
        )
    elif vector == "d09_no_master_signature":
        return replace(
            p, upstream=tuple(
                replace(x, independently_accepted=False)
                if x.task_id == "D09" else x for x in p.upstream
            ),
        )
    elif vector == "d09_unverified_hash":
        return replace(
            p, upstream=tuple(
                replace(x, report_sha256="") if x.task_id == "D09" else x
                for x in p.upstream
            ),
        )
    elif vector == "duplicated_upstream":
        return replace(p, upstream=p.upstream + (p.upstream[0],))
    elif vector == "self_reviewer":
        return replace(p, reviewer_ids=("candidate-executor", "reviewer-b"))
    elif vector == "only_one_reviewer":
        return replace(p, reviewer_ids=("reviewer-a",))
    elif vector == "same_reviewer_twice":
        return replace(p, reviewer_ids=("reviewer-a", "reviewer-a"))
    elif vector == "candidate_evaluator":
        return replace(p, evaluator_id=p.executor_id)
    elif vector == "no_grader_version":
        return replace(p, grader_version="")
    elif vector == "missing_rubric":
        return replace(p, rubric_sha256="")
    elif vector == "missing_scorer_build":
        return replace(p, scorer_build_sha256="")
    elif vector == "missing_calibration":
        return replace(p, calibration_sha256="")
    elif vector == "unapproved_interface":
        return replace(p, runtime_interface_sha256="")
    elif vector == "missing_approval":
        return replace(p, approval_sha256="")
    elif vector in {
        "missing_billing_authority", "missing_source_authority",
        "self_signed_scorer", "scorer_key_untrusted",
        "scorer_bad_signature", "scorer_expired",
        "scorer_wrong_corpus", "scorer_claims_not_independent",
        "duplicated_scorer",
    }:
        auth = list(p.authorities)
        if vector.startswith("missing_"):
            role = "billing" if "billing" in vector else "source_rights"
            auth = [a for a in auth if a.role != role]
        else:
            ix = next(i for i, a in enumerate(auth) if a.role == "scorer")
            a = auth[ix]
            updates = {
                "self_signed_scorer": {"signer_id": p.executor_id},
                "scorer_key_untrusted": {"key_id": "executor-key"},
                "scorer_bad_signature": {"signature_sha256": "not-digest"},
                "scorer_expired": {"expires_utc": 1000},
                "scorer_wrong_corpus": {"authorized_for_dataset_sha256": H2},
                "scorer_claims_not_independent": {"independently_custodied": False},
                "duplicated_scorer": {},
            }
            if vector == "duplicated_scorer":
                auth.append(a)
            else:
                auth[ix] = replace(a, **updates[vector])
        return replace(p, authorities=tuple(auth))
    elif vector == "no_original_benchmark_gate":
        return replace(p, original_benchmark_gate_required=False)
    else:
        raise AssertionError(vector)
    return replace(p, candidate=c, corpus=h, source=s)


@pytest.mark.parametrize("vector", VECTORS)
def test_each_adversarial_metadata_corruption_blocks(vector):
    bad = corrupt(clean_packet(), vector)
    decision = external_gate().inspect(bad)
    assert decision.status == BLOCKED, vector
    assert decision.reasons, vector
    assert not decision.official_evaluation_ran
    assert not decision.release_certified


def test_opaque_decision_digest_is_reproducible_and_no_hidden_content():
    p = clean_packet()
    a, b = external_gate().inspect(p), external_gate().inspect(p)
    assert a.decision_sha256 == b.decision_sha256
    assert len(a.decision_sha256) == 64
    assert "answer" not in str(a).lower()


def test_one_shot_ledger_no_retest_even_when_candidate_differs(tmp_path):
    ledger = OnceLedger(tmp_path)
    first = ledger.reserve("run-opaque-id", H, H2)
    assert len(first) == 64
    with pytest.raises(FileExistsError):
        ledger.reserve("run-opaque-id", H3, H2)
    events = list(tmp_path.iterdir())
    assert len(events) == 1
    assert events[0].stat().st_mode & 0o777 == 0o600
    assert "run-opaque-id" not in events[0].read_text()


@pytest.mark.parametrize("bad_id,bad_candidate,bad_corpus", [
    ("", H, H), ("x", "bad", H), ("x", H, ""),
])
def test_ledger_rejects_missing_identity(tmp_path, bad_id, bad_candidate, bad_corpus):
    with pytest.raises(ValueError):
        OnceLedger(tmp_path).reserve(bad_id, bad_candidate, bad_corpus)
    assert list(tmp_path.iterdir()) == []


def receipt(case_id="a", **updates):
    t = ClientTrace(
        "independent-client-monotonic", 1_000_000_000, 1_100_000_000,
        1_150_000_000, 1_500_000_000, H, 32,
    )
    base = CaseReceipt(
        case_id, "ANSWER", 90, True, True, True, True, False, t,
        ("attempt-1",), ("attempt-1",), 12, True, True,
    )
    return replace(base, **updates)


def outcome_one(r, *, safe=False):
    return audit_opaque_offline(
        (OpaqueCase("a", "SAFE_ABSTAIN" if safe else "ANSWERABLE"),),
        (r,),
    )


def test_valid_fixture_audit_remains_diagnostic():
    out = outcome_one(receipt())
    assert out.status == "OFFLINE_DIAGNOSTIC_NOT_PRODUCT_SCORE"
    assert out.answerable_success == 1
    assert out.p95_ms == 500
    assert out.total_cost_micros == 12
    assert out.reasons == ()


RESULT_FAULTS = (
    "grade_84", "self_grade", "source_binding", "unsupported_positive",
    "privacy", "false_safe", "semantic_bad", "safe_false",
    "missing_ack", "progress_only", "terminal_only", "zero_bytes",
    "wrong_clock", "wrong_clock_domain", "client_terminal_before_request",
    "first_text_terminal", "cited_segment_terminal", "first_text_after_cited",
    "no_verified_first_text", "no_cited_segment", "no_client_digest",
    "first_text_negative", "no_cost", "unknown_price",
    "self_billing", "missing_invoice", "billing_delay",
    "duplicate_invoices", "duplicate_attempts", "missing_attempts",
    "timeout", "unknown", "partial", "error",
)


def corrupt_result(vector):
    r = receipt()
    t = r.trace
    if vector == "grade_84":
        return replace(r, score=84)
    if vector == "self_grade":
        return replace(r, independent_grade_verified=False)
    if vector == "source_binding":
        return replace(r, evidence_and_original_citation_verified=False)
    if vector == "unsupported_positive":
        return replace(r, supported=False)
    if vector == "privacy":
        return replace(r, privacy_ok=False)
    if vector == "false_safe":
        return replace(r, false_safe=True)
    if vector == "semantic_bad":
        return replace(r, semantic_bad_published=True)
    if vector == "safe_false":
        return replace(r, result="ABSTAIN")
    if vector == "missing_ack":
        return replace(r, trace=None)
    if vector == "progress_only":
        t = replace(t, progress_only=True)
    if vector == "terminal_only":
        t = replace(t, terminal_only=True)
    if vector == "zero_bytes":
        t = replace(t, verified_bytes=0)
    if vector == "wrong_clock":
        t = replace(t, terminal_received_ns=None)
    if vector == "wrong_clock_domain":
        t = replace(t, clock_domain="")
    if vector == "client_terminal_before_request":
        t = replace(t, terminal_received_ns=0)
    if vector == "first_text_terminal":
        t = replace(t, verified_substantive_received_ns=t.terminal_received_ns)
    if vector == "cited_segment_terminal":
        t = replace(t, cited_segment_received_ns=t.terminal_received_ns)
    if vector == "first_text_after_cited":
        t = replace(t, verified_substantive_received_ns=1_200_000_000)
    if vector == "no_verified_first_text":
        t = replace(t, verified_substantive_received_ns=None)
    if vector == "no_cited_segment":
        t = replace(t, cited_segment_received_ns=None)
    if vector == "no_client_digest":
        t = replace(t, client_receipt_sha256="")
    if vector == "first_text_negative":
        t = replace(t, verified_substantive_received_ns=-1)
    if vector == "no_cost":
        return replace(r, cost_micros=None)
    if vector == "unknown_price":
        return replace(r, price_authority_verified=False)
    if vector == "self_billing":
        return replace(r, billing_authority_verified=False)
    if vector == "missing_invoice":
        return replace(r, invoiced_attempts=())
    if vector == "billing_delay":
        return replace(r, cost_micros=None, billing_authority_verified=False)
    if vector == "duplicate_invoices":
        return replace(r, invoiced_attempts=("attempt-1", "attempt-1"))
    if vector == "duplicate_attempts":
        return replace(r, attempts=("attempt-1", "attempt-1"))
    if vector == "missing_attempts":
        return replace(r, attempts=())
    if vector in ("timeout", "unknown", "partial", "error"):
        return replace(r, result=vector.upper())
    return replace(r, trace=t)


@pytest.mark.parametrize("vector", RESULT_FAULTS)
def test_each_adversarial_result_denied_in_offline_diagnostic(vector):
    out = outcome_one(corrupt_result(vector))
    assert out.status == "OFFLINE_DIAGNOSTIC_NOT_PRODUCT_SCORE"
    assert out.answerable_success == 0, vector
    assert out.failure_count == 1


def test_omitted_and_timeout_cases_remain_in_p95_and_denominator():
    cohort = tuple(OpaqueCase(str(i), "ANSWERABLE") for i in range(20))
    receipts = tuple(receipt(str(i)) for i in range(18))
    out = audit_opaque_offline(cohort, receipts)
    assert out.denominator == 20
    assert out.missing_count == 2
    assert out.answerable_success_rate == 0.9
    assert out.p95_ms == 30_000
    assert out.total_cost_micros is None


def test_duplicate_result_and_unassigned_result_never_inflate_success():
    out = audit_opaque_offline(
        (OpaqueCase("a", "ANSWERABLE"),),
        (receipt(), receipt(), receipt("unassigned")),
    )
    assert "DUPLICATE_RESULT_OR_RETEST" in out.reasons
    assert out.answerable_success == 0
    assert "UNASSIGNED_OR_INELIGIBLE_RESULT" in out.reasons
    assert "NONSELECTIVE_DENOMINATOR_INCOMPLETE" in out.reasons


def test_nearest_rank_p95_and_gate_boundary():
    cohort = tuple(OpaqueCase(str(i), "ANSWERABLE") for i in range(20))
    rs = []
    for i in range(20):
        t = receipt().trace
        terminal = 15_000_000_000 if i >= 18 else 2_000_000_000
        rs.append(receipt(str(i), trace=replace(t, terminal_received_ns=terminal)))
    out = audit_opaque_offline(cohort, tuple(rs))
    assert out.p95_ms == 14_000.0
    assert out.failure_count == 0
    rs[18] = receipt("18", trace=replace(t, terminal_received_ns=16_000_000_000))
    rs[19] = receipt("19", trace=replace(t, terminal_received_ns=16_000_000_000))
    out = audit_opaque_offline(cohort, tuple(rs))
    assert out.p95_ms == 15_000.0
    assert "TRUE_CLIENT_P95_NOT_UNDER_15_SECONDS" in out.reasons


def test_safe_abstention_and_false_safe_separately_accounted():
    safe = receipt(result="ABSTAIN", score=None)
    out = outcome_one(safe, safe=True)
    assert out.safe_correct == 1
    unsafe = outcome_one(safe)
    assert unsafe.false_safe_count == 1
    assert "FALSE_SAFE_SUPPORTED_CASE" in unsafe.reasons


def test_no_invoice_cannot_be_zero_price():
    out = outcome_one(receipt(cost_micros=0, invoiced_attempts=()))
    assert out.total_cost_micros is None
    assert out.billing_unknown_count == 1


@pytest.mark.parametrize("hard_timeout", [0, 14999, -1, True])
def test_invalid_latency_penalty_configuration_rejected(hard_timeout):
    with pytest.raises(ValueError):
        audit_opaque_offline((), (), deadline_ms=hard_timeout)


def test_empty_cohort_and_missing_label_rejected():
    empty = audit_opaque_offline((), ())
    assert "DUPLICATE_OR_EMPTY_ASSIGNED_CASES" in empty.reasons
    bad = audit_opaque_offline((OpaqueCase("x", "MODEL_SAYS_GO"),), ())
    assert "INVALID_INDEPENDENT_LABEL" in bad.reasons


def test_no_implicit_523_from_341_live_plus_182_replay():
    h = replace(
        clean_packet().corpus, original_523_distinct_questions=341,
        includes_historical_182_replays=True,
    )
    d = external_gate().inspect(replace(clean_packet(), corpus=h))
    assert "ORIGINAL_523_DISTINCT_BENCHMARK_UNPROVEN" in d.reasons
    assert "HOLDOUT_CONTAMINATED_BY_KNOWN_QUESTIONS" in d.reasons



def test_timeout_with_early_error_terminal_gets_full_deadline_penalty():
    out = outcome_one(receipt(result="TIMEOUT"))
    assert out.failure_count == 1
    assert out.p95_ms == 30_000
    assert "TRUE_CLIENT_P95_NOT_UNDER_15_SECONDS" in out.reasons


def test_duplicate_case_consumes_failure_not_success():
    out = audit_opaque_offline(
        (OpaqueCase("a", "ANSWERABLE"),), (receipt(), receipt()),
    )
    assert out.answerable_success == 0
    assert out.failure_count == 1
    assert out.p95_ms == 30_000
    assert "DUPLICATE_RESULT_OR_RETEST" in out.reasons
