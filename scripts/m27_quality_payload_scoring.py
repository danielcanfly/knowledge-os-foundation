from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from tests.test_m27_production_evidence_bridge import (
    ProductionKnowledgeProvider,
    _production_bridge_material,
    _provider,
    _request,
)

from knowledge_engine.m26_pa5_v8_live import MODEL, MiniMaxClient
from knowledge_engine.m27_independent_quality_scorer import (
    M27_INDEPENDENT_QUALITY_SCHEMA,
    M27_SCORING_POLICY_VERSION,
    per_case_scores_digest,
    sha256_file,
)
from knowledge_engine.m27_runtime_harness import M27RuntimeHarness
from knowledge_engine.m27_tool_executor import ReadOnlyToolExecutor
from knowledge_engine.m27_workspace_store import WorkspaceStore
from knowledge_engine.qa_answer_quality_evaluator import (
    ANSWER_QUALITY_CRITERION_MAX,
    ANSWER_QUALITY_PASS_THRESHOLD,
    ANSWER_QUALITY_RUBRIC_VERSION,
    SEMANTIC_EVALUATOR_VERSION,
    AnswerQualityEvaluation,
    answer_quality_boundary_codes,
    canonical_failure_provenance,
    validate_answer_quality_evaluation,
)
from scripts.m27_fresh_small_smoke import runtime_input

ROOT = Path(__file__).resolve().parents[1]
ADMISSION = Path(
    "/home/ubuntu/LLM_Wiki-m27-admission-release-rerun/docs/m27/research/admission_ladder_receipts.json"
)
OUT = ROOT / "docs/m27/research/quality_payload_score_receipts.json"
WORK = Path("/tmp/m27-quality-payload-scoring-workspaces")
RELEASE_HEAD = "f406be4a07ae360655e073c4dea1e13fe2796689"
HARD_GATE_HEAD = "e864417c2380f2ce8d6c24576fb129c37b95ccad"
QUALITY_GATE_HEAD = "80b0b0ddc1ccc52ccb86b3acb1d2e9782579102a"
POLICY = "unique-question-stratified-all-verified-categories/v1"


def canonical_digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def load_sample() -> tuple[list[dict[str, Any]], int]:
    doc = json.loads(ADMISSION.read_text())
    eligible = [
        x
        for x in doc["gates"]["full523"]["cases"]
        if x.get("expectation") == "verified_cited_answer"
    ]
    sample: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in eligible:
        key = (str(row["category"]), str(row["question"]))
        if key in seen:
            continue
        seen.add(key)
        sample.append(row)
    categories = {str(x["category"]) for x in eligible}
    if {str(x["category"]) for x in sample} != categories:
        raise RuntimeError("sample does not cover every verified-answer category")
    if len(sample) != 9:
        raise RuntimeError(f"expected 9 unique verified prompts, got {len(sample)}")
    return sample, len(eligible)


def capture(row: dict[str, Any]) -> dict[str, Any]:
    evidence, authority = _production_bridge_material()
    provider = _provider()
    request = replace(_request(provider, evidence, authority), question=str(row["question"]))
    case_id = str(row["case_id"])
    harness = M27RuntimeHarness(
        workspace_store=WorkspaceStore(root=WORK / case_id / "workspace"),
        tool_executor=ReadOnlyToolExecutor(
            knowledge_provider=ProductionKnowledgeProvider(evidence)
        ),
    )
    result = harness.run(runtime_input(request, f"quality:{case_id}"))
    verification = dict(result.verification or {})
    if result.status_code != "M27_RUNTIME_COMPOSED" or not result.answer:
        raise RuntimeError(f"payload capture failed closed for {case_id}: {result.status_code}")
    answer_payload = dict(result.answer)
    answer_payload["selected_evidence"] = [evidence]
    answer_payload["citations"] = list(
        verification.get("citations") or answer_payload.get("citations") or []
    )
    answer_payload["terminal_status"] = "answered"
    answer_payload["safe_abstention"] = False
    answer_payload["integrity"] = {
        "material_claim_support_verified": bool(
            verification.get("material_claim_support_verified")
        ),
        "citation_locator_valid": bool(verification.get("citation_locator_valid")),
        "unsupported_accepted_claims": int(verification.get("unsupported_accepted_claims", 0) or 0),
    }
    payload = {
        "case_id": case_id,
        "source_case_id": case_id,
        "category": str(row["category"]),
        "question": str(row["question"]),
        "answer_payload": answer_payload,
        "forensic_trace": {
            "runtime_status": result.status_code,
            "terminal_reason": result.terminal_reason,
            "production_touched": result.production_touched,
            "runtime_telemetry": result.runtime_telemetry,
        },
    }
    payload["input_digest"] = canonical_digest(
        {
            "question": payload["question"],
            "answer_payload": answer_payload,
            "forensic_trace": payload["forensic_trace"],
        }
    )
    return payload


