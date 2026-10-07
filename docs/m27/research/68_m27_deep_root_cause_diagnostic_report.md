# 68 M27 Deep Root-Cause Diagnostic Report

## 1. Final state

`M27_DEEP_ROOT_CAUSE_DIAGNOSIS_READY`

Final HEAD: `cf3ef730afdac327b72d361f051bcd9d4aca0aee`

This is a diagnosis-only artifact. It does not claim canary readiness or product readiness.

## 2. Executive diagnosis in plain language

M27 is not failing the live product gate because one knob is wrong. It is failing because the context-native runtime has an unfinished product-answer layer: it can isolate evidence, enforce authority, call providers and verify final answers, but it does not yet have a claim-native answer planner and stream publisher. The result is a little answer factory with strong vault doors but a half-built conveyor belt: some good answers emerge, some answerable questions become false safe terminals, some answers become thin one-citation summaries, and several cases produce HTTP 200 with neither a cited answer nor a safe terminal.

The most load-bearing finding is stream timing: `m27_isolated_event_stream` only emits `verified_claim_ready` and `cited_segment_ready` after `await worker`, meaning after the authoritative runtime finishes. That makes first material latency structurally close to final latency on slow paths.

Stage 22 measured p95 final latency `44915.431` ms, p95 first material latency `40327.837` ms, cited final-answer rate `35.0`%, and safe-terminal rate `20.0`%. Only `3/20` cases are good cited answers scoring >=85 under the Owner rubric.

## 3. Methodology and boundaries

Inputs used:

- Stage 22 receipts: `docs/m27/research/provider_only_config_rerun_receipts.json`
- Stage 21/20 diagnostic receipts: `docs/m27/research/m27_provider_tail_product_answer_repair_receipts.json`
- Stage 20 side-by-side receipts: `docs/m27/research/test_page_product_readiness_stage20_side_by_side_receipts.json`
- Runtime code inspection: `src/knowledge_engine/m27_runtime_execution.py`, `src/knowledge_engine/m27_isolated_streaming.py`, `src/knowledge_engine/m27_test_page_executor.py`
- Owner scoring source recorded by Stage 22: `/Users/huaihsuanhuang/Desktop/語意問題/問題評分標準.md`

Boundaries kept: no production deploy, no canary activation, no release pointer mutation, no admission/full523 rerun, no Stage13/14, no Chunk002, no repair patch, no M26 mature composer shortcut, no verifier-standard lowering, and no raw secrets.

## 4. 20-case outcome matrix

| Case | Slice | Cited | Safe terminal | Answer len | Citations | Final ms | First material ms | Outcome | Earliest unrecoverable stage | Owner score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C01 | browser_use_warning | no | no | 0 | 0 | 19899.914 | not emitted | empty nonterminal; Browser Use warning not cleared | product-surface answer planner / stream publication | n/a |
| C02 | ordinary_cited | yes | no | 1047 | 1 | 11410.376 | 11408.408 | cited answer but Owner hard-fail: source coverage too narrow | evidence strengthening / citation coverage admission | 85 |
| C03 | ordinary_cited | no | yes | 0 | 0 | 11147.403 | 11146.400 | verifier-gap safe terminal on answerable case | verifier claim support / safe-terminal decision | n/a |
| C04 | ordinary_cited | no | no | 0 | 0 | 44915.431 | not emitted | empty nonterminal regression after prior thin cited answer | answer composition / citation binding / stream publication | n/a |
| C05 | ordinary_cited | no | yes | 0 | 0 | 29629.738 | 29629.450 | verifier-gap safe terminal on answerable case | answer composition / verifier claim support | n/a |
| C06 | ordinary_cited | yes | no | 72 | 1 | 34165.078 | 34158.568 | thin cited answer below 85 | answer composition | 64 |
| C07 | multilingual | yes | no | 503 | 3 | 12655.788 | 12652.453 | good cited answer >=85 | none; passes bounded product gate for this case | 88 |
| C08 | ordinary_cited | no | no | 0 | 0 | 8659.228 | not emitted | empty nonterminal regression from Stage 20 pass | answer composition / stream publication | n/a |
| C09 | ordinary_cited | no | no | 0 | 0 | 14612.415 | not emitted | empty nonterminal regression from Stage 20 pass | answer composition / stream publication | n/a |
| C10 | ordinary_cited | yes | no | 220 | 1 | 40331.241 | 40327.837 | thin cited answer below 85 | answer composition / evidence breadth | 73 |
| C11 | ordinary_cited | yes | no | 230 | 1 | 31354.169 | 31348.937 | thin cited answer below 85 | answer composition / evidence breadth | 73 |
| C12 | ordinary_cited | no | no | 0 | 0 | 9959.773 | not emitted | empty nonterminal; verifier-gap terminal mismatch | verifier claim support / stream publication | n/a |
| C13 | ordinary_cited | yes | no | 1190 | 4 | 15105.740 | 15093.896 | good cited answer >=85 | none; passes bounded product gate for this case | 94 |
| C14 | ordinary_cited | no | no | 0 | 0 | 23441.998 | not emitted | empty nonterminal regression from Stage 20 pass | answer composition / stream publication | n/a |
| C15 | multilingual | no | no | 0 | 0 | 44304.658 | not emitted | multilingual normalization/coverage failure; empty nonterminal | query normalization / retrieval / multilingual evidence normalization | n/a |
| C16 | multilingual | no | yes | 0 | 0 | 13820.864 | 13820.174 | multilingual safe terminal; likely verifier-gap or inconsistent justification evidence | multilingual evidence normalization / verifier support matching | n/a |
| C17 | retrieval_hard | yes | no | 1218 | 4 | 14306.544 | 14301.912 | good cited answer >=85 | none; passes bounded product gate for this case | 94 |
| C18 | retrieval_hard | no | no | 0 | 0 | 19961.333 | not emitted | retrieval-hard verifier gap; empty nonterminal | verifier waiting for full answer / stream publication | n/a |
| C19 | safe_terminal | no | yes | 0 | 0 | 309.474 | 291.476 | justified safe terminal | pre-retrieval safety policy | n/a |
| C20 | safe_terminal | no | no | 0 | 0 | 33222.029 | not emitted | underspecified prompt not handled as clean safe terminal; empty nonterminal | query normalization / underspecified-question policy / stream publication | n/a |

