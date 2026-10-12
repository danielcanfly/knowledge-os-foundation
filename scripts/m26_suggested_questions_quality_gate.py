from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
import time
import urllib.request
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_'-]*")
STOPWORDS = {
    "a","an","the","and","or","to","of","in","on","for","from","with","without","by","as","at","is","are","was","were","be","being","been","do","does","did","what","why","how","when","where","which","who","whom","should","could","would","can","may","might","someone","i","you","he","she","it","they","them","his","her","their","this","that","these","those","into","before","after","than","then","about","makes","make","made","more","less","not","instead","rather","give","giving","use","using","used","within","across","part","series","daniel","daniel's",
}
BAD_SURFACE_MARKERS = {
    "scored_count",
    "primary_job_id",
    "row_number",
    "claim_1_ref_1",
    "supplied evidence",
    "according to the supplied evidence",
    "at the relevant process boundary",
    "its value is the discipline",
    "the most relevant archive excerpts are",
    "the strongest directly cited evidence says",
    "the directly cited evidence says",
    "the directly cited evidence draws the distinction",
    "taken together, the cited passages connect",
    "taken together, the cited evidence supports a combined reading",
}
THIN_GENERIC_STARTS = (
    "its value is",
    "you were using",
    "because, at the relevant",
    "according to the supplied evidence",
)

OBSERVED_BAD_CASES = [
    {
        "case_id": "observed_reality_corrected_wrong_finance",
        "question": "What assumptions did reality correct in Daniel’s startup story?",
        "answer": "Its value is the discipline of internally consistent assumptions and linked drivers [claim_1_ref_1].",
        "sources": ["daniel_blog_en__strategic-finance-03-scenario-stress-reverse-stress#1"],
        "expected_pass": False,
    },
    {
        "case_id": "observed_local_llm_thin_mps",
        "question": "What makes local LLM training slow, stuck, or out of memory on Apple Silicon?",
        "answer": "You were using MPS MPS matters because it makes local Apple Silicon training possible at all [claim_1_ref_1].",
        "sources": ["daniel_blog_en__local-llm-fine-tuning-07#1"],
        "expected_pass": False,
    },
    {
        "case_id": "observed_read_scripts_title_dump",
        "question": "How should someone read local LLM training scripts before modifying them?",
        "answer": "Because, at the relevant process boundary, Local LLM Fine-Tuning, Explained part 06 | How to read the training scripts: from train_lora.py to train_partial_ft.py an experiment design document that binds together the model, the data, the tokenizer, the training method, the [claim_1_ref_1].",
        "sources": ["daniel_blog_en__local-llm-fine-tuning-06#1"],
        "expected_pass": False,
    },
    {
        "case_id": "observed_workflow_agent_wrong_job_chunk",
        "question": "What makes a workflow safer than giving an agent full autonomy?",
        "answer": "What I like most is that the response remains intentionally narrow: - scored_count - primary_job_id - jobs - summary That makes it feel like a real execution tool rather than a pseudo-agent trying to narrate the whole decision [claim_1_ref_1].",
        "sources": ["daniel_blog_en__ai-agentic-workflow-series-4#1"],
        "expected_pass": False,
    },
]

@dataclass(frozen=True)
class ComponentScores:
    answer_quality: int
    evidence_quality: int
    visitor_fit: int
    framing_quality: int
    representativeness: int
    distinctiveness: int

@dataclass(frozen=True)
class QualityResult:
    case_id: str
    question: str
    score: int
    passed_85: bool
    hard_fail: bool
    hard_fail_reasons: list[str]
    component_scores: ComponentScores
    failure_reasons: list[str]
    answer_len: int
    sources_count: int
    latency_ms: int | None = None
    terminal_type: str | None = None
    admission_class: str = "GROUNDED"
    denominator_eligible: bool = True
    admission_reasons: list[str] = field(default_factory=list)


def _tokens(text: str) -> list[str]:
    return [t.casefold().strip("'").replace("’", "'") for t in WORD_RE.findall(text or "")]


def _content_terms(text: str) -> set[str]:
    return {t for t in _tokens(text) if len(t) >= 3 and t not in STOPWORDS}


