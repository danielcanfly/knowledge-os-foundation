"""Fresh AR05 evidence verifier: local, feature-off, nonauthoritative test component.

All successful decisions are TEST FIXTURE ONLY. Signed fixture input and local
checks are not external issuer, provider, transport, or durable AR02 authority.
No journal mutations, network, publication, production, or provider calls.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import subprocess
import zipfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol

HEX = frozenset("0123456789abcdef")
SUCCESS = "ELIGIBLE_TEST_FIXTURE_ONLY"
DENIED = "DENIED_TEST_FIXTURE_ONLY"


def sha(data: bytes) -> str:
    """Hex SHA256 of bytes actually received."""
    return hashlib.sha256(data).hexdigest()


def _valid_sha(digest: str) -> bool:
    return isinstance(digest, str) and len(digest) == 64 and set(digest) <= HEX


def canonical(obj: object) -> bytes:
    """Domain-separated deterministic serialization; byte values are never decoded."""
    def normal(value: object) -> object:
        if isinstance(value, bytes):
            return {"sha256": sha(value), "size": len(value)}
        if hasattr(value, "__dataclass_fields__"):
            return normal(asdict(value))
        if isinstance(value, dict):
            return {str(k): normal(v) for k, v in sorted(value.items())}
        if isinstance(value, (list, tuple)):
            return [normal(v) for v in value]
        if isinstance(value, (set, frozenset)):
            return sorted(value)
        return value

    return json.dumps(normal(obj), sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True, slots=True)
class SignedProof:
    issuer_id: str
    key_id: str
    domain: str
    signature: str


class AuthenticatingTrust(Protocol):
    """Injected separately controlled custody; NEVER supplied by a model response."""

    def verify(
        self, issuer_id: str, key_id: str, domain: str, message: bytes, signature: str
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class ArtifactEvidenceV1:
    workspace_root: str
    relative_path: str
    byte_length: int
    sha256: str
    pinned_head: str
    tenant_id: str
    task_id: str
    run_id: str
    outcome_id: str


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    workspace_root: str
    pinned_head: str
    artifact_sha256: str
    command: tuple[str, ...]
    command_cwd: str
    executed: bool
    exit_code: int | None
    process_id: int | None
    started_at_ms: int
    finished_at_ms: int
    positive_tests: int
    negative_tests: int
    stdout_sha256: str
    stderr_sha256: str
    execution_id: str
    proof: SignedProof


@dataclass(frozen=True, slots=True)
class VerifierIdentity:
    generator_id: str
    verifier_id: str
    verifier_domain: str
    runner_domain: str


@dataclass(frozen=True, slots=True)
class VerifierAttestation:
    verifier_id: str
    evidence_sha256: str
    journal_head_sha256: str
    issued_at_ms: int
    proof: SignedProof


@dataclass(frozen=True, slots=True)
class NativeSource:
    source_id: str
    revision: str
    original_bytes: bytes
    bytes_sha256: str


@dataclass(frozen=True, slots=True)
class SourceRights:
    source_id: str
    revision: str
    bytes_sha256: str
    tenant_id: str
    principal: str
    audience: str
    allowed: bool
    revoked: bool
    expires_at_ms: int
    proof: SignedProof


@dataclass(frozen=True, slots=True)
class NativeCitationProof:
    citation_id: str
    source_id: str
    source_revision: str
    source_sha256: str
    claim_start: int
    claim_end: int
    quoted_original_bytes: bytes
    claim_sha256: str


@dataclass(frozen=True, slots=True)
class CitationReview:
    citation_id: str
    claim_sha256: str
    semantic_supported: bool
    counterevidence_checked: bool
    counterevidence_ids: tuple[str, ...]
    proof: SignedProof


@dataclass(frozen=True, slots=True)
class VerifiedFrame:
    kind: Literal["verified_text", "progress", "terminal", "provisional"]
    content: bytes
    citation_ids: tuple[str, ...]
    verification_id: str
    session_id: str
    nonce: str
    segment_id: str
    revision: int
    first_text_sent_at_ms: int
    terminal_at_ms: int


@dataclass(frozen=True, slots=True)
class ServerTransportProof:
    stage: Literal["QUEUED", "FLUSHED"]
    session_id: str
    nonce: str
    segment_id: str
    revision: int
    payload_sha256: str
    flushed_at_ms: int | None
    proof: SignedProof


@dataclass(frozen=True, slots=True)
class TransportAckProof:
    ack_id: str
    session_id: str
    nonce: str
    segment_id: str
    revision: int
    payload_sha256: str
    client_cursor: int
    received_at_ms: int
    proof: SignedProof


@dataclass(frozen=True, slots=True)
class OperationObservation:
    requested_ids: tuple[str, ...]
    completed_ids: tuple[str, ...]
    effect: Literal["APPLIED", "CONFIRMED_NOT_APPLIED", "UNKNOWN_EFFECT"]
    resource_revision: str
    negative_visibility_complete: bool
    proof: SignedProof


@dataclass(frozen=True, slots=True)
class CostEvidence:
    charge_ids: tuple[str, ...]
    estimated_microunits: int | None
    actual_microunits: int | None
    reserved_microunits: int
    late_billing_reconciled: bool
    proof: SignedProof


@dataclass(frozen=True, slots=True)
class VerificationContext:
    tenant_id: str
    task_id: str
    task_version: int
    run_id: str
    outcome_id: str
    outcome_sha256: str
    journal_head_sha256: str
    journal_epoch: int
    current_journal_head_sha256: str
    workspace_root: str
    pinned_head: str
    required_command: tuple[str, ...]
    workload: Literal["CODING", "RESEARCH", "QA", "ACTION"]
    approved_revisions: tuple[tuple[str, str], ...]
    principal: str
    audience: str
    now_ms: int
    max_artifact_bytes: int = 1_048_576
    max_archive_unpacked_bytes: int = 4_194_304
    seen_ack_ids: frozenset[str] = frozenset()
    seen_execution_ids: frozenset[str] = frozenset()
    committed_terminal_ids: frozenset[str] = frozenset()
    trust_issuers: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    artifact: ArtifactEvidenceV1
    execution: ExecutionReceipt
    identity: VerifierIdentity
    sources: tuple[NativeSource, ...]
    rights: tuple[SourceRights, ...]
    citations: tuple[NativeCitationProof, ...]
    reviews: tuple[CitationReview, ...]
    frame: VerifiedFrame
    server: ServerTransportProof
    client_acks: tuple[TransportAckProof, ...]
    operation: OperationObservation | None
    cost: CostEvidence
    verifier: VerifierAttestation
    tenant_id: str
    task_id: str
    task_version: int
    run_id: str
    outcome_id: str
    outcome_sha256: str
    journal_head_sha256: str
    journal_epoch: int
    terminal_id: str
    unknown_effect: bool = False
    terminal_already_committed: bool = False
    response_generated_proof: bool = False


@dataclass(frozen=True, slots=True)
class VerifierDecision:
    status: Literal["ELIGIBLE_TEST_FIXTURE_ONLY", "DENIED_TEST_FIXTURE_ONLY"]
    failures: tuple[str, ...]
    checked_artifact_sha256: str | None
    can_terminalize: bool = False
    can_publish: bool = False
    real_client_delivery_proven: bool = False
    ar02_mutated: bool = False


def _message(domain: str, item: object) -> bytes:
    """Sign every field except its own signature under role/version separation."""
    return b"AR05-V05N/fixture/v1/" + domain.encode() + b"\0" + canonical(
        replace(item, proof=SignedProof("", "", "", ""))
    )


def _auth(item: object, role: str, ctx: VerificationContext,
          trust: AuthenticatingTrust | None, generator: str,
          excluded: frozenset[str] = frozenset()) -> bool:
    proof = getattr(item, "proof", None)
    if not isinstance(proof, SignedProof) or trust is None:
        return False
    if (not proof.issuer_id or not proof.key_id or proof.domain != role
            or (role, proof.issuer_id) not in ctx.trust_issuers
            or proof.issuer_id == generator or proof.issuer_id in excluded):
        return False
    try:
        return trust.verify(proof.issuer_id, proof.key_id, role,
                            _message(role, item), proof.signature)
    except (ValueError, TypeError, KeyError):
        return False


def _safe_artifact(artifact: ArtifactEvidenceV1, ctx: VerificationContext) -> bytes:
    """Open at each path component with O_NOFOLLOW, reject escapes and archive bombs."""
    root = Path(ctx.workspace_root)
    if (not root.is_absolute() or root.is_symlink()
            or artifact.workspace_root != ctx.workspace_root):
        raise ValueError("WORKSPACE_MISMATCH")
    path = PurePosixPath(artifact.relative_path)
    if (path.is_absolute() or not path.parts or any(
            part in {"..", ".", ""} for part in artifact.relative_path.split("/")
    ) or "\\" in artifact.relative_path):
        raise ValueError("PATH_TRAVERSAL")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            os.close(fd)
            fd = child
        leaf = os.open(path.parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        try:
            meta = os.fstat(leaf)
            if not stat.S_ISREG(meta.st_mode):
                raise ValueError("NOT_REGULAR_FILE")
            if meta.st_size > ctx.max_artifact_bytes or meta.st_size < 0:
                raise ValueError("OVERSIZED_ARTIFACT")
            data = bytearray()
            while True:
                chunk = os.read(leaf, min(65536, ctx.max_artifact_bytes + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > ctx.max_artifact_bytes:
                    raise ValueError("OVERSIZED_ARTIFACT")
            after = os.fstat(leaf)
            if ((meta.st_dev, meta.st_ino, meta.st_size, meta.st_mtime_ns)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
                raise ValueError("FILE_CHANGED_DURING_READ")
            if path.suffix.lower() in {".zip", ".whl", ".jar"}:
                _check_archive(bytes(data), ctx.max_archive_unpacked_bytes)
            return bytes(data)
        finally:
            os.close(leaf)
    except OSError as exc:
        raise ValueError("UNSAFE_ARTIFACT_PATH") from exc
    finally:
        os.close(fd)


def _check_archive(data: bytes, max_unpacked: int) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > 1000 or sum(i.file_size for i in infos) > max_unpacked:
                raise ValueError("OVERSIZED_ARCHIVE")
            for info in infos:
                path = PurePosixPath(info.filename)
                mode = info.external_attr >> 16
                if (path.is_absolute() or ".." in path.parts or "\\" in info.filename
                        or stat.S_ISLNK(mode) or info.file_size > max_unpacked):
                    raise ValueError("UNSAFE_ARCHIVE_ENTRY")
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ValueError("INVALID_ARCHIVE") from exc


def _actual_git_head(root: str) -> str | None:
    """Fixed read-only Git argv, not caller commands; no shell and no checkout."""
    try:
        r = subprocess.run(
            ["git", "-C", root, "rev-parse", "--verify", "HEAD"],
            capture_output=True, timeout=4, check=False, text=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def propose_eligibility(
    bundle: EvidenceBundle,
    ctx: VerificationContext,
    *,
    trust: AuthenticatingTrust | None,
) -> VerifierDecision:
    """Deterministic TEST-ONLY eligibility proposal, never AR02 terminal or publish."""
    faults: list[str] = []

    def check(ok: bool, code: str) -> None:
        if not ok:
            faults.append(code)

    same = (
        ("tenant_id", "tenant_id"), ("task_id", "task_id"),
        ("task_version", "task_version"), ("run_id", "run_id"),
        ("outcome_id", "outcome_id"), ("outcome_sha256", "outcome_sha256"),
        ("journal_head_sha256", "journal_head_sha256"),
        ("journal_epoch", "journal_epoch"),
    )
    for left, right in same:
        check(getattr(bundle, left) == getattr(ctx, right), "IDENTITY_" + left.upper())
    check(_valid_sha(ctx.outcome_sha256), "OUTCOME_DIGEST_INVALID")
    check(_valid_sha(ctx.journal_head_sha256), "HEAD_DIGEST_INVALID")
    check(ctx.current_journal_head_sha256 == bundle.journal_head_sha256,
          "STALE_JOURNAL_HEAD")
    check(not bundle.unknown_effect and not bundle.terminal_already_committed,
          "UNRESOLVED_OR_TERMINAL")
    check(bundle.terminal_id not in ctx.committed_terminal_ids and bool(bundle.terminal_id),
          "REPLAYED_TERMINAL")
    check(not bundle.response_generated_proof, "SELF_GENERATED_PROOF")

    a, run, identity = bundle.artifact, bundle.execution, bundle.identity
    for label, value in (
        ("ARTIFACT_TENANT", a.tenant_id == ctx.tenant_id),
        ("ARTIFACT_TASK", a.task_id == ctx.task_id),
        ("ARTIFACT_RUN", a.run_id == ctx.run_id),
        ("ARTIFACT_OUTCOME", a.outcome_id == ctx.outcome_id),
        ("PINNED_HEAD", a.pinned_head == ctx.pinned_head),
        ("RUNNER_PINNED_HEAD", run.pinned_head == ctx.pinned_head),
        ("RUNNER_WORKSPACE", run.workspace_root == ctx.workspace_root),
        ("RUNNER_CWD", run.command_cwd == ctx.workspace_root),
        ("WORKTREE_HEAD_NOW", _actual_git_head(ctx.workspace_root) == ctx.pinned_head),
        ("RUNNER_COMMAND", run.command == ctx.required_command),
        ("RUNNER_ARTIFACT_HASH", run.artifact_sha256 == a.sha256),
        ("RUNNER_EXECUTED", run.executed and run.process_id is not None
         and run.process_id > 0 and run.started_at_ms > 0),
        ("RUNNER_GREEN_EXIT", run.exit_code == 0),
        ("RUNNER_TIME", run.started_at_ms <= run.finished_at_ms <= ctx.now_ms),
        ("RUNNER_TEST_COUNTS", run.positive_tests > 0 and run.negative_tests >= 25),
        ("RUNNER_LOG_HASH", _valid_sha(run.stdout_sha256) and _valid_sha(run.stderr_sha256)),
        ("RUNNER_REPLAY", run.execution_id not in ctx.seen_execution_ids
         and bool(run.execution_id)),
        ("INDEPENDENT_VERIFIER_ID", bool(identity.verifier_id)
         and identity.verifier_id != identity.generator_id),
        ("INDEPENDENT_TRUST_DOMAIN", bool(identity.verifier_domain)
         and identity.verifier_domain != identity.runner_domain),
    ):
        check(value, label)
    check(_auth(run, "runner", ctx, trust, identity.generator_id),
          "RUNNER_AUTH_UNVERIFIED")
    artifact_sha: str | None = None
    try:
        payload = _safe_artifact(a, ctx)
        artifact_sha = sha(payload)
        check(len(payload) == a.byte_length and artifact_sha == a.sha256,
              "ARTIFACT_CONTENT_CHANGED")
    except (ValueError, OSError) as exc:
        check(False, "ARTIFACT_" + str(exc))

    expected_revisions = dict(ctx.approved_revisions)
    sources = {s.source_id: s for s in bundle.sources}
    rights = {r.source_id: r for r in bundle.rights}
    reviews = {r.citation_id: r for r in bundle.reviews}
    citations = {c.citation_id: c for c in bundle.citations}
    check(len(sources) == len(bundle.sources) and len(rights) == len(bundle.rights),
          "DUPLICATE_SOURCE_OR_RIGHTS")
    check(len(reviews) == len(bundle.reviews) and len(citations) == len(bundle.citations),
          "DUPLICATE_CITATIONS_OR_REVIEWS")
    check(set(citations) == set(reviews), "MISSING_SEMANTIC_REVIEW")
    check(set(sources) == set(rights) == set(expected_revisions),
          "SOURCE_RIGHTS_INCOMPLETE")
    for source_id, source in sources.items():
        right = rights.get(source_id)
        check(_valid_sha(source.bytes_sha256)
              and sha(source.original_bytes) == source.bytes_sha256,
              "SOURCE_ORIGINAL_BYTES")
        check(source.revision == expected_revisions.get(source_id), "SOURCE_REVISION")
        if right is None:
            continue
        check(right.source_id == source_id and right.revision == source.revision
              and right.bytes_sha256 == source.bytes_sha256
              and right.tenant_id == ctx.tenant_id and right.principal == ctx.principal
              and right.audience == ctx.audience and right.allowed and not right.revoked
              and right.expires_at_ms > ctx.now_ms, "SOURCE_RIGHTS_EXPIRED_OR_WRONG")
        check(_auth(right, "rights", ctx, trust, identity.generator_id),
              "SOURCE_RIGHTS_NOT_INDEPENDENT")
    for citation_id, citation in citations.items():
        source = sources.get(citation.source_id)
        if source is None:
            check(False, "CITATION_UNKNOWN_SOURCE")
            continue
        check(bool(citation_id) and citation.source_revision == source.revision
              and citation.source_sha256 == source.bytes_sha256,
              "CITATION_SOURCE_IDENTITY")
        exact = (
            isinstance(citation.claim_start, int)
            and isinstance(citation.claim_end, int)
            and 0 <= citation.claim_start < citation.claim_end <= len(source.original_bytes)
            and source.original_bytes[citation.claim_start:citation.claim_end]
            == citation.quoted_original_bytes
        )
        check(exact and sha(citation.quoted_original_bytes) == citation.claim_sha256,
              "CITATION_SPAN_UNSUPPORTED")
        review = reviews.get(citation_id)
        if review is None:
            continue
        check(review.citation_id == citation_id
              and review.claim_sha256 == citation.claim_sha256
              and review.semantic_supported, "CITATION_SEMANTIC_UNSUPPORTED")
        check(_auth(review, "citation_oracle", ctx, trust, identity.generator_id),
              "CITATION_ORACLE_NOT_INDEPENDENT")
        if ctx.workload == "RESEARCH":
            check(review.counterevidence_checked and bool(review.counterevidence_ids)
                  and all(source_id in sources for source_id in review.counterevidence_ids),
                  "COUNTEREVIDENCE_MISSING")
    if ctx.workload in {"RESEARCH", "QA"}:
        check(bool(bundle.citations), "NATIVE_CITATIONS_MISSING")

    frame = bundle.frame
    check(frame.kind == "verified_text" and bool(frame.content.strip())
          and frame.verification_id == bundle.verifier.verifier_id,
          "NO_MATERIAL_VERIFIED_TEXT")
    try:
        frame.content.decode("utf-8")
    except UnicodeDecodeError:
        check(False, "INVALID_STREAM_UTF8")
    check(set(frame.citation_ids) == set(citations)
          and len(frame.citation_ids) == len(set(frame.citation_ids)),
          "STREAM_CITATIONS_INVALID")
    check(0 < frame.first_text_sent_at_ms < frame.terminal_at_ms <= ctx.now_ms,
          "STREAM_NOT_PRETERMINAL")
    sv = bundle.server
    check(sv.stage == "FLUSHED" and sv.flushed_at_ms is not None
          and frame.first_text_sent_at_ms <= sv.flushed_at_ms < frame.terminal_at_ms,
          "NOT_FLUSHED_PRETERMINAL")
    check((sv.session_id, sv.nonce, sv.segment_id, sv.revision, sv.payload_sha256)
          == (frame.session_id, frame.nonce, frame.segment_id, frame.revision,
              sha(frame.content)), "SERVER_FRAME_BINDING")
    check(_auth(sv, "server_transport", ctx, trust, identity.generator_id),
          "SERVER_TRANSPORT_NOT_AUTHENTICATED")
    check(len(bundle.client_acks) == 1, "CLIENT_ACK_COUNT")
    for ack in bundle.client_acks:
        check(bool(ack.ack_id) and ack.ack_id not in ctx.seen_ack_ids
              and ack.client_cursor > 0
              and (ack.ack_id, ack.session_id, ack.nonce) not in {
                  (a2.ack_id, a2.session_id, a2.nonce) for a2 in bundle.client_acks
                  if a2 is not ack
              }, "DUPLICATE_OR_REPLAYED_ACK")
        check((ack.session_id, ack.nonce, ack.segment_id, ack.revision,
               ack.payload_sha256)
              == (frame.session_id, frame.nonce, frame.segment_id, frame.revision,
                  sha(frame.content)), "CLIENT_ACK_FRAME_BINDING")
        check(sv.flushed_at_ms is not None
              and sv.flushed_at_ms <= ack.received_at_ms < frame.terminal_at_ms,
              "CLIENT_ACK_TIME")
        check(_auth(ack, "client_ack", ctx, trust, identity.generator_id),
              "CLIENT_ACK_NOT_AUTHENTICATED")

    op = bundle.operation
    if ctx.workload == "ACTION":
        check(op is not None, "EXTERNAL_OBSERVER_MISSING")
    if op is not None:
        check(bool(op.requested_ids) and set(op.requested_ids) == set(op.completed_ids)
              and len(op.completed_ids) == len(op.requested_ids)
              and op.effect == "APPLIED" and bool(op.resource_revision),
              "OPERATION_INCOMPLETE_OR_UNKNOWN")
        check(_auth(op, "observer", ctx, trust, identity.generator_id),
              "OBSERVER_NOT_INDEPENDENT")
    cost = bundle.cost
    check(cost.estimated_microunits is not None and cost.actual_microunits is not None
          and cost.estimated_microunits >= 0 and cost.actual_microunits >= 0
          and cost.reserved_microunits >= cost.actual_microunits
          and cost.late_billing_reconciled and len(cost.charge_ids) == len(set(cost.charge_ids)),
          "COST_UNPRICED_OR_UNRECONCILED")
    check(_auth(cost, "billing", ctx, trust, identity.generator_id),
          "BILLING_NOT_INDEPENDENT")

    v = bundle.verifier
    proof_root = sha(canonical(replace(bundle, verifier=replace(
        v, evidence_sha256="", proof=SignedProof("", "", "", "")
    ))))
    check(v.evidence_sha256 == proof_root and v.verifier_id == identity.verifier_id
          and v.journal_head_sha256 == ctx.current_journal_head_sha256
          and 0 < v.issued_at_ms <= ctx.now_ms, "VERIFIER_EVIDENCE_BINDING")
    check(v.proof.issuer_id == identity.verifier_id
          and _auth(v, "verifier", ctx, trust, identity.generator_id,
                    frozenset({run.proof.issuer_id})),
          "VERIFIER_NOT_INDEPENDENT")
    return VerifierDecision(
        status=DENIED if faults else SUCCESS,
        failures=tuple(dict.fromkeys(faults)),
        checked_artifact_sha256=artifact_sha,
    )


def finalize_test_fixture(bundle: EvidenceBundle) -> EvidenceBundle:
    """Compute the verifier's canonical evidence-root field, but NEVER authenticate it.

    This pure helper is intended only for fixtures; a separate key custodian still
    must sign the result. It cannot produce independently authorized evidence.
    """
    verifier = bundle.verifier
    root = sha(canonical(replace(
        bundle, verifier=replace(verifier, evidence_sha256="",
                                 proof=SignedProof("", "", "", ""))
    )))
    return replace(bundle, verifier=replace(verifier, evidence_sha256=root))