## 5. Per-case root-cause table

| Case | Earliest unrecoverable stage | Root cause |
| --- | --- | --- |
| C01 | product-surface answer planner / stream publication | Stage 20 produced a cited answer, but Stage 22 returned HTTP 200 with no cited answer, no safe terminal, no first material event, and a 19.9s final latency. The product-surface Browser Use warning path still has no durable M27 publication path. |
| C02 | evidence strengthening / citation coverage admission | The answer was long enough and directly responsive, but it carried only one citation and triggered SOURCE_COVERAGE_TOO_NARROW under the Owner rubric. M27 can compose, but its citation/evidence boundary is too narrow for homepage-grade answer quality. |
| C03 | verifier claim support / safe-terminal decision | M26 and Stage 20 both show the topic is answerable with citations, yet Stage 22 emits a safe terminal. This is not a justified abstention; it is a verifier-gap terminal caused by failure to transform available evidence into verifier-acceptable cited claims. |
| C04 | answer composition / citation binding / stream publication | Stage 20 at least published a thin cited answer. Stage 22 drops to no answer and no safe terminal. That indicates the runtime crossed evidence selection, then failed to publish either a valid answer or an explicit safe terminal. |
| C05 | answer composition / verifier claim support | Kubernetes-in-AI-infra is supported by the corpus and answered by M26/Stage 20. Stage 22 safe-terminal behavior points to composer/verifier mismatch, not absence of evidence. |
| C06 | answer composition | The answer was only 72 characters with one citation and failed THIN_ANSWER_SURFACE and SOURCE_COVERAGE_TOO_NARROW. The runtime accepted a citation-bound answer shape without enough product substance. |
| C07 | none; passes bounded product gate for this case | Chinese GPU case demonstrates M27 can answer multilingual questions when lexical evidence alignment happens to work and citation coverage is adequate. |
| C08 | answer composition / stream publication | Stage 20 produced a cited answer and Stage 22 produced no answer or safe terminal. The evidence path can work, but the Stage 22 provider-only runtime loses publication on this ordinary cited case. |
| C09 | answer composition / stream publication | RAG is an ordinary supported topic. Stage 20 cited output and M26 cited output show coverage exists; Stage 22 empty nonterminal is a publication/composition regression. |
| C10 | answer composition / evidence breadth | A broad multi-tenant platform question collapsed into a 220-character, one-citation answer. This is product answer planning failure: the runtime publishes a valid citation envelope but not a homepage-grade answer. |
| C11 | answer composition / evidence breadth | Private AI / TEE needs multi-source explanation. Stage 22 returned a short one-citation answer and failed thin-surface/source-breadth criteria. |
| C12 | verifier claim support / stream publication | Single-request cost is answerable in M26 and became safe in Stage 20. Stage 22 returned neither a cited answer nor a safe terminal. The system failed both verifier closure and final-state publication semantics. |
| C13 | none; passes bounded product gate for this case | Reliability/observability question produced a long, multi-citation answer that passes Owner quality scoring. |
| C14 | answer composition / stream publication | The model-to-service question is supported and passed in Stage 20. Stage 22 no-answer/no-safe behavior identifies product-surface publication rather than retrieval absence. |
| C15 | query normalization / retrieval / multilingual evidence normalization | Chinese multi-tenant question did not pass and was not a justified safe fail. The executor uses lexical-primary retrieval without remote dense or explicit cross-lingual expansion, so language mismatch can starve downstream evidence or produce unverifiable claims. |
| C16 | multilingual evidence normalization / verifier support matching | Stage 22 product-gate boolean marks C16 as pass-or-justified-safe, but the same receipt diagnosis lists C16 under answerable_safe_terminal_case_ids. Treat this as an unresolved multilingual verifier-gap ambiguity, not product readiness. |
| C17 | none; passes bounded product gate for this case | Retrieval/verification/citation/safe-terminal meta-question produced a long, multi-citation answer and passes the Owner rubric. |
| C18 | verifier waiting for full answer / stream publication | The latency/TTFT/streaming relationship is answerable and Stage 20 safe-terminaled it. Stage 22 did not publish safe terminal or cited answer, showing a final-state contract gap after verifier failure. |
| C19 | pre-retrieval safety policy | The safety/prompt-injection probe should not return private prompts or credentials. Safe-terminal behavior is justified here. |
| C20 | query normalization / underspecified-question policy / stream publication | The vague request should become a clarification/safe terminal. Stage 22 returned no answer and no safe terminal after a long latency, which is a product-surface terminal semantics failure. |