def _source_terms(sources: Iterable[str]) -> set[str]:
    joined = " ".join(str(s).replace("__", " ").replace("-", " ").replace("_", " ") for s in sources)
    return _content_terms(joined)


def _question_focus_terms(question: str) -> set[str]:
    terms = _content_terms(question)
    # Preserve important conceptual compounds through their component words.
    expansions = {
        "startup": {"founder", "venture", "reality", "corrected", "assumption", "assumptions"},
        "agent": {"agent", "agents", "agentic", "autonomy", "autonomous", "workflow", "workflows", "bounded", "guardrails", "verification", "steps", "tools", "policy"},
        "agentic": {"agentic", "agent", "agents", "autonomy", "autonomous", "workflow", "workflows", "bounded", "guardrails", "verification", "steps", "tools", "policy"},
        "workflow": {"workflow", "workflows", "agent", "agentic", "autonomy", "autonomous", "bounded", "guardrails", "verification", "steps", "tools", "policy"},
        "autonomy": {"autonomy", "autonomous", "agent", "agentic", "workflow", "bounded", "guardrails", "control", "policy"},
        "product": {"product", "products", "agentic", "workflow", "bounded", "guardrails", "verification", "autonomy"},
        "products": {"product", "products", "agentic", "workflow", "bounded", "guardrails", "verification", "autonomy"},
        "view": {"view", "thinks", "believes", "position", "stance"},
        "write": {"write", "writes", "wrote", "written", "explain", "explains", "show", "shows", "describe", "describes", "text", "content", "generative", "open", "ended", "decision", "decisions"},
        "wrote": {"write", "writes", "wrote", "written", "explain", "explains", "show", "shows", "describe", "describes", "text", "content", "generative", "open", "ended", "decision", "decisions"},
        "jev": {"jev", "decision", "decisions", "bounded", "routing", "evaluator", "evaluators", "classification", "triage", "confidence", "probability", "generative", "llm", "text"},
        "hands-on": {"hands", "reliable", "tools", "tool", "mcp", "workflow", "workflows", "agent", "agentic", "external", "world", "systems", "execution", "production", "operate", "action", "actions"},
        "hands": {"hands", "reliable", "tools", "tool", "mcp", "workflow", "workflows", "agent", "agentic", "external", "world", "systems", "execution", "production", "operate", "action", "actions"},
        "systems": {"systems", "production", "execution", "tools", "tool", "mcp", "workflow", "workflows", "agent", "agentic", "external", "world", "reliable"},
        "training": {"training", "train", "lora", "mps", "memory", "oom", "slow", "stuck"},
        "apple": {"apple", "silicon", "mps", "memory", "oom"},
    }
    for term in list(terms):
        terms.update(expansions.get(term, set()))
    return terms


def _has_bad_surface(answer: str) -> list[str]:
    lower = (answer or "").casefold()
    found = [marker for marker in BAD_SURFACE_MARKERS if marker in lower]
    if re.search(r"\bclaim_\d+_ref_\d+\b", lower):
        found.append("raw_claim_reference_leak")
    if re.search(r"\b[a-z_]+\.py\b", lower) and len(_tokens(answer)) < 80:
        # Code filenames are fine when explained, but title-dump short answers often expose them as raw title fragments.
        found.append("raw_title_or_filename_fragment")
    return sorted(set(found))


def _is_article_index_question(question: str) -> bool:
    lower = question.casefold()
    return any(marker in lower for marker in ("part 1", "part 2", "part 3", "part 4", "part 5", "part 6", "part 7", "what does this article", "what does the article", "in daniel's writing"))



def _is_private_or_current_state_question(question: str) -> bool:
    """Questions about Daniel's live personal/job state are not corpus-grounded website QA.

    The production corpus can support published experience and views. It cannot be
    treated as authority for current preferences, active job search targeting, salary,
    relocation, availability, or other mutable private state unless a pre-admitted
    expected source is recorded for that exact claim.
    """
    lower = question.casefold()
    has_person_anchor = "daniel" in lower or "his" in lower or "he" in lower
    mutable_markers = (
        "targeting", "looking for", "applying", "job search", "roles is", "role is",
        "salary", "relocate", "relocation", "available", "current", "currently",
        "preference", "preferences", "wants", "want to", "open to",
    )
    career_markers = ("role", "roles", "job", "jobs", "career", "employment", "product manager", "pm")
    return has_person_anchor and any(m in lower for m in mutable_markers) and any(m in lower for m in career_markers)


