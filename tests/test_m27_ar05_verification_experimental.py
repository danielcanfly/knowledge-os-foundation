from __future__ import annotations

import hashlib
import hmac
from dataclasses import replace

import pytest

from knowledge_engine.m27_ar05_verification_experimental import (
    CitationBinding,
    ContentFrame,
    HardGate,
    JournalSnapshot,
    NativeEvidenceFixture,
    PublicationCandidate,
    VerificationDenied,
    VerificationPublicationGate,
    VerificationReceipt,
    verification_message,
)

SECRET = b"synthetic-verifier-secret"
CONTENT = b"verified synthetic answer"
CONTENT_SHA = hashlib.sha256(CONTENT).hexdigest()


def gate() -> VerificationPublicationGate:
    return VerificationPublicationGate(
        verifier_keys={"trusted-key": SECRET},
        signer_for_key={"trusted-key": "independent-verifier"},
        generator_id="answer-generator",
    )


def snapshot(**changes: object) -> JournalSnapshot:
    base = JournalSnapshot(
        tenant_id="tenant-a",
        task_id="task-a",
        task_version=1,
        run_id="run-a",
        attempt=2,
        head_seq=11,
        head_hash="a" * 64,
        lease_epoch=7,
        outcome_id="outcome-a",
        outcome_digest="b" * 64,
        unknown_effect=False,
    )
    return replace(base, **changes)


def unsigned_receipt(**changes: object) -> VerificationReceipt:
    base = VerificationReceipt(
        verification_id="verification-a",
        signer_id="independent-verifier",
        key_id="trusted-key",
        tenant_id="tenant-a",
        task_id="task-a",
        task_version=1,
        run_id="run-a",
        attempt=2,
        outcome_id="outcome-a",
        outcome_digest="b" * 64,
        journal_head_seq=11,
        journal_head_hash="a" * 64,
        lease_epoch=7,
        checked_at=100,
        expires_at=200,
        hard_gates=(
            HardGate("policy", "pass"),
            HardGate("provenance", "pass"),
            HardGate("citation", "pass"),
        ),
        signature="",
    )
    return replace(base, **changes)


def signed_receipt(**changes: object) -> VerificationReceipt:
    value = unsigned_receipt(**changes)
    signature = hmac.new(SECRET, verification_message(value), hashlib.sha256).hexdigest()
    return replace(value, signature=signature)


def evidence(**changes: object) -> NativeEvidenceFixture:
    citation = CitationBinding(
        citation_id="citation-1",
        source_id="source-1",
        source_revision="revision-1",
        source_bytes_sha256=CONTENT_SHA,
        claim_start=0,
        claim_end=8,
    )
    base = NativeEvidenceFixture(
        identity_kind="native",
        content_bytes=CONTENT,
        content_sha256=CONTENT_SHA,
        citations=(citation,),
    )
    return replace(base, **changes)


def publication(**changes: object) -> PublicationCandidate:
    original = evidence()
    base = PublicationCandidate(
        publication_id="publication-a",
        segment_id="segment-a",
        revision=1,
        irreversible=False,
        claim_client_delivered=False,
        original_evidence=original,
        observed_evidence=original,
        expected_citation_ids=("citation-1",),
        frames=(
            ContentFrame("progress", "progress", b"working", (), None, True, None),
            ContentFrame(
                "verified",
                "verified_text",
                b"supported answer",
                ("citation-1",),
                "verification-a",
                True,
                "client-ack-1",
            ),
            ContentFrame("terminal", "terminal", b"done", (), None, True, None),
        ),
    )
    return replace(base, **changes)


def evaluate(
    *,
    journal: JournalSnapshot | None = None,
    receipt: VerificationReceipt | None = None,
    candidate: PublicationCandidate | None = None,
):
    return gate().evaluate(
        snapshot=journal or snapshot(),
        receipt=receipt or signed_receipt(),
        publication=candidate or publication(),
        now=110,
    )


@pytest.mark.parametrize(
    "receipt_changes",
    [
        {"tenant_id": "tenant-b"},
        {"run_id": "run-b"},
        {"attempt": 3},
        {"task_version": 2},
        {"outcome_digest": "c" * 64},
        {"journal_head_seq": 10},
        {"journal_head_hash": "d" * 64},
        {"lease_epoch": 6},
    ],
)
def test_identity_version_digest_and_stale_head_are_denied(
    receipt_changes: dict[str, object],
) -> None:
    with pytest.raises(VerificationDenied, match="IDENTITY_DIGEST_OR_STALE_HEAD_MISMATCH"):
        evaluate(receipt=signed_receipt(**receipt_changes))


def test_untrusted_self_signer_and_invalid_signature_are_denied() -> None:
    with pytest.raises(VerificationDenied, match="GENERATOR_SELF_SIGN_DENIED"):
        evaluate(receipt=signed_receipt(signer_id="answer-generator"))
    with pytest.raises(VerificationDenied, match="UNTRUSTED_VERIFIER"):
        evaluate(receipt=replace(unsigned_receipt(key_id="other-key"), signature="0" * 64))
    with pytest.raises(VerificationDenied, match="INVALID_VERIFIER_SIGNATURE"):
        evaluate(receipt=replace(unsigned_receipt(), signature="0" * 64))


