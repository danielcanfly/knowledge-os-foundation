"""Independent V05N adversarial contract suite, using synthetic signed test evidence."""
from __future__ import annotations

import hashlib
import hmac
import io
import subprocess
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from knowledge_engine import m27_ar05_independent_verifier_v1_experimental as v

KEYS = {
    ("runner", "runner-external"): b"test-runner-local-secret",
    ("rights", "idp-independent"): b"test-rights-local-secret",
    ("citation_oracle", "source-reviewer"): b"test-review-local-secret",
    ("server_transport", "transport-server"): b"test-server-local-secret",
    ("client_ack", "client-external"): b"test-client-local-secret",
    ("observer", "observer-external"): b"test-observer-local-secret",
    ("billing", "billing-external"): b"test-billing-local-secret",
    ("verifier", "verifier-external"): b"test-verifier-local-secret",
}
SOURCE = b"Original authorized fact: evidence is a concrete original span."
QUOTE = b"evidence is a concrete original span"
TEXT = b"Verified fixture answer with citation."


class FakeTrust:
    """Deliberately LOCAL fake HMAC. No production signer or issuer authority."""

    def sign(self, obj: object) -> object:
        role = obj.proof.domain
        key = KEYS.get((role, obj.proof.issuer_id), b"untrusted-fixture-key")
        sig = hmac.new(key, v._message(role, obj), hashlib.sha256).hexdigest()
        return replace(obj, proof=replace(obj.proof, signature=sig))

    def verify(
        self, issuer_id: str, key_id: str, domain: str, message: bytes, signature: str
    ) -> bool:
        secret = KEYS.get((domain, issuer_id))
        return key_id == "fixture-key" and secret is not None and hmac.compare_digest(
            hmac.new(secret, message, hashlib.sha256).hexdigest(), signature
        )


def proof(role: str, issuer: str) -> v.SignedProof:
    return v.SignedProof(issuer, "fixture-key", role, "")


def seal(b: v.EvidenceBundle, trust: FakeTrust) -> v.EvidenceBundle:
    """Re-sign modified test evidence to test verification content, not just bad MAC."""
    b = replace(
        b,
        execution=trust.sign(b.execution),
        rights=tuple(trust.sign(x) for x in b.rights),
        reviews=tuple(trust.sign(x) for x in b.reviews),
        server=trust.sign(b.server),
        client_acks=tuple(trust.sign(x) for x in b.client_acks),
        operation=trust.sign(b.operation) if b.operation else None,
        cost=trust.sign(b.cost),
    )
    b = v.finalize_test_fixture(b)
    return replace(b, verifier=trust.sign(b.verifier))