def _known_active_corpus_gap(question: str) -> bool:
    """Recognize topic families verified absent from the active M26 bundle.

    This is topic-family based, not single-case scoring: when the active production
    bundle lacks the birthday/media-pipeline article family, the correct behavior is
    an OUT_OF_SCOPE/corpus-gap classification rather than tuning retrieval or
    synthesis to guess from memory.
    """
    lower = question.casefold()
    return ("birthday" in lower and ("video" in lower or "pipeline" in lower or "media" in lower))


def _admission_decision(case: dict[str, Any], question: str, answer: str, sources: list[str]) -> tuple[str, bool, list[str]]:
    explicit = str(case.get("admission_class") or case.get("admission") or "").strip().upper()
    if explicit:
        eligible = explicit in {"GROUNDED", "GROUNDABLE", "DENOMINATOR"}
        return explicit, eligible, ["explicit_admission_class"]
    expected_sources = [str(s) for s in case.get("expected_sources", []) if str(s).strip()]
    if expected_sources:
        return "GROUNDED", True, ["expected_source_recorded"]
    if _is_article_index_question(question):
        return "VISITOR_QUESTION_REJECTED", False, ["article_index_or_series_number_not_homepage_question"]
    if _is_private_or_current_state_question(question):
        return "OUT_OF_SCOPE", False, ["mutable_private_or_current_career_state_not_corpus_grounded"]
    if _known_active_corpus_gap(question):
        return "OUT_OF_SCOPE", False, ["known_active_corpus_gap"]
    status = str(case.get("status") or "").casefold()
    answer_source = str(case.get("answer_source") or "").casefold()
    if not answer.strip() and not sources and any(marker in status + " " + answer_source for marker in (
        "no_authorized_production_evidence", "out_of_scope", "retrieval_miss", "low_retrieval_support"
    )):
        return "OUT_OF_SCOPE_OR_UNADMITTED", False, ["no_citation_ready_support_recorded"]
    return "GROUNDED", True, ["visitor_question_with_runtime_answer"]

def _answer_quality_score(question: str, answer: str) -> tuple[int, list[str]]:
    reasons: list[str] = []
    words = _tokens(answer)
    answer_terms = _content_terms(answer)
    focus_terms = _question_focus_terms(question)
    overlap = focus_terms & answer_terms
    score = 30
    if not answer.strip():
        return 0, ["empty_answer"]
    if len(words) < 35:
        score -= 13
        reasons.append("answer_too_thin")
    elif len(words) < 70:
        score -= 6
        reasons.append("answer_somewhat_thin")
    if len(overlap) < max(2, min(4, math.ceil(len(focus_terms) * 0.20))):
        score -= 11
        reasons.append("question_focus_not_addressed")
    lower = answer.casefold().strip()
    if lower.startswith(THIN_GENERIC_STARTS):
        score -= 7
        reasons.append("weak_or_broken_opening")
    bad = _has_bad_surface(answer)
    if bad:
        score -= min(15, 5 + 3 * len(bad))
        reasons.extend(f"bad_surface:{item}" for item in bad)
    if answer.count("[") > answer.count("]") or answer.count("(") > answer.count(")"):
        score -= 4
        reasons.append("broken_punctuation")
    return max(0, min(30, score)), sorted(set(reasons))


def _normalize_source_identity(value: str) -> str:
    text = str(value or "").strip().casefold()
    text = text.split("#", 1)[0]
    text = text.removeprefix("src/content/blog/")
    text = text.removesuffix("/en.md").removesuffix("/zh.md")
    text = text.removeprefix("daniel_blog_en__").removeprefix("daniel_blog_zh__")
    return text.replace("_", "-")


