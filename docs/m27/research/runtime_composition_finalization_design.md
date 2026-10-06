# M27 Runtime Composition Finalization Design

Canonical isolated workspace: /home/ubuntu/LLM_Wiki-m27-runtime-finalization. Base e20e27068fac746c3b901d620ddcb99b5d005570.

## 1. Exact M26 answer/model seam
`knowledge_engine.m26_aq_semantic_contract.synthesize_and_verify(question, trace_id, intent_class, evidence, provider_client, requirements, endpoint_proof)` delegates to the existing `m26_pa7_semantic_closure_runtime._synthesize_and_verify`, which performs model calls, claim-local binding, source/locator/quote checking, semantic review, and safe abstention. Canonical production entrypoint remains `m26_aq_semantic_contract.run_owner_arbitrary_query` through `m26_ask_api`; no production entrypoint is rebound.

## 2. Narrowest safe seam
Calling the canonical semantic synthesis/verification function after isolated retrieval avoids a second answer engine or bypass of M26 claim/citation governance. Inject a provider client instead of loading live credentials. Account each real provider invocation, including internal semantic reviewer/repair calls. The returned M26 verification controls publication.

## 3. Injected dependencies
`M26IsolatedExecutionAdapter` receives an offline `provider_client`, an isolated read-only evidence materializer, and the digest-bound M26.3 synthetic context policy. M27 harness receives this optional adapter; legacy normalization-only tests remain usable without it. No network, production bundle, storage, or production config provider is provided by default.

## 4. Isolated execution guarantee
M26.3 `compile_context_package` is **synthetic-only** by its own signed authority contract and must never be presented as the production serving compiler. Execution only permits explicitly injected synthetic evidence whose IDs, source identities and locators match actual authorized read-only `knowledge.search` / `knowledge.expand` outputs. The compiler's own signed package must succeed before answering. No R2/Qdrant/SQLite/prod mutations. No direct production process interactions.

## 5. Bounded continuation state machine
Round 0: select and execute read-only tool(s), collect and provenance-check evidence, call existing M26.3 compiler, call canonical M26 semantic synthesis/verification. On sufficient verified cited output terminal. On verifier/evidence gap, advance only if positive max rounds, authorized next capability, remaining tool attempts, remaining provider attempts, and deadline headroom all permit. Round n repeats actual gather, compile, answer, verify. Reached limits, insufficient evidence, or unavailable provider/deadline => governed safe terminal. Count *actual* provider calls through a budget-enforcing wrapper, including calls made inside M26 review/repair. No adaptive benchmark/case tuning.

## 6. Executable compiler and verifier
Construct in-memory, self-digest-bound M26.2-form envelope/gap objects solely from materialized authorized synthetic evidence and call unchanged `m26_context_compiler.compile_context_package` with unchanged M26.3 signed policy. Restrict model's evidence to compiler-selected passage IDs. Invoke `m26_aq_semantic_contract.synthesize_and_verify`; accept cited answers only when M26 returns verified material support, locator validity, zero unsupported accepted claims, no abstention and non-empty citations. No independent verifier.

## 7. Feature-off inertness
`m27_enabled=False` returns M26_BASELINE_UNCHANGED before planning, read-only tools, provider, compiler, workspace, or candidate systems are invoked. Old normalization-based harness mode retained for existing contract tests.

## 8. Impossible production authorities
Only read-only stage5 descriptor capability execution. Synthetic compiler authority is pinned and verified. Injected workspace root isolated. Memory remains candidate-only; memory never populates authorized evidence. Learning proposal-only and meta review-only; no shell/deploy/release/storage writes. No Stage13/14 imports.

## 9. Test plan
Acceptance tests on new executable pathway: cited single-round, actual two-round knowledge.expand->recompile->reverify, max rounds, provider budget exhaustion, tool budget exhaustion, unauthorized capability, feature off, immutable workspace, nonauthoritative memory, no production reads/writes, sanitized per-round trace, synthetic-only compiler validation. Run prior 28 composition tests, Stage1-12 plus M26 safety 541 equivalent, Ruff, compileall, diff --check, read-only production health before and after. Audit every commit 06681024..3592b22b without cherry-pick.
