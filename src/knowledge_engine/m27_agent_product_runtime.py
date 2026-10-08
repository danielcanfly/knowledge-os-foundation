from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


M27_AGENT_PRODUCT_SCHEMA = "m27-agent-native-product-answer/v1"
M27_PRODUCT_SLO_MS = 14500
_M27_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_'-]*", flags=re.I)
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")

class M27ProductEvent(StrEnum):
    EVIDENCE_READY = "evidence_ready"
    ANSWER_PLAN_READY = "answer_plan_ready"
    CLAIM_GRAPH_READY = "claim_graph_ready"
    CLAIM_VERIFICATION_STARTED = "claim_verification_started"
    VERIFIED_CLAIM_READY = "verified_claim_ready"
    CITATION_BOUND = "citation_bound"
    CITED_SEGMENT_READY = "cited_segment_ready"
    STREAM_PUBLISHABLE = "stream_publishable"
    FINAL_ANSWER_DONE = "final_answer_done"
    SAFE_TERMINAL_DONE = "safe_terminal_done"
    VERIFIER_GAP_DETECTED = "verifier_gap_detected"
    VERIFIER_GAP_REPAIR_STARTED = "verifier_gap_repair_started"
    VERIFIER_GAP_REPAIR_DONE = "verifier_gap_repair_done"

class M27VerifierGap(StrEnum):
    INSUFFICIENT_SOURCE_BREADTH = "INSUFFICIENT_SOURCE_BREADTH"
    MISSING_CITATION_LOCATOR = "MISSING_CITATION_LOCATOR"
    UNSUPPORTED_CLAIM_SPAN = "UNSUPPORTED_CLAIM_SPAN"
    CITATION_BINDING_DRIFT = "CITATION_BINDING_DRIFT"
    MULTILINGUAL_SUPPORT_MISMATCH = "MULTILINGUAL_SUPPORT_MISMATCH"
    PROVIDER_MALFORMED_OUTPUT = "PROVIDER_MALFORMED_OUTPUT"
    TRUE_NO_EVIDENCE = "TRUE_NO_EVIDENCE"
    PROMPT_UNSAFE_OR_PRIVATE = "PROMPT_UNSAFE_OR_PRIVATE"
    UNDERSPECIFIED_USER_QUERY = "UNDERSPECIFIED_USER_QUERY"
    PRODUCT_THIN_SURFACE = "PRODUCT_THIN_SURFACE"
    SOURCE_COVERAGE_TOO_NARROW = "SOURCE_COVERAGE_TOO_NARROW"
    SLO_BUDGET_EXHAUSTED = "SLO_BUDGET_EXHAUSTED"

@dataclass(frozen=True, slots=True)
class M27SloComputePolicy:
    product_slo_ms: int = M27_PRODUCT_SLO_MS
    deadline_ms: int = M27_PRODUCT_SLO_MS
    provider_attempts_allowed: int = 0
    deterministic_repair_first: bool = True
    reason_codes: tuple[str, ...] = ("M27_PRODUCT_SLO_14500MS", "DETERMINISTIC_REPAIR_BEFORE_PROVIDER_RETRY")
    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True, slots=True)
class M27ClaimNode:
    claim_id: str
    claim_text: str
    supporting_evidence_ids: tuple[str, ...]
    citation_locators: tuple[str, ...]
    source_identities: tuple[str, ...]
    source_breadth: int
    support_status: str
    verifier_status: str
    product_quality_status: str
    citations: tuple[dict[str, Any], ...]
    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim_text": self.claim_text,
            "supporting_evidence_ids": list(self.supporting_evidence_ids),
            "citation_locators": list(self.citation_locators),
            "source_identities": list(self.source_identities),
            "source_breadth": self.source_breadth,
            "support_status": self.support_status,
            "verifier_status": self.verifier_status,
            "product_quality_status": self.product_quality_status,
            "citations": [dict(item) for item in self.citations],
        }

@dataclass(slots=True)
class M27ProductTimeline:
    request_start_ms: float = 0.0
    retrieval_start_ms: float | None = None
    retrieval_end_ms: float | None = None
    evidence_admission_start_ms: float | None = None
    evidence_admission_end_ms: float | None = None
    answer_planning_start_ms: float | None = None
    answer_planning_end_ms: float | None = None
    claim_graph_start_ms: float | None = None
    claim_graph_end_ms: float | None = None
    first_claim_verification_start_ms: float | None = None
    first_claim_verification_end_ms: float | None = None
    first_verified_claim_ready_ms: float | None = None
    first_citation_bound_ms: float | None = None
    first_cited_segment_ready_ms: float | None = None
    first_material_emitted_ms: float | None = None
    provider_call_count: int = 0
    provider_total_duration_ms: float = 0.0
    verifier_exclusive_duration_ms: float = 0.0
    final_emitted_ms: float | None = None
    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True, slots=True)