## 6. Latency timeline table

Stage 22 comparator receipts preserve final latency and first-material latency, but not exact per-case retrieval/evidence/provider/verifier timestamps. The code path does have runtime telemetry writers, but those micro-timings were not preserved in the product comparison receipt. The table below therefore distinguishes observed timings from missing internal stage timings rather than inventing numbers.

| Case | Request start ms | Retrieval start/end | Evidence admission start/end | First provider call start/end | Verifier start/end | First verified claim ready | First cited segment ready | First material ms | Final ms | Latency class |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C01 | 0 | runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps | not preserved; code path admits production evidence before compile/verify | not preserved; provider calls occur inside verifier block after fast deterministic path misses | not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify | after worker completion only; no live claim-ready timestamp | after worker completion only; no live cited-segment timestamp | not emitted | 19899.914 | provider generation tail plus empty-final publication delay |
| C02 | 0 | runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps | not preserved; code path admits production evidence before compile/verify | not preserved; provider calls occur inside verifier block after fast deterministic path misses | not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify | after worker completion only; no live claim-ready timestamp | after worker completion only; no live cited-segment timestamp | 11408.408 | 11410.376 | provider/verifier path with insufficient source breadth |
| C03 | 0 | runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps | not preserved; code path admits production evidence before compile/verify | not preserved; provider calls occur inside verifier block after fast deterministic path misses | not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify | after worker completion only; no live claim-ready timestamp | after worker completion only; no live cited-segment timestamp | 11146.400 | 11147.403 | safe-terminal delay after verifier gap |
| C04 | 0 | runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps | not preserved; code path admits production evidence before compile/verify | not preserved; provider calls occur inside verifier block after fast deterministic path misses | not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify | after worker completion only; no live claim-ready timestamp | after worker completion only; no live cited-segment timestamp | not emitted | 44915.431 | provider generation tail plus publication drop |
| C05 | 0 | runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps | not preserved; code path admits production evidence before compile/verify | not preserved; provider calls occur inside verifier block after fast deterministic path misses | not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify | after worker completion only; no live claim-ready timestamp | after worker completion only; no live cited-segment timestamp | 29629.450 | 29629.738 | safe-terminal delay after verifier gap |
| C06 | 0 | runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps | not preserved; code path admits production evidence before compile/verify | not preserved; provider calls occur inside verifier block after fast deterministic path misses | not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify | after worker completion only; no live claim-ready timestamp | after worker completion only; no live cited-segment timestamp | 34158.568 | 34165.078 | provider/verifier path ending in thin surface |
| C07 | 0 | runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps | not preserved; code path admits production evidence before compile/verify | not preserved; provider calls occur inside verifier block after fast deterministic path misses | not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify | after worker completion only; no live claim-ready timestamp | after worker completion only; no live cited-segment timestamp | 12652.453 | 12655.788 | acceptable answer quality, still latency-sensitive |
| C08 | 0 | runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps | not preserved; code path admits production evidence before compile/verify | not preserved; provider calls occur inside verifier block after fast deterministic path misses | not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify | after worker completion only; no live claim-ready timestamp | after worker completion only; no live cited-segment timestamp | not emitted | 8659.228 | publication delay/drop after runtime work |
| C09 | 0 | runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps | not preserved; code path admits production evidence before compile/verify | not preserved; provider calls occur inside verifier block after fast deterministic path misses | not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify | after worker completion only; no live claim-ready timestamp | after worker completion only; no live cited-segment timestamp | not emitted | 14612.415 | publication delay/drop after runtime work |
| C10 | 0 | runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps | not preserved; code path admits production evidence before compile/verify | not preserved; provider calls occur inside verifier block after fast deterministic path misses | not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify | after worker completion only; no live claim-ready timestamp | after worker completion only; no live cited-segment timestamp | 40327.837 | 40331.241 | provider tail with thin final surface |
| C11 | 0 | runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps | not preserved; code path admits production evidence before compile/verify | not preserved; provider calls occur inside verifier block after fast deterministic path misses | not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify | after worker completion only; no live claim-ready timestamp | after worker completion only; no live cited-segment timestamp | 31348.937 | 31354.169 | provider tail with thin final surface |
| C12 | 0 | runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps | not preserved; code path admits production evidence before compile/verify | not preserved; provider calls occur inside verifier block after fast deterministic path misses | not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify | after worker completion only; no live claim-ready timestamp | after worker completion only; no live cited-segment timestamp | not emitted | 9959.773 | verifier gap with empty final event |
| C13 | 0 | runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps | not preserved; code path admits production evidence before compile/verify | not preserved; provider calls occur inside verifier block after fast deterministic path misses | not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify | after worker completion only; no live claim-ready timestamp | after worker completion only; no live cited-segment timestamp | 15093.896 | 15105.740 | acceptable answer quality, still latency-sensitive |
| C14 | 0 | runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps | not preserved; code path admits production evidence before compile/verify | not preserved; provider calls occur inside verifier block after fast deterministic path misses | not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify | after worker completion only; no live claim-ready timestamp | after worker completion only; no live cited-segment timestamp | not emitted | 23441.998 | publication delay/drop after runtime work |
| C15 | 0 | runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps | not preserved; code path admits production evidence before compile/verify | not preserved; provider calls occur inside verifier block after fast deterministic path misses | not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify | after worker completion only; no live claim-ready timestamp | after worker completion only; no live cited-segment timestamp | not emitted | 44304.658 | multilingual retrieval/composition gap plus provider tail |
| C16 | 0 | runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps | not preserved; code path admits production evidence before compile/verify | not preserved; provider calls occur inside verifier block after fast deterministic path misses | not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify | after worker completion only; no live claim-ready timestamp | after worker completion only; no live cited-segment timestamp | 13820.174 | 13820.864 | safe-terminal delay with multilingual support mismatch |
| C17 | 0 | runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps | not preserved; code path admits production evidence before compile/verify | not preserved; provider calls occur inside verifier block after fast deterministic path misses | not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify | after worker completion only; no live claim-ready timestamp | after worker completion only; no live cited-segment timestamp | 14301.912 | 14306.544 | acceptable answer quality, still latency-sensitive |
| C18 | 0 | runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps | not preserved; code path admits production evidence before compile/verify | not preserved; provider calls occur inside verifier block after fast deterministic path misses | not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify | after worker completion only; no live claim-ready timestamp | after worker completion only; no live cited-segment timestamp | not emitted | 19961.333 | verifier waiting for full answer plus empty publication |
| C19 | 0 | runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps | not preserved; code path admits production evidence before compile/verify | not preserved; provider calls occur inside verifier block after fast deterministic path misses | not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify | after worker completion only; no live claim-ready timestamp | after worker completion only; no live cited-segment timestamp | 291.476 | 309.474 | fast justified safe terminal |
| C20 | 0 | runtime emits retrieval stage events, but Stage22 comparator receipts do not preserve per-stage timestamps | not preserved; code path admits production evidence before compile/verify | not preserved; provider calls occur inside verifier block after fast deterministic path misses | not preserved; verifier block wraps deterministic fast path, fast provider answer, and synthesize_and_verify | after worker completion only; no live claim-ready timestamp | after worker completion only; no live cited-segment timestamp | not emitted | 33222.029 | safe-terminal policy miss plus publication delay |

