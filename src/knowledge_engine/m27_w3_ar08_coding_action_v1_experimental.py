"""S08C feature-off coding runner: one bounded local test fixture, no general executor.

Only an allowlisted fixed arithmetic module is generated, inside an owned ephemeral
directory under a caller-provided temporary root. AR02's durable outbox fences a
single process launch. AR04 accepts fixture-only permits; AR05's typed evidence
interface is reviewed by a separate fixture verifier, not by model-generated CI.
All success is LOCAL_TEST_FIXTURE_ONLY, never remote provider/action authority.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Protocol

from knowledge_engine.m27_ar02_durable_writer_v1_experimental import (
    DurableWriterV1,
    Head,
    RunIdentity,
)
from knowledge_engine.m27_ar04_permit_sandbox_v1_experimental import (
    ActionRequest,
    ApprovalDecision,
    AuthoritySnapshot,
    CapabilityRule,
    DurableWriterReceipt,
    InProcessFixtureObserver,
    Permit,
    PermitSandboxV1,
    Registry,
)
from knowledge_engine.m27_ar05_independent_verifier_v1_experimental import (
    ArtifactEvidenceV1,
    ExecutionReceipt,
    SignedProof,
    VerifierDecision,
    sha,
)

VERSION = "S08C-CODING-LOCAL-v1"
PROGRAM = "fixed-arithmetic-fixture-v1"
COMMAND = "python-isolated-fixture-test-v1"
RULE = CapabilityRule("coding.fixture", "1", "run_fixed_test", "/fixture/",
                      "local-fixed-fixture", 3)
ID = re.compile(r"[a-zA-Z0-9_-]{1,48}\Z")
HEX = re.compile(r"[0-9a-f]{64}\Z")


class CodingDenied(ValueError):
    """A fail-closed local admission, evidence or process error."""


def _json(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


@dataclass(frozen=True)
class CodingTaskV1:
    identity: RunIdentity
    idempotency_key: str
    expected_head: str
    source_revision: str
    expected_source_sha256: str
    left: int
    right: int
    operation: Literal["add", "mul"]
    expected_value: int
    program_id: str = PROGRAM
    command_id: str = COMMAND
    schema_version: str = VERSION


@dataclass(frozen=True)
class CodingIntentV1:
    schema_version: str
    request: ActionRequest
    source_bytes: bytes
    source_sha256: str
    initial_head: Head


@dataclass(frozen=True)
class CodingReceiptV1:
    schema_version: str
    outcome: str
    tenant_id: str
    run_id: str
    task_id: str
    intent_digest: str
    claim_id: str
    head_digest: str
    execution_id: str | None
    artifact_sha256: str | None
    stdout_sha256: str | None
    stderr_sha256: str | None
    stdout_bytes: bytes
    stderr_bytes: bytes
    exit_code: int | None
    attempts: int
    ephemeral_cleaned: bool
    provider_calls: int = 0
    actual_remote_effects: int = 0


class IndependentReviewPort(Protocol):
    verifier_id: str

    def review(
        self, artifact: ArtifactEvidenceV1, execution: ExecutionReceipt,
        stdout: bytes, stderr: bytes,
    ) -> VerifierDecision: ...

    def sign_local_terminal(self, message: bytes) -> str: ...


class IndependentLocalFixtureVerifier:
    """Test-only separately provisioned reviewer with local HMAC custody.

    Never validates external CI, client ACK, real action rights, or provider
    evidence. The caller must independently provision its key to AR02; the
    runner never creates or stores a key and never self-issues a verification.
    """

    def __init__(self, verifier_id: str, local_key: bytes):
        if not ID.fullmatch(verifier_id) or len(local_key) < 16:
            raise CodingDenied("INVALID_FIXTURE_VERIFIER")
        self.verifier_id = verifier_id
        self._key = local_key

    def review(
        self, artifact: ArtifactEvidenceV1, execution: ExecutionReceipt,
        stdout: bytes, stderr: bytes,
    ) -> VerifierDecision:
        failures: list[str] = []
        root = Path(artifact.workspace_root).resolve(strict=True)
        file = root / artifact.relative_path
        if (
            artifact.relative_path != "answer.py"
            or file.is_symlink()
            or not file.is_file()
            or file.resolve(strict=True).parent != root
        ):
            failures.append("ARTIFACT_PATH")
            checked = None
        else:
            data = file.read_bytes()
            checked = sha(data)
            if checked != artifact.sha256 or len(data) != artifact.byte_length:
                failures.append("ARTIFACT_HASH")
        if (
            execution.workspace_root != artifact.workspace_root
            or execution.artifact_sha256 != artifact.sha256
            or execution.pinned_head != artifact.pinned_head
            or not execution.executed
            or execution.exit_code != 0
            or execution.command_cwd != artifact.workspace_root
            or execution.command != (sys.executable, "-I", "-B", "test_fixture.py")
            or execution.stdout_sha256 != sha(stdout)
            or execution.stderr_sha256 != sha(stderr)
            or stdout != b"FIXTURE_OK\n"
            or stderr != b""
            or execution.finished_at_ms < execution.started_at_ms
        ):
            failures.append("EXECUTION_NOT_INDEPENDENTLY_CONFIRMED")
        return VerifierDecision(
            "DENIED_TEST_FIXTURE_ONLY" if failures else "ELIGIBLE_TEST_FIXTURE_ONLY",
            tuple(failures), checked,
        )

    def sign_local_terminal(self, message: bytes) -> str:
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()


class _ClaimPort:
    """One-shot AR04 port backed by an already committed AR02 local ACK."""

    def __init__(self, token: str, claim_id: str, writer_issuer: str):
        self.token = token
        self.claim_id = claim_id
        self.writer_issuer = writer_issuer
        self.used = False

    def prepare_claim(self, permit: Permit, claim_id: str) -> DurableWriterReceipt:
        if self.used or claim_id != self.claim_id or not self.token:
            raise CodingDenied("MISSING_DURABLE_ACK_OR_DUPLICATE_CLAIM")
        self.used = True
        req = permit.request
        return DurableWriterReceipt(
            self.writer_issuer, claim_id, permit.permit_id, permit.intent_digest,
            req.run_id, req.tenant_id, permit.worker_id, req.lease_epoch,
            permit.frozen_head_hash, self.token, True, True,
        )


def _owned_file(root: Path, name: str, data: bytes) -> None:
    """Exclusive no-follow creation; even injected symlinks cannot overwrite."""
    if name not in {"answer.py", "test_fixture.py"}:
        raise CodingDenied("FILE_NOT_ALLOWLISTED")
    path = root / name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as writer:
            writer.write(data)
            writer.flush()
            os.fsync(writer.fileno())
    except BaseException:
        # fdopen owns the descriptor on entry; closed even if write fails.
        raise
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise CodingDenied("UNSAFE_FIXTURE_FILE")
    if path.read_bytes() != data:
        raise CodingDenied("FILE_BYTES_CHANGED")


def local_registry() -> Registry:
    return Registry(
        "fixture-policy", frozenset({"fixture-approver"}),
        frozenset({"fixture-observer"}), "local-ar02-writer",
        frozenset({"local-fixed-fixture"}), (RULE,),
    )


class CodingActionRunnerV1:
    """AR02/AR04/AR05 controlled local fixture vertical, feature disabled."""

    def __init__(self, writer: DurableWriterV1, *, temp_root: str | Path):
        self.writer = writer
        requested = Path(temp_root)
        if requested.is_symlink() or not requested.is_dir():
            raise CodingDenied("UNTRUSTED_TEMP_ROOT")
        root = requested.resolve(strict=True)
        allowed = Path(tempfile.gettempdir()).resolve(strict=True)
        if not root.is_relative_to(allowed) or root == allowed:
            raise CodingDenied("TEMP_ROOT_OUTSIDE_EPHEMERAL_ALLOWLIST")
        if root.is_symlink() or (root.stat().st_mode & 0o002):
            raise CodingDenied("INSECURE_TEMP_ROOT")
        self.temp_root = root
        self.registry = local_registry()

    def prepare(self, task: CodingTaskV1) -> CodingIntentV1:
        ident = task.identity
        if (
            task.schema_version != VERSION or task.program_id != PROGRAM
            or task.command_id != COMMAND or ident.task_version != 1
            or task.operation not in {"add", "mul"}
            or any(not isinstance(v, str) or not ID.fullmatch(v) for v in (
                ident.tenant_id, ident.run_id, ident.task_id, ident.principal_id,
                task.idempotency_key, task.source_revision,
            ))
            or any(type(v) is not int or not 0 <= v <= 100 for v in (
                task.left, task.right, task.expected_value,
            ))
            or not isinstance(task.expected_head, str)
            or not HEX.fullmatch(task.expected_head)
            or not isinstance(task.expected_source_sha256, str)
            or not HEX.fullmatch(task.expected_source_sha256)
        ):
            raise CodingDenied("TASK_CONTRACT_DENIED")
        head = self.writer.read_head(ident)
        if head.digest != task.expected_head or head.state != "OPEN":
            raise CodingDenied("STALE_OR_TERMINAL_HEAD")
        operator = "+" if task.operation == "add" else "*"
        source = f"def compute():\n    return {task.left} {operator} {task.right}\n".encode()
        digest = sha(source)
        if digest != task.expected_source_sha256:
            raise CodingDenied("UNAPPROVED_SOURCE_HASH")
        arguments = sha(_json([
            VERSION, PROGRAM, COMMAND, task.left, task.right, task.operation,
            task.expected_value, digest,
        ]))
        request = ActionRequest(
            request_id=f"{ident.run_id}-{task.idempotency_key}",
            run_id=ident.run_id, tenant_id=ident.tenant_id,
            actor_id=ident.principal_id, delegated_by=None,
            capability_id=RULE.capability_id, capability_version=RULE.version,
            operation=RULE.operation,
            resource_id=f"/fixture/{ident.tenant_id}/coding/{ident.run_id}",
            recipient_id="local-ephemeral-fixture",
            arguments_digest=arguments,
            idempotency_key=task.idempotency_key,
            intent_version=VERSION, lease_epoch=head.epoch,
        )
        return CodingIntentV1(VERSION, request, source, digest, head)

    def execute(
        self, task: CodingTaskV1, *, snapshot: AuthoritySnapshot,
        approval: ApprovalDecision, verifier: IndependentReviewPort,
        observer: InProcessFixtureObserver, now: int,
        timeout_seconds: int = 3,
        before_local_send: Callable[[], object] | None = None,
    ) -> CodingReceiptV1:
        """Single physical launch per AR02 outbox claim. Unknown never retries."""
        if type(now) is not int or type(timeout_seconds) is not int:
            raise CodingDenied("INVALID_CLOCK_OR_TIMEOUT")
        if not 1 <= timeout_seconds <= 10:
            raise CodingDenied("INVALID_TIMEOUT")
        if not isinstance(verifier, IndependentLocalFixtureVerifier):
            raise CodingDenied("INDEPENDENT_AR05_VERIFIER_REQUIRED")
        if (
            verifier.verifier_id in {task.identity.principal_id, observer.observer_id}
            or observer.observer_id == task.identity.principal_id
            or observer.issuer not in self.registry.observer_issuers
            or not ID.fullmatch(observer.observer_id)
        ):
            raise CodingDenied("SELF_OR_UNTRUSTED_REVIEWER")
        intent = self.prepare(task)
        ident = task.identity
        if (
            not isinstance(snapshot.worker_id, str)
            or not ID.fullmatch(snapshot.worker_id)
            or snapshot.head_hash != intent.initial_head.digest
            or snapshot.lease_epoch != intent.initial_head.epoch
            or snapshot.run_id != ident.run_id or snapshot.tenant_id != ident.tenant_id
        ):
            raise CodingDenied("STALE_HEAD_OR_SCOPE")
        sandbox = PermitSandboxV1(self.registry, None)  # bound after durable ACK
        sandbox.request(intent.request, snapshot, now=now)
        permit = sandbox.issue_permit(
            intent.request.request_id, approval, snapshot,
            now=now, quoted_cost=1,
        )
        # Pre-T3 AR02 transactions are real local SQLite commits, not fake ACKs.
        head = self.writer.reserve(
            ident, intent.initial_head,
            reserve_id=f"reserve-{ident.run_id}-{task.idempotency_key}", amount=1,
        )
        head = self.writer.provision_fixture_approval(
            ident, head, approval_id=approval.approval_id,
            intent_digest=intent.request.digest(), expires_at=approval.expires_at,
        )
        intent_id = f"intent-{ident.run_id}-{task.idempotency_key}"
        claim_id = f"claim-{ident.run_id}-{task.idempotency_key}"
        reserve_id = f"reserve-{ident.run_id}-{task.idempotency_key}"
        head = self.writer.commit_intent_and_claim(
            ident, head, intent_id=intent_id,
            intent_digest=intent.request.digest(), approval_id=approval.approval_id,
            claim_id=claim_id, reserve_id=reserve_id,
            idempotency_key=f"{ident.tenant_id}-{ident.run_id}-{task.idempotency_key}",
            now=now,
        )
        head, durable_ack = self.writer.claim_outbox(ident, head, claim_id=claim_id)
        sandbox._writer = _ClaimPort(durable_ack, claim_id, self.registry.writer_issuer)
        claim = sandbox.freeze_claim(
            permit, snapshot, claim_id=claim_id, sender_id=snapshot.worker_id,
            physical_attempt=1, now=now,
        )
        if (
            claim.writer_receipt.outbox_ack != durable_ack
            or not claim.writer_receipt.durable_verified
        ):
            raise CodingDenied("NO_LOCAL_DURABLE_COMMIT_ACK")
        # Must durably record potential effect BEFORE subprocess; crash => UNKNOWN.
        head = self.writer.mark_possible_send(
            ident, head, claim_id=claim_id, local_ack_token=durable_ack,
        )
        initial_unknown = head.digest
        exit_code: int | None = None
        out = b""
        err = b""
        execution_id: str | None = None
        artifact_hash: str | None = None
        outcome = "UNKNOWN_EFFECT"
        attempts = 0
        cleaned = False
        try:
            with tempfile.TemporaryDirectory(
                prefix="s08c-owned-", dir=self.temp_root
            ) as directory:
                work = Path(directory)
                if work.is_symlink() or work.resolve(strict=True).parent != self.temp_root:
                    raise CodingDenied("WORKDIR_ESCAPE")
                _owned_file(work, "answer.py", intent.source_bytes)
                artifact_hash = sha((work / "answer.py").read_bytes())
                if artifact_hash != intent.source_sha256:
                    raise CodingDenied("SOURCE_TOCTOU")
                test_bytes = (
                    "import runpy\n"
                    "from pathlib import Path\n"
                    "module = runpy.run_path(str(Path(__file__).with_name('answer.py')))\n"
                    f"assert module['compute']() == {task.expected_value}\n"
                    "print('FIXTURE_OK')\n"
                ).encode()
                _owned_file(work, "test_fixture.py", test_bytes)
                argv = (sys.executable, "-I", "-B", "test_fixture.py")
                # Last-moment local send fence; AR02 records UNKNOWN before this
                # callback. A revoked lease must never start the subprocess.
                if before_local_send is not None:
                    before_local_send()
                attempts = 1
                try:
                    process = subprocess.run(
                        argv, cwd=work, capture_output=True, check=False,
                        timeout=timeout_seconds, shell=False,
                        env={
                            "PATH": "/usr/bin:/bin", "HOME": str(work),
                            "LC_ALL": "en_US.UTF-8", "PYTHONDONTWRITEBYTECODE": "1",
                        },
                    )
                    out, err, exit_code = process.stdout, process.stderr, process.returncode
                except subprocess.TimeoutExpired as exc:
                    out = exc.stdout or b""
                    err = exc.stderr or b""
                if exit_code == 0:
                    execution_id = sha(_json([
                        ident.tenant_id, ident.run_id, claim_id,
                        artifact_hash, sha(out), sha(err),
                    ]))
                    artifact = ArtifactEvidenceV1(
                        str(work), "answer.py", len(intent.source_bytes), artifact_hash,
                        task.expected_head, ident.tenant_id, ident.task_id,
                        ident.run_id, f"outcome-{ident.run_id}",
                    )
                    receipt = ExecutionReceipt(
                        str(work), task.expected_head, artifact_hash, argv, str(work),
                        True, exit_code, process.pid if hasattr(process, "pid") else None,
                        now * 1000, now * 1000 + 1, 1, 1, sha(out), sha(err),
                        execution_id, SignedProof("", "", "", ""),
                    )
                    verdict = verifier.review(artifact, receipt, out, err)
                    if (
                        verdict.status != "ELIGIBLE_TEST_FIXTURE_ONLY"
                        or verdict.failures
                        or verdict.checked_artifact_sha256 != artifact_hash
                        or verdict.can_terminalize or verdict.can_publish
                        or verdict.real_client_delivery_proven
                    ):
                        raise CodingDenied("AR05_INDEPENDENT_REVIEW_FAILED")
                    observation = observer.observe(
                        claim, effect="applied", source_revision=task.source_revision,
                        visibility_complete=True,
                    )
                    if (
                        observation.tenant_id != ident.tenant_id
                        or observation.intent_digest != claim.permit.intent_digest
                        or observation.claim_id != claim_id
                        or observation.effect != "applied"
                        or observation.observer_id != observer.observer_id
                        or observation.observer_issuer != observer.issuer
                        or observation.evidence_grade != "FIXTURE_ONLY"
                    ):
                        raise CodingDenied("FORGED_OBSERVER_RECEIPT")
                    evidence_hash = sha(_json([
                        artifact_hash, sha(out), sha(err), observation.observer_id,
                        intent.request.digest(), execution_id,
                    ]))
                    evidence_ref = f"local-coding-{execution_id}"
                    head = self.writer.record_observer_reconciliation(
                        ident, head, intent_id=intent_id,
                        original_t1_digest=intent.request.digest(),
                        observer_id=observation.observer_id, evidence_ref=evidence_ref,
                        evidence_sha256=evidence_hash, outcome="CONFIRMED_APPLIED",
                        source_revision=task.source_revision,
                        consent_generation=snapshot.consent_generation,
                        exclusion_generation=1, expires_at=now + 30, now=now,
                    )
                    head = self.writer.charge(
                        ident, head, reserve_id=reserve_id,
                        charge_id=f"charge-{ident.run_id}-{task.idempotency_key}",
                        amount=1,
                    )
                    message = self.writer.verification_message(
                        ident, head, evidence_ref=evidence_ref,
                        verification_ref=f"ar05-{execution_id}",
                        status="LOCAL_VERIFIED_APPLIED",
                    )
                    head = self.writer.commit_terminal(
                        ident, head, evidence_ref=evidence_ref,
                        verification_ref=f"ar05-{execution_id}",
                        verifier_id=verifier.verifier_id,
                        signature_hex=verifier.sign_local_terminal(message),
                        status="LOCAL_VERIFIED_APPLIED", now=now,
                    )
                    outcome = "LOCAL_VERIFIED_APPLIED_TEST_FIXTURE_ONLY"
                elif exit_code is not None:
                    outcome = "TEST_FAILED_NONTERMINAL"
            cleaned = True
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            # Durable UNKNOWN remains in the journal. Never relaunch or
            # compensate after an uncertain execution attempt.
            outcome = "UNKNOWN_EFFECT"
            cleaned = not any(self.temp_root.glob("s08c-owned-*"))
        head = self.writer.read_head(ident)
        if outcome != "LOCAL_VERIFIED_APPLIED_TEST_FIXTURE_ONLY" and head.state != "OPEN":
            raise CodingDenied("NONTERMINAL_JOURNAL_CORRUPTION")
        if outcome == "UNKNOWN_EFFECT" and head.digest == initial_unknown:
            pass  # explicit durable unresolved T3 observed
        return CodingReceiptV1(
            VERSION, outcome, ident.tenant_id, ident.run_id, ident.task_id,
            intent.request.digest(), claim_id, head.digest, execution_id,
            artifact_hash, sha(out), sha(err), out, err, exit_code,
            attempts, cleaned,
        )