class M27ProductAnswerPlan:
    question_language: str
    canonical_question: str
    broad_homepage_question: bool
    required_source_breadth: int
    selected_evidence_ids: tuple[str, ...]
    distinct_sources: tuple[str, ...]
    source_breadth_status: str
    answer_depth_target: str
    reason_codes: tuple[str, ...]
    def as_dict(self) -> dict[str, Any]:
        return {
            "question_language": self.question_language,
            "canonical_question": self.canonical_question,
            "broad_homepage_question": self.broad_homepage_question,
            "required_source_breadth": self.required_source_breadth,
            "selected_evidence_ids": list(self.selected_evidence_ids),
            "distinct_sources": list(self.distinct_sources),
            "source_breadth_status": self.source_breadth_status,
            "answer_depth_target": self.answer_depth_target,
            "reason_codes": list(self.reason_codes),
        }

@dataclass(frozen=True, slots=True)
class M27ProductAnswerResult:
    publishable: bool
    answer: dict[str, Any]
    claim_graph: tuple[M27ClaimNode, ...]
    plan: M27ProductAnswerPlan
    gap_taxonomy: tuple[str, ...]
    repair_attempts: tuple[dict[str, Any], ...]
    micro_timeline: M27ProductTimeline
    state_events: tuple[dict[str, Any], ...]
    terminal_reason: str
    safe_terminal_justification: dict[str, Any] = field(default_factory=dict)
    def stream_events(self) -> tuple[dict[str, Any], ...]:
        return self.state_events
    def as_runtime_result(self, *, question_sha256: str) -> dict[str, Any]:
        verification = dict(self.answer) if self.publishable else {
            "status": "owner_only_safe_abstention",
            "safe_abstention": True,
            "citation_locator_valid": False,
            "material_claim_support_verified": False,
            "unsupported_accepted_claims": 0,
            "citations": [],
            "answer_claims": [],
            "reason_codes": list(self.gap_taxonomy),
            "safe_terminal_justification": dict(self.safe_terminal_justification),
        }
        verification.update({
            "schema_version": M27_AGENT_PRODUCT_SCHEMA,
            "claim_graph": [node.as_dict() for node in self.claim_graph],
            "answer_plan": self.plan.as_dict(),
            "gap_taxonomy": list(self.gap_taxonomy),
            "repair_attempts": [dict(item) for item in self.repair_attempts],
            "micro_timeline": self.micro_timeline.as_dict(),
            "slo_compute_policy": M27SloComputePolicy().as_dict(),
            "product_quality_status": "product_grade" if self.publishable else "safe_terminal",
        })
        return {
            "status_code": "M27_RUNTIME_COMPOSED" if self.publishable else "M27_RUNTIME_SAFE_TERMINAL",
            "answer": dict(self.answer) if self.publishable else {},
            "verification": verification,
            "terminal_reason": self.terminal_reason,
            "production_touched": False,
            "question_sha256": question_sha256,
        }

def _elapsed_ms(start_ns: int, now_ns: int | None = None) -> float:
    return round(((now_ns or time.perf_counter_ns()) - start_ns) / 1_000_000, 3)

def _language(question: str) -> str:
    if any("\u4e00" <= ch <= "\u9fff" for ch in question):
        return "zh"
    if any("\u3040" <= ch <= "\u30ff" for ch in question):
        return "ja"
    return "en"