Why first material is close to final: `m27_isolated_event_stream` drains runtime progress events while the worker runs, but it converts the final result to streamable verified material only after `await worker`. Then it emits `verified_claim_ready`, `cited_segment_ready`, and `final_answer_done` sequentially. So verified material is a post-hoc serialization of the final DTO, not a live first-answer-text stream.

## 7. Verifier-gap safe-terminal analysis

| Case | Justified? | Outcome | Analysis | Earliest stage |
| --- | --- | --- | --- | --- |
| C03 | no | verifier-gap safe terminal on answerable case | M26 and Stage 20 both show the topic is answerable with citations, yet Stage 22 emits a safe terminal. This is not a justified abstention; it is a verifier-gap terminal caused by failure to transform available evidence into verifier-acceptable cited claims. | verifier claim support / safe-terminal decision |
| C05 | no | verifier-gap safe terminal on answerable case | Kubernetes-in-AI-infra is supported by the corpus and answered by M26/Stage 20. Stage 22 safe-terminal behavior points to composer/verifier mismatch, not absence of evidence. | answer composition / verifier claim support |
| C16 | no / unresolved conflict | multilingual safe terminal; likely verifier-gap or inconsistent justification evidence | Stage 22 product-gate boolean marks C16 as pass-or-justified-safe, but the same receipt diagnosis lists C16 under answerable_safe_terminal_case_ids. Treat this as an unresolved multilingual verifier-gap ambiguity, not product readiness. | multilingual evidence normalization / verifier support matching |
| C19 | yes | justified safe terminal | The safety/prompt-injection probe should not return private prompts or credentials. Safe-terminal behavior is justified here. | pre-retrieval safety policy |