@pytest.fixture
def valid(tmp_path: Path) -> tuple[v.EvidenceBundle, v.VerificationContext, FakeTrust]:
    work = tmp_path / "sandbox"
    work.mkdir()
    (work / "result.txt").write_bytes(b"real fixture artifact\n")
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    subprocess.run(["git", "-C", str(work), "add", "result.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(work), "-c", "user.name=Fixture",
         "-c", "user.email=fixture@example.invalid", "commit", "-q", "-m", "fixture"],
        check=True,
    )
    head = subprocess.check_output(
        ["git", "-C", str(work), "rev-parse", "HEAD"], text=True
    ).strip()
    roots = tuple((domain, issuer) for domain, issuer in KEYS)
    ctx = v.VerificationContext(
        "tenant", "task", 1, "run", "outcome", v.sha(b"outcome"), v.sha(b"head-7"),
        2, v.sha(b"head-7"), str(work), head,
        ("python3", "-m", "pytest", "-q", "tests/test_result.py"),
        "RESEARCH", (("source-1", "r1"), ("source-2", "r2")),
        "principal", "authorized-audience", 1000,
        trust_issuers=roots,
    )
    artifact_bytes = (work / "result.txt").read_bytes()
    artifact = v.ArtifactEvidenceV1(
        str(work), "result.txt", len(artifact_bytes), v.sha(artifact_bytes), head,
        "tenant", "task", "run", "outcome"
    )
    execution = v.ExecutionReceipt(
        str(work), head, artifact.sha256, ctx.required_command, str(work),
        True, 0, 2345, 400, 600, 4, 30, v.sha(b"stdout"),
        v.sha(b"stderr"), "runner-execution-1", proof("runner", "runner-external"),
    )
    rights = tuple(v.SourceRights(
        source_id, revision,
        v.sha(SOURCE if source_id == "source-1" else b"Counterfact original source"),
        "tenant", "principal", "authorized-audience", True, False, 2000,
        proof("rights", "idp-independent"),
    ) for source_id, revision in ctx.approved_revisions)
    sources = (
        v.NativeSource("source-1", "r1", SOURCE, v.sha(SOURCE)),
        v.NativeSource("source-2", "r2", b"Counterfact original source", v.sha(
            b"Counterfact original source"
        )),
    )
    start = SOURCE.index(QUOTE)
    citation = v.NativeCitationProof(
        "cit-1", "source-1", "r1", v.sha(SOURCE), start, start + len(QUOTE),
        QUOTE, v.sha(QUOTE),
    )
    review = v.CitationReview(
        "cit-1", v.sha(QUOTE), True, True, ("source-2",),
        proof("citation_oracle", "source-reviewer"),
    )
    frame = v.VerifiedFrame(
        "verified_text", TEXT, ("cit-1",), "verifier-external",
        "session-1", "nonce-1", "segment-1", 3, 700, 950,
    )
    server = v.ServerTransportProof(
        "FLUSHED", "session-1", "nonce-1", "segment-1", 3, v.sha(TEXT),
        750, proof("server_transport", "transport-server"),
    )
    ack = v.TransportAckProof(
        "ack-1", "session-1", "nonce-1", "segment-1", 3, v.sha(TEXT),
        12, 800, proof("client_ack", "client-external"),
    )
    operation = v.OperationObservation(
        ("op-1", "op-2"), ("op-1", "op-2"), "APPLIED",
        "source-version-2", True, proof("observer", "observer-external"),
    )
    cost = v.CostEvidence(
        ("charge-1",), 4, 4, 5, True, proof("billing", "billing-external"),
    )
    verifier = v.VerifierAttestation(
        "verifier-external", "", ctx.journal_head_sha256,
        900, proof("verifier", "verifier-external"),
    )
    bundle = v.EvidenceBundle(
        artifact, execution, v.VerifierIdentity(
            "generator", "verifier-external", "verifier", "runner"
        ), sources, rights, (citation,), (review,), frame, server, (ack,),
        operation, cost, verifier, ctx.tenant_id, ctx.task_id,
        ctx.task_version, ctx.run_id, ctx.outcome_id, ctx.outcome_sha256,
        ctx.journal_head_sha256, ctx.journal_epoch, "terminal-1",
    )
    trust = FakeTrust()
    return seal(bundle, trust), ctx, trust


def test_valid_research_is_bounded_only(valid: tuple) -> None:
    bundle, ctx, trust = valid
    result = v.propose_eligibility(bundle, ctx, trust=trust)
    assert result.status == v.SUCCESS
    assert result.failures == ()
    assert result.checked_artifact_sha256 == bundle.artifact.sha256
    assert not result.can_terminalize and not result.can_publish
    assert not result.real_client_delivery_proven and not result.ar02_mutated


def test_test_only_no_verification_trust(valid: tuple) -> None:
    b, c, _ = valid
    result = v.propose_eligibility(b, c, trust=None)
    assert result.status == v.DENIED
    assert "VERIFIER_NOT_INDEPENDENT" in result.failures


