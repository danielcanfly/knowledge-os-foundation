# 03｜M27 Stage 0B Blocker Register

Status: Not clean for implementation. Stage 1 code must not begin until blockers B001/B002/B003 are resolved or explicitly accepted by owner with mitigation.

## Blockers

| ID | Category | Description | Evidence | Status | Mitigation / next action |
|---|---|---|---|---|---|
| B001 | UNKNOWN_SOURCE | M27 clean branch is not complete production source. Production image has 382 Python files matching dirty worktree; M27 matches only 331. | Production image source copied/read-only compared against `/home/ubuntu/LLM_Wiki-f746-quality-gate-20260930`; 382/382 match dirty, 331/382 match M27. | OPEN | Stage 0C source reconciliation: decide whether to import production-only modules into M27 branch or create a new clean branch from production image/dirty source. Do not implement runtime before this. |
| B002 | UNKNOWN_SOURCE | Production entrypoint `knowledge_engine.m26_console_api:app` is missing from M27 clean branch. | Container inspect shows uvicorn command uses `knowledge_engine.m26_console_api:app`; `src/knowledge_engine/m26_console_api.py` not present in M27. | OPEN | Bring console/control-plane source into clean M27 base or explicitly make M27 research branch docs-only. Any insertion point chosen before this is suspect. |
| B003 | DIRTY_WORKTREE | Current source evidence lives in dirty worktree with many modified/untracked production modules. | `/home/ubuntu/LLM_Wiki-f746-quality-gate-20260930` has modified M26 files and 37 production-only untracked `m26*.py` modules. | OPEN | Create a clean source-reconciliation commit containing the production image-matching files only. Do not use dirty worktree as development base. |
| B004 | PRODUCTION_RISK | Production freeze contains generic fallback guard not present in M27 clean branch. | Freeze snippet: `# Guard: do not emit generic extractive evidence fallback as user-facing answer. return None`. Existing M27 branch predates this guard. | OPEN | Add invariant test/contract before any M27 routing/refactor. No M27 answer path can re-enable generic extractive fallback. |
| B005 | CONTRACT_AMBIGUITY | Proposed `ContextPlanner`, `ContextCompiler`, and `ComputePolicy` are partly already implemented in M26 under different names. | `m26_aq_semantic_contract.py` contains `SemanticRoutingDecision`, `_routing_decision`, deadline/provider budget logic. `m26_context_compiler.py` already builds context manifests/budgets. | RESOLVED_WITH_MITIGATION | M27 must extract/generalize existing code through `LegacyM26*Adapter`; do not build parallel implementations first. |
| B006 | CONTRACT_AMBIGUITY | Evidence selection, evidence strengthening, and context compilation are entangled; boundary is not yet clean. | Current runtime does `_select_evidence`, `_strengthen_evidence`, dynamic budgets, augmentation, then verification; `m26_context_compiler.py` is envelope-based. | ACCEPTED_WITH_MITIGATION | Introduce `EvidencePlanner` boundary before expanding `ContextCompiler`. Stage 1 may log summaries only. |
| B007 | MISSING_TRACE | Current runtime has stage/model events but not a normalized decision-level trace. | Public stream sanitizes fields; no stable `ContextPlan` / `ComputeDecision` trace artifact yet. | OPEN_FOR_STAGE1 | Add sanitized shadow trace only after B001/B002/B003 source reconciliation. No raw query/answer. |
| B008 | SECURITY_BOUNDARY_UNCLEAR | Admin/control-plane modules are production entrypoint-adjacent; M27 tool registry could accidentally expose write/admin capabilities. | Console app installs admin control plane, ingestion, QA inbox, suggested questions admin, jobs rollback, admin settings/audit. | ACCEPTED_WITH_MITIGATION | Stage 1 tool surface must be read-only and native-only. Admin/release/write tools are out of scope. |
| B009 | EVAL_GAP | Existing production-only QA inbox and quality repository are missing from M27 clean branch. | `m26_qa_inbox_integration.py`, `qa_answer_quality*.py` present in production/dirty, absent in M27. | OPEN | Include QA modules in source reconciliation before defining Evaluator/TraceStore. |
| B010 | ROLLBACK_GAP | M27 docs mention rollback, but clean branch lacks current production promotion/rollback modules. | `m26_production_promotion.py`, `m26_jobs_rollback_api.py`, active release modules missing from M27. | OPEN | Source reconciliation must include promotion/rollback modules; Stage 1 must not expose rollback/promote tools. |
| B011 | PRODUCTION_RISK | External harness SDK replacement is unsafe now. | M26 harness includes admission, streaming, event sink, provider budgets, semantic recovery, verification, QA capture, console/admin composition. | RESOLVED_WITH_MITIGATION | Initial Harness implementation is existing M26 runtime. No OpenAI/LangGraph/Claude harness provider in Stage 1. |
| B012 | PRODUCTION_RISK | Jev/FastDecision would be premature because current routing depends on rich runtime signals, not just query classification. | Existing routing uses failure codes, evidence coverage, deadline, provider attempts, semantic requirement class. | DEFERRED | Jev only as future shadow agreement experiment after normalized M26 decisions are logged. |
| B013 | EVAL_GAP | No no-blocker handoff can be produced yet. | B001-B004, B007, B009, B010 remain open. | OPEN | Produce Stage 0C source reconciliation handoff instead of `05_no_blocker_handoff.md`. |

## Blocker priority

Formal implementation must not begin until at least these are resolved:

```text
B001 source mismatch
B002 production entrypoint missing in M27 clean branch
B003 dirty-worktree source-of-truth problem
B004 production fallback guard invariant
```

Stage 1 shadow tracing can begin only after:

```text
- clean branch contains or references exact production source truth
- existing M26 route/budget/compiler code is mapped to adapters
- M27 feature flag is default off
- no raw query / raw answer is logged
```

## Resolved-by-research findings

The following are no longer unknowns:

```text
- production entrypoint is m26_console_api:app
- dirty worktree exactly matches production image source for Python files
- M27 clean branch is incomplete relative to production image
- existing M26 already has routing, compute-budget, context-compiler, verification, QA and admin/control-plane foundations
- M27 should extract/generalize these, not reimplement them
```

## Remaining Stage 1 blockers

```text
OPEN: B001, B002, B003, B004, B007, B009, B010, B013
```

Therefore Stage 1 implementation is not yet cleared.