Verifier gap summary:

- Answerable safe-terminal candidates: `C03, C05, C16`.
- Empty nonterminal cases: `C01, C04, C08, C09, C12, C14, C15, C18, C20`.
- Justified safety terminal: `C19`.
- C16 has contradictory Stage 22 evidence: the product gate boolean marks it pass-or-justified-safe, while the Stage 22 diagnosis lists it under answerable safe terminals. This should remain a diagnosis item, not readiness evidence.

## 8. Owner 85-point scoring table

Rubric source recorded by Stage 22: `/Users/huaihsuanhuang/Desktop/語意問題/問題評分標準.md`. Stage 22 scored only successful cited final answers, which is correct because no-answer and safe-terminal cases fail the product gate before rubric scoring.

| Case | Score | Result | Answer len | Citations | Hard fail codes | Dimension failures |
| --- | --- | --- | --- | --- | --- | --- |
| C02 | 85 | fail | 1047 | 1 | SOURCE_COVERAGE_TOO_NARROW | Answer Quality From Canonical API /30: 28; Evidence, Sources, and Citation Quality /20: 11; Visitor Intent and Homepage Fit /15: 14; Question Framing Quality /15: 14; Corpus Representativeness /10: 9; Non-Duplication and Distinctiveness /10: 9 |
| C06 | 64 | fail | 72 | 1 | THIN_ANSWER_SURFACE, SOURCE_COVERAGE_TOO_NARROW | Answer Quality From Canonical API /30: 7; Evidence, Sources, and Citation Quality /20: 11; Visitor Intent and Homepage Fit /15: 14; Question Framing Quality /15: 14; Corpus Representativeness /10: 9; Non-Duplication and Distinctiveness /10: 9 |
| C07 | 88 | pass | 503 | 3 |  | Answer Quality From Canonical API /30: 24; Evidence, Sources, and Citation Quality /20: 18; Visitor Intent and Homepage Fit /15: 14; Question Framing Quality /15: 14; Corpus Representativeness /10: 9; Non-Duplication and Distinctiveness /10: 9 |
| C10 | 73 | fail | 220 | 1 | THIN_ANSWER_SURFACE, SOURCE_COVERAGE_TOO_NARROW | Answer Quality From Canonical API /30: 16; Evidence, Sources, and Citation Quality /20: 11; Visitor Intent and Homepage Fit /15: 14; Question Framing Quality /15: 14; Corpus Representativeness /10: 9; Non-Duplication and Distinctiveness /10: 9 |
| C11 | 73 | fail | 230 | 1 | THIN_ANSWER_SURFACE, SOURCE_COVERAGE_TOO_NARROW | Answer Quality From Canonical API /30: 16; Evidence, Sources, and Citation Quality /20: 11; Visitor Intent and Homepage Fit /15: 14; Question Framing Quality /15: 14; Corpus Representativeness /10: 9; Non-Duplication and Distinctiveness /10: 9 |
| C13 | 94 | pass | 1190 | 4 |  | Answer Quality From Canonical API /30: 28; Visitor Intent and Homepage Fit /15: 14; Question Framing Quality /15: 14; Corpus Representativeness /10: 9; Non-Duplication and Distinctiveness /10: 9 |
| C17 | 94 | pass | 1218 | 4 |  | Answer Quality From Canonical API /30: 28; Visitor Intent and Homepage Fit /15: 14; Question Framing Quality /15: 14; Corpus Representativeness /10: 9; Non-Duplication and Distinctiveness /10: 9 |

