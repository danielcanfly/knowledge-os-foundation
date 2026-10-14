"""A08 experimental, deterministic local ablation. NO real provider, billing, or promotion."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD = Path(__file__).with_name("workload.json")
POLICY_ABI = "m27-a08-decision-cost/v1"
PROPOSAL_ABI = "m27-a08-review-only/v1"
# TEST-ONLY fictional quote, denominated micro-USD, NOT a vendor rate card.
QUOTE = {"id": "A08_SIMULATED_QUOTE_V1", "input_micro_usd_per_1k": 1000,
         "output_micro_usd_per_1k": 3000, "real_invoice": False}
SENTINEL = object()


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def percentile95(data: list[int]) -> int | None:
    return sorted(data)[math.ceil(.95 * len(data)) - 1] if data else None


@dataclass(frozen=True)
class Policy:
    policy_id: str
    revision: str
    fixed_rounds: int
    adaptive: bool
    max_provider_calls: int = 3
    max_input_tokens: int = 900
    max_output_tokens: int = 360
    max_cost_micro_usd: int = 1800
    max_latency_ms: int = 480
    max_failovers: int = 1
    max_tool_calls: int = 0

    def __post_init__(self) -> None:
        if any(type(v) is not int for v in (
            self.fixed_rounds, self.max_provider_calls, self.max_input_tokens,
            self.max_output_tokens, self.max_cost_micro_usd, self.max_latency_ms,
            self.max_failovers, self.max_tool_calls)):
            raise ValueError("budget caps must be finite integers, not booleans")
        if not self.policy_id or not self.revision:
            raise ValueError("policy version required")
        if not (1 <= self.fixed_rounds <= self.max_provider_calls <= 3):
            raise ValueError("bounded number of rounds required")
        if not (0 <= self.max_failovers <= 1 and self.max_tool_calls == 0):
            raise ValueError("provider-only sandbox: no tool grants")
        if any(v <= 0 for v in (self.max_input_tokens, self.max_output_tokens,
                               self.max_cost_micro_usd, self.max_latency_ms)):
            raise ValueError("finite positive cost, token, time limits required")


BASELINE = Policy("a08-fixed", "1.0.0", fixed_rounds=3, adaptive=False)
CANDIDATE = Policy("a08-adaptive", "1.1.0-review-only", fixed_rounds=3, adaptive=True)
# This is the immutable deployed/reference pointer in this experiment, not a Production pointer.
ACTIVE_POLICY_ID = BASELINE.policy_id


def validate_source(case: dict) -> None:
    docs = case["source_evidence"]
    if not docs or case["kind"] not in ("QA", "RESEARCH"):
        raise ValueError("invalid firstparty workload")
    for evidence in docs:
        path = ROOT / evidence["path"]
        if not path.is_file() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError("disallowed source path")
        raw = path.read_bytes()
        if digest(raw) != evidence["sha256"]:
            raise ValueError("SOURCE_DRIFT")
        if evidence["quote"] not in raw.decode("utf-8"):
            raise ValueError("SOURCE_QUOTE_NOT_FOUND")
        if len(evidence["quote"]) < 15:
            raise ValueError("source quote too short")


def load_workload() -> list[dict]:
    obj = json.loads(WORKLOAD.read_text())
    if obj["abi"] != "m27-a08-firstparty-workload/v1" or len(obj["cases"]) < 32:
        raise ValueError("unqualified workload")
    ids = [c["id"] for c in obj["cases"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate workload identifiers")
    for case in obj["cases"]:
        validate_source(case)
        if case["split"] not in ("development", "independent_holdout"):
            raise ValueError("invalid split")
        if case["needed_rounds"] != len(case["source_evidence"]):
            raise ValueError("fixture gold rounds inconsistent")
        if case["quota_calls"] not in (2, 3):
            raise ValueError("invalid test call ceiling")
    return obj["cases"]


def forecast_charge(input_tokens: int, output_tokens: int) -> int:
    return (input_tokens * QUOTE["input_micro_usd_per_1k"] +
            output_tokens * QUOTE["output_micro_usd_per_1k"] + 999) // 1000


def run_case(case: dict, policy: Policy, *, fault: str = "",
             quote: dict | None = None, provider_receipt: dict | None | object = SENTINEL,
             failover_permission: bool = True) -> dict:
    """Run a sandboxed synthetic provider, with all budget checks BEFORE dispatch.

    Receipt structure describes deterministic fixture usage, NEVER an actual invoice.
    Unknown side effects and untracked usage are terminal and not blindly retried.
    """
    validate_source(case)
    q = QUOTE if quote is None else quote
    if q != QUOTE:
        return _outcome(case, policy, "UNTRUSTED_OR_STALE_QUOTE", [], 0)
    if policy.max_tool_calls:
        return _outcome(case, policy, "TOOLS_NOT_GRANTED", [], 0)
    rounds = case["needed_rounds"] if policy.adaptive else policy.fixed_rounds
    events: list[dict] = []
    actual_evidence = 0
    input_tokens = output_tokens = spend = latency = 0
    provider_attempts = 0
    no_send_seen = False
    for round_idx in range(rounds):
        if provider_attempts >= min(policy.max_provider_calls, case["quota_calls"]):
            return _outcome(case, policy, "CALL_QUOTA_EXCEEDED", events, actual_evidence)
        # Known upper-bounded response for this simulated scenario; reservations are conservative.
        this_input = 170 + round_idx * 10
        this_output = 60
        this_latency = 120 + round_idx * 15
        charge = forecast_charge(this_input, this_output)
        if input_tokens + this_input > policy.max_input_tokens or output_tokens + this_output > policy.max_output_tokens:
            return _outcome(case, policy, "TOKEN_CAP_EXCEEDED", events, actual_evidence)
        if spend + charge > policy.max_cost_micro_usd:
            return _outcome(case, policy, "COST_CAP_EXCEEDED", events, actual_evidence)
        if latency + this_latency > policy.max_latency_ms:
            return _outcome(case, policy, "LATENCY_CAP_EXCEEDED", events, actual_evidence)
        provider_attempts += 1
        route = "primary"
        if fault == "NO_SEND" and not no_send_seen:
            no_send_seen = True
            events.append({"route": route, "state": "NO_SEND", "attempt": provider_attempts})
            if not failover_permission or policy.max_failovers == 0:
                return _outcome(case, policy, "FAILOVER_NOT_AUTHORIZED", events, actual_evidence)
            if provider_attempts >= min(policy.max_provider_calls, case["quota_calls"]):
                return _outcome(case, policy, "FAILOVER_QUOTA_EXCEEDED", events, actual_evidence)
            provider_attempts += 1
            route = "backup"
        elif fault in ("UNKNOWN_EFFECT", "TIMEOUT_AFTER_SEND"):
            events.append({"route": route, "state": "POSSIBLY_SENT_UNRESOLVED",
                           "attempt": provider_attempts})
            return _outcome(case, policy, "UNKNOWN_EFFECT_RECONCILE_REQUIRED", events, actual_evidence)
        elif fault == "TIMEOUT_BEFORE_SEND":
            events.append({"route": route, "state": "NO_SEND", "attempt": provider_attempts})
            return _outcome(case, policy, "SAFE_NO_SEND_TIMEOUT", events, actual_evidence)
        # An actual provider receipt must be verified if supplied; this nonprod driver
        # accepts only its explicitly deterministic simulator usage.
        if provider_receipt is not SENTINEL:
            if provider_receipt is None:
                events.append({"route": route, "state": "UNRESOLVED_USAGE", "attempt": provider_attempts})
                return _outcome(case, policy, "USAGE_RECEIPT_UNKNOWN", events, actual_evidence)
            if (not isinstance(provider_receipt, dict) or
                provider_receipt.get("input_tokens") != this_input or
                provider_receipt.get("output_tokens") != this_output or
                provider_receipt.get("attempt_id") != case["id"] + ":" + str(round_idx)):
                events.append({"route": route, "state": "UNRESOLVED_USAGE", "attempt": provider_attempts})
                return _outcome(case, policy, "USAGE_RECEIPT_MISMATCH", events, actual_evidence)
        input_tokens += this_input
        output_tokens += this_output
        spend += charge
        latency += this_latency
        if round_idx < case["needed_rounds"]:
            actual_evidence += 1
        events.append({"route": route, "state": "SIMULATED_SETTLED", "attempt": provider_attempts,
                       "input_tokens": this_input, "output_tokens": this_output,
                       "latency_ms_modeled": this_latency, "cost_micro_usd_modeled": charge,
                       "quote_id": q["id"], "source_verified": actual_evidence,
                       "quote_sha256": (digest(case["source_evidence"][round_idx]["quote"].encode())
                                        if round_idx < case["needed_rounds"] else None)})
    status = "ACCEPTED" if actual_evidence == len(case["source_evidence"]) else "ORACLE_INCOMPLETE"
    # Preserve all actual counter details for failures, never silently count failed as free.
    return _outcome(case, policy, status, events, actual_evidence)


def _outcome(case: dict, policy: Policy, status: str, events: list[dict], evidence_count: int) -> dict:
    settled = [e for e in events if e["state"] == "SIMULATED_SETTLED"]
    return {
        "task_id": case["id"], "split": case["split"], "kind": case["kind"],
        "policy": policy.policy_id, "policy_revision": policy.revision, "status": status,
        "accepted": status == "ACCEPTED", "evidence_verified": evidence_count,
        "expected_evidence": len(case["source_evidence"]),
        "provider_attempts": len(events) if not events else max(e["attempt"] for e in events),
        "tokens_input_simulated": sum(e["input_tokens"] for e in settled),
        "tokens_output_simulated": sum(e["output_tokens"] for e in settled),
        "cost_micro_usd_simulated": sum(e["cost_micro_usd_modeled"] for e in settled),
        "latency_ms_modeled": sum(e["latency_ms_modeled"] for e in settled),
        "events": events, "has_real_provider_receipt": False, "has_real_invoice": False,
        "oracle": "EXACT_FIRSTPARTY_SOURCE_QUOTE_SHA256_PINNED",
    }


def evaluate(cases: list[dict], policy: Policy) -> dict:
    rows = [run_case(c, policy) for c in cases]
    successful = [r for r in rows if r["accepted"]]
    return {
        "policy": asdict(policy), "total": len(rows), "accepted": len(successful),
        "failed": len(rows) - len(successful),
        "quality_accepted_percent": round(100 * len(successful) / len(rows), 2),
        "quality_metric_kind": "DETERMINISTIC_FIRSTPARTY_QUOTE_COMPLETENESS_NOT_LLM_ANSWER_QUALITY",
        "total_provider_attempts": sum(x["provider_attempts"] for x in rows),
        "total_input_tokens_simulated": sum(x["tokens_input_simulated"] for x in rows),
        "total_output_tokens_simulated": sum(x["tokens_output_simulated"] for x in rows),
        "total_cost_micro_usd_simulated": sum(x["cost_micro_usd_simulated"] for x in rows),
        "cost_per_accepted_micro_usd_simulated": (round(sum(x["cost_micro_usd_simulated"] for x in rows) / len(successful), 2) if successful else None),
        "p95_latency_ms_modeled_accepted": percentile95([x["latency_ms_modeled"] for x in successful]),
        "failed_reasons": {name: sum(r["status"] == name for r in rows)
                           for name in sorted(set(r["status"] for r in rows if not r["accepted"]))},
        "rows": rows,
    }


def propose_from_real_failure(baseline: dict, candidate: dict) -> dict:
    failed = next((r for r in baseline["rows"]
                   if r["status"] in ("CALL_QUOTA_EXCEEDED", "LATENCY_CAP_EXCEEDED")), None)
    if failed is None:
        raise ValueError("must observe actual local baseline failure before proposing")
    fixed = next(r for r in candidate["rows"] if r["task_id"] == failed["task_id"])
    if not fixed["accepted"]:
        raise ValueError("candidate did not repair observed failure")
    return {
        "abi": PROPOSAL_ABI, "id": "A08-PROP-" + digest(canonical(failed))[:12],
        "origin": {"task_id": failed["task_id"], "failure_status": failed["status"],
                   "failure_row_sha256": digest(canonical(failed))},
        "candidate": CANDIDATE.policy_id, "candidate_revision": CANDIDATE.revision,
        "diff": {"fixed_rounds": 3, "adaptive_stop_on_source_oracle": True,
                 "maintain_fail_closed_caps": True},
        "rationale": "Three fixed rounds exceed bounded owner-firstparty task call ceiling after proof is sufficient.",
        "independent_holdout_required": True, "review_required": True,
        "status": "READY_FOR_REVIEW_NOT_APPROVED", "approved": False,
        "autopromote": False, "rollback_to": BASELINE.policy_id,
        "source": "local-observed failure only; no private payloads",
    }


def heldout_review(holdout_cases: list[dict], proposal: dict) -> dict:
    # Independent evaluator consumes only untouched holdout cases; no training updates.
    if len(holdout_cases) < 8 or any(c["split"] != "independent_holdout" for c in holdout_cases):
        raise ValueError("independent holdout separation required")
    reference = evaluate(holdout_cases, BASELINE)
    candidate = evaluate(holdout_cases, CANDIDATE)
    gates = {
        "quality_nondecreasing": candidate["accepted"] >= reference["accepted"],
        "cost_per_accepted_lower": (candidate["cost_per_accepted_micro_usd_simulated"] is not None
                                   and reference["cost_per_accepted_micro_usd_simulated"] is not None
                                   and candidate["cost_per_accepted_micro_usd_simulated"] < reference["cost_per_accepted_micro_usd_simulated"]),
        "modeled_p95_improves": (candidate["p95_latency_ms_modeled_accepted"] is not None
                                and reference["p95_latency_ms_modeled_accepted"] is not None
                                and candidate["p95_latency_ms_modeled_accepted"] < reference["p95_latency_ms_modeled_accepted"]),
        "not_promoted": ACTIVE_POLICY_ID == BASELINE.policy_id and not proposal["autopromote"],
        "same_holdout_roster": [r["task_id"] for r in reference["rows"]] == [r["task_id"] for r in candidate["rows"]],
    }
    return {"evaluator": "A08_LOCAL_INDEPENDENT_HOLDOUT_EVALUATOR_V1",
            "holdout_ids_sha256": digest(canonical([c["id"] for c in holdout_cases])),
            "proposal_id": proposal["id"], "gates": gates,
            "review_gate": "PENDING_HUMAN_REVIEW",
            "candidate_deployable": False, "eligible_for_review": all(gates.values()),
            "rollback_test": {"before": CANDIDATE.policy_id,
                              "after": BASELINE.policy_id,
                              "reference_unchanged": ACTIVE_POLICY_ID == BASELINE.policy_id},
            "reference": {k: v for k, v in reference.items() if k != "rows"},
            "candidate": {k: v for k, v in candidate.items() if k != "rows"}}


def main(output: Path) -> dict:
    cases = load_workload()
    dev = [c for c in cases if c["split"] == "development"]
    holdout = [c for c in cases if c["split"] == "independent_holdout"]
    before = evaluate(dev, BASELINE)
    after = evaluate(dev, CANDIDATE)
    proposal = propose_from_real_failure(before, after)
    heldout = heldout_review(holdout, proposal)
    if not heldout["eligible_for_review"]:
        raise RuntimeError("independent holdout gates failed")
    result = {
        "abi": POLICY_ABI, "source": "I37 exact nonprod source base",
        "source_commit_parent": "216f912994d20d134b1c8af50f7b2dd1a1c89a15",
        "workload_sha256": digest(WORKLOAD.read_bytes()),
        "quote": QUOTE, "economics_class": "FIXTURE_ONLY_NOT_ACTUAL_PROVIDER",
        "metrics_class": "MODELED_LATENCY_AND_SIMULATED_USAGE_NOT_NETWORK_TIME",
        "development": {
            "baseline": {k: v for k, v in before.items() if k != "rows"},
            "candidate": {k: v for k, v in after.items() if k != "rows"}},
        "development_rows": {"baseline": before["rows"], "candidate": after["rows"]},
        "independent_holdout_rows": {
            "baseline": evaluate(holdout, BASELINE)["rows"],
            "candidate": evaluate(holdout, CANDIDATE)["rows"]},
        "learning_proposal": proposal, "independent_holdout": heldout,
        "active_policy": ACTIVE_POLICY_ID, "product_release": "UNCHANGED",
        "real_provider_receipt": False, "real_invoice": False,
        "forbidden_actions": ["production_write", "memory_write", "skill_write", "auto_promote"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    obj = main(args.output)
    print(json.dumps({"development_baseline": obj["development"]["baseline"],
                      "development_candidate": obj["development"]["candidate"],
                      "independent_holdout": obj["independent_holdout"],
                      "learning_proposal": obj["learning_proposal"],
                      "output": str(args.output)}, sort_keys=True))
