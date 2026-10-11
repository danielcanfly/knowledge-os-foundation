"""Synthetic-only E15 fail-closed regression vectors; no actual 523 corpus."""
from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from knowledge_engine import m27_w5_e15_original523_evaluator_admission_v1_experimental as e

NOW = 1000


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def signed_fixture(cohort: str = e.ORIGINAL):
    count = 523 if cohort == e.ORIGINAL else 200
    sources = tuple(
        e.SourcePin(
            source_id=f"src-{i:03d}", revision="revision-1",
            document_id=f"document-{i % 30}", family_id=f"family-{(i % 11) % 9}",
            origin_id=f"origin-{i % 11}",
            source_sha256=sha(f"source-{i}"),
            span_index_sha256=sha(f"span-index-{i}"),
            consent_until_ms=5000, acl_until_ms=5000,
        ) for i in range(120)
    )
    cases = tuple(
        e.OpaqueCase(
            case_id=f"case-{i:03d}", intent_digest=sha(f"intent-{i}"),
            lexical_dedup_digest=sha(f"lexical-{i}"),
            source_id=sources[i % 120].source_id, source_revision="revision-1",
        ) for i in range(count)
    )
    candidate = e.FrozenImage(
        commit="a" * 40, tree="b" * 40,
        image_sha256=sha("synthetic-image"), build_sha256=sha("synthetic-build"),
        runner_sha256=sha("synthetic-runner"),
        instrumentation_sha256=sha("synthetic-instrumentation"),
    )
    manifest = e.SealedManifest(
        version=e.VERSION, cohort=cohort,
        dataset_id="synthetic-sealed", sealed_dataset_sha256=sha("dataset"),
        nonce="synthetic-nonce", custodian_id="custodian-fixture",
        evaluator_id="evaluator-fixture",
        implementer_ids=("implementer-fixture",),
        reviewer_ids=("reviewer-one", "reviewer-two"),
        license_id="synthetic-license", license_scope="EVALUATION_ONLY",
        issued_ms=100, expires_ms=2000,
        rubric_id="rubric-synthetic", rubric_version="version-1",
        candidate=candidate, sources=sources, cases=cases,
    )
    results = tuple(
        e.ScoredCase(
            case_id=case.case_id, outcome="ANSWER", answerable=True, grade=92,
            cited=True, final_answer_sha256=sha(f"synthetic-answer-{i}"),
            final_text_bytes=24, cited_span_bytes=10,
            cited_source_id=case.source_id, cited_source_revision="revision-1",
            cited_span_start=0, cited_span_end=10,
            citation_span_sha256=sha(f"synthetic-citation-{i}"),
            client_payload_sha256=sha(f"synthetic-receipt-{i}"),
            first_client_text_ms=300, terminal_ms=12000,
        ) for i, case in enumerate(cases)
    )
    packet = e.RunPacket(
        run_id="synthetic-run", manifest_sha256=e.digest(e.asdict(manifest)),
        candidate_image_sha256=candidate.image_sha256,
        rubric_id=manifest.rubric_id, rubric_version=manifest.rubric_version,
        results=results, claims=(),
    )
    roots = []
    claims = []
    expected = e._expected_payloads(manifest, packet)
    for role in e.ROLES:
        secret = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(
            ("fixture-secret-" + role).encode()
        ).digest())
        root = e.TrustRoot(
            role=role, signer_id="synthetic-" + role, key_id="fixture-key",
            issuer_id="synthetic-non-authority",
            ed25519_public_key=secret.public_key().public_bytes(
                Encoding.Raw, PublicFormat.Raw
            ), tier="FIXTURE",
        )
        claim = e.SignedClaim(
            role=role, signer_id=root.signer_id, key_id=root.key_id,
            algorithm="ed25519", scope=cohort + ":EVALUATION_ONLY",
            issued_ms=100, expires_ms=2000, payload_sha256=expected[role],
            signature="",
        )
        claim = replace(claim, signature=secret.sign(
            e.claim_bytes(claim)
        ).hex())
        roots.append(root)
        claims.append(claim)
    packet = replace(packet, claims=tuple(claims))
    ctx = e.IndependentContext(
        roots=tuple(roots),
        externally_provisioned=False,
        independent_custodian_nominated=False,
        sealed_dataset_hashes={manifest.dataset_id: manifest.sealed_dataset_sha256},
        source_revisions={
            p.source_id: (p.revision, p.source_sha256, p.span_index_sha256)
            for p in sources
        },
        source_taxonomy={
            p.source_id: (p.document_id, p.family_id, p.origin_id)
            for p in sources
        },
        reviewed_cases={
            case.case_id: frozenset(manifest.reviewer_ids) for case in cases
        },
        approved_reviewer_ids=frozenset(manifest.reviewer_ids),
        approved_licenses=frozenset({manifest.license_id}),
        approved_rubrics=frozenset({(manifest.rubric_id, manifest.rubric_version)}),
        authorized_images=frozenset({candidate.image_sha256}),
    )
    return manifest, packet, ctx