Cited final answer diagnosis:

- Passing cited answers: `C07, C13, C17`.
- Cited answers below product standard or hard-failed: `C02, C06, C10, C11`.
- Main scoring failure mode: one-source / thin answer surface, especially C06, C10 and C11.

## 9. 2027-style architecture subsystem gap map

| Subsystem | Current observed behavior | Expected 2027-style behavior | Gap | Evidence | Repair direction, not implemented |
| --- | --- | --- | --- | --- | --- |
| context contract | Request, task, budget and evidence authorities are explicit, but the product surface still inherits legacy answer semantics through adapters. | Context-native contract should expose answerable state, evidence sufficiency, claim graph readiness and publication intent as first-class milestones. | Mature for isolation, immature for product-answer state transitions; no per-claim readiness contract crosses into stream publication. | src/knowledge_engine/m27_runtime_execution.py:568-600, 946-973 | Add explicit answer-state machine with answerable/evidence-ready/claim-ready/publication-ready transitions. |
| evidence boundary | Production authority admission exists and citation binding drift is checked, but cited answers can collapse to one source or no final publication. | Evidence boundary should carry coverage requirements and source-breadth obligations into composition and verifier decisions. | Authority is treated mostly as validity, not sufficiency; broad questions can pass with one source or fail into safe terminal despite evidence existing. | src/knowledge_engine/m27_runtime_execution.py:654-660, 720-727, 779-797 | Represent required source coverage and corpus breadth before answer composition. |
| claim graph | The public answer often has a single claim and the stream adapter only emits claim events after final runtime completion. | Claim graph should allow incremental verified subclaims with per-claim evidence/citation binding. | No live partial claim graph is emitted from the runtime; verifier waits for whole answer. | src/knowledge_engine/m27_isolated_streaming.py:132-191, 256-267 | Introduce claim-level verifier outputs as runtime events, not post-hoc DTO splitting. |
| citation binding | Binding preservation is validated after answer generation, and drift becomes safe terminal. | Binding should be preserved through evidence selection, composition, verifier and stream publication without late all-or-nothing drop. | Late binding failure loses answer, and narrow binding can still produce thin one-citation answers. | src/knowledge_engine/m27_runtime_execution.py:779-797 | Make citation-bound answer plans before provider generation; require source breadth for broad questions. |
| verifier interface | Verifier closure is binary: owner_only_cited_answer or safe terminal/empty terminal after gap. | Verifier should return actionable gap categories, partial verified claims, and repairable unsupported spans. | Verifier gap becomes continuation/provider retry or safe terminal; it does not expose enough structured cause to the stream or planner. | src/knowledge_engine/m27_runtime_execution.py:821-861 | Add verifier-gap taxonomy and bounded deterministic repair hooks before provider retry. |
| stream publication semantics | Verified material events are generated only after await worker; safe terminals emit only final safe_abstention_done. | Stream should publish first verified cited segment as soon as it is verified, before full answer completion. | First material latency is structurally close to final latency in failing paths. | src/knowledge_engine/m27_isolated_streaming.py:230-267 | Wire runtime event_sink to verified_claim_ready/cited_segment_ready events during execution. |
| provider orchestration | Owner-only executor allows 4 provider attempts and 60s deadline; runtime can continue on verifier gap. | Provider policy should be bounded by product p95 and stop/recover deterministically when enough evidence exists. | Provider tail is allowed to dominate p95 and retry without producing early material. | src/knowledge_engine/m27_test_page_executor.py:201-206, 236-247; src/knowledge_engine/m27_runtime_execution.py:588-599, 832-861 | Cap provider tail under product SLO and prefer deterministic evidence-bound composition before retries. |
| compute budget policy | Budget has a 60s deadline and 4 attempts in the product path. | Budget policy should be product-surface aware: p95 <15s and first material <15s are hard constraints, not after-the-fact metrics. | Current budget admits work that cannot satisfy p95/first-material goals. | src/knowledge_engine/m27_test_page_executor.py:240-246 | Compute budgets should be derived from public SLO with per-stage timeboxes. |
| multilingual evidence normalization | Executor normalizes question, then runs lexical-primary retrieval with dense channels disabled and no explicit cross-lingual expansion. | Multilingual query should map to canonical article/evidence language and preserve support matching across languages. | C15/C16 show Chinese/Japanese coverage gaps despite English corpus support. | src/knowledge_engine/m27_test_page_executor.py:123-172 | Add multilingual canonical term expansion and cross-lingual evidence support matching before verifier. |
| memory/governance interaction | No production datastore writes occurred, and governance/redaction held. | Governance should remain isolated while still carrying product-quality diagnostics. | Safety is solid; diagnostic telemetry is too thin for root-cause latency attribution. | docs/m27/research/provider_only_config_rerun_receipts.json | Keep governance invariant, expand redacted per-stage telemetry. |
| tool/MCP integration | Only knowledge.search is permitted in the isolated runtime. | Tool integration should expose retrieval timing, evidence deltas and article boundary quality to verifier and streamer. | Tool records exist but comparator receipts did not preserve per-stage timing and provider-call telemetry per case. | src/knowledge_engine/m27_runtime_execution.py:630-649, 974-994 | Persist per-case execution_summary/telemetry in product comparison receipts. |
| product-surface answer planner | The planner accepts thin answers and empty nonterminal finals on homepage-style questions. | Planner should enforce homepage-grade answer depth, visitor fit, source breadth and clean terminal semantics before publication. | Only 3/20 cases were good cited >=85 in Stage 22; 4/7 cited answers failed Owner scoring. | docs/m27/research/provider_only_config_rerun_receipts.json | Add product answer planner between evidence sufficiency and verifier, not M26 composer rebase. |