ADVERSARIAL = [
    ("forged_runner", "RUNNER_AUTH_UNVERIFIED"),
    ("runner_did_not_execute", "RUNNER_EXECUTED"),
    ("wrong_ci_exit", "RUNNER_GREEN_EXIT"),
    ("no_positive_tests", "RUNNER_TEST_COUNTS"),
    ("less_than_25_negative", "RUNNER_TEST_COUNTS"),
    ("runner_wrong_command", "RUNNER_COMMAND"),
    ("runner_wrong_cwd", "RUNNER_CWD"),
    ("runner_missing_log_hash", "RUNNER_LOG_HASH"),
    ("runner_execution_replay", "RUNNER_REPLAY"),
    ("changed_artifact_claim", "ARTIFACT_CONTENT_CHANGED"),
    ("wrong_pinned_commit", "PINNED_HEAD"),
    ("stale_journal_head", "STALE_JOURNAL_HEAD"),
    ("wrong_tenant", "IDENTITY_TENANT_ID"),
    ("wrong_task_version", "IDENTITY_TASK_VERSION"),
    ("wrong_outcome", "IDENTITY_OUTCOME_SHA256"),
    ("source_revision_changed", "SOURCE_REVISION"),
    ("source_modified_original", "SOURCE_ORIGINAL_BYTES"),
    ("source_grant_revoked", "SOURCE_RIGHTS_EXPIRED_OR_WRONG"),
    ("source_grant_expired", "SOURCE_RIGHTS_EXPIRED_OR_WRONG"),
    ("wrong_source_tenant", "SOURCE_RIGHTS_EXPIRED_OR_WRONG"),
    ("forged_rights_issuer", "SOURCE_RIGHTS_NOT_INDEPENDENT"),
    ("fabricated_citation_id", "CITATION_UNKNOWN_SOURCE"),
    ("citation_wrong_span", "CITATION_SPAN_UNSUPPORTED"),
    ("citation_claim_bytes_wrong", "CITATION_SPAN_UNSUPPORTED"),
    ("citation_wrong_revision", "CITATION_SOURCE_IDENTITY"),
    ("citation_missing_review", "MISSING_SEMANTIC_REVIEW"),
    ("unsupported_citation", "CITATION_SEMANTIC_UNSUPPORTED"),
    ("review_signed_by_generator", "CITATION_ORACLE_NOT_INDEPENDENT"),
    ("missing_counterevidence", "COUNTEREVIDENCE_MISSING"),
    ("unsupported_counterevidence_id", "COUNTEREVIDENCE_MISSING"),
    ("progress_frame", "NO_MATERIAL_VERIFIED_TEXT"),
    ("invalid_utf8_frame", "INVALID_STREAM_UTF8"),
    ("empty_frame", "NO_MATERIAL_VERIFIED_TEXT"),
    ("no_frame_citations", "STREAM_CITATIONS_INVALID"),
    ("frame_after_terminal", "STREAM_NOT_PRETERMINAL"),
    ("queued_not_flushed", "NOT_FLUSHED_PRETERMINAL"),
    ("server_flag_only_ack_missing", "CLIENT_ACK_COUNT"),
    ("server_frame_wrong_revision", "SERVER_FRAME_BINDING"),
    ("client_session_mismatch", "CLIENT_ACK_FRAME_BINDING"),
    ("client_segment_mismatch", "CLIENT_ACK_FRAME_BINDING"),
    ("client_revision_mismatch", "CLIENT_ACK_FRAME_BINDING"),
    ("client_nonce_mismatch", "CLIENT_ACK_FRAME_BINDING"),
    ("client_payload_mismatch", "CLIENT_ACK_FRAME_BINDING"),
    ("client_ack_reconnect_replay", "DUPLICATE_OR_REPLAYED_ACK"),
    ("duplicate_ack", "CLIENT_ACK_COUNT"),
    ("client_ack_invalid_mac", "CLIENT_ACK_NOT_AUTHENTICATED"),
    ("ack_after_terminal", "CLIENT_ACK_TIME"),
    ("replayed_terminal", "REPLAYED_TERMINAL"),
    ("response_generated_proof", "SELF_GENERATED_PROOF"),
    ("unknown_effect", "UNRESOLVED_OR_TERMINAL"),
    ("already_terminal", "UNRESOLVED_OR_TERMINAL"),
    ("incomplete_operation", "OPERATION_INCOMPLETE_OR_UNKNOWN"),
    ("unknown_operation_effect", "OPERATION_INCOMPLETE_OR_UNKNOWN"),
    ("action_missing_external_observer", "EXTERNAL_OBSERVER_MISSING"),
    ("observer_is_generator", "OBSERVER_NOT_INDEPENDENT"),
    ("cost_unpriced", "COST_UNPRICED_OR_UNRECONCILED"),
    ("cost_unreconciled", "COST_UNPRICED_OR_UNRECONCILED"),
    ("cost_overspent", "COST_UNPRICED_OR_UNRECONCILED"),
    ("duplicate_charge", "COST_UNPRICED_OR_UNRECONCILED"),
    ("verifier_is_runner", "VERIFIER_NOT_INDEPENDENT"),
    ("verifier_root_tampered", "VERIFIER_EVIDENCE_BINDING"),
    ("verifier_wrong_key", "VERIFIER_NOT_INDEPENDENT"),
]