@pytest.fixture(scope="module")
def original():
    return signed_fixture()


def test_original_523_synthetic_mechanics_never_becomes_official(original):
    m, p, c = original
    d = e.inspect(m, p, c)
    assert d.mechanics == e.MECHANICS
    assert d.status == e.REJECT_523
    assert d.independent_rights == e.RIGHTS_FAIL
    assert not d.official_cited_gate_pass
    assert not d.may_execute_official_evaluation
    assert d.total_assigned == d.result_count == d.cited_qualified == 523
    assert d.missing == d.rejected_or_failed == 0
    assert d.p95_terminal_ms == 12000
    assert d.cited_fraction == 1.0
    assert "FIXTURE_SIGNATURE_NOT_REAL_AUTHORITY" in d.reasons


def test_phase_b_fixture_is_not_original_523_or_a_real_phase_b_gate():
    m, p, c = signed_fixture(e.PHASE_B)
    d = e.inspect(m, p, c)
    assert d.total_assigned == 200
    assert d.status == e.REJECT_B
    assert d.official_cited_gate_pass is False
    assert d.mechanics == e.MECHANICS


def test_no_manifest_or_independent_scoring_defaults_closed():
    assert e.inspect(None).status == e.REJECT_523
    m, p, c = signed_fixture()
    d = e.inspect(m, context=c)
    assert d.status == e.REJECT_523
    assert d.missing == 523
    assert d.p95_terminal_ms is None
    assert "INDEPENDENT_SCORER_RESULTS_MISSING" in d.reasons


def test_counted_failed_attempts_do_not_vanish_from_p95(original):
    m, p, c = original
    failed = replace(p.results[1], outcome="TIMEOUT", cited=False,
                     grade=None, terminal_ms=20000, first_client_text_ms=None)
    packet = replace(p, results=(p.results[0], failed, *p.results[2:]))
    d = e.inspect(m, packet, c)
    assert d.total_assigned == 523
    assert d.rejected_or_failed == 1
    assert d.cited_qualified == 522
    assert d.p95_terminal_ms == 12000
    assert not d.official_cited_gate_pass


def test_missing_timeout_duration_prevents_any_p95(original):
    m, p, c = original
    failure = replace(p.results[100], outcome="TIMEOUT", terminal_ms=None)
    d = e.inspect(m, replace(p, results=(
        *p.results[:100], failure, *p.results[101:]
    )), c)
    assert d.p95_terminal_ms is None
    assert "P95_DENOMINATOR_INCOMPLETE" in d.reasons


def test_grade_below_threshold_is_not_cited_qualified(original):
    m, p, c = original
    bad = replace(p.results[0], grade=84)
    d = e.inspect(m, replace(p, results=(bad, *p.results[1:])), c)
    assert d.cited_qualified == 522
    assert d.rejected_or_failed == 1


def test_receipts_do_not_expose_question_content(original):
    m, p, c = original
    d = e.inspect(m, p, c)
    assert not any("synthetic-answer" in x for x in d.reasons)
    assert not hasattr(e.OpaqueCase, "question")
    assert not hasattr(e.ScoredCase, "answer_text")