def canonicalize_question_for_retrieval(question: str) -> str:
    q = re.sub(r"\s+", " ", str(question or "")).strip()
    lower = q.casefold()
    expansions: list[str] = []
    rules = (
        (("browser use", "browser-use", "ブラウザ", "瀏覽器", "浏览器"), "Browser Use browser automation web agent tool"),
        (("localbridge", "local bridge"), "LocalBridge MCP local bridge model context protocol desktop connector"),
        (("mcp", "model context protocol"), "MCP Model Context Protocol tool integration agent context"),
        (("m27", "context-native"), "M27 context-native runtime answer runtime claim verification citations safe terminal"),
        (("answer runtime", "answer system"), "answer runtime retrieval verification citations safe terminals first answer streaming"),
        (("kubernetes", "k8s", "インフラで kubernetes", "kubernetes は"), "Kubernetes AI infrastructure orchestration GPU workloads services scaling"),
        (("gpu", "裡", "里面", "グラフィック"), "GPU inference kernels memory tokens transformer llm answer"),
        (("rag",), "RAG retrieval augmented generation evidence grounding citations"),
        (("multi-tenant", "many companies", "多家公司", "多公司", "複数社", "many tenants"), "multi tenant AI platform isolation tenant security serving many companies"),
        (("private ai", "tee", "trusted execution", "機密", "プライベート"), "private AI trusted execution environment TEE confidential computing"),
        (("cost", "費用", "成本", "コスト"), "single AI request cost tokens latency GPU provider economics"),
        (("observability", "failing", "可靠", "失敗"), "AI systems failing reliability observability metrics tracing evaluation"),
        (("latency", "ttft", "streaming", "first-answer", "串流"), "latency TTFT first answer text streaming final latency"),
        (("model that can answer", "service", "服務", "service"), "model to service deployment runtime reliability API product"),
        (("after you hit send", "hit send", "send"), "AI app request lifecycle after send retrieval inference response"),
    )
    haystack = lower + " " + q
    for triggers, expansion in rules:
        if any(trigger.casefold() in haystack for trigger in triggers):
            expansions.append(expansion)
    if _language(q) in {"zh", "ja"} and not expansions:
        # Generic English fallback is only for queries without a domain-specific
        # canonical expansion. Otherwise it pollutes ranking with unrelated AI terms.
        expansions.append("English corpus canonical concepts")
    if not expansions:
        return q
    return (q + " " + " ".join(dict.fromkeys(expansions))).strip()

def _focus_terms(text: str) -> set[str]:
    canonical = canonicalize_question_for_retrieval(text)
    stop = {"the", "and", "for", "with", "that", "this", "what", "why", "how", "does", "did", "are", "was", "were", "after", "before", "into", "from", "about", "actually", "help", "one", "many", "can", "you", "your", "when", "where", "which", "between", "relationship", "explain", "blog"}
    terms = {token.casefold() for token in _M27_WORD_RE.findall(canonical) if len(token) >= 3 and token.casefold() not in stop}
    if "localbridge" in canonical.casefold():
        terms.update({"localbridge", "mcp", "desktop", "bridge"})
    if "browser use" in canonical.casefold():
        terms.update({"browser", "automation", "agent"})
    return terms

def _evidence_id(item: Mapping[str, Any], index: int) -> str:
    return str(item.get("evidence_id") or item.get("passage_id") or f"ev-{index:02d}")

def _source_identity(item: Mapping[str, Any]) -> str:
    return str(item.get("source_identity") or item.get("source_id") or item.get("artifact_key") or item.get("section_id") or "unknown")

def _locator_id(item: Mapping[str, Any]) -> str:
    return str(item.get("locator_id") or item.get("section_id") or item.get("passage_id") or "")

def _text(item: Mapping[str, Any]) -> str:
    return str(item.get("passage_text") or item.get("text") or "").strip()

def _topic_tokens(question: str) -> set[str]:
    # Preserve query specificity: expansion tokens are not proof of semantic support.
    base = str(question or "").casefold()
    stop = {"what","does","this","that","have","with","from","where","when","which",
            "into","about","after","before","there","their","your","could","would",
            "should","explain","actually","help","helps","many","single","what's",
            "infrastructure","system","systems","platform","service","services","agent",
            "agents","model","models","answer","runtime","product","work","working",
            "the","why","how","can","and","for","are","you","use","using"}
    terms = {t for t in _M27_WORD_RE.findall(base) if len(t)>=3 and t not in stop}
    # Cross-lingual technical names survive unchanged.
    return terms

def _topic_supported(question: str, item: Mapping[str, Any]) -> bool:
    raw_terms = _topic_tokens(question)
    focus_terms = _focus_terms(question)
    if not raw_terms and not focus_terms:
        return False
    blob = " ".join(str(item.get(k) or "") for k in (
        "title", "concept_id", "section_id", "passage_text", "text")).casefold()
    # Canonical focus terms are candidate-admission signals only. They never
    # count as semantic entailment; the calibrated provider remains mandatory.
    return any(term and term in blob for term in (raw_terms | focus_terms))

def _question_obligation_gap(question: str, text: str) -> str | None:
    """Fail closed when the cited surface does not answer explicit factual obligations.

    This is a query-class constraint rather than a case-ID or dataset-label rule.
    Entailment of a source excerpt alone is not proof it answers the question.
    """
    q = question.casefold()
    a = text.casefold()
    if "exact" in q and "production traffic volume" in q:
        if not re.search(r"\b(?:[0-9][0-9,.]*|zero)\s*(?:requests?|visits?|sessions?|queries|calls|users|events|rps|qps)\b", a):
            return "MISSING_EXACT_PRODUCTION_TRAFFIC_MEASURE"
        release_ids = re.findall(r"\b20\d{6}t\d{6}z-[a-f0-9]{8,}\b", q)
        if release_ids and not any(x in a for x in release_ids):
            return "MISSING_RELEASE_ANCHOR"
    if ("retrieved-at" in q and "source-commit" in q and "release" in q):
        keys = ("retrieved-at", "source-commit", "release")
        if not all(k in a for k in keys):
            return "MISSING_PROVENANCE_IDENTITY_DIMENSIONS"
    return None