## 10. Counterfactual probe results

These are bounded diagnostic probes, not product evidence.

| Probe | Result |
| --- | --- |
| P1_stream_emission_dry_run | {"dependency_note": "Static dry-run used because importing knowledge_engine in this shell requires optional httpx dependency unavailable in the diagnostic environment.", "interpretation": "Publication adapter can serialize verified material events, but code emits them only after awaiting the worker result; it is not a live claim-level stream.", "stream_safe_terminal_dry_run": ["safe_abstention_done"], "stream_verified_dry_run": ["verified_claim_ready", "cited_segment_ready", "final_answer_done"]} |
| P2_static_stream_timing_probe | {"code_refs": ["src/knowledge_engine/m27_isolated_streaming.py:230-267"], "evidence": "m27_isolated_event_stream awaits the worker before converting result to DTO and emitting verified material events.", "result": "positive"} |
| P3_provider_budget_static_probe | {"continuation_rounds_1": true, "deadline_60000_ms": true, "interpretation": "The product path can legally spend far beyond the 15s p95 target before producing final material.", "provider_attempts_4": true, "result": "positive"} |
| P4_multilingual_retrieval_static_probe | {"interpretation": "No explicit cross-lingual expansion was found in the owner-only executor before lexical retrieval.", "lexical_primary_dense_disabled": true, "result": "positive"} |
| P5_no_provider_deterministic_path_probe | {"code_refs": ["src/knowledge_engine/m27_runtime_execution.py:753-769"], "evidence": "Runtime tries _try_canonical_evidence_bound_fast_path before provider synthesis, but Stage22 still produced only 7/20 cited finals and only 3/20 good cited finals.", "result": "implemented_but_insufficient"} |
| P6_receipt_counterfactual_stage20_vs_stage22 | {"interpretation": "Several answerable Stage20 cases regressed to empty nonterminal under Stage22 provider-only config, so the problem is not just missing corpus evidence.", "result": "positive_regression_signal", "stage20_ok_or_cited_cases_that_became_stage22_empty_nonterminal": ["C01", "C04", "C08", "C09", "C14", "C20"]} |

## 11. Root-cause tree with ranked causes

| Rank | Cause | Confidence | Evidence | Support |
| --- | --- | --- | --- | --- |
| 1 | Stream publication is post-hoc, not claim-native | High | m27_isolated_event_stream waits for worker completion before emitting verified_claim_ready/cited_segment_ready; this structurally ties first material latency to final latency. | src/knowledge_engine/m27_isolated_streaming.py:230-267 |
| 2 | Verifier-gap path is all-or-nothing | High | Failure to produce a fully verified cited answer becomes continuation, safe terminal, or empty final; partial verified claims and precise gap causes are not surfaced. | src/knowledge_engine/m27_runtime_execution.py:821-861 |
| 3 | Product answer planner is immature | High | Thin one-citation answers can be published, while answerable cases become safe/empty terminals. Product-depth and homepage-fit are not first-class gates before publication. | Stage22 Owner 85 scoring and case matrix |
| 4 | Provider budget violates product SLO | High | The owner-only product path grants 60s and 4 provider attempts; p95 final 44.9s and p95 first material 40.3s are unsurprising under this policy. | src/knowledge_engine/m27_test_page_executor.py:240-246 |
| 5 | Evidence sufficiency is weaker than evidence validity | Medium | Authority/binding checks validate provenance, but broad questions still receive one-source/thin answers or fail despite available evidence. | Stage22 C02/C06/C10/C11 scores |
| 6 | Multilingual retrieval/support normalization is missing | Medium | C15/C16 fail while related English topics are answerable; lexical-primary retrieval with dense disabled is brittle for cross-lingual queries. | src/knowledge_engine/m27_test_page_executor.py:143-153 |
| 7 | Diagnostic receipts omit internal per-stage telemetry | Medium | Comparator receipts preserve final/first material timings but not retrieval/provider/verifier micro-timeline per case, forcing root cause to be reconstructed from code and prior receipts. | Stage22 receipts schema |

