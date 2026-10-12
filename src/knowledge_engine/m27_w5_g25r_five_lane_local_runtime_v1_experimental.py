"""G25R REAL five committed-source-lane local integration; no release rights.

Combines I25 actual P24/C24/E24/B24 physical client runtime with original,
separately committed M24 admission boundary and I23 local OS witnesses.
Synthetic, fixture-only, no external Provider/OCI or official evaluation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from knowledge_engine import m27_w5_i25_four_lane_staging_v1_experimental as i25
from knowledge_engine import m27_w5_m24_m16_admission_boundary_v1_experimental as m24

I25_COMMIT = "612dc046b74f66e2069597a79b915f293b729cc9"
M24_COMMIT = "144bf8c2fd65edd2b001e46376c2512c203560cf"
I23_COMMIT = "52c18e9979ec24dedaed35cae4ca8690d8dfddcd"
PASS = "G25R_LOCAL_FIVE_LANE_CODE_EXECUTION_PASS"
FAIL = "G25R_LOCAL_FIVE_LANE_NOT_VERIFIED"
M24_PATHS = (
    "docs/m27/m27_w5_m24_m16_admission_boundary_v1.md",
    "src/knowledge_engine/m27_w5_m24_m16_admission_boundary_v1_experimental.py",
    "tests/test_m27_w5_m24_m16_admission_boundary_v1_experimental.py",
)
M24_SHA = {
    "docs/m27/m27_w5_m24_m16_admission_boundary_v1.md":
        "d61e3201c41100a10e22b1597f75bc181625ea01f4d424881c4993754cf5d381",
    "src/knowledge_engine/m27_w5_m24_m16_admission_boundary_v1_experimental.py":
        "3cca255315251f8aabdb28c6b9494c27acffe84f2e166d1d5a3df646e79e9748",
    "tests/test_m27_w5_m24_m16_admission_boundary_v1_experimental.py":
        "0c3a71715298d89d9aedca2a9aa0f747c45be17e4db10efceb40f8e86fc9b176",
}
GATES = dict(i25.GATES)


class FiveDenied(ValueError):
    """Five-lane execution contract failed; official external grants absent."""


def need(condition: bool, reason: str) -> None:
    if not condition:
        raise FiveDenied(reason)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(root: Path, *arguments: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *arguments],
                            capture_output=True, timeout=18, check=False)
    need(result.returncode == 0 and len(result.stdout) < 4_000_000,
         "GIT_SOURCE_UNAVAILABLE:" + arguments[0])
    return result.stdout


def attest_five_sources(worktree: Path, m24_original: Path) -> dict[str, Any]:
    """Actual original commits, exact Git blob identities, no copied dummy lane."""
    need(worktree.is_absolute() and m24_original.is_absolute(),
         "SOURCE_PATHS_NOT_ABSOLUTE")
    need(worktree.is_dir() and not worktree.is_symlink()
         and m24_original.is_dir() and not m24_original.is_symlink(),
         "SOURCE_WORKTREE_INVALID")
    head = git(worktree, "rev-parse", "HEAD").decode().strip()
    need(bool(head) and head not in (I23_COMMIT, I25_COMMIT, M24_COMMIT),
         "STAGING_MUST_HAVE_FIFTH_COMMIT")
    need(git(worktree, "merge-base", "--is-ancestor", I25_COMMIT, "HEAD") == b"",
         "I25_NOT_ANCESTOR")
    need(not git(worktree, "status", "--porcelain=v1").strip(), "STAGING_GIT_DIRTY")
    need(git(m24_original, "rev-parse", "HEAD").decode().strip() == M24_COMMIT,
         "M24_ORIGINAL_HEAD_UNVERIFIED")
    need(git(m24_original, "rev-parse", "HEAD^").decode().strip() == I23_COMMIT,
         "M24_NOT_I23_CHILD")
    need(not git(m24_original, "status", "--porcelain=v1").strip(),
         "M24_ORIGINAL_DIRTY")
    raw_changes = git(m24_original, "diff-tree", "--no-commit-id",
                      "--name-status", "-r", "HEAD").decode().splitlines()
    need(raw_changes == ["A\t" + name for name in M24_PATHS],
         "M24_ORIGINAL_WRONG_THREE_PATHS")
    origins = i25.attest_four_origins(worktree)
    need(set(origins) == set(i25.ORIGINS), "FOUR_SOURCE_LANES_INVALID")
    m24_hashes = {}
    for name in M24_PATHS:
        integrated = worktree / name
        original = m24_original / name
        need(integrated.is_file() and original.is_file()
             and not integrated.is_symlink() and not original.is_symlink(),
             "M24_SOURCE_MISSING_OR_LINK")
        actual = integrated.read_bytes()
        orig = original.read_bytes()
        blob = git(worktree, "show", M24_COMMIT + ":" + name)
        need(actual == orig == blob and digest(actual) == M24_SHA[name],
             "M24_WRONG_PHYSICAL_ORIGIN_BLOB")
        m24_hashes[name] = digest(actual)
    m24_identity = m24.inspect_candidate(m24_original)
    need(m24_identity.head == M24_COMMIT
         and m24_identity.local_wire_imported
         and m24_identity.clean_or_owned_only, "M24_CANDIDATE_WITNESS_INVALID")
    return {"head": head, "i25_source_commit": I25_COMMIT,
            "i23_baseline": I23_COMMIT, "m24_original_commit": M24_COMMIT,
            "original_clean": True, "staging_clean": True,
            "source_origins": {**origins, "m24": m24_hashes},
            "m24_candidate": m24_identity}


def audit_completed_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    need(isinstance(receipt, dict), "FIVE_RECEIPT_NOT_OBJECT")
    need(receipt.get("status") == PASS and receipt.get("fixture_only") is True,
         "FIVE_RECEIPT_NOT_LOCAL_PASS")
    gates = receipt.get("gates")
    need(isinstance(gates, dict) and set(gates) == set(GATES)
         and all(gates[k] is False for k in GATES),
         "EXTERNAL_ADMISSION_UNVERIFIED")
    need(receipt.get("official_release_admitted") is False
         and receipt.get("real_app_client_p95_ms") is None
         and receipt.get("real_provider_calls") == 0, "FAKE_EXTERNAL_QUALIFICATION")
    source = receipt.get("source_provenance")
    need(isinstance(source, dict), "NO_FIVE_SOURCE_PROVENANCE")
    need(source.get("m24_original_commit") == M24_COMMIT
         and source.get("i25_source_commit") == I25_COMMIT
         and set(source.get("source_origins", {})) ==
         set(i25.ORIGINS) | {"m24"}, "FIVE_SOURCE_PROVENANCE_MISMATCH")
    need(source.get("staging_clean") is True
         and source.get("original_clean") is True, "DIRTY_FIVE_SOURCE")
    m = receipt.get("m24")
    need(isinstance(m, dict) and m.get("admission_decision") == m24.DENIAL
         and m.get("synthetic_local_status") == "COMPLETE"
         and m.get("external_gates_admitted") is False,
         "M24_NOT_FAIL_CLOSED")
    four = receipt.get("four_lanes")
    need(isinstance(four, dict) and four.get("status") == i25.PASS
         and four.get("sha256") and not four.get("problems"),
         "FOUR_LANE_PHYSICAL_RUNTIME_FAILED")
    local = receipt.get("physical_counts")
    need(isinstance(local, dict) and local.get("attempted") == 28
         and local.get("completed") == 12 and local.get("expected_denied") == 16
         and local.get("overlap_attempted") == 6
         and local.get("overlap_completed") == 3
         and local.get("overlap_denied") == 3
         and isinstance(local.get("late_client_ms"), (float, int))
         and local["late_client_ms"] >= 4500
         and local.get("c24_client_preterminal") is True,
         "PHYSICAL_COUNTS_INVALID")
    return {"five_source_lanes": 5, "physical_fixture_only": True,
            "external_qualified": False}


def run(worktree: Path, m24_original: Path, scratch: Path,
        namespace: str = "g25r-five") -> dict[str, Any]:
    need(worktree.is_absolute() and m24_original.is_absolute()
         and scratch.is_absolute() and not scratch.is_symlink()
         and not scratch.resolve().is_relative_to(worktree.resolve()),
         "WRONG_SCRATCH_OR_SOURCE_SCOPE")
    need(bool(namespace) and namespace.isascii()
         and namespace.replace("-", "").isalnum()
         and len(namespace) <= 17 and namespace[0].isalpha(),
         "NAMESPACE_INVALID")
    scratch.mkdir(parents=True, exist_ok=True, mode=0o700)
    provenance = attest_five_sources(worktree, m24_original)
    identity = provenance.pop("m24_candidate")
    local = m24.local_protocol_preflight(m24_original, namespace + "-m24")
    need(local["status"] == "COMPLETE" and local["first_text_before_terminal"]
         and local["cleanup_reaped"], "M24_OS_CLIENT_NOT_COMPLETED")
    decision = m24.assess(identity, local_wire=local)
    need(decision.decision == m24.DENIAL
         and all(x != "APPROVED" for x in decision.gate_states.values()),
         "M24_FAKE_EXTERNAL_AUTHORITY")
    four = i25.run(worktree, scratch / "four", namespace)
    need(four.get("status") == i25.PASS, "I25_LOCAL_RUNTIME_FAILED")
    raw = json.loads(Path(four["receipt_path"]).read_bytes())
    physical = json.loads(Path(raw["outcomes"]["i23"]["receipt_path"]).read_bytes())
    audited = physical["outcomes"]["n22_audited"]
    overlap = physical["outcomes"]["l22_six"]
    delay = physical["outcomes"]["l22_delayed"]
    counts = {"attempted": 28, "completed": audited["completed"],
              "expected_denied": audited["expected_denied"],
              "overlap_attempted": 6,
              "overlap_completed": overlap["completed"],
              "overlap_denied": overlap["expected_denied"],
              "late_client_ms": delay["delay_elapsed_ms"],
              "c24_client_preterminal":
                  raw["outcomes"]["c24_client"]["first_text_ns"] <
                  raw["outcomes"]["c24_client"]["terminal_ns"]}
    report = {"schema": "m27.w5.g25r.five_lane_local.v1", "status": PASS,
              "fixture_only": True, "source_provenance": provenance,
              "m24": {"admission_decision": decision.decision,
                      "synthetic_local_status": local["status"],
                      "external_gates_admitted": False,
                      "admission_reasons": list(decision.reasons)},
              "four_lanes": four, "physical_counts": counts,
              "gates": GATES, "official_release_admitted": False,
              "real_app_client_p95_ms": None, "real_provider_calls": 0}
    audit_completed_receipt(report)
    out = scratch / "G25R_FIVE_LANE_LOCAL_RECEIPT.json"
    payload = (json.dumps(report,sort_keys=True,indent=2)+"\n").encode()
    out.write_bytes(payload)
    out.chmod(0o600)
    return {"status": PASS,"receipt_path": str(out),
            "sha256": digest(payload), "physical_counts": counts,
            "official_gates": GATES, "external_admitted": False}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--worktree", type=Path, required=True)
    p.add_argument("--m24-original", type=Path, required=True)
    p.add_argument("--scratch", type=Path, required=True)
    p.add_argument("--namespace", default="g25r-five")
    a = p.parse_args(argv)
    try:
        result = run(a.worktree, a.m24_original, a.scratch, a.namespace)
    except (FiveDenied, i25.IntegrationDenied, OSError, ValueError,
            subprocess.SubprocessError, KeyError, TypeError,
            AssertionError) as exc:
        result = {"status": FAIL, "reason": type(exc).__name__ + ":" + str(exc)[:160],
                  "official_gates": GATES, "external_admitted": False}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == PASS else 20


if __name__ == "__main__":
    raise SystemExit(main())