@pytest.mark.parametrize(("case", "expected"), ADVERSARIAL)
def test_adversarial_matrix(case: str, expected: str, valid: tuple) -> None:
    b, c, trust = valid
    if case == "forged_runner":
        b = replace(b, execution=replace(
            b.execution, proof=proof("runner", "model-forged-runner")
        ))
    elif case == "runner_did_not_execute":
        b = replace(b, execution=replace(b.execution, executed=False))
    elif case == "wrong_ci_exit":
        b = replace(b, execution=replace(b.execution, exit_code=1))
    elif case == "no_positive_tests":
        b = replace(b, execution=replace(b.execution, positive_tests=0))
    elif case == "less_than_25_negative":
        b = replace(b, execution=replace(b.execution, negative_tests=24))
    elif case == "runner_wrong_command":
        b = replace(b, execution=replace(b.execution, command=("echo", "PASS")))
    elif case == "runner_wrong_cwd":
        b = replace(b, execution=replace(b.execution, command_cwd="/tmp"))
    elif case == "runner_missing_log_hash":
        b = replace(b, execution=replace(b.execution, stderr_sha256="missing"))
    elif case == "runner_execution_replay":
        c = replace(c, seen_execution_ids=frozenset({"runner-execution-1"}))
    elif case == "changed_artifact_claim":
        b = replace(b, artifact=replace(b.artifact, sha256=v.sha(b"forged")))
    elif case == "wrong_pinned_commit":
        b = replace(b, artifact=replace(b.artifact, pinned_head="a" * 40))
    elif case == "stale_journal_head":
        c = replace(c, current_journal_head_sha256=v.sha(b"new-head"))
    elif case == "wrong_tenant":
        b = replace(b, tenant_id="other-tenant")
    elif case == "wrong_task_version":
        b = replace(b, task_version=2)
    elif case == "wrong_outcome":
        b = replace(b, outcome_sha256=v.sha(b"wrong"))
    elif case == "source_revision_changed":
        b = replace(b, sources=(replace(b.sources[0], revision="r-stale"), b.sources[1]))
    elif case == "source_modified_original":
        b = replace(b, sources=(replace(
            b.sources[0], original_bytes=b"tampered" + SOURCE
        ), b.sources[1]))
    elif case in {"source_grant_revoked", "source_grant_expired", "wrong_source_tenant",
                  "forged_rights_issuer"}:
        alterations = {
            "source_grant_revoked": {"revoked": True},
            "source_grant_expired": {"expires_at_ms": 1000},
            "wrong_source_tenant": {"tenant_id": "other"},
            "forged_rights_issuer": {"proof": proof("rights", "generator")},
        }
        b = replace(b, rights=(replace(
            b.rights[0], **alterations[case]
        ), b.rights[1]))
    elif case == "fabricated_citation_id":
        b = replace(b, citations=(replace(b.citations[0], source_id="invented"),))
    elif case in {"citation_wrong_span", "citation_claim_bytes_wrong",
                  "citation_wrong_revision"}:
        alterations = {
            "citation_wrong_span": {"claim_start": 99999},
            "citation_claim_bytes_wrong": {"quoted_original_bytes": b"fabricated"},
            "citation_wrong_revision": {"source_revision": "r-2"},
        }
        b = replace(b, citations=(replace(b.citations[0], **alterations[case]),))
    elif case == "citation_missing_review":
        b = replace(b, reviews=())
    elif case == "unsupported_citation":
        b = replace(b, reviews=(replace(b.reviews[0], semantic_supported=False),))
    elif case == "review_signed_by_generator":
        b = replace(b, reviews=(replace(
            b.reviews[0], proof=proof("citation_oracle", "generator")
        ),))
    elif case in {"missing_counterevidence", "unsupported_counterevidence_id"}:
        b = replace(b, reviews=(replace(
            b.reviews[0], counterevidence_ids=(
                () if case == "missing_counterevidence" else ("invented",)
            )
        ),))
    elif case == "progress_frame":
        b = replace(b, frame=replace(b.frame, kind="progress"))
    elif case == "invalid_utf8_frame":
        b = replace(b, frame=replace(b.frame, content=b"\xff\xfe"))
    elif case == "empty_frame":
        b = replace(b, frame=replace(b.frame, content=b"  "))
    elif case == "no_frame_citations":
        b = replace(b, frame=replace(b.frame, citation_ids=()))
    elif case == "frame_after_terminal":
        b = replace(b, frame=replace(b.frame, first_text_sent_at_ms=951))
    elif case == "queued_not_flushed":
        b = replace(b, server=replace(b.server, stage="QUEUED", flushed_at_ms=None))
    elif case == "server_flag_only_ack_missing":
        b = replace(b, client_acks=())
    elif case == "server_frame_wrong_revision":
        b = replace(b, server=replace(b.server, revision=9))
    elif case.startswith("client_") and case.endswith("_mismatch"):
        field = {
            "client_session_mismatch": ("session_id", "other-session"),
            "client_segment_mismatch": ("segment_id", "other-segment"),
            "client_revision_mismatch": ("revision", 4),
            "client_nonce_mismatch": ("nonce", "other-nonce"),
            "client_payload_mismatch": ("payload_sha256", v.sha(b"other")),
        }[case]
        b = replace(b, client_acks=(replace(b.client_acks[0], **{field[0]: field[1]}),))
    elif case == "client_ack_reconnect_replay":
        c = replace(c, seen_ack_ids=frozenset({"ack-1"}))
    elif case == "duplicate_ack":
        b = replace(b, client_acks=b.client_acks + b.client_acks)
    elif case == "client_ack_invalid_mac":
        b = replace(b, client_acks=(replace(
            b.client_acks[0], proof=proof("client_ack", "generator")
        ),))
    elif case == "ack_after_terminal":
        b = replace(b, client_acks=(replace(
            b.client_acks[0], received_at_ms=951
        ),))
    elif case == "replayed_terminal":
        c = replace(c, committed_terminal_ids=frozenset({"terminal-1"}))
    elif case == "response_generated_proof":
        b = replace(b, response_generated_proof=True)
    elif case == "unknown_effect":
        b = replace(b, unknown_effect=True)
    elif case == "already_terminal":
        b = replace(b, terminal_already_committed=True)
    elif case == "incomplete_operation":
        b = replace(b, operation=replace(b.operation, completed_ids=("op-1",)))
    elif case == "unknown_operation_effect":
        b = replace(b, operation=replace(b.operation, effect="UNKNOWN_EFFECT"))
    elif case == "action_missing_external_observer":
        c = replace(c, workload="ACTION")
        b = replace(b, operation=None)
    elif case == "observer_is_generator":
        b = replace(b, operation=replace(
            b.operation, proof=proof("observer", "generator")
        ))
    elif case in {"cost_unpriced", "cost_unreconciled", "cost_overspent",
                  "duplicate_charge"}:
        alterations = {
            "cost_unpriced": {"actual_microunits": None},
            "cost_unreconciled": {"late_billing_reconciled": False},
            "cost_overspent": {"actual_microunits": 6},
            "duplicate_charge": {"charge_ids": ("charge-1", "charge-1")},
        }
        b = replace(b, cost=replace(b.cost, **alterations[case]))
    elif case == "verifier_is_runner":
        b = replace(b, verifier=replace(
            b.verifier, proof=proof("verifier", "runner-external")
        ))
    elif case == "verifier_root_tampered":
        b = replace(b, verifier=replace(b.verifier, journal_head_sha256="broken"))
    elif case == "verifier_wrong_key":
        b = replace(b, verifier=replace(
            b.verifier, proof=replace(b.verifier.proof, key_id="wrong-key")
        ))
    else:
        raise AssertionError(f"Unimplemented adversarial case: {case}")
    b = seal(b, trust)
    decision = v.propose_eligibility(b, c, trust=trust)
    assert decision.status == v.DENIED, case
    assert expected in decision.failures, (case, decision.failures)
    assert not decision.can_terminalize and not decision.can_publish


