# M27 Runtime Composition Finalization Report (43)

Status: M27_RUNTIME_COMPOSITION_COMPLETE (isolated composition scope only)
Date: 2026-10-06
Workspace: /home/ubuntu/LLM_Wiki-m27-runtime-finalization
Branch: m27/runtime-composition-finalization
Expected clean base: e20e27068fac746c3b901d620ddcb99b5d005570

## Finalization audit correction

The upstream runtime composition report (42) claimed COMPLETE after 28 green tests, but the feature-on path still normalized caller-supplied compiled_output and verification_output and calculated a continuation decision without executing another round. That was a premature completion claim. This session preserved upstream compatibility while adding a distinct executable mode. Existing legacy composition tests are not counted as proof of execution.

The new executable mode requires M27ExecutableRequest with injected isolated evidence catalog, explicit synthetic compiler policy and semantic provider, but does NOT accept precomputed compiler or verifier outputs. Feature-off is checked first, without workspace or provider work.

## Actual M26 answer/model seam

The exact seam invoked is knowledge_engine.m26_aq_semantic_contract.synthesize_and_verify. This is the existing canonical M26 semantic closure and verification machinery, using the same downstream M26 verification and provider call classes. The public production admission/retrieval entrypoint run_owner_arbitrary_query remains unchanged. No M26 production code was modified or imported from Stage13/14.

ProviderQuota wraps the injected provider and enforces a finite call allowance and deadline before every M26 model/review/repair call. Any quota exhaustion results in safe terminal, without publishing partial or unsupported answer text.

## Executable compiler path

M27 invokes knowledge_engine.m26_context_compiler.compile_context_package, not the old normalization adapter. Inputs are a digest-bound isolated synthetic M26.2 envelope and gap, validated against the existing M26.3 synthetic-only compiler policy. Compiler-selected passage identities determine which exact source/locator-bound evidence records may reach the M26 synthesis/verifier. The adapter verifies passage text SHA, provenance digest presence, and equality of retrieved Stage5 source/locator IDs to the injected catalog.

IMPORTANT AUTHORITY LIMIT: M26.3 compiler is synthetic-only. The E2E proof demonstrates isolated composition with deterministic evidence selection, not admission of a live production evidence bundle. Production-compatible compiler binding requires separate validation before any fresh admission smoke. No live production answer bundle was loaded.

## Executable verifier path

After each actual compile, the M27 executable mode invokes the existing M26 semantic synthesis/verification routine, receives M26 verification status, material-claim support, citation locator validity and unsupported accepted claim count, and publishes a cited answer only when all deterministic criteria pass and there is at least one compiler-selected evidence/citation. The outer M27 gate may narrow an M26 result to safe terminal but cannot approve an answer that M26 rejected.

The legacy compiled-output and verification-output normalization-only path is retained for compatibility and is NOT eligible as an execution proof.

## Real bounded continuation state machine

For each round (round 0 through max_continuation_rounds inclusive): authorize Stage5 knowledge.search, execute the provider-backed retrieval, resolve digest/source/locator-bound evidence, compile with M26, call the M26 synthesis+verifier under quota, then evaluate M26 verification. Only an actual verifier/evidence gap with remaining tool/provider/deadline budget and a remaining round may start another iteration. Every subsequent round re-runs gather, compile, model and verifier.

Every round records sanitized round_index, continuation_reason, capabilities_invoked, evidence_count, evidence_delta, compiler_status, verification_status, budget_outcome, provider_calls, tool_calls and terminal_reason. No raw retrieved text, model prompt or private provider payload is stored in trace or workspace diagnostics. Workspace manifests are isolated under an injected root. Unknown budgets fail closed.

## Isolated E2E proof and acceptance

The isolated end-to-end route covers:
- Direct one-round cited answer with real M26 compiler and real M26 semantic verifier.
- First-round M26 abstention -> second retrieval, compile, M26 model answer, verifier -> cited terminal answer.
- Gap remaining after continuation -> finite safe terminal (max rounds).
- Provider budget exhausted inside the M26 verifier -> safe terminal with no additional round.
- Tool call count exhaustion -> no further gather.
- Unauthorized tool capability -> no provider, evidence or model execution.
- Distinct workspace roots and feature-off baseline.
- Source/locator mismatch -> no evidence admitted, no citation published.
- Explicit memory candidate cannot grant evidence authority.
- Deadline budget failure before the first read-only retrieval.
- No production mutation or admission evaluation.

