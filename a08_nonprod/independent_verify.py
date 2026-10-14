"""Independent-codepath local reviewer of A08 output, not an independent human or LLM."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def hash_bytes(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def percentile95(data):
    return sorted(data)[math.ceil(.95 * len(data)) - 1] if data else None


def verify(result_path: Path) -> dict:
    raw = result_path.read_bytes()
    result = json.loads(raw)
    workload_raw = (HERE / "workload.json").read_bytes()
    tasklist = json.loads(workload_raw)["cases"]
    assert result["workload_sha256"] == hash_bytes(workload_raw), "fixture mismatch"
    assert len(tasklist) == 48, "roster changed"
    reference_ids = [c["id"] for c in tasklist[:32]]
    heldout_ids = [c["id"] for c in tasklist[32:]]
    assert all(c["split"] == "development" for c in tasklist[:32])
    assert all(c["split"] == "independent_holdout" for c in tasklist[32:])
    quote_dev = {e["quote"] for c in tasklist[:32] for e in c["source_evidence"]}
    quote_holdout = {e["quote"] for c in tasklist[32:] for e in c["source_evidence"]}
    assert not quote_dev.intersection(quote_holdout), "holdout leakage"
    for case in tasklist:
        for e in case["source_evidence"]:
            file = (ROOT / e["path"]).resolve()
            assert file.is_relative_to(ROOT.resolve()), "path traversal"
            data = file.read_bytes()
            assert hash_bytes(data) == e["sha256"] and e["quote"] in data.decode(), "source mismatch"
    all_rows = []
    for section_name, roster_ids in (("development", reference_ids),
                                      ("independent_holdout", heldout_ids)):
        rowsection = result[section_name + "_rows"]
        meta = result[section_name] if section_name == "development" else result["independent_holdout"]
        for policy in ("baseline", "candidate"):
            rows = rowsection[policy]
            assert [r["task_id"] for r in rows] == roster_ids, "roster mismatch"
            counts = {"accepted": 0, "cost": 0, "attempts": 0, "latencies": []}
            for row, case_id in zip(rows, roster_ids):
                case = next(c for c in tasklist if c["id"] == case_id)
                assert row["split"] == case["split"] and row["kind"] == case["kind"]
                assert row["expected_evidence"] == len(case["source_evidence"])
                assert row["accepted"] == (row["status"] == "ACCEPTED"), "false acceptance"
                assert not row["has_real_invoice"] and not row["has_real_provider_receipt"]
                settled = [e for e in row["events"] if e["state"] == "SIMULATED_SETTLED"]
                cost = sum(e["cost_micro_usd_modeled"] for e in settled)
                duration = sum(e["latency_ms_modeled"] for e in settled)
                inputtokens = sum(e["input_tokens"] for e in settled)
                outputtokens = sum(e["output_tokens"] for e in settled)
                attempts = max([e["attempt"] for e in row["events"]], default=0)
                assert attempts <= min(case["quota_calls"], 3), "overquota"
                assert row["provider_attempts"] == attempts, "attempts mismatch"
                assert row["cost_micro_usd_simulated"] == cost <= 1800, "cost accounting"
                assert row["latency_ms_modeled"] == duration <= 480, "latency accounting"
                assert row["tokens_input_simulated"] == inputtokens <= 900
                assert row["tokens_output_simulated"] == outputtokens <= 360
                assert len(set(e["attempt"] for e in row["events"])) == len(row["events"]), "attempt replay"
                if row["accepted"]:
                    expected = [hash_bytes(e["quote"].encode()) for e in case["source_evidence"]]
                    actual = [e["quote_sha256"] for e in settled if e.get("quote_sha256")]
                    assert actual == expected, "unverified claimed evidence"
                    assert row["evidence_verified"] == len(expected), "unverified accepted"
                    counts["accepted"] += 1
                    counts["latencies"].append(duration)
                else:
                    assert row["status"] != "ACCEPTED"
                counts["cost"] += cost
                counts["attempts"] += attempts
                all_rows.append(row)
            key = "reference" if section_name == "independent_holdout" and policy == "baseline" else policy
            summary = meta[key]
            assert summary["accepted"] == counts["accepted"], "fake pass-count"
            assert summary["total_cost_micro_usd_simulated"] == counts["cost"], "fake spend"
            assert summary["total_provider_attempts"] == counts["attempts"], "fake attempts"
            assert summary["p95_latency_ms_modeled_accepted"] == percentile95(counts["latencies"])
    baseline = result["development_rows"]["baseline"]
    candidate = result["development_rows"]["candidate"]
    failed = next(r for r in baseline if r["status"] == "CALL_QUOTA_EXCEEDED")
    proposal = result["learning_proposal"]
    assert proposal["origin"]["task_id"] == failed["task_id"]
    assert proposal["origin"]["failure_row_sha256"] == hash_bytes(canonical(failed))
    assert next(r for r in candidate if r["task_id"] == failed["task_id"])["accepted"]
    assert proposal["status"] == "READY_FOR_REVIEW_NOT_APPROVED"
    assert proposal["review_required"] and not proposal["approved"] and not proposal["autopromote"]
    assert result["active_policy"] == "a08-fixed", "self-promotion forbidden"
    heldout = result["independent_holdout"]
    assert heldout["review_gate"] == "PENDING_HUMAN_REVIEW"
    assert not heldout["candidate_deployable"] and heldout["eligible_for_review"]
    assert heldout["holdout_ids_sha256"] == hash_bytes(canonical(heldout_ids))
    assert all(heldout["gates"].values()), "review gate failed"
    assert heldout["reference"]["accepted"] == 8 and heldout["candidate"]["accepted"] == 16
    assert result["real_provider_receipt"] is False and result["real_invoice"] is False
    assert result["product_release"] == "UNCHANGED"
    return {
        "independent_codepath_verdict": "PASS_LOCAL_FIXTURE_ONLY",
        "actual_real_finops_verdict": "UNQUALIFIED_NO_PROVIDER_INVOICE",
        "development_count": len(reference_ids), "holdout_count": len(heldout_ids),
        "rows_reverified": len(all_rows), "source_sha_verified": True,
        "negative_failure_preserved": failed["status"],
        "learning_review_only": True, "rollback_reference": proposal["rollback_to"],
        "artifact_sha256": hash_bytes(raw), "workload_sha256": hash_bytes(workload_raw),
        "independent_human_review": False, "true_blind_grader": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    decision = verify(args.input)
    args.output.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n")
    print(json.dumps(decision, sort_keys=True))