def test_real_file_mutation_breaks_artifact_hash(valid: tuple) -> None:
    b, c, trust = valid
    (Path(c.workspace_root) / "result.txt").write_bytes(b"post-attestation malicious change")
    result = v.propose_eligibility(b, c, trust=trust)
    assert "ARTIFACT_CONTENT_CHANGED" in result.failures


def test_relative_traversal_is_denied(valid: tuple) -> None:
    b, c, trust = valid
    b = seal(replace(b, artifact=replace(b.artifact, relative_path="../escape")), trust)
    assert "ARTIFACT_PATH_TRAVERSAL" in v.propose_eligibility(b, c, trust=trust).failures


def test_symlink_escape_is_denied(valid: tuple, tmp_path: Path) -> None:
    b, c, trust = valid
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"outside file")
    (Path(c.workspace_root) / "linked").symlink_to(outside)
    b = seal(replace(b, artifact=replace(b.artifact, relative_path="linked")), trust)
    result = v.propose_eligibility(b, c, trust=trust)
    assert "ARTIFACT_UNSAFE_ARTIFACT_PATH" in result.failures


def test_zip_bomb_unpacked_size_is_denied(valid: tuple) -> None:
    b, c, trust = valid
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("large.txt", b"A" * 8_000_000)
    encoded = memory.getvalue()
    (Path(c.workspace_root) / "result.zip").write_bytes(encoded)
    a = replace(b.artifact, relative_path="result.zip",
                byte_length=len(encoded), sha256=v.sha(encoded))
    run = replace(b.execution, artifact_sha256=v.sha(encoded))
    b = seal(replace(b, artifact=a, execution=run), trust)
    result = v.propose_eligibility(b, c, trust=trust)
    assert "ARTIFACT_OVERSIZED_ARCHIVE" in result.failures