# Each pytest parameter is a distinct executed fault-injection test ID.
# A test must assert the particular defect, not merely fixture roots' baseline refusal.
MANIFEST_VECTORS = [
    ("version", "not-supported", "INVALID_COHORT_OR_SCHEMA"),
    ("cohort", e.HISTORICAL, "INVALID_COHORT_OR_SCHEMA"),
    ("dataset_id", "", "INVALID_IDENTIFIER"),
    ("nonce", "", "INVALID_IDENTIFIER"),
    ("custodian_id", "", "INVALID_IDENTIFIER"),
    ("custodian_id", "evaluator-fixture", "CUSTODIAN_EVALUATOR_IMPLEMENTER_COLLUSION"),
    ("evaluator_id", "implementer-fixture", "CUSTODIAN_EVALUATOR_IMPLEMENTER_COLLUSION"),
    ("implementer_ids", (), "CUSTODIAN_EVALUATOR_IMPLEMENTER_COLLUSION"),
    ("implementer_ids", ("x", "x"), "CUSTODIAN_EVALUATOR_IMPLEMENTER_COLLUSION"),
    ("license_id", "", "INVALID_IDENTIFIER"),
    ("license_scope", "PRODUCTION", "RIGHTS_SCOPE_OR_SEAL_INVALID"),
    ("issued_ms", 2001, "MANIFEST_EXPIRED_OR_FUTURE"),
    ("expires_ms", 999, "MANIFEST_EXPIRED_OR_FUTURE"),
    ("issued_ms", True, "MANIFEST_EXPIRED_OR_FUTURE"),
    ("sealed_dataset_sha256", "sha256:mutable", "RIGHTS_SCOPE_OR_SEAL_INVALID"),
    ("rubric_id", "", "INVALID_IDENTIFIER"),
    ("rubric_version", "", "INVALID_IDENTIFIER"),
]
IMAGE_VECTORS = [
    ("commit", "missing"), ("tree", "nothex"),
    ("image_sha256", "sha256:tag-latest"), ("build_sha256", "0"),
    ("runner_sha256", ""), ("instrumentation_sha256", "bad"),
]
SOURCE_VECTORS = [
    ("source_id", ""), ("revision", ""), ("document_id", ""),
    ("family_id", ""), ("origin_id", ""),
    ("source_sha256", "bad"), ("span_index_sha256", "bad"),
    ("consent_until_ms", 999), ("acl_until_ms", 999),
    ("consent_until_ms", True),
]
CASE_VECTORS = [
    ("case_id", "", "DUPLICATE_EXPOSED_OR_UNVERIFIED_CASE"),
    ("intent_digest", "invalid", "DUPLICATE_EXPOSED_OR_UNVERIFIED_CASE"),
    ("lexical_dedup_digest", "invalid", "DUPLICATE_EXPOSED_OR_UNVERIFIED_CASE"),
    ("source_id", "not-registered", "CASE_SOURCE_REVISION_NOT_PINNED"),
    ("source_revision", "future-revision", "CASE_SOURCE_REVISION_NOT_PINNED"),
    ("exposed_before", True, "DUPLICATE_EXPOSED_OR_UNVERIFIED_CASE"),
]
RESULT_VECTORS = [
    ("outcome", "SUCCESS", "INVALID_RESULT_OUTCOME"),
    ("answerable", "yes", "INVALID_RESULT_OUTCOME"),
    ("grade", float("nan"), "INVALID_INDEPENDENT_GRADE"),
    ("grade", float("inf"), "INVALID_INDEPENDENT_GRADE"),
    ("grade", -1, "INVALID_INDEPENDENT_GRADE"),
    ("grade", 101, "INVALID_INDEPENDENT_GRADE"),
    ("grade", None, "INVALID_INDEPENDENT_GRADE"),
    ("grade", True, "INVALID_INDEPENDENT_GRADE"),
    ("cited", False, "UNVERIFIED_CITED_FINAL_ANSWER_OR_CLIENT_FIRST_TEXT"),
    ("final_answer_sha256", "", "UNVERIFIED_CITED_FINAL_ANSWER_OR_CLIENT_FIRST_TEXT"),
    ("final_answer_sha256", hashlib.sha256(b"").hexdigest(),
     "UNVERIFIED_CITED_FINAL_ANSWER_OR_CLIENT_FIRST_TEXT"),
    ("final_text_bytes", 0, "UNVERIFIED_CITED_FINAL_ANSWER_OR_CLIENT_FIRST_TEXT"),
    ("cited_span_bytes", 0, "UNVERIFIED_CITED_FINAL_ANSWER_OR_CLIENT_FIRST_TEXT"),
    ("citation_span_sha256", "", "UNVERIFIED_CITED_FINAL_ANSWER_OR_CLIENT_FIRST_TEXT"),
    ("client_payload_sha256", "", "UNVERIFIED_CITED_FINAL_ANSWER_OR_CLIENT_FIRST_TEXT"),
    ("cited_source_id", "other-source", "UNVERIFIED_CITED_FINAL_ANSWER_OR_CLIENT_FIRST_TEXT"),
    ("cited_source_revision", "old", "UNVERIFIED_CITED_FINAL_ANSWER_OR_CLIENT_FIRST_TEXT"),
    ("cited_span_start", -1, "UNVERIFIED_CITED_FINAL_ANSWER_OR_CLIENT_FIRST_TEXT"),
    ("cited_span_end", 0, "UNVERIFIED_CITED_FINAL_ANSWER_OR_CLIENT_FIRST_TEXT"),
    ("first_client_text_ms", None, "UNVERIFIED_CITED_FINAL_ANSWER_OR_CLIENT_FIRST_TEXT"),
    ("first_client_text_ms", 12000,
     "UNVERIFIED_CITED_FINAL_ANSWER_OR_CLIENT_FIRST_TEXT"),
    ("terminal_ms", 0, "TERMINAL_DURATION_MISSING_OR_INVALID"),
    ("terminal_ms", None, "TERMINAL_DURATION_MISSING_OR_INVALID"),
    ("terminal_ms", False, "TERMINAL_DURATION_MISSING_OR_INVALID"),
]
CLAIM_VECTORS = [
    ("role", "evil-role", "DUPLICATE_OR_UNEXPECTED_SIGNER_ROLE"),
    ("signer_id", "implementer-fixture", "SIGNER_COLLUSION_OR_IMPLEMENTER_ISSUER"),
    ("key_id", "", "SIGNER_SCOPE_EXPIRY_OR_DIGEST_INVALID"),
    ("algorithm", "fixture-hmac-sha256", "SIGNATURE_OR_INDEPENDENT_TRUST_ROOT_INVALID"),
    ("scope", "PRODUCTION", "SIGNER_SCOPE_EXPIRY_OR_DIGEST_INVALID"),
    ("issued_ms", 2001, "SIGNER_SCOPE_EXPIRY_OR_DIGEST_INVALID"),
    ("expires_ms", 999, "SIGNER_SCOPE_EXPIRY_OR_DIGEST_INVALID"),
    ("payload_sha256", "0" * 64, "SIGNER_SCOPE_EXPIRY_OR_DIGEST_INVALID"),
    ("signature", "faked", "SIGNATURE_OR_INDEPENDENT_TRUST_ROOT_INVALID"),
]