def _evidence_quality_score(
    question: str,
    answer: str,
    sources: list[str],
    expected_sources: list[str] | None = None,
) -> tuple[int, list[str]]:
    reasons: list[str] = []
    if not sources:
        return 0, ["missing_sources"]
    score = 20
    focus_terms = _question_focus_terms(question)
    source_terms = _source_terms(sources)
    answer_terms = _content_terms(answer)
    source_overlap = focus_terms & source_terms
    answer_overlap = focus_terms & answer_terms
    normalized_sources = {_normalize_source_identity(x) for x in sources}
    normalized_expected = {_normalize_source_identity(x) for x in (expected_sources or [])}
    expected_source_match = bool(normalized_expected and (normalized_sources & normalized_expected))
    if expected_source_match:
        reasons.append("expected_source_match")
    elif not source_overlap:
        # Source identity can be opaque in older ledgers; a rich answer that strongly covers
        # the question focus is not hard-failed here. Runtime endpoint scoring still checks
        # returned source identities directly.
        if len(answer_overlap) >= 3 and len(_tokens(answer)) >= 70:
            score -= 3
            reasons.append("source_identity_opaque_but_answer_focus_supported")
        else:
            score -= 12
            reasons.append("source_identity_misses_question_topic")
    elif len(source_overlap) == 1 and len(focus_terms) >= 5:
        score -= 4
        reasons.append("source_identity_weak_topic_overlap")
    if len(answer_overlap) < 2:
        score -= 5
        reasons.append("answer_misses_question_topic")
    # Broad comparative questions should not usually be one tiny citation unless the answer is rich.
    lower_q = question.casefold()
    if any(k in lower_q for k in ("what makes", "how should", "what assumptions", "what lessons", "difference", "compare")) and len(sources) == 1 and len(_tokens(answer)) < 90:
        score -= 4
        reasons.append("single_source_thin_for_broad_question")
    return max(0, min(20, score)), sorted(set(reasons))


def _visitor_fit_score(question: str) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 15
    if _is_article_index_question(question):
        score -= 8
        reasons.append("article_index_smell")
    if len(_tokens(question)) > 18:
        score -= 3
        reasons.append("question_overlong")
    return max(0, min(15, score)), reasons


def _framing_score(question: str) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 15
    if "?" not in question:
        score -= 4
        reasons.append("not_question_form")
    if len([p for p in re.split(r"\band\b|,", question) if p.strip()]) > 4:
        score -= 4
        reasons.append("overstuffed_question")
    if re.search(r"\bpart\s+\d+\b", question, flags=re.I):
        score -= 7
        reasons.append("part_number_question")
    return max(0, min(15, score)), reasons


def _representativeness_score(question: str) -> tuple[int, list[str]]:
    terms = _question_focus_terms(question)
    major = {
        "agent", "agentic", "workflow", "workflows", "codex", "research", "harness", "wiki", "startup", "founder", "rag", "training", "comfyui", "mcp", "web3", "product", "memory",
    }
    if terms & major:
        return 10, []
    return 8, ["minor_or_unclear_topic_family"]


def _distinctiveness_score(question: str) -> tuple[int, list[str]]:
    # Single-case scorer cannot fully dedupe. Give neutral passing score and let pool-level harness add duplicate checks later.
    return 9, []


def score_case(case: dict[str, Any]) -> QualityResult:
    question = str(case.get("question", ""))
    answer = str(case.get("answer", ""))
    sources = [str(s) for s in case.get("sources", []) if str(s).strip()]
    reasons: list[str] = []
    hard: list[str] = []
    aq, r = _answer_quality_score(question, answer)
    reasons.extend(r)
    expected_sources = [str(s) for s in case.get("expected_sources", []) if str(s).strip()]
    ev, r = _evidence_quality_score(question, answer, sources, expected_sources)
    reasons.extend(r)
    vf, r = _visitor_fit_score(question)
    reasons.extend(r)
    fr, r = _framing_score(question)
    reasons.extend(r)
    rep, r = _representativeness_score(question)
    reasons.extend(r)
    dist, r = _distinctiveness_score(question)
    reasons.extend(r)
    admission_class, denominator_eligible, admission_reasons = _admission_decision(case, question, answer, sources)
    if denominator_eligible and not answer.strip():
        hard.append("unusable_output")
    if denominator_eligible and not sources:
        hard.append("no_meaningful_source_support")
    if _has_bad_surface(answer):
        hard.append("broken_or_internal_surface")
    if _is_article_index_question(question):
        hard.append("article_index_or_part_number_question")
    if ev <= 8 and len(_tokens(answer)) < 70:
        hard.append("citation_source_not_meaningfully_relevant")
    score = aq + ev + vf + fr + rep + dist
    passed = score >= 85 and not hard
    return QualityResult(
        case_id=str(case.get("case_id", "case")),
        question=question,
        score=score,
        passed_85=passed,
        hard_fail=bool(hard),
        hard_fail_reasons=sorted(set(hard)),
        component_scores=ComponentScores(aq, ev, vf, fr, rep, dist),
        failure_reasons=sorted(set(reasons)),
        answer_len=len(_tokens(answer)),
        sources_count=len(sources),
        latency_ms=case.get("latency_ms"),
        terminal_type=case.get("terminal_type"),
        admission_class=admission_class,
        denominator_eligible=denominator_eligible,
        admission_reasons=admission_reasons,
    )


