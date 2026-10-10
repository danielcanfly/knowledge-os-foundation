# C07 | AR07 Adaptive Compute, Offline Proof Receipts

**Evidence class:** isolated mock-only deterministic unit component.
**Product/stage status:** `ISOLATED_MOCK_COMPONENT_PASS` only if all scoped gates pass, `AR07_STAGE_DONE = FALSE`.
**Parent:** `144ff8694b2a8a7b01b0349a1c8e99d524193e71` (accepted AR09C/C02 mock-only evaluator).
**Branch/worktree:** `m27/c07-compute-offline`, `06_WORKSITES/C07_AR07_ADAPTIVE_COMPUTE_OFFLINE`.
**Strict tracked-file delta:** only this document, new experimental source and new experimental tests.

## 1. Non-authoritative typed policy boundary

`ComputeDecisionInput` is a frozen fixture envelope, NOT a signed TaskContract.
`ProviderCatalogFixture` and `PriceSnapshotFixture` are exact provider/model/version and synthetic quote snapshots, NOT live provider statements or current billable prices. Version, availability observation lifetime, currency, residency, privacy, tenant-owned approved-provider list, and AR03 source revision/grant/expiry are checked before compute utility or price can influence route selection.

`ComputePolicyProposal` + `DecisionTrace` only describe a possible next step. A positive result is deliberately named `RESERVATION_REQUIRED`, with `required_owner_action=AR02_CAS_RESERVE`, `provider_call_authorized=False` and `no_external_effect=True`. Neither a policy object nor a trace is a budget mutation, admit token, signed authority, bill, execution permit, verification report or provider call receipt.

Future consumer MUST reacquire contemporaneous source/grant/version, lease, cancellation, availability, and quote validity and obtain a **real AR02 sole-writer versioned CAS reservation** before any billable dispatch. CAS conflicts cause recomputation. The planner does not expose or invoke a dispatch adapter. AR04 separately owns tool permit and unknown-effect reconciliation; this component explicitly denies tool calls even with an available synthetic tool budget.

Cost is integer microunits only; the fixture currency is `MICROUSD` and **no FX conversion** is asserted. For each proposal, projected tokens = requested tokens × bounded agent count; projected upper-bound cost = tokens × pinned fixture rate. Exact inclusive limit is checked against `spent + reserved + proposed`, never just `max - spent`. Positive synthetic score, extra reflection, retries or fanout cannot increase a ceiling.

QA-I is a separate branch from RES-L and CODE-L. QA preserves synthetic per-request verifier time reserve before optional generation and does not make or weaken any independent <15s product terminal p95 claim. No new numeric first-text SLA is proposed. `verified_first_answer_preterminal` in the mock trace is **true only** for an explicit synthetic four-part fixture with verified content, substantiveness, pinned citation, and preterminal ordering. A terminal-only frame is not magically promoted to streaming success. No real verified client delivery, original native Q&A bytes or clock timestamps are proven.

Research/coding may request independently capped retrieval depth, reflection and agent fanout. Any cap overrun denies; retry-safe failures are typed and bounded by both attempts and per-phase retry limits. Cancellation, possible external effect, late billing overrun, unpriced route, source expiry or uncertain invoice prevents further spend. A missing actual invoice stays `UNKNOWN`, never cost zero or economic certification. An observed actual cost is `OBSERVED_NOT_SETTLED` and no billing record is created or silently refunded.

Decision traces are reason-coded and contain only bounded IDs, coarse route rejects, economic fields and version pins, no raw prompts, credentials, provider payloads, learned-feature labels or protected holdouts. There is no self-learning, online router, remote tool, real Provider or network access.

## 2. Red-first behavioral proof

The initial implementation intentionally returned `None` to all policy decisions. With complete test classes and collected tests, the initial run recorded **28 failed / 0 passed, exit 1**, rather than misrepresenting an import/collection error as a meaningful RED. Raw stdout: `05_EVIDENCE_INDEX/C07_AR07_ADAPTIVE_COMPUTE_OFFLINE_SCRATCH/RED_BEHAVIOR_PYTEST.log`. Replacing the stub with a deterministic, fail-closed policy is the only code behavior change in this new experimental file.

Required B01–B10 fixtures:
- B01 zero cost: DENY even at extreme marginal value.
- B02 zero tokens: DENY regardless of cheap fallback.
- B03 equality admits a proposal, +1 overspend DENY.
- B04 two proposals with same version do not each reserve; after hypothetical first CAS the second fails bounded budget. This is **NOT** proof of atomic CAS or multi-process durability.
- B05 max attempts/retries: STOP without another attempt.
- B06 only explicitly retry-safe pre-dispatch failure may propose a new reservation; untyped failure DENY/STOP.
- B07 timeout after possible dispatch/UNKNOWN_EFFECT: PAUSE for reconciliation; no blind re-send.
- B08 late billing overrun: STOP, actual observation retained, no phantom refund.
- B09 missing invoice: actual cost `UNKNOWN`, not zero; unsettled uncertainty denies new spend.
- B10 missing/stale/untrusted/incorrect-model quote: DENY even at high marginal utility.

Additional adversaries exercise privacy/residency/authorization first, stale provider health, source revision/grant mismatch, QA verifier reserve and terminal-only stream, cancellation/deadline, agent joint budget, negative/malformed budget, and AR04 tool permission.

## 3. Synthetic ablation / Pareto oracle

`MockAblationCase` + `mock_ablation` are an **invented fixture calculator**, not benchmark telemetry. Every `(workload, case_id)` must include exactly one simple and one adaptive fixture, duplicated/unpaired records are rejected. No mixing QA-I and RES-L/CODE-L denominators. Cost includes all fixture attempts, including failures; `cost_per_accepted=None` when no independently accepted *synthetic* outcomes. Pareto dominance compares fixed synthetic acceptance count, summed cost, and summed latency and is explicitly suffixed `_fixture`. It cannot justify real quality, cost, speed, p95, model switching, or policy promotion.

## 4. Evidence and non-claims

The raw test stdout/exit, Ruff, `git show --check`, tracked allowlist and original-parent audit, exact diff, and all new SHA256 belong in the separate task-owned `05_EVIDENCE_INDEX/C07_AR07_ADAPTIVE_COMPUTE_OFFLINE_SCRATCH/` and the separate `C07_AR07_ADAPTIVE_COMPUTE_OFFLINE_TEST_RECEIPTS.md`.

No real provider/IdP, source authority, VM, remote billing, Q&A protected route, physical durable reservation, native citation verifier, independently accepted real outcome, owner release, Prod, merge or push. AR02 writer CAS, AR03 authority, AR04 execution, AR05 verification, REL01/AR09 evaluation and full AR07 Stage remain OPEN.
