"""Independent OS read-only local acceptance observer for I28 evidence.
No production, rights grant, secret, external issuer, or self-signed success.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(run: Path, fault: Path) -> dict:
    result = json.loads((run / "i28_integrated_receipt.json").read_text())
    fault_rows = json.loads((fault / "summary.json").read_text())
    cases = {c["case"]: c for c in fault_rows["cases"]}
    browser = result["chrome_client.json"]
    c24 = result["c24_client.json"]
    artifact = Path(result["research"]["artifact_path"])
    denied = [
        a for a in result["attempts"] if a.get("denied") is True or a.get("expected_denial") is True
    ]
    unknown = [a for a in result["attempts"] if a.get("ar09_reason") == "ORACLE_UNAVAILABLE"]
    checks = {
        "distinct_real_browser_process": (
            result["attempts"][1]["pid"] != result["server_pid"]
            and browser["transport"] == "chrome_fetch_readable_stream"
            and browser["observed_chunk_count"] >= 2
        ),
        "browser_first_cited_text_before_terminal": (
            browser["cited_before_terminal"] is True
            and browser["first_substantive_event_index"] < browser["terminal_event_index"]
            and browser["first_substantive_sha256"] is not None
        ),
        "c24_distinct_client_process": (
            c24["client_pid"] != result["server_pid"]
            and c24["client_pid"] != result["attempts"][1]["pid"]
            and c24["first_substantive_text_ns"] < c24["terminal_ns"]
            and c24["progress_events"] == 1
            and c24["answer_events"] >= 1
            and bool(c24["source_native_citations"])
        ),
        "client_cited_original_exact_source_sha": (
            c24["answer_sha256"] == c24["source_native_citations"][0]["source_sha256"]
            and c24["answer_sha256"] == browser["first_substantive_sha256"]
            if browser["first_substantive_byte_length"] == c24["answer_bytes"]
            else c24["answer_sha256"] == result["runC24_server.json"]["cited_sha256"][0]
        ),
        "research_file_original_bytes_independently_hashed": (
            artifact.is_file()
            and sha(artifact) == result["research"]["artifact_sha256"]
            and artifact.read_bytes().startswith(b"#")
            and result["research"]["checkpoint_count"] == 2
        ),
        "coding_os_fixture_independently_recorded": (
            result["coding"]["status"] == "CODING_LOCAL_VERIFIED_FIXTURE_ONLY"
            and result["coding"]["exit"] == 0
            and result["coding"]["ephemeral_cleaned"]
            and result["coding"]["head"]["state"] == "LOCAL_VERIFIED_APPLIED"
        ),
        "revocation_actual_separate_os_child": (
            result["revocation"]["child"]["child_pid"] != result["entrypoint_pid"]
            and result["revocation"]["child"]["expected_denied"]
            and result["revocation"]["physical_flush_after_revocation"] == 0
            and result["revocation"]["child_exit"] == 0
        ),
        "no_cross_tenant_or_unauthorized_writes": (
            all(result["negative_guards"]["results"].values())
            and result["negative_guards"]["outbox_unchanged"]
            and result["attempts"][0]["http_status"] == 400
            and result["attempts"][0]["no_journal_side_effect"]
        ),
        "k28_six_distinct_real_sigkill_restart": (
            len(cases) == 6
            and all(
                c["worker_exit"] == -9
                and c["restart_pid"] != c["worker_pid"]
                and c["service_pid"] != c["worker_pid"]
                for c in cases.values()
            )
        ),
        "k28_no_double_effect_after_lost_ack": (
            cases["after_send_before_ack"]["service"]["effect_count"] == 1
            and cases["after_send_before_ack"]["service"]["post_attempt_count"] == 1
        ),
        "k28_unknown_effects_not_excluded": (
            cases["observer_unknown"]["terminal_or_unknown"] == "UNKNOWN_EFFECT"
            and cases["observer_timeout"]["terminal_or_unknown"] == "UNKNOWN_EFFECT"
            and fault_rows["failed"] == 0
        ),
        "ar09_untrusted_oracle_fenced_with_full_denominator": (
            len(unknown) == len(result["attempts"])
            and all(x["externally_verified"] is False for x in result["attempts"])
        ),
        "ar10_never_self_promotes": (
            result["ar10"]["candidate_only"]
            and not result["ar10"]["auto_promoted"]
            and result["ar10"]["release_writes"] == 0
            and result["ar10"]["tool_effects"] == 0
        ),
        "attempted_denied_unknown_kept": (len(denied) >= 6 and len(result["attempts"]) >= 10),
    }
    return {
        "schema": "m27.i28.local_independent_os_acceptance.v1",
        "observer_pid": os.getpid(),
        "entrypoint_pid": result["entrypoint_pid"],
        "fixture_only": True,
        "official_signed_authority": False,
        "attempted": len(result["attempts"]),
        "denied_or_expected_denied": len(denied),
        "unknown_or_unqualified": len(unknown),
        "fault_cases": len(cases),
        "checks": checks,
        "passed": sum(checks.values()),
        "failed": sum(not v for v in checks.values()),
        "local_acceptance": all(checks.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--fault", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    receipt = inspect(args.run, args.fault)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["local_acceptance"] else 27


if __name__ == "__main__":
    raise SystemExit(main())