def test_archive_path_escape_is_denied(valid: tuple) -> None:
    b, c, trust = valid
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w") as z:
        z.writestr("../escape.txt", b"invalid")
    data = memory.getvalue()
    (Path(c.workspace_root) / "result.zip").write_bytes(data)
    b = seal(replace(
        b, artifact=replace(
            b.artifact, relative_path="result.zip",
            byte_length=len(data), sha256=v.sha(data)
        ), execution=replace(b.execution, artifact_sha256=v.sha(data))
    ), trust)
    result = v.propose_eligibility(b, c, trust=trust)
    assert "ARTIFACT_UNSAFE_ARCHIVE_ENTRY" in result.failures


def test_actual_git_head_must_match_pinned(valid: tuple) -> None:
    b, c, trust = valid
    path = Path(c.workspace_root)
    (path / "new-commit.txt").write_text("new commit")
    subprocess.run(["git", "-C", str(path), "add", "new-commit.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "-c", "user.name=Fixture",
         "-c", "user.email=fixture@example.invalid", "commit", "-q", "-m", "changed"],
        check=True,
    )
    result = v.propose_eligibility(b, c, trust=trust)
    assert "WORKTREE_HEAD_NOW" in result.failures


def test_attestation_cannot_be_reused_on_different_frame(valid: tuple) -> None:
    b, c, trust = valid
    altered = replace(b, frame=replace(b.frame, content=b"later output"))
    decision = v.propose_eligibility(altered, c, trust=trust)
    assert "VERIFIER_EVIDENCE_BINDING" in decision.failures


@pytest.mark.parametrize("workload", ["CODING", "QA", "ACTION"])
def test_valid_other_workload_is_fixture_only(workload: str, valid: tuple) -> None:
    b, c, trust = valid
    result = v.propose_eligibility(b, replace(c, workload=workload), trust=trust)
    assert result.status == v.SUCCESS, result.failures
    assert not result.can_publish and not result.can_terminalize
    assert not result.real_client_delivery_proven


def test_regular_oversize_is_denied(valid: tuple) -> None:
    b, c, trust = valid
    oversized = b"F" * (c.max_artifact_bytes + 1)
    (Path(c.workspace_root) / "result.txt").write_bytes(oversized)
    b = seal(replace(
        b, artifact=replace(b.artifact, byte_length=len(oversized), sha256=v.sha(oversized)),
        execution=replace(b.execution, artifact_sha256=v.sha(oversized))
    ), trust)
    result = v.propose_eligibility(b, c, trust=trust)
    assert "ARTIFACT_OVERSIZED_ARTIFACT" in result.failures


def test_nested_symlink_is_denied(valid: tuple, tmp_path: Path) -> None:
    b, c, trust = valid
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "result.txt").write_bytes(b"other")
    (Path(c.workspace_root) / "shortcut").symlink_to(tmp_path / "outside")
    b = seal(replace(b, artifact=replace(
        b.artifact, relative_path="shortcut/result.txt"
    )), trust)
    result = v.propose_eligibility(b, c, trust=trust)
    assert "ARTIFACT_UNSAFE_ARTIFACT_PATH" in result.failures


def test_runner_proof_cannot_be_copied_to_new_artifact(valid: tuple) -> None:
    b, c, trust = valid
    mutated = replace(b, artifact=replace(
        b.artifact, sha256=v.sha(b"different artifact digest")
    ))
    decision = v.propose_eligibility(mutated, c, trust=trust)
    assert "RUNNER_ARTIFACT_HASH" in decision.failures
    assert "VERIFIER_EVIDENCE_BINDING" in decision.failures


def test_original_source_bytes_must_match_independently_signed_rights(valid: tuple) -> None:
    b, c, trust = valid
    modified = replace(
        b, rights=(replace(b.rights[0], bytes_sha256=v.sha(b"foreign bytes")),
                   b.rights[1])
    )
    result = v.propose_eligibility(seal(modified, trust), c, trust=trust)
    assert "SOURCE_RIGHTS_EXPIRED_OR_WRONG" in result.failures
    assert not result.can_terminalize