def _score_evidence(question: str, item: Mapping[str, Any]) -> tuple[int, int, int, int]:
    raw_terms = _topic_tokens(question)
    focus_terms = _focus_terms(question)
    blob = " ".join(str(item.get(k) or "") for k in (
        "title", "concept_id", "section_id", "passage_text", "text")).casefold()
    raw_hits = sum(1 for term in raw_terms if term and term in blob)
    focus_hits = sum(1 for term in focus_terms if term and term in blob)
    locator_bonus = int(bool(_locator_id(item)))
    # User terms dominate; canonical expansion is only a recall/ranking aid.
    return raw_hits * 4 + focus_hits, raw_hits, focus_hits, locator_bonus

def _is_broad_homepage_question(question: str) -> bool:
    q = canonicalize_question_for_retrieval(question).casefold()
    narrow_patterns = ("stand for", "what does mcp stand", "what does browser use do")
    if any(pattern in q for pattern in narrow_patterns):
        return False
    broad_markers = ("what is", "how does", "how can", "why is", "relationship", "differ", "what happens", "runtime", "infrastructure", "platform", "service", "systems", "private ai", "kubernetes", "rag", "cost")
    return any(marker in q for marker in broad_markers) or bool(_CJK_RE.search(question))

def _select_evidence(question: str, evidence: Sequence[Mapping[str, Any]], *, broad: bool) -> tuple[Mapping[str, Any], ...]:
    usable = [item for item in evidence if _text(item) and _locator_id(item) and _topic_supported(question,item)]
    ranked = sorted(usable, key=lambda item: _score_evidence(question, item), reverse=True)
    target = 4 if broad else 2
    selected: list[Mapping[str, Any]] = []
    used_ids: set[tuple[str, str]] = set()
    for item in ranked:
        identity = (_source_identity(item), _locator_id(item))
        if identity in used_ids:
            continue
        selected.append(item)
        used_ids.add(identity)
        if len(selected) >= target:
            break
    return tuple(selected)