@pytest.mark.parametrize(
    "field,value,reason", MANIFEST_VECTORS,
    ids=[f"manifest-{x[0]}-{i}" for i, x in enumerate(MANIFEST_VECTORS)],
)
def test_negative_manifest(original, field, value, reason):
    m, p, c = original
    d = e.inspect(replace(m, **{field: value}), p, c)
    assert reason in d.reasons
    assert not d.official_cited_gate_pass


@pytest.mark.parametrize(
    "field,value", IMAGE_VECTORS,
    ids=[f"image-{x[0]}" for x in IMAGE_VECTORS],
)
def test_negative_immutable_image(original, field, value):
    m, p, c = original
    d = e.inspect(replace(m, candidate=replace(m.candidate, **{
        field: value
    })), p, c)
    assert "IMMUTABLE_EXECUTED_IMAGE_PROVENANCE_INVALID" in d.reasons
    assert d.status == e.REJECT_523


@pytest.mark.parametrize(
    "field,value", SOURCE_VECTORS,
    ids=[f"source-{x[0]}-{i}" for i, x in enumerate(SOURCE_VECTORS)],
)
def test_negative_source_rights(original, field, value):
    m, p, c = original
    pins = (replace(m.sources[0], **{field: value}), *m.sources[1:])
    d = e.inspect(replace(m, sources=pins), p, c)
    assert "SOURCE_SHA_REVISION_OR_RIGHTS_INVALID" in d.reasons


@pytest.mark.parametrize(
    "field,value,reason", CASE_VECTORS,
    ids=[f"case-{x[0]}" for x in CASE_VECTORS],
)
def test_negative_case_metadata(original, field, value, reason):
    m, p, c = original
    cases = (replace(m.cases[0], **{field: value}), *m.cases[1:])
    d = e.inspect(replace(m, cases=cases), p, c)
    assert reason in d.reasons