def test_expired_unknown_effect_missing_hard_gate_and_terminal_fail_closed() -> None:
    with pytest.raises(VerificationDenied, match="PROOF_EXPIRED_OR_FROM_FUTURE"):
        evaluate(receipt=signed_receipt(expires_at=100))
    with pytest.raises(VerificationDenied, match="UNKNOWN_EFFECT"):
        evaluate(journal=snapshot(unknown_effect=True))
    with pytest.raises(VerificationDenied, match="HARD_GATE_NOT_PASS"):
        evaluate(
            receipt=signed_receipt(
                hard_gates=(HardGate("policy", "pass"), HardGate("citation", "indeterminate"))
            )
        )
    with pytest.raises(VerificationDenied, match="TERMINAL_IMMUTABLE"):
        evaluate(journal=snapshot(terminal=True))


def test_original_bytes_digest_and_native_identity_are_immutable() -> None:
    changed_bytes = evidence(content_bytes=b"changed bytes")
    with pytest.raises(VerificationDenied, match="OBSERVED_SOURCE_BYTES_DIGEST_MISMATCH"):
        evaluate(candidate=publication(observed_evidence=changed_bytes))
    synthetic = evidence(identity_kind="synthetic")
    with pytest.raises(VerificationDenied, match="NATIVE_SYNTHETIC_MIXUP"):
        evaluate(candidate=publication(observed_evidence=synthetic))


def test_citation_order_and_spans_cannot_be_rewritten() -> None:
    first = evidence().citations[0]
    second = replace(first, citation_id="citation-2", claim_start=9, claim_end=12)
    original = evidence(citations=(first, second))
    candidate = publication(
        original_evidence=original,
        observed_evidence=original,
        expected_citation_ids=("citation-2", "citation-1"),
    )
    with pytest.raises(VerificationDenied, match="CITATION_ORDER_CHANGED"):
        evaluate(candidate=candidate)
    bad_span = evidence(citations=(replace(first, claim_end=len(CONTENT) + 1),))
    with pytest.raises(VerificationDenied, match="CITATION_BINDING_OR_SPAN_INVALID"):
        evaluate(candidate=publication(original_evidence=bad_span, observed_evidence=bad_span))


def test_progress_only_terminal_only_and_uncited_text_do_not_count() -> None:
    progress_only = publication(
        frames=(
            ContentFrame("progress", "progress", b"working", (), None, True, None),
            ContentFrame("terminal", "terminal", b"done", (), None, True, None),
        )
    )
    with pytest.raises(VerificationDenied, match="NO_VERIFIED_SUBSTANTIVE_TEXT"):
        evaluate(candidate=progress_only)
    terminal_first = publication(
        frames=(
            ContentFrame("terminal", "terminal", b"done", (), None, True, None),
            publication().frames[1],
        )
    )
    with pytest.raises(VerificationDenied, match="TERMINAL_ONLY_CONTENT"):
        evaluate(candidate=terminal_first)
    uncited = replace(publication().frames[1], citation_ids=())
    with pytest.raises(VerificationDenied, match="UNCITED_OR_REORDERED_VERIFIED_TEXT"):
        evaluate(candidate=publication(frames=(uncited, publication().frames[2])))


def test_server_emission_is_not_client_delivery_proof() -> None:
    no_ack = replace(publication().frames[1], client_ack_id=None)
    candidate = publication(frames=(no_ack, publication().frames[2]))
    proposal = evaluate(candidate=candidate)
    assert proposal.server_emission_observed is True
    assert proposal.client_delivery_proven is False
    with pytest.raises(VerificationDenied, match="CLIENT_DELIVERY_UNPROVEN"):
        evaluate(candidate=replace(candidate, claim_client_delivered=True))


def test_irreversible_sink_denies_provisional_frames() -> None:
    provisional = ContentFrame(
        "draft", "provisional", b"draft", (), None, True, None
    )
    candidate = publication(
        irreversible=True,
        frames=(provisional, publication().frames[1], publication().frames[2]),
    )
    with pytest.raises(VerificationDenied, match="IRREVERSIBLE_PROVISIONAL_DENIED"):
        evaluate(candidate=candidate)


def test_positive_result_is_only_an_eligible_proposal() -> None:
    proposal = evaluate()
    assert proposal.status == "ELIGIBLE_PROPOSAL"
    assert proposal.terminal_committed is False
    assert gate().provider_calls == 0


def test_post_terminal_correction_is_append_only_sidecar() -> None:
    notice = gate().append_terminal_notice(
        publication_id="publication-a",
        prior_revision=3,
        prior_cursor=8,
        kind="retraction",
        supersedes_segment_id="segment-a",
        content=b"withdrawn",
    )
    assert (notice.revision, notice.cursor) == (4, 9)
    assert notice.run_state_changed is False