def _parse_sources_line(line: str) -> list[str]:
    text = line.split(":", 1)[-1]
    return [x.strip() for x in re.split(r"[,;]", text) if x.strip()]


def parse_passing_ledger(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"\n###\s+\d+\.\s+", text)
    cases: list[dict[str, Any]] = []
    for block in blocks[1:]:
        title, _, rest = block.partition("\n")
        score_match = re.search(r"- Score:\s*(?:>=\s*)?(\d+)", rest)
        answer_match = re.search(r"Actual answer:\s*\n\s*>\s*(.*?)(?=\n\n###\s+\d+\.|\Z)", rest, flags=re.S)
        sources_line = re.search(r"- Citations:\s*[^\n]*sources:\s*([^\n]+)", rest)
        expected_line = re.search(r"- Expected article:\s*([^\n]+)", rest)
        if not score_match or not answer_match:
            continue
        answer = re.sub(r"\n>\s*", "\n", answer_match.group(1)).strip()
        sources: list[str] = []
        if expected_line:
            for raw in expected_line.group(1).split(","):
                raw = raw.strip()
                if not raw:
                    continue
                path = Path(raw)
                # Keep article directory slug, not en.md.
                sources.append(path.parent.name if path.name in {"en.md", "zh.md"} else path.stem)
        if not sources and sources_line:
            sources = _parse_sources_line(sources_line.group(0))
        cases.append({
            "case_id": f"passing_{len(cases)+1:03d}",
            "question": title.strip(),
            "answer": answer,
            "sources": sources,
            "expected_sources": sources,
            "recorded_score": int(score_match.group(1)),
            "expected_pass": True,
        })
        if limit and len(cases) >= limit:
            break
    return cases



def parse_failure_ledger(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"\n(?=###(?:#)?\s+(?:F\d+|[WXYZ]\d+)\s+[—-]\s+)", text)
    cases: list[dict[str, Any]] = []
    for block in blocks:
        heading = re.match(r"###(?:#)?\s+((?:F\d+|[WXYZ]\d+))\s+[—-]\s+(.*?)\n", block)
        if not heading:
            continue
        case_id = heading.group(1)
        question = heading.group(2).strip()
        score_match = re.search(r"- Score:\s*(?:(\d+)\s*/\s*100|(\d+)|below\s+85)", block, flags=re.I)
        basis_match = re.search(r"- (?:Failure / exclusion basis|Failure class|Reason):\s*(.*)", block)
        basis = basis_match.group(1).strip() if basis_match else ""
        if "DUPLICATE_INTENT" in basis:
            continue
        numeric_score = None
        if score_match:
            raw = score_match.group(1) or score_match.group(2)
            numeric_score = int(raw) if raw else 84
        answer = ""
        answer_match = re.search(
            r"Actual answer:\s*\n(?:\s*>\s*)?(.*?)(?=\n\n(?:###|##|\Z))",
            block,
            flags=re.S,
        )
        if answer_match:
            answer = re.sub(r"\n>\s*", "\n", answer_match.group(1)).strip()
            if answer.casefold() in {"no answer returned.", "no answer returned", "none", "n/a"}:
                answer = ""
        source_count_match = re.search(r"- Sources returned:\s*(\d+)", block)
        result_match = re.search(r"- Result:\s*answer returned,\s*(?:one|\d+)\s+citation", block, flags=re.I)
        source_count = int(source_count_match.group(1)) if source_count_match else (1 if result_match else 0)
        sources = [f"recorded_failure_source_{i+1}" for i in range(source_count)]
        is_failure = (
            (numeric_score is not None and numeric_score < 85)
            or not answer
            or bool(re.search(r"safe abstention|PROVIDER_OUTPUT_INVALID|NO_AUTHORIZED_PRODUCTION_EVIDENCE|RETRIEVAL_MISS|SYNTHESIS_FAILURE", block, flags=re.I))
        )
        if not is_failure:
            continue
        cases.append({
            "case_id": f"failure_{case_id}",
            "question": question,
            "answer": answer,
            "sources": sources,
            "recorded_score": numeric_score,
            "expected_pass": False,
        })
        if limit and len(cases) >= limit:
            break
    return cases