@pytest.mark.parametrize(
    "field,value,reason", RESULT_VECTORS,
    ids=[f"result-{x[0]}-{i}" for i, x in enumerate(RESULT_VECTORS)],
)
def test_negative_result_metadata(original, field, value, reason):
    m, p, c = original
    results = (replace(p.results[0], **{field: value}), *p.results[1:])
    d = e.inspect(m, replace(p, results=results), c)
    assert reason in d.reasons
    assert not d.official_cited_gate_pass


@pytest.mark.parametrize(
    "field,value,reason", CLAIM_VECTORS,
    ids=[f"claim-{x[0]}" for x in CLAIM_VECTORS],
)
def test_negative_signer_claim(original, field, value, reason):
    m, p, c = original
    claims = (replace(p.claims[0], **{field: value}), *p.claims[1:])
    d = e.inspect(m, replace(p, claims=claims), c)
    assert reason in d.reasons
    assert d.authority != "EXTERNAL_AUTHORITY_VERIFIED"


PACKET_VECTORS = [
    ("run_id", "", "MANIFEST_RUN_OR_EXECUTED_IMAGE_MISMATCH"),
    ("manifest_sha256", "0" * 64, "MANIFEST_RUN_OR_EXECUTED_IMAGE_MISMATCH"),
    ("candidate_image_sha256", "0" * 64, "MANIFEST_RUN_OR_EXECUTED_IMAGE_MISMATCH"),
    ("rubric_id", "rubric-wrong", "RUBRIC_OR_VERSION_CONFLICT"),
    ("rubric_version", "version-wrong", "RUBRIC_OR_VERSION_CONFLICT"),
]


@pytest.mark.parametrize(
    "field,value,reason", PACKET_VECTORS,
    ids=[f"packet-{x[0]}" for x in PACKET_VECTORS],
)
def test_negative_packet_binding(original, field, value, reason):
    m, p, c = original
    d = e.inspect(m, replace(p, **{field: value}), c)
    assert reason in d.reasons


def test_negative_duplicate_case_id(original):
    m, p, c = original
    duplicate = replace(m.cases[1], case_id=m.cases[0].case_id)
    d = e.inspect(replace(m, cases=(m.cases[0], duplicate, *m.cases[2:])), p, c)
    assert "DUPLICATE_EXPOSED_OR_UNVERIFIED_CASE" in d.reasons


def test_negative_duplicate_lexical_digest(original):
    m, p, c = original
    duplicate = replace(
        m.cases[1], lexical_dedup_digest=m.cases[0].lexical_dedup_digest
    )
    d = e.inspect(replace(m, cases=(m.cases[0], duplicate, *m.cases[2:])), p, c)
    assert "DUPLICATE_EXPOSED_OR_UNVERIFIED_CASE" in d.reasons


def test_negative_all_questions_same_semantic_intent(original):
    m, p, c = original
    cases = tuple(replace(x, intent_digest=sha("same-intent")) for x in m.cases)
    d = e.inspect(replace(m, cases=cases), p, c)
    assert "INSUFFICIENT_DISTINCT_INTENT_ATTESTATION" in d.reasons


def test_negative_shrinking_original_523_denominator(original):
    m, p, c = original
    d = e.inspect(replace(m, cases=m.cases[:-1]), p, c)
    assert "FROZEN_DENOMINATOR_NOT_EXACT" in d.reasons


def test_negative_replay_under_original_label(original):
    m, p, c = original
    cases = (replace(m.cases[0], exposed_before=True), *m.cases[1:])
    d = e.inspect(replace(m, cases=cases), p, c)
    assert "DUPLICATE_EXPOSED_OR_UNVERIFIED_CASE" in d.reasons


def test_negative_omit_failed_case_without_denominator_reduction(original):
    m, p, c = original
    d = e.inspect(m, replace(p, results=p.results[:-1]), c)
    assert d.missing == 1
    assert d.p95_terminal_ms is None
    assert "ASSIGNED_CASE_OUTCOME_MISSING" in d.reasons


def test_negative_duplicate_result_is_not_an_extra_success(original):
    m, p, c = original
    packet = replace(p, results=(*p.results[:-1], p.results[0]))
    d = e.inspect(m, packet, c)
    assert d.cited_qualified == 522
    assert d.missing == 1
    assert "DUPLICATE_OR_UNASSIGNED_RESULT" in d.reasons