def main() -> int:
    key = os.environ.get("MINIMAX_API_KEY", "").strip()
    if not key:
        raise SystemExit("INDEPENDENT_EVALUATOR_CREDENTIAL_UNAVAILABLE")
    sample, eligible_count = load_sample()
    if WORK.exists():
        shutil.rmtree(WORK)
    captures = [capture(row) for row in sample]
    client = MiniMaxClient(key, max_calls=64, max_cost=Decimal("20"))

    def independent_evaluate(item: dict[str, Any]) -> AnswerQualityEvaluation:
        rubric = {k: v for k, v in ANSWER_QUALITY_CRITERION_MAX.items()}
        system = (
            "You are an independent semantic answer-quality judge. Use only the supplied "
            "question, answer, citations, and selected evidence. "
            "Score exactly these seven criteria as integers within their maxima: "
            + json.dumps(rubric, sort_keys=True)
            + ". "
            "Return exactly one JSON object and no markdown. Required keys: criterion_scores, "
            "hard_fail_codes, question_intent. "
            "criterion_scores must contain all seven keys exactly. hard_fail_codes must be an "
            "array. question_intent must contain task, subjects, qualifiers. "
            "Evidence-only grounding is mandatory; do not use outside knowledge."
        )
        package = {"question": item["question"], "answer": item["answer_payload"]}
        last = None
        for attempt in range(2):
            out = client.call(
                {
                    "model": MODEL,
                    "max_tokens": 700,
                    "temperature": 0,
                    "stream": False,
                    "system": system
                    + (
                        " Previous output violated the JSON contract; comply exactly."
                        if attempt
                        else ""
                    ),
                    "messages": [
                        {
                            "role": "user",
                            "content": json.dumps(
                                package, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                            ),
                        }
                    ],
                },
                "answer_quality_evaluation",
            )
            text = str(out.get("text", "")).strip()
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            try:
                data = json.loads(text)
            except Exception as exc:
                last = exc
                continue
            criteria = data.get("criterion_scores") if isinstance(data, dict) else None
            if not isinstance(criteria, dict) or set(criteria) != set(rubric):
                last = RuntimeError("criterion_scores contract mismatch")
                continue
            norm = {k: int(criteria[k]) for k in rubric}
            hard = tuple(sorted(str(x) for x in (data.get("hard_fail_codes") or [])))
            score = sum(norm.values())
            hard = answer_quality_boundary_codes(score, hard)
            result = "pass" if score >= ANSWER_QUALITY_PASS_THRESHOLD and not hard else "fail"
            failure_stage = failure_class = failure_signature = None
            if result == "fail":
                failure_stage, failure_class, failure_signature = canonical_failure_provenance(
                    hard_fail_codes=hard, criterion_scores=norm, safe_abstention=False
                )
            evaluation = AnswerQualityEvaluation(
                score=score,
                result=result,
                criterion_scores=norm,
                hard_fail_codes=hard,
                failure_class=failure_class,
                failure_stage=failure_stage,
                failure_signature=failure_signature,
                evaluator_provider="minimax",
                evaluator_model=MODEL,
                evaluator_version=SEMANTIC_EVALUATOR_VERSION,
            )
            return validate_answer_quality_evaluation(evaluation)
        raise RuntimeError(
            f"independent evaluator JSON contract failed after retry: {type(last).__name__}"
        )

    scored: list[dict[str, Any]] = []
    for item in captures:
        evaluation = independent_evaluate(item)
        score_payload = evaluation.to_payload()
        scored.append(
            {
                "case_id": item["case_id"],
                "category": item["category"],
                "question_digest": canonical_digest(item["question"]),
                "input_digest": item["input_digest"],
                "score": evaluation.score,
                "result": evaluation.result,
                "criterion_scores": dict(evaluation.criterion_scores),
                "hard_fail_codes": list(evaluation.hard_fail_codes),
                "score_output_digest": canonical_digest(score_payload),
            }
        )
    aggregate = sum(x["score"] for x in scored) / len(scored)
    input_records_digest = canonical_digest(
        [{"case_id": x["case_id"], "input_digest": x["input_digest"]} for x in captures]
    )
    score_digest = per_case_scores_digest(scored)
    artifact = {
        "schema_version": M27_INDEPENDENT_QUALITY_SCHEMA,
        "artifact_id": "m27-quality-payload-score-20261007",
        "source_admission_head": RELEASE_HEAD,
        "release_candidate_head": RELEASE_HEAD,
        "hard_gate_head": HARD_GATE_HEAD,
        "quality_gate_head": QUALITY_GATE_HEAD,
        "source_receipts_sha256": sha256_file(ADMISSION),
        "evaluator_provider": "minimax",
        "evaluator_model": MODEL,
        "evaluator_identity": "repo-qualified-minimax-answer-quality-evaluator",
        "evaluator_version": SEMANTIC_EVALUATOR_VERSION,
        "rubric_version": ANSWER_QUALITY_RUBRIC_VERSION,
        "scoring_policy_version": M27_SCORING_POLICY_VERSION,
        "sampling_policy": POLICY,
        "eligible_verified_answer_row_count": eligible_count,
        "scored_case_count": len(scored),
        "case_count_scored": len(scored),
        "skipped_rows": eligible_count - len(scored),
        "skipped_reason": (
            "duplicate semantic prompt instances across deterministic full523 repetitions; "
            "all 9 unique verified prompts scored"
        ),
        "payload_capture_label": (
            "isolated quality-scoring payload capture; not admission authority"
        ),
        "payload_records": captures,
        "source_input_digest": input_records_digest,
        "per_case_scores": scored,
        "per_case_scores_digest": score_digest,
        "score_output_digest": score_digest,
        "quality_score": round(aggregate, 3),
        "aggregate_quality_score": round(aggregate, 3),
        "threshold": ANSWER_QUALITY_PASS_THRESHOLD,
        "passed": aggregate >= ANSWER_QUALITY_PASS_THRESHOLD,
        "reason_codes": [],
        "safe_terminals_policy": (
            "excluded from semantic quality score; correctness remains separate admission evidence"
        ),
        "deterministic_admission_is_not_quality_score": True,
        "production_touched": False,
        "production_no_mutation_proof": {
            "capture_runtime": (
                "isolated in-process M27 harness using production-equivalent "
                "read-only fixture evidence"
            ),
            "production_endpoint_called_for_answers": False,
            "production_datastore_writes": False,
            "release_pointer_mutation": False,
        },
    }
    if not artifact["passed"]:
        artifact["reason_codes"].append("QUALITY_SCORE_BELOW_THRESHOLD")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                k: artifact[k]
                for k in [
                    "quality_score",
                    "threshold",
                    "passed",
                    "case_count_scored",
                    "eligible_verified_answer_row_count",
                    "per_case_scores_digest",
                ]
            },
            indent=2,
        )
    )
    return 0 if artifact["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