Root-cause tree:

1. Publication semantics: post-hoc stream conversion after worker completion.
   1.1 First material cannot lead final by much because verified material events are emitted only after full runtime completion.
   1.2 Empty/safe terminal results produce only terminal events, not answer progress.
2. Verifier/composer interface: whole-answer verification creates all-or-nothing outcomes.
   2.1 False safe terminals occur when evidence exists but claims are not verifier-acceptable.
   2.2 Empty nonterminals occur when final-state mapping fails to publish either answer or safe terminal.
3. Product planner immaturity: homepage answer quality is not a native contract.
   3.1 Thin one-citation answers can pass structural verification but fail Owner 85 scoring.
   3.2 Source-breadth and visitor-fit are not enforced before publication.
4. Provider orchestration and compute policy: 60s / 4-attempt budget is not product-SLO aware.
   4.1 Slow provider/verifier paths consume tail budget without emitting useful material.
5. Multilingual normalization: cross-lingual evidence support is brittle.
   5.1 C07 works, C15/C16 fail, which points to incidental lexical match rather than robust multilingual architecture.

## 12. What not to fix next, because it is a patch/shortcut

- Do not rebase M27 product answers onto the M26 mature composer.
- Do not lower verifier standards to make cited-answer rates look better.
- Do not special-case the 20-case set or memorize case IDs.
- Do not increase provider timeouts, raise rate limits, or add retries as the primary solution.
- Do not count safe terminals as success unless the terminal is justified and answerability is disproven.
- Do not hide empty nonterminal cases behind HTTP success.
- Do not treat one-citation thin answers as product-ready simply because citation binding is valid.

## 13. Recommended principled repair plan, without implementing it

1. Build a native M27 product-answer planner that turns evidence sufficiency into an answer plan with required facets, source breadth, target depth, citation slots and visitor-fit constraints.
2. Add a claim graph between evidence and answer text. Each claim should carry support refs, citation locators, source identities and verifier state.
3. Change stream publication from post-hoc DTO splitting to live claim-level publication. Emit `verified_claim_ready` and `cited_segment_ready` from runtime execution when a claim is verified, not after full worker completion.
4. Replace all-or-nothing verifier gaps with structured gap categories: missing citation locator, unsupported claim span, insufficient source breadth, multilingual support mismatch, provider malformed output, and true no-evidence.
5. Make compute policy product-SLO aware. Derive provider call caps and verifier deadlines from p95 <15s and first material <15s, not from a 60s semantic recovery budget.
6. Add multilingual canonicalization before retrieval: translate/expand key technical terms, map them to canonical article themes, and verify support across language boundaries.
7. Persist redacted per-stage telemetry in comparison receipts: retrieval start/end, evidence admission start/end, provider call count/duration, verifier exclusive time, first claim-ready time and stream emission time.
8. Re-run only bounded product diagnostics after repairs. Do not run admission/full523 until the product-surface 20-case gate is structurally fixed.

## 14. Safety/no-production proof

- New artifacts are diagnostic-only docs, CSV and JSON receipts.
- No production deploy, no canary activation, no release pointer mutation.
- Stage22 cleanup proof is carried forward in receipts under `safety_proof.stage22_cleanup_source`.
- No raw owner/provider secret values are stored in new artifacts.
- Raw answer text was intentionally omitted from the new JSON receipt; the prompt-injection safety case question is sanitized.


## Validation

- `python3 -m compileall -q src scripts tests`: PASS
- `git diff --check`: PASS before commit
- JSON load/schema sanity for `m27_deep_root_cause_diagnostic_receipts.json`: PASS
- Diagnostic script run: PASS
- `ruff`: unavailable in this isolated shell (`exit 127`), recorded as unavailable rather than skipped silently

## 15. Artifact list

- `docs/m27/research/68_m27_deep_root_cause_diagnostic_report.md`
- `docs/m27/research/m27_deep_root_cause_diagnostic_receipts.json`
- `docs/m27/research/68_case_failure_matrix.csv`
- `docs/m27/handoffs/M27_DEEP_ROOT_CAUSE_DIAGNOSTIC_HANDOFF.md`
- `scripts/m27_deep_root_cause_diagnostic_23.py`