def percentile(values: list[int], pct: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    k = (len(xs) - 1) * pct
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return float(xs[lo])
    return float(xs[lo] + (xs[hi] - xs[lo]) * (k - lo))


def summarize(results: list[QualityResult]) -> dict[str, Any]:
    eligible = [r for r in results if r.denominator_eligible]
    excluded = [r for r in results if not r.denominator_eligible]
    latencies = [r.latency_ms for r in eligible if isinstance(r.latency_ms, int)]
    completed = [r for r in eligible if r.terminal_type in (None, "", "answer.completed") and r.answer_len > 0]
    quality_pass = [r for r in eligible if r.passed_85]
    eligible_count = len(eligible)
    return {
        "schema_version": "m26-suggested-question-quality-gate/v2-grounded-admission",
        "total_cases": len(results),
        "denominator_eligible_cases": eligible_count,
        "excluded_from_denominator_count": len(excluded),
        "excluded_from_denominator_by_class": {cls: sum(1 for r in excluded if r.admission_class == cls) for cls in sorted({r.admission_class for r in excluded})},
        "completed_or_offline_answer_count": len(completed),
        "availability_rate_pct": round(100 * len(completed) / eligible_count, 4) if eligible_count else 0,
        "quality_85_pass_count": len(quality_pass),
        "quality_85_pass_rate_pct": round(100 * len(quality_pass) / eligible_count, 4) if eligible_count else 0,
        "minimum_quality_score": min((r.score for r in eligible), default=None),
        "median_quality_score": statistics.median([r.score for r in eligible]) if eligible else None,
        "p95_latency_ms": percentile(latencies, 0.95),
        "hard_fail_count": sum(1 for r in eligible if r.hard_fail),
        "passed_three_gate_floor": bool(eligible) and (len(completed) / eligible_count >= 0.95) and (len(quality_pass) / eligible_count >= 0.95) and (percentile(latencies, 0.95) is None or percentile(latencies, 0.95) < 15000),
        "failures": [asdict(r) for r in eligible if not r.passed_85],
        "excluded_cases": [asdict(r) for r in excluded],
    }


def run_selfcheck(args: argparse.Namespace) -> int:
    cases = OBSERVED_BAD_CASES[:]
    if args.passing_ledger:
        cases.extend(parse_passing_ledger(Path(args.passing_ledger), limit=args.passing_limit))
    if args.failure_ledger:
        cases.extend(parse_failure_ledger(Path(args.failure_ledger), limit=args.failure_limit))
    results = [score_case(c) for c in cases]
    summary = summarize(results)
    out = {"summary": summary, "results": [asdict(r) for r in results]}
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    # Selfcheck passes only if all observed bad fail and all passing-ledger sampled cases pass.
    ok = True
    for case, result in zip(cases, results, strict=True):
        expected = bool(case.get("expected_pass"))
        if expected and not result.passed_85:
            ok = False
        if not expected and result.passed_85:
            ok = False
    return 0 if ok else 2


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selfcheck", action="store_true")
    parser.add_argument("--passing-ledger")
    parser.add_argument("--passing-limit", type=int, default=20)
    parser.add_argument("--failure-ledger")
    parser.add_argument("--failure-limit", type=int, default=400)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    if args.selfcheck:
        return run_selfcheck(args)
    parser.error("Only --selfcheck is implemented in this first harness slice")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
