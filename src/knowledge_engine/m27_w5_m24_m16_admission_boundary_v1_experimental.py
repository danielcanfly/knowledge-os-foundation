"""M24 fail-closed admission firewall for I23 synthetic staging.

This experimental module CANNOT issue canonical M16 or production approval. It
binds observed Git and file bytes, and separately records missing authorities.
Only explicitly pinned non-secret source files are ever opened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from knowledge_engine import m27_w5_i23_n22_l22_combined_local_runtime_v1_experimental as i23

BASE_COMMIT = "52c18e9979ec24dedaed35cae4ca8690d8dfddcd"
BASE_TREE = "2fb1400b486938ea6b94c76d1e38c49f73b74506"
CANONICAL_M16 = "19c73028c9689c250e756987d1f2598e5f1fc891"
LOCAL_STATUS = "M24_LOCAL_INTEGRATION_STAGING_ONLY"
DENIAL = "NOT_ADMITTED"
SCHEMA = "m27-w5-m24-m16-boundary-v1"
OWNED = frozenset({
    "src/knowledge_engine/m27_w5_m24_m16_admission_boundary_v1_experimental.py",
    "tests/test_m27_w5_m24_m16_admission_boundary_v1_experimental.py",
    "docs/m27/m27_w5_m24_m16_admission_boundary_v1.md",
})
EXTRA_PINS = {
    "src/knowledge_engine/m27_w5_e15_original523_evaluator_admission_v1_experimental.py":
        "3b9cdaff2465fe96557c0db9b1d7affce8261ce3c1b6abb50272c8049db6ed18",
    "src/knowledge_engine/m27_w5_p16_external_evidence_ingress_v1_experimental.py":
        "7ea3c37866188bcb834523ec971c68122924bc424969fe0090de6154fc497b47",
    "src/knowledge_engine/m27_w5_i23_n22_l22_combined_local_runtime_v1_experimental.py":
        "df0b91384bafaf76ae1fee5bafc0aa74509aa2d7a76c960236121c9931ee4b3f",
}
FILE_PINS = {**i23.PINNED, **EXTRA_PINS}
ORIGINS = (
    ("I15", "bc1246382852b5fc15e1bf3f70325ea7c1f1275c", "original source imported in L21"),
    ("C16", "9e2f97d097e52271b6b333853159d41b45ce281b", "I15 bounded subprocess recovery"),
    ("E15", "d917333d2a2862fd10db8b8d4196f41f5fa0494d", "original evaluator contract"),
    ("P16", "97d5caff50fb78aae36a6e534b8b61e1b4a53b8a", "original tests not admitted"),
    ("P17", "2d7f9a8b433102670c339f9c28f9f1ec1204b70f", "P16 CLI denial correction"),
    ("L21", "6fcc6790eaf7e8ae45731944aebdf01636f7fffb", "local integration"),
    ("L22", "8e094bb673e4529e248db9c6212d0f1c4e760316", "bounded 20s accept"),
    ("N22", "7facd57a0e6a7e8c0225ed071ccdea2e2d7a237c", "independent localhost client"),
    ("I23", BASE_COMMIT, "combined nonproduction integration"),
)
GATES = (
    "p16_original_seven_suite_and_ast", "b13_original_full_positive",
    "source_rights", "original523_independent_grader",
    "phase_b200_independent_custodian", "native_client_external_ack",
    "current_candidate_signed_image", "real_all_outcome_p95",
    "provider_authenticated_usage", "signed_oci_and_rollback",
    "owner_canonical_m16_release",
)
# Git object IDs follow the repository object format; file digests are SHA-256.
# This I23-base source is pinned to a SHA-1 repository, not an arbitrary OID.
FILE_SHA256 = re.compile(r"^[a-f0-9]{64}$")
GIT_OBJECT_IDS = {
    "sha1": re.compile(r"^[a-f0-9]{40}$"),
    "sha256": re.compile(r"^[a-f0-9]{64}$"),
}
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,95}$")
# No externally provided keys or trusted grants are provisioned in M24.
RELEASE_ADMISSION_ENABLED = False


@dataclass(frozen=True, slots=True)
class CandidateIdentity:
    head: str
    baseline_commit: str
    baseline_tree: str
    candidate_tree: str
    file_sha256: Mapping[str, str]
    source_origins: tuple[tuple[str, str, str], ...]
    clean_or_owned_only: bool
    local_wire_imported: bool
    git_object_format: str = "sha1"


@dataclass(frozen=True, slots=True)
class AuthorityEvidence:
    gate: str
    status: str = "UNKNOWN"
    issuer: str = ""
    witness_id: str = ""
    nonce: str = ""
    candidate_commit: str = ""
    source_sha256: str = ""
    signed_claim: str = ""
    original_count: int | None = None
    live_count: int | None = None
    replay_count: int | None = None
    phase_b_count: int | None = None
    p95_ms: float | None = None


@dataclass(frozen=True, slots=True)
class CLIObservation:
    exit_code: int
    stdout: str
    stderr: str = ""


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    schema: str
    decision: str
    local_state: str
    candidate_head: str
    candidate_tree: str
    gate_states: Mapping[str, str]
    reasons: tuple[str, ...]
    local_wire: Mapping[str, Any] = field(default_factory=dict)


def _git(root: Path, *args: str) -> str:
    run = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True,
        text=True, timeout=12, check=False,
    )
    if run.returncode or len(run.stdout) > 262144:
        raise ValueError("GIT_IDENTITY_UNAVAILABLE")
    return run.stdout.strip()


def _file_sha(root: Path, relative: str) -> str:
    """Open a pinned regular file without following symlinks or exporting bytes."""
    path = root / relative
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > 2_000_000:
            raise ValueError("SOURCE_NOT_REGULAR_OR_TOO_LARGE")
        digest = hashlib.sha256()
        while chunk := os.read(fd, 65536):
            digest.update(chunk)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise ValueError("SOURCE_CONCURRENT_MUTATION")
        return digest.hexdigest()
    finally:
        os.close(fd)


def inspect_candidate(worktree: Path) -> CandidateIdentity:
    """Real read-only Git/physical checks; tolerates ONLY our three owned files."""
    root = worktree.resolve(strict=True)
    if not (root / ".git").exists():
        raise ValueError("NOT_A_GIT_WORKTREE")
    object_format = _git(root, "rev-parse", "--show-object-format")
    expected_oid = GIT_OBJECT_IDS.get(object_format)
    if expected_oid is None:
        raise ValueError("UNSUPPORTED_GIT_OBJECT_FORMAT")
    head, tree = _git(root, "rev-parse", "HEAD", "HEAD^{tree}").splitlines()
    if not expected_oid.fullmatch(head) or not expected_oid.fullmatch(tree):
        raise ValueError("INVALID_GIT_OBJECT_ID")
    base_tree = _git(root, "rev-parse", BASE_COMMIT + "^{tree}")
    if not expected_oid.fullmatch(BASE_COMMIT) or not expected_oid.fullmatch(base_tree):
        raise ValueError("BASELINE_GIT_OBJECT_FORMAT_MISMATCH")
    if base_tree != BASE_TREE:
        raise ValueError("WRONG_I23_TREE")
    if head != BASE_COMMIT and _git(root, "rev-parse", "HEAD^") != BASE_COMMIT:
        raise ValueError("WRONG_CANDIDATE_PARENT")
    changes = set(_git(root, "diff", "--name-only", BASE_COMMIT, "HEAD").splitlines())
    tracked = _git(root, "status", "--porcelain", "--untracked-files=all").splitlines()
    dirty = {line[3:] for line in tracked if len(line) >= 4}
    if not changes.issubset(OWNED) or not dirty.issubset(OWNED):
        raise ValueError("FOREIGN_OR_DIRTY_SOURCE")
    if head == BASE_COMMIT and tree != BASE_TREE:
        raise ValueError("WRONG_I23_TREE")
    pins = {}
    for relative, expected in sorted(FILE_PINS.items()):
        try:
            value = _file_sha(root, relative)
        except (OSError, ValueError) as exc:
            raise ValueError("SOURCE_UNREADABLE:" + relative) from exc
        if value != expected:
            raise ValueError("SOURCE_SHA_MISMATCH:" + relative)
        pins[relative] = value
    # Actual I23 module/protocol symbol import, not a simulated flag.
    if not callable(i23.attest_sources) or not callable(i23.audit_n22):
        raise ValueError("I23_IMPORT_CONTRACT_MISSING")
    i23.attest_sources(root)
    return CandidateIdentity(
        head=head, baseline_commit=BASE_COMMIT, baseline_tree=base_tree,
        candidate_tree=tree, file_sha256=pins, source_origins=ORIGINS,
        clean_or_owned_only=True, local_wire_imported=True,
        git_object_format=object_format,
    )


def cli_reasons(observation: CLIObservation) -> tuple[str, ...]:
    """OS exit, stdout semantics and nested denial MUST agree."""
    issues = []
    if type(observation.exit_code) is not int:
        return ("CLI_EXIT_NOT_INTEGER",)
    if len(observation.stdout) > 65536 or len(observation.stderr) > 65536:
        return ("CLI_OUTPUT_TOO_LARGE",)
    try:
        payload = json.loads(observation.stdout)
    except (ValueError, TypeError):
        return ("CLI_JSON_INVALID",)
    if type(payload) is not dict:
        return ("CLI_JSON_NOT_OBJECT",)

    def contains_denial(value: Any, depth: int = 0) -> bool:
        if depth > 6:
            return True
        if type(value) is str:
            upper = value.upper()
            return "DENIED" in upper or "NOT_ADMITTED" in upper or "NOT_VERIFIED" in upper
        if type(value) is dict:
            return any(contains_denial(v, depth + 1) for v in value.values())
        if type(value) is list:
            return any(contains_denial(v, depth + 1) for v in value)
        return False

    if contains_denial(payload) and observation.exit_code == 0:
        issues.append("CLI_EXIT_ZERO_WITH_JSON_DENIAL")
    if observation.exit_code != 0:
        issues.append("CLI_NONZERO_NOT_POSITIVE")
    if payload.get("status") != i23.PASS and payload.get("status") != LOCAL_STATUS:
        issues.append("CLI_STATUS_NOT_LOCAL_PASS")
    return tuple(issues)


def assess(
    identity: CandidateIdentity | None,
    evidence: Sequence[AuthorityEvidence] = (),
    cli: CLIObservation | None = None,
    local_wire: Mapping[str, Any] | None = None,
) -> AdmissionDecision:
    """No self-asserted JSON, unsigned roots or local PASS can elevate M16."""
    reasons: list[str] = []
    verified = identity is not None and identity.clean_or_owned_only
    if not verified:
        reasons.append("CANDIDATE_IDENTITY_NOT_VERIFIED")
    else:
        expected_oid = GIT_OBJECT_IDS.get(identity.git_object_format)
        if (identity.baseline_commit != BASE_COMMIT or
                identity.baseline_tree != BASE_TREE or
                expected_oid is None or
                not expected_oid.fullmatch(identity.baseline_commit) or
                not expected_oid.fullmatch(identity.baseline_tree) or
                not expected_oid.fullmatch(identity.head) or
                not expected_oid.fullmatch(identity.candidate_tree) or
                (identity.head == BASE_COMMIT and identity.candidate_tree != BASE_TREE)):
            reasons.append("WRONG_I23_TREE_OR_HEAD")
        if identity.source_origins != ORIGINS:
            reasons.append("SOURCE_ORIGIN_CHAIN_MISMATCH")
        if set(identity.file_sha256) != set(FILE_PINS) or any(
            identity.file_sha256.get(k) != v for k, v in FILE_PINS.items()
        ):
            reasons.append("SOURCE_SHA_PIN_MISMATCH")
        if not identity.local_wire_imported:
            reasons.append("I23_PROTOCOL_IMPORT_UNVERIFIED")
    slots: dict[str, str] = {key: "MISSING_UNVERIFIED" for key in GATES}
    seen_nonces: set[str] = set()
    seen_witnesses: set[str] = set()
    for claim in evidence:
        if claim.gate not in slots:
            reasons.append("UNKNOWN_AUTHORITY_GATE")
            continue
        if slots[claim.gate] != "MISSING_UNVERIFIED":
            reasons.append("DUPLICATE_AUTHORITY_GATE:" + claim.gate)
            continue
        invalid = (
            claim.status != "APPROVED"
            or not all(SAFE_ID.fullmatch(x) for x in (claim.issuer, claim.witness_id, claim.nonce))
            or not claim.signed_claim
            or not FILE_SHA256.fullmatch(claim.source_sha256)
            or identity is None or claim.candidate_commit != identity.head
            or claim.nonce in seen_nonces or claim.witness_id in seen_witnesses
        )
        if claim.gate == "original523_independent_grader":
            invalid |= (
                claim.original_count, claim.live_count, claim.replay_count
            ) != (523, 341, 182)
        if claim.gate == "phase_b200_independent_custodian":
            invalid |= claim.phase_b_count != 200
        if claim.gate == "real_all_outcome_p95":
            invalid |= (type(claim.p95_ms) not in (int, float) or
                        not 0 <= claim.p95_ms <= 15000)
        if invalid:
            slots[claim.gate] = "REJECTED_UNVERIFIED"
            reasons.append("AUTHORITY_UNTRUSTED_OR_MISBOUND:" + claim.gate)
        else:
            # There is deliberately no crypto verifier/trusted external root.
            # A caller-provided signature *string* is NOT authentication.
            slots[claim.gate] = "UNVERIFIED_EXTERNAL_WITNESS"
            reasons.append("INDEPENDENT_WITNESS_NOT_AUTHENTICATED:" + claim.gate)
            seen_nonces.add(claim.nonce)
            seen_witnesses.add(claim.witness_id)
    if cli is not None:
        reasons.extend(cli_reasons(cli))
    if not RELEASE_ADMISSION_ENABLED:
        reasons.append("M24_RELEASE_ADMISSION_DISABLED")
    if local_wire and local_wire.get("status") != "COMPLETE":
        reasons.append("LOCAL_PROTOCOL_NOT_COMPLETE")
    if not local_wire:
        reasons.append("LOCAL_PROTOCOL_NOT_EXECUTED")
    for gate, state in slots.items():
        if state == "MISSING_UNVERIFIED":
            reasons.append("AUTHORITY_MISSING:" + gate)
    # No payload, secrets, question text, source bodies or external corpus emitted.
    return AdmissionDecision(
        schema=SCHEMA, decision=DENIAL, local_state=LOCAL_STATUS,
        candidate_head=identity.head if identity else "",
        candidate_tree=identity.candidate_tree if identity else "",
        gate_states=slots, reasons=tuple(dict.fromkeys(reasons)),
        local_wire=dict(local_wire or {}),
    )


def local_protocol_preflight(worktree: Path, namespace: str) -> dict[str, Any]:
    """Genuinely launch separate I23-lineage N22 client and I15 server processes."""
    from knowledge_engine import m27_w5_n21_independent_local_client_v1_experimental as n22

    if not re.fullmatch(r"[a-z][a-z0-9-]{1,39}", namespace):
        raise ValueError("INVALID_LOCAL_NAMESPACE")
    case = n22.run_case(worktree, 0, "positive", namespace)
    client = case.get("client", {})
    cleanup = case.get("cleanup", {})
    first = client.get("first_answer_ns") if isinstance(client, dict) else None
    full = client.get("full_answer_ns") if isinstance(client, dict) else None
    terminal = client.get("terminal_ns") if isinstance(client, dict) else None
    before_terminal = (all(type(x) is int and x > 0
                           for x in (first, full, terminal)) and
                       first <= full < terminal)
    good = (case.get("status") == "COMPLETE" and
            isinstance(client, dict) and client.get("status") == "COMPLETE" and
            client.get("recv_calls", 0) > 0 and client.get("answer_events", 0) > 0 and
            case.get("endpoint", "").startswith("127.0.0.1:") and
            case.get("server_pid") != case.get("client_pid") and
            case.get("source_sha256") == n22.fixture_spec(0, namespace)["source_sha256"] and
            before_terminal and len(cleanup) == 2 and
            all(isinstance(v, dict) and v.get("reaped") is True
                for v in cleanup.values()))
    return {
        "status": "COMPLETE" if good else "DENIED",
        "mode": "isolated-synthetic-127.0.0.1",
        "source_revision": case.get("source_revision"),
        "source_sha256": case.get("source_sha256"),
        "client_pid": case.get("client_pid"),
        "server_pid": case.get("server_pid"),
        "recv_calls": client.get("recv_calls") if isinstance(client, dict) else None,
        "first_text_before_terminal": before_terminal,
        "cleanup_reaped": good,
    }


def write_receipt(scratch: Path, decision: AdmissionDecision) -> Path:
    """Outside Git, 0700 directory / 0600 no-follow exclusive receipt."""
    root = scratch.resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    path = root / "M24_ADMISSION_DECISION.json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        payload = (json.dumps(asdict(decision), sort_keys=True, indent=2) + "\n").encode()
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M24 synthetic-only candidate preflight")
    parser.add_argument("--worktree", required=True, type=Path)
    parser.add_argument("--scratch", required=True, type=Path)
    parser.add_argument("--namespace", default="m24-preflight")
    args = parser.parse_args(argv)
    identity = None
    local: dict[str, Any] = {}
    try:
        if args.scratch.resolve().is_relative_to(args.worktree.resolve()):
            raise ValueError("SCRATCH_INSIDE_SOURCE")
        identity = inspect_candidate(args.worktree)
        local = local_protocol_preflight(args.worktree, args.namespace)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        local = {"status": "DENIED", "reason": type(exc).__name__ + ":" + str(exc)[:120]}
    decision = assess(identity, local_wire=local)
    print(json.dumps(asdict(decision), sort_keys=True))
    try:
        write_receipt(args.scratch, decision)
    except OSError:
        return 22
    return 0 if local.get("status") == "COMPLETE" else 20


if __name__ == "__main__":
    raise SystemExit(main())