All 14 new tests are acceptance guards that fail on upstream e20e2706 because its harness has no executable_request contract or round execution. Existing 28 composition tests remain intact.

## Test gates

- New finalization tests: 14 PASS.
- Previous composition tests: 28 PASS.
- Full Stage1-12 + M26 safety-equivalent suite including new tests: 555 PASS, 1 existing Starlette/httpx deprecation warning.
- Ruff on changed M27 source and test: PASS.
- Ruff format: PASS.
- compileall src/knowledge_engine + tests: PASS.
- git diff --check: PASS.
- Production read-only /v1/health before and after: HTTP 200 and ok true.
- Production build SHA observed: 7d4b2358464654bf3de7d9561ec89de841d279bd.
- Production canonical entrypoint: knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query.
- No production container stop, restart, rebuild, config mutation, R2/Qdrant/SQLite writes, Stage13/14 admission, Chunk002, 100-case or full523.

## Post-Stage12 A/B/C/D/E reconciliation

Codes: A architecture-neutral infrastructure; B isolated evaluation/quota support; C benchmark-specific runtime changes needing separate justification; D forensic/report-only; E reject. retain_now is deliberately NO for every commit: no cherry-pick was performed. requires_future_revalidation flags any code or evaluation reused later.

| commit | category | reason | retain_now | requires_future_revalidation |
|---|---|---|---|---|
| 06681024 | D | Stage12 master integration report, baseline history | NO | NO |
| 6e147d23 | B | Stage13 isolated evaluation tools and fixtures; not runtime authority | NO | YES |
| c8f8f678 | D | Stage13 master integration report | NO | NO |
| 649908f2 | C | Stage14 benchmark-facing M26 PA7 runtime edits mixed with diagnosis | NO | YES |
| 8799d774 | B | Stage14b isolated endpoint evaluation and evidence fixtures | NO | YES |
| 34f7b808 | C | M26 canonical/legacy runtime modifications for Stage14b provider contract | NO | YES |
| 8b567264 | D | Stage14 repair integration report | NO | NO |
| ab597e2a | D | Stage13r blocked smoke artifacts and report | NO | NO |
| 5889fcbd | D | Stage13r quota blocked retry artifacts/report | NO | NO |
| 8dfeb516 | D | Stage13r master smoke blocker integration report | NO | NO |
| 6db19db8 | D | Stage13q quota lease forensic root cause | NO | NO |
| fe8ed9b5 | B | Isolated quota lifecycle release and test, conditional future utility | NO | YES |
| bac017cd | B | Isolated quota lease proof and captured test artifacts | NO | YES |
| a946933f | D | Stage13q quota lease master integration report | NO | NO |
| 3d1dcae0 | B | Stage13r2 isolated smoke runner and evidence | NO | YES |
| 09aa3a1e | D | Stage13r2 master integration report | NO | NO |
| 3592b22b | D | Single-VM stability guard report and policy documentation | NO | YES |

No E category was assigned without a substantive safety finding. No C changes were imported, merged or silently copied.

## Remaining blockers before admission

1. The isolated proof uses the M26.3 synthetic-only compiler and injected provider fixture. Production-grade context compilation and verified provenance against a pinned production-equivalent bundle are NOT proven in this session. This is an admission blocker, not an isolated composition execution gap.
2. No fresh small admission smoke has been executed; no comparative quality/p95/citation readiness claims are authorized.
3. Stage13/14 benchmark-specific runtime modifications remain excluded and require an explicit independent justification review.

## Fresh small admission smoke decision

ready_for_fresh_small_admission_smoke: NO

Rationale: complete isolated composition execution does not grant production-grade evidence-bundle compiler authority. The next owner must first establish that bridge in a separate authorized scope, then assess whether fresh small admission smoke can start. This is not Stage13/14 continuation.

## Finalization disposition

M27_RUNTIME_COMPOSITION_COMPLETE, scoped narrowly to isolated end-to-end composition and its safety gates. Admission readiness remains NO. No production or forbidden worktrees touched.