def _quote(question: str, item: Mapping[str, Any], *, max_chars: int = 360) -> str:
    text = re.sub(r"\s+", " ", _text(item)).strip()
    if not text:
        return ""
    terms = _focus_terms(question)
    chunks = [chunk.strip() for chunk in re.split(r"(?<=[.!?。！？])\s+|\n+", text) if chunk.strip()]
    if not chunks:
        chunks = [text]
    def score(chunk: str) -> tuple[int, int, int]:
        lower = chunk.casefold()
        hits = sum(1 for term in terms if term in lower)
        words = len(_M27_WORD_RE.findall(chunk))
        return hits, min(words, 80), -abs(45 - min(words, 80))
    chosen = max(chunks, key=score)
    if len(chosen) <= max_chars:
        return chosen
    lower = chosen.casefold()
    positions = [lower.find(term) for term in terms if lower.find(term) >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - max_chars // 3)
    end = min(len(chosen), start + max_chars)
    window = chosen[start:end].strip()
    if start > 0 and " " in window:
        window = window.split(" ", 1)[1].strip()
    if end < len(chosen) and " " in window:
        window = window.rsplit(" ", 1)[0].strip()
    return window if window else chosen[:max_chars].strip()

def _material_claim_excerpt(question: str, item: Mapping[str, Any], *, max_chars: int = 620) -> str:
    """Build a richer extractive claim surface from one evidence passage.

    Only source sentences related to the retrieval focus are included. The
    provider still has to semantically verify the complete resulting claim.
    """
    text = re.sub(r"\s+", " ", _text(item)).strip()
    if not text:
        return ""
    sentences = [x.strip() for x in re.split(r"(?<=[.!?。！？])\s+|\n+", text) if x.strip()]
    if not sentences:
        return text[:max_chars].strip()
    raw_terms = _focus_terms(question) | _topic_tokens(question)
    stems = {t[:-1] if t.endswith("s") and len(t) > 4 else t for t in raw_terms}
    ranked = []
    for idx, sentence in enumerate(sentences):
        lower = sentence.casefold()
        hits = sum(1 for term in stems if term and term in lower)
        if hits:
            words = len(_M27_WORD_RE.findall(sentence))
            ranked.append((hits, min(words, 90), -idx, idx, sentence))
    if not ranked:
        # Retrieval has already selected this passage as a candidate. If the
        # question terms do not overlap cleanly, still expose a bounded
        # extractive sentence window to the semantic provider instead of
        # silently skipping verification. Provider rejection remains fail-closed.
        selected = []
        total_words = 0
        total_chars = 0
        for sentence in sentences:
            extra = len(sentence) + (1 if selected else 0)
            if selected and total_chars + extra > max_chars:
                break
            selected.append(sentence)
            total_words += len(_M27_WORD_RE.findall(sentence))
            total_chars += extra
            if total_words >= 45 or len(selected) >= 3:
                break
        return " ".join(selected).strip()
    ranked.sort(reverse=True)
    selected = []
    total_words = 0
    total_chars = 0
    for _hits, _length, _negidx, idx, sentence in ranked:
        extra = len(sentence) + (1 if selected else 0)
        if selected and total_chars + extra > max_chars:
            continue
        selected.append((idx, sentence))
        total_words += len(_M27_WORD_RE.findall(sentence))
        total_chars += extra
        if total_words >= 42 or len(selected) >= 3:
            break
    return " ".join(sentence for _, sentence in sorted(selected)).strip()


def _human_topic(question: str) -> str:
    q = str(question or "").strip().rstrip("?。？")
    return q[:1].lower() + q[1:] if q else "this question"

def _claim_units(question, item):
    anchors = _topic_tokens(question)
    units = [u.strip() for u in re.split(r"(?<=[.!?。！？])\s+|\n+", _text(item)) if len(u.strip()) >= 35]
    if not units and len(_text(item)) >= 35: units = [_text(item)]
    out = []
    for unit in units:
        overlap = len(anchors & set(_M27_WORD_RE.findall(unit.casefold())))
        ratio = overlap / max(1, len(anchors))
        if overlap and ratio >= (0.34 if len(anchors)>=3 else 0.5):
            out.append((unit[:450], ratio))
    return sorted(out, key=lambda v: v[1], reverse=True)

def _semantic_support(question, claim, item):
    # Conservative extractive guarantee: no generated claim can outrun its quoted source.
    source = re.sub(r"\s+", " ", _text(item)).casefold()
    span = re.sub(r"\s+", " ", claim).casefold()
    return bool(span and span in source and _claim_units(question, item) and
                len(_topic_tokens(question) & set(_M27_WORD_RE.findall(span))) >= 1)

def _localized_answer(question, selected, quotes, *, broad):
    return "\n\n".join(quotes)

def _citation(item: Mapping[str, Any], claim_id: str, index: int, quote: str) -> dict[str, Any]:
    evidence_id = _evidence_id(item, index)
    locator_id = _locator_id(item)
    return {
        "citation_id": f"cite_{index}",
        "claim_id": claim_id,
        "evidence_id": evidence_id,
        "locator_id": locator_id,
        "source_identity": _source_identity(item),
        "source_id": str(item.get("source_id") or _source_identity(item)),
        "section_id": str(item.get("section_id") or locator_id),
        "concept_id": str(item.get("concept_id") or ""),
        "release_id": str(item.get("release_id") or ""),
        "provenance_record_sha256": str(item.get("provenance_record_sha256") or ""),
        "source_artifact_sha256": str(item.get("artifact_sha256") or ""),
        "support_text_sha256": str(item.get("passage_text_sha256") or ""),
        "source_locator": f"{item.get('artifact_key', '')}#{item.get('section_id', '')}",
        "runtime_owned_locator": True,
        "exact_quote_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
        "exact_support_snippet_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
        "support_status": "SUPPORTED",
    }

def _redacted_event(event: M27ProductEvent, start_ns: int, **payload: Any) -> dict[str, Any]:
    safe = {key: value for key, value in payload.items() if key not in {"raw_provider_key", "owner_bypass", "secret"}}
    return {"type": event.value, "event_ms": _elapsed_ms(start_ns), **safe}

def _semantic_runtime_provider():
    """Separate narrow NLI judge; no M26 answer composer delegation."""
    import os
    from decimal import Decimal
    from .m26_pa5_v8_live import MiniMaxClient
    from .m27_native_judge_provider import M27NativeJudgeAdapter
    key = os.environ.get("MINIMAX_API_KEY", "")
    if not key:
        return None
    client = MiniMaxClient(key, max_calls=12, max_cost=Decimal("2"))
    def invoke(claim, passages):
        import json
        system = ("You are a strict independent semantic NLI verifier, never an answer composer. "
                  "Verify EVERY factual aspect of the claim from ONLY the cited passages. "
                  "Do not mistake citation presence, literal overlap or shared topics for entailment. "
                  "Reject contradictory, unrelated, thinly cited and cross-domain claims. "
                  "Return ONLY JSON with exactly support_class, confidence, reason, evidence_references. "
                  "support_class is DIRECT_SUPPORT, PARAPHRASE_SUPPORT, CLUSTER_SUPPORT, "
                  "TOPICAL_ONLY, UNSUPPORTED, CONTRADICTED, or INSUFFICIENT_PROVIDER_CAPABILITY. "
                  "confidence is numeric 0..1, reason nonempty <=500 chars. "
                  "evidence_references must contain only genuinely supporting IDs, otherwise [].")
        user = json.dumps({"claim": claim.text, "language": claim.language,
                           "evidence": [{"id": x.passage_id, "text": x.text} for x in passages]}, ensure_ascii=False)
        payload = {"model": "MiniMax-M3", "max_tokens": 400, "temperature": 0,
                   "stream": False, "system": system,
                   "messages": [{"role": "user", "content": user}]}
        def call():
            value = client.call(payload, "aq_claim_semantic_entailment")["text"].strip()
            if value.startswith(chr(96)*3):
                value = value.split("\n", 1)[-1].rsplit(chr(96)*3, 1)[0].strip()
            return value
        return call()
    return M27NativeJudgeAdapter(invoke)

def build_agent_native_product_answer(*, question: str, intent_class: str, evidence: Sequence[Mapping[str, Any]], requirements: Sequence[object] = (), retrieval_latency_ms: float | None = None, semantic_provider=None) -> M27ProductAnswerResult:
    start_ns = time.perf_counter_ns()
    timeline = M27ProductTimeline(request_start_ms=0.0)
    events: list[dict[str, Any]] = []
    broad = _is_broad_homepage_question(question)
    required_breadth = 2 if broad else 1
    timeline.evidence_admission_start_ms = _elapsed_ms(start_ns)
    selected = _select_evidence(question, evidence, broad=broad)
    timeline.evidence_admission_end_ms = _elapsed_ms(start_ns)
    if retrieval_latency_ms is not None:
        timeline.retrieval_start_ms = 0.0
        timeline.retrieval_end_ms = round(float(retrieval_latency_ms), 3)
    sources = tuple(dict.fromkeys(_source_identity(item) for item in selected))
    evidence_ids = tuple(_evidence_id(item, idx) for idx, item in enumerate(selected, 1))
    events.append(_redacted_event(M27ProductEvent.EVIDENCE_READY, start_ns, selected_evidence_count=len(selected), distinct_source_count=len(sources)))
    canonical = canonicalize_question_for_retrieval(question)
    source_breadth_status = "sufficient" if len(sources) >= required_breadth else "narrow_but_repairable" if selected else "insufficient"
    plan = M27ProductAnswerPlan(_language(question), canonical, broad, required_breadth, evidence_ids, sources, source_breadth_status, "multi-source_product_explanation" if broad else "direct_grounded_answer", ("M27_NATIVE_PRODUCT_PLANNER", "ARTICLE_INDEX_SMELL_AVOIDED", "SOURCE_BREADTH_GATE"))
    timeline.answer_planning_start_ms = _elapsed_ms(start_ns)
    events.append(_redacted_event(M27ProductEvent.ANSWER_PLAN_READY, start_ns, answer_plan=plan.as_dict()))
    gaps: list[str] = []
    repair_attempts: list[dict[str, Any]] = []
    if not selected:
        gaps.append(M27VerifierGap.TRUE_NO_EVIDENCE.value)
    if len(sources) < required_breadth and selected:
        # Breadth is a product-quality diagnostic, not semantic proof. A single
        # strong source may still answer a factual query if every material claim
        # passes the calibrated entailment gate and the answer is not thin.
        events.append(_redacted_event(
            M27ProductEvent.VERIFIER_GAP_DETECTED, start_ns,
            gap=M27VerifierGap.INSUFFICIENT_SOURCE_BREADTH.value,
        ))
        repair_attempts.append({
            "gap": M27VerifierGap.INSUFFICIENT_SOURCE_BREADTH.value,
            "strategy": "semantic_verification_over_available_bound_evidence",
            "provider_retry_used": False,
        })
    timeline.answer_planning_end_ms = _elapsed_ms(start_ns)
    if not selected:
        terminal = M27VerifierGap.TRUE_NO_EVIDENCE.value
        timeline.final_emitted_ms = _elapsed_ms(start_ns)
        events.append(_redacted_event(M27ProductEvent.SAFE_TERMINAL_DONE, start_ns, terminal_reason=terminal, gap_taxonomy=gaps))
        return M27ProductAnswerResult(False, {}, (), plan, tuple(dict.fromkeys(gaps)), tuple(repair_attempts), timeline, tuple(events), terminal, {"structured": True, "gap_taxonomy": list(dict.fromkeys(gaps)), "source_breadth_status": source_breadth_status})
    timeline.claim_graph_start_ms = _elapsed_ms(start_ns)
    claims, citations, quotes = [], [], []
    verification_receipts = []
    from .m27_semantic_entailment import EvidencePassage, MaterialClaim
    from .m27_semantic_publication_gate import verify_publication_claim
    try:
        provider = semantic_provider if semantic_provider is not None else _semantic_runtime_provider()
    except Exception:
        provider = None
    rejected_verification_receipts = []
    min_verified_claims = 2
    max_verified_claims = 3
    min_publish_words = 55 if broad else 45
    for idx, item in enumerate(selected, 1):
        current_words = len(_M27_WORD_RE.findall(" ".join(quotes)))
        if len(claims) >= min_verified_claims and current_words >= min_publish_words:
            break
        if len(claims) >= max_verified_claims:
            break
        units = _claim_units(question, item)
        score = units[0][1] if units else 0.0
        quote = _material_claim_excerpt(question, item)
        if not quote:
            continue
        claim_id = f"claim_{idx}"
        pid = _evidence_id(item, idx)
        bound = EvidencePassage(_source_identity(item), _locator_id(item), pid, _text(item), _language(question))
        claim = MaterialClaim(claim_id, quote, 0, len(quote), _language(question), (pid,))
        accepted, audit = verify_publication_claim(claim, (bound,), provider)
        if not accepted:
            rejected_verification_receipts.append(audit)
            continue
        verification_receipts.append(audit)
        citation = _citation(item, claim_id, idx, quote)
        citation["semantic_entailment_confidence"] = audit["confidence"]
        citation["topic_overlap_ratio"] = round(score, 3)
        citation["support_unit_excerpt"] = quote
        citations.append(citation)
        quotes.append(quote)
        claims.append(M27ClaimNode(claim_id, quote, (_evidence_id(item,idx),),
            (_locator_id(item),), (_source_identity(item),), 1,
            "SUPPORTED", "SEMANTIC_VERIFIED", "evidence_bound", (citation,)))
    if not claims: gaps.append(M27VerifierGap.UNSUPPORTED_CLAIM_SPAN.value)
    if len(_M27_WORD_RE.findall(" ".join(quotes))) < 45:
        gaps.append(M27VerifierGap.PRODUCT_THIN_SURFACE.value)
    answer_text = _localized_answer(question, selected, quotes, broad=broad)
    obligation_gap = _question_obligation_gap(question, answer_text)
    if obligation_gap:
        gaps.append(M27VerifierGap.UNSUPPORTED_CLAIM_SPAN.value)
        repair_attempts.append({"gap": obligation_gap, "strategy": "fail_closed_question_obligation_guard"})
    if broad and len(_M27_WORD_RE.findall(answer_text)) < 55:
        gaps.append(M27VerifierGap.PRODUCT_THIN_SURFACE.value)
    timeline.claim_graph_end_ms = _elapsed_ms(start_ns)
    events.append(_redacted_event(M27ProductEvent.CLAIM_GRAPH_READY, start_ns, claim_count=len(claims)))
    timeline.first_claim_verification_start_ms = _elapsed_ms(start_ns)
    for c in claims:
        events.append(_redacted_event(M27ProductEvent.CLAIM_VERIFICATION_STARTED, start_ns, claim_id=c.claim_id))
    timeline.first_claim_verification_end_ms = _elapsed_ms(start_ns)
    if gaps:
        timeline.final_emitted_ms = _elapsed_ms(start_ns)
        unique_gaps = tuple(dict.fromkeys(gaps))
        events.append(_redacted_event(M27ProductEvent.VERIFIER_GAP_DETECTED, start_ns, gap_taxonomy=list(unique_gaps)))
        events.append(_redacted_event(M27ProductEvent.SAFE_TERMINAL_DONE, start_ns, terminal_reason=unique_gaps[0], gap_taxonomy=list(unique_gaps)))
        return M27ProductAnswerResult(
            False, {}, tuple(claims), plan, unique_gaps, tuple(repair_attempts),
            timeline, tuple(events), unique_gaps[0],
            {"structured": True,
             "thin_cited_answer": M27VerifierGap.PRODUCT_THIN_SURFACE.value in unique_gaps,
             "gap_taxonomy": list(unique_gaps),
             "source_breadth_status": source_breadth_status,
             "semantic_verification_receipts": verification_receipts,
             "rejected_semantic_verification_receipts": rejected_verification_receipts},
        )
    timeline.first_verified_claim_ready_ms = _elapsed_ms(start_ns)
    events.append(_redacted_event(M27ProductEvent.VERIFIED_CLAIM_READY, start_ns, claim_id="claim_1", text=answer_text, citations=citations))
    timeline.first_citation_bound_ms = _elapsed_ms(start_ns)
    events.append(_redacted_event(M27ProductEvent.CITATION_BOUND, start_ns, claim_id="claim_1", citation_count=len(citations)))
    timeline.first_cited_segment_ready_ms = _elapsed_ms(start_ns)
    timeline.first_material_emitted_ms = timeline.first_verified_claim_ready_ms
    events.append(_redacted_event(M27ProductEvent.CITED_SEGMENT_READY, start_ns, text=answer_text, citations=citations))
    events.append(_redacted_event(M27ProductEvent.STREAM_PUBLISHABLE, start_ns, answer_len=len(answer_text), citation_count=len(citations)))
    timeline.final_emitted_ms = _elapsed_ms(start_ns)
    answer = {
        "schema_version": M27_AGENT_PRODUCT_SCHEMA,
        "status": "owner_only_cited_answer",
        "terminal_status": "answered",
        "answer_text": answer_text,
        "citations": citations,
        "answer_claims": [{"claim_id": c.claim_id, "claim_role": "direct", "surface_text": c.claim_text, "citation_ids": [v["citation_id"] for v in c.citations], "support_ref_count": len(c.citations), "source_breadth": c.source_breadth} for c in claims],
        "safe_abstention": False,
        "reason_codes": [],
        "provider_invoked": provider is not None,
        "provider_call_count": sum(int(x.get("provider_attempt_count") or 0) for x in verification_receipts),
        "material_claim_support_verified": True,
        "citation_locator_valid": True,
        "unsupported_accepted_claims": 0,
        "repair_attempted": bool(repair_attempts),
        "answer_source": "m27_agent_native_claim_graph",
        "answer_plan": plan.as_dict(),
        "claim_graph": [c.as_dict() for c in claims],
        "gap_taxonomy": [],
        "thin_cited_answer": False,
        "semantic_support_method": "calibrated_narrow_nli_provider",
        "semantic_verification_receipts": verification_receipts,
        "rejected_semantic_verification_receipts": rejected_verification_receipts,
        "source_breadth_status": source_breadth_status,
        "micro_timeline": timeline.as_dict(),
        "slo_compute_policy": M27SloComputePolicy().as_dict(),
    }
    return M27ProductAnswerResult(True, answer, tuple(claims), plan, (), tuple(repair_attempts), timeline, tuple(events), "VERIFIED_CITED_ANSWER")

def strict_product_success(answer: Mapping[str, Any]) -> bool:
    if answer.get("status") != "owner_only_cited_answer":
        return False
    text = str(answer.get("answer_text") or "")
    citations = answer.get("citations")
    if len(_M27_WORD_RE.findall(text)) < 45:
        return False
    if not isinstance(citations, Sequence) or isinstance(citations, (str, bytes)) or not citations:
        return False
    if answer.get("thin_cited_answer") is True:
        return False
    if answer.get("material_claim_support_verified") is not True:
        return False
    if answer.get("citation_locator_valid") is not True:
        return False
    if int(answer.get("unsupported_accepted_claims") or 1) != 0:
        return False
    plan = answer.get("answer_plan") if isinstance(answer.get("answer_plan"), Mapping) else {}
    if plan.get("broad_homepage_question") is True and len(citations) < 2:
        return False
    return True

__all__ = ["M27_AGENT_PRODUCT_SCHEMA", "M27_PRODUCT_SLO_MS", "M27ProductEvent", "M27VerifierGap", "M27SloComputePolicy", "M27ClaimNode", "M27ProductAnswerPlan", "M27ProductAnswerResult", "canonicalize_question_for_retrieval", "build_agent_native_product_answer", "strict_product_success", "canonicalize_question", "build_claim_native_answer"]


# Backwards-compatible names used by the Stage 23 runtime shell. These are still
# M27-native and do not delegate to the M26 answer composer.
def canonicalize_question(question: str) -> tuple[str, str]:
    return canonicalize_question_for_retrieval(question), _language(question)


def build_claim_native_answer(
    *,
    question: str,
    evidence: Sequence[Mapping[str, Any]],
    event_sink: Any | None = None,
) -> dict[str, Any]:
    result = build_agent_native_product_answer(
        question=question,
        intent_class="direct_grounded_knowledge",
        evidence=evidence,
    )
    if event_sink is not None:
        for event in result.stream_events():
            event_sink(event)
    if result.publishable:
        return dict(result.answer)
    runtime = result.as_runtime_result(question_sha256="redacted")
    return dict(runtime["verification"])