def test_negative_unassigned_result_never_inflates_success(original):
    m, p, c = original
    packet = replace(p, results=(*p.results, replace(
        p.results[0], case_id="unknown-case"
    )))
    d = e.inspect(m, packet, c)
    assert d.cited_qualified == 523
    assert "DUPLICATE_OR_UNASSIGNED_RESULT" in d.reasons


def test_negative_missing_one_signer(original):
    m, p, c = original
    d = e.inspect(m, replace(p, claims=p.claims[:-1]), c)
    assert "REQUIRED_INDEPENDENT_AUTHORITY_MISSING" in d.reasons


def test_negative_fake_external_tier_does_not_validate_signature(original):
    m, p, c = original
    root = replace(c.roots[0], ed25519_public_key=bytes(32),
                   tier="AUTHORIZED_EXTERNAL")
    d = e.inspect(m, p, replace(c, roots=(root, *c.roots[1:]),
                                externally_provisioned=True,
                                independent_custodian_nominated=True))
    assert "SIGNATURE_OR_INDEPENDENT_TRUST_ROOT_INVALID" in d.reasons


def test_negative_unsigned_source_revision_registry(original):
    m, p, c = original
    revisions = dict(c.source_revisions)
    revisions["src-000"] = ("fake-revision", sha("fake"), sha("span"))
    d = e.inspect(m, p, replace(c, source_revisions=revisions))
    assert "SOURCE_REVISION_OR_SPAN_SHA_INDEPENDENT_MISMATCH" in d.reasons


def test_negative_broken_seal(original):
    m, p, c = original
    d = e.inspect(m, p, replace(c, sealed_dataset_hashes={}))
    assert "SEALED_DATASET_NOT_INDEPENDENTLY_MATCHED" in d.reasons


def test_negative_unapproved_rights_and_rubric(original):
    m, p, c = original
    d = e.inspect(m, p, replace(c, approved_licenses=frozenset(),
                                approved_rubrics=frozenset()))
    assert "LICENSE_RIGHTS_NOT_INDEPENDENTLY_APPROVED" in d.reasons
    assert "RUBRIC_NOT_INDEPENDENTLY_APPROVED" in d.reasons


def test_negative_forged_image_registry(original):
    m, p, c = original
    d = e.inspect(m, p, replace(c, authorized_images=frozenset()))
    assert "EXECUTED_IMAGE_NOT_INDEPENDENTLY_ATTESTED" in d.reasons


def test_negative_caller_claims_fake_external_without_external_roots(original):
    m, p, c = original
    d = e.inspect(m, p, replace(c, externally_provisioned=True,
                                independent_custodian_nominated=True))
    assert "FIXTURE_SIGNATURE_NOT_REAL_AUTHORITY" in d.reasons
    assert not d.official_cited_gate_pass


def test_negative_independent_per_case_review_missing(original):
    m, p, c = original
    reviewed = dict(c.reviewed_cases)
    del reviewed[m.cases[0].case_id]
    d = e.inspect(m, p, replace(c, reviewed_cases=reviewed))
    assert "PER_CASE_INDEPENDENT_REVIEW_MISSING" in d.reasons


def test_negative_fake_reviewer_roster(original):
    m, p, c = original
    d = e.inspect(replace(m, reviewer_ids=("implementer-fixture", "reviewer-one")),
                  p, c)
    assert "INDEPENDENT_REVIEWERS_NOT_VERIFIED" in d.reasons


def test_negative_source_origin_family_collision(original):
    m, p, c = original
    other = replace(m.sources[1], origin_id=m.sources[0].origin_id,
                    family_id="family-conflicting")
    d = e.inspect(replace(m, sources=(m.sources[0], other, *m.sources[2:])), p, c)
    assert "SOURCE_FAMILY_ORIGIN_COLLISION" in d.reasons


def test_negative_registered_taxonomy_mismatch(original):
    m, p, c = original
    tax = dict(c.source_taxonomy)
    tax[m.sources[0].source_id] = ("misleading-document", "family-0", "origin-0")
    d = e.inspect(m, p, replace(c, source_taxonomy=tax))
    assert "SOURCE_ORIGIN_INDEPENDENCE_NOT_VERIFIED" in d.reasons


def test_negative_many_unreferenced_source_pins(original):
    m, p, c = original
    cases = tuple(replace(x, source_id="src-000") for x in m.cases)
    d = e.inspect(replace(m, cases=cases), p, c)
    assert "INSUFFICIENT_USED_SOURCE_DIVERSITY" in d.reasons
