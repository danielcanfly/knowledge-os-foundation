# M27 Stage 2 Replay / Equivalence Report

Date: 2026-10-03
Workspace: /home/ubuntu/LLM_Wiki-m27-stage2-replay
Branch: m27/stage2-replay-equivalence
Base: 30488a8d

## 1. Summary of files changed

Stage 2 adds only the assigned replay/equivalence surface:

- src/knowledge_engine/m27_replay_harness.py
- src/knowledge_engine/m27_equivalence_report.py
- tests/test_m27_replay_harness.py
- tests/test_m27_equivalence_report.py
- docs/m27/research/stage2_replay_equivalence_report.md

No M26 core runtime file was modified. No production configuration, route,
container, data store, release path, or provider integration was modified.

## 2. Harness public API

The replay harness public surface is intentionally small and provider-free.

capture_sanitized_replay_input(...)

Purpose:
- accept already-produced M26 routing/context/verifier objects or mappings
- immediately reduce them to an allowlisted sanitized snapshot
- never retain raw query, raw answer, evidence/source bodies, provider prompts,
  credentials, environment values, or private payloads

run_replay_equivalence(replay_input)

Purpose:
- rebuild only the safe fields needed by the Stage 1 adapters
- normalize through:
  - LegacyM26SemanticRoutingAdapter
  - LegacyM26DeadlineBudgetAdapter
  - LegacyM26ContextCompilerAdapter
  - LegacyM26VerifierAdapter
- compare legacy-safe signals against normalized Stage 1 representation
- return field-level classifications and one overall case classification

classify_response_status(...)

Purpose:
- normalize M26 response outcome into:
  - CITED_ANSWER
  - SAFE_ABSTENTION
  - ERROR
  - OTHER
  - UNAVAILABLE

classify_equivalence(...)

Purpose:
- classify one legacy/normalized field pair while preserving the distinction
  between true equivalence, Stage 1 unavailability, missing input signals,
  normalization drift, and safety-critical drift

build_equivalence_report(...)

Purpose:
- aggregate replay results without serializing replay values
- emit only sanitized case ids, field names, classification counts, and drift lists
- provide a privacy-safe Markdown summary

## 3. Replay fixture/input design

Replay inputs are deterministic and do not require a live provider.

The tests cover:
- the real M26 SemanticRoutingDecision object shape
- sanitized context compiler output mappings
- sanitized verification/final-response mappings
- explicit sanitized guard outcomes when such a signal is already available
- explicit legacy expectation metadata for the known PA7 stale-test drift
- intentionally missing signals to prove they are not falsely labeled equivalent

No fixture stores:
- raw query
- raw answer
- full evidence text
- full source text
- provider prompt
- secret
- API key
- credential
- environment value
- private payload

No provider call is made.
No retrieval round is added.
No context compilation is re-run.
No verification is re-run.

## 4. Comparison fields

The harness compares at least the required Stage 2 fields:

Response/outcome:
- response_status_class
- safe_abstention
- verification_status
- terminal_status

Routing:
- route
- route_reason

Budget/compute:
- deadline_remaining_ms
- minimum_budget_ms
- deadline_affordable
- provider_attempts_remaining
- provider_budget_class when available
- compute_tier when available

Evidence/citations:
- selected_evidence_count
- selected_evidence_ids
- context_compiler_citation_count
- verification_citation_count
- citation_shape

Provider/verifier:
- provider_call_count
- material_claim_support_verified
- unsupported_accepted_claims

Context/compiler:
- context_compiler_status

Guards:
- guard.BAD_TEMPLATE
- guard.UNSUPPORTED_MATERIAL_CLAIM
- guard.GENERIC_EXTRACTIVE_FALLBACK

Important: Stage 2 does not infer the generic-extractive-fallback guard from
broad_deterministic_fallback_used because those are not the same signal.

## 5. Equivalence classifications

The classification set is:

EQUIVALENT
- both sides have the signal and the normalized representation matches

EXPECTED_UNAVAILABLE_STAGE1
- the legacy/sanitized side has a signal, but the Stage 1 contract deliberately
  does not expose it
- this is not counted as equivalence

LEGACY_EXPECTATION_DRIFT
- an older test expectation differs from current production-reconciled M26 behavior
- this is classified separately from M27 normalization drift

NORMALIZATION_DRIFT
- both sides represent the field, but the Stage 1 normalized value differs
- non-safety-critical mismatch

MISSING_SIGNAL
- the legacy replay input did not contain the signal
- the harness refuses to invent it or label it equivalent

UNSAFE_DRIFT
- a safety-critical represented field differs across legacy and normalized views
- examples include response status class, safe-abstention outcome, verifier status,
  terminal status, citation count, or material-claim verification fields

Overall case classification uses the following severity order:

UNSAFE_DRIFT
NORMALIZATION_DRIFT
LEGACY_EXPECTATION_DRIFT
MISSING_SIGNAL
EXPECTED_UNAVAILABLE_STAGE1
EQUIVALENT

The report also exposes available_signals_equivalent independently, so expected
unavailability and missing signals do not masquerade as normalization failure.

## 6. Privacy guarantees

Privacy is enforced structurally rather than by convention.

SanitizedReplayInput:
- has no raw-query field
- has no raw-answer field
- has no evidence/source text field
- has no prompt field
- has no secret/credential/environment field
- case_id must match a short identifier regex and rejects free-form query text

Citation handling:
- citation bodies are discarded
- only citation count is retained
- citation shape stores only an allowlisted set of known schema field names
- exact_quote and other evidence text are not retained

Report handling:
- FieldComparison.as_dict() omits both legacy_value and normalized_value
- ReplayCaseResult.as_dict() contains only case id, classification, boolean summary,
  and field classification metadata
- EquivalenceReport renders field names and classification counts, not replay values

Privacy tests pass even when raw answer text, raw provider output, full evidence text,
provider prompt, credential-like strings, and context instruction text are supplied
to capture_sanitized_replay_input(...).

## 7. Exact tests and results

Required compile command:

    cd /home/ubuntu/LLM_Wiki-m27-stage2-replay
    python3 -m compileall -q       src/knowledge_engine/m27_replay_harness.py       src/knowledge_engine/m27_equivalence_report.py       tests/test_m27_replay_harness.py       tests/test_m27_equivalence_report.py

Result:
- PASS
- exit 0
- no compile output

Focused Stage 2 tests:

    PYTHONPATH=/home/ubuntu/LLM_Wiki-m27-stage2-replay/src       /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest -q       tests/test_m27_replay_harness.py       tests/test_m27_equivalence_report.py

Result:
- 16 passed in 1.01s

Required Stage 1 + Stage 2 gate:

    PYTHONPATH=/home/ubuntu/LLM_Wiki-m27-stage2-replay/src       /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest -q       tests/test_m27_context_runtime_contracts.py       tests/test_m27_legacy_m26_adapters.py       tests/test_m27_decision_trace.py       tests/test_m27_replay_harness.py       tests/test_m27_equivalence_report.py

Result:
- 50 passed in 1.17s

Required Ruff command:

    /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/ruff check       src/knowledge_engine/m27_replay_harness.py       src/knowledge_engine/m27_equivalence_report.py       tests/test_m27_replay_harness.py       tests/test_m27_equivalence_report.py

Result before final report:
- All checks passed!

No full 523 was run.
No Docker build was run.


## 8. Equivalence findings

A deterministic Stage 2 findings run covered four representative cases:

1. cited answer with routing, context compiler, citations, verifier fields, and explicit guards
2. conservative safe abstention with deadline/provider exhaustion
3. deferred PA7 legacy expectation drift
4. intentionally incomplete input proving missing signals are not treated as equivalent

Aggregate field results:

- EQUIVALENT: 51
- EXPECTED_UNAVAILABLE_STAGE1: 7
- LEGACY_EXPECTATION_DRIFT: 1
- MISSING_SIGNAL: 38
- NORMALIZATION_DRIFT: 0
- UNSAFE_DRIFT: 0

The report result was:

- available_signals_equivalent: true
- threatens_production_invariants: false
- ready_for_next_stage_review: true

Answer to the first required question:

Does M27 normalization faithfully represent the M26 signals that are actually
available in Stage 1?

Yes for the deterministic Stage 2 coverage implemented here. Every represented,
available M26 signal compared by the harness matched the Stage 1 adapter-normalized
value. No normalization mismatch was observed.

This statement is intentionally scoped to signals that Stage 1 actually exposes and
to the deterministic replay cases in this Stage 2 harness. It does not claim that
Stage 1 exposes every M26 runtime signal.

## 9. Legacy expectation drift findings

The known deferred file remains:

- tests/test_m26_pa_7_arbitrary_query_runtime.py

Several historical tests encode an older semantic expectation in which bounded
repair or deterministic recovery ends in a cited answer.

The production-reconciled runtime is now more conservative on some corresponding
failure paths and can terminate in safe abstention.

Stage 2 models this explicitly with:

- legacy expected status class: CITED_ANSWER
- current production-reconciled M26 status class: SAFE_ABSTENTION
- classification: LEGACY_EXPECTATION_DRIFT

This does not become NORMALIZATION_DRIFT because the current M26 safe-abstention
signal and the Stage 1 normalized representation agree.

No runtime code was modified to satisfy the stale expectation.
No verifier was loosened.
No safe-abstention boundary was weakened.

## 10. Missing/unavailable signals

Stage 1 intentionally does not expose every requested Stage 2 field.

Expected unavailable after Stage 1 normalization:
- citation shape
- explicit guard outcomes when supplied as a sanitized legacy-side signal
- compute tier if an external/current M26 signal is supplied, because
  ComputeDecision.compute_tier remains unavailable_in_stage1
- provider budget class if supplied separately, because Stage 1 carries the
  underlying provider-attempt signal but has no provider-budget-class contract

Common missing legacy-side signals in replay inputs:
- compute tier, because current M26 SemanticRoutingDecision does not contain one
- provider budget class, because current M26 routing decision exposes provider
  attempts remaining rather than a named budget class
- context compiler fields when a case never supplies a compiled package
- guard outcomes when no existing sanitized guard observation is available

The harness distinguishes both situations:

- legacy signal exists but Stage 1 cannot represent it:
  EXPECTED_UNAVAILABLE_STAGE1
- legacy replay input never had the signal:
  MISSING_SIGNAL

Neither is labeled EQUIVALENT.

Guard-specific finding:
- Stage 1 canonical DecisionTraceEvent has fixed guard schema support
- Stage 1 adapters do not currently populate guard observations
- Stage 2 therefore does not synthesize guard results from unrelated fields
- especially, broad_deterministic_fallback_used is not treated as equivalent to the
  generic-extractive-fallback guard

## 11. Blockers and mitigations

No Stage 2 blocker remains.

One tooling issue occurred while writing the second source file:
- LocalBridge rejected one large write request at its safety layer
- the same file was written in smaller chunks through LocalBridge
- no alternate host access path was used
- no repository or runtime state was damaged

No blocker required modifying:
- src/knowledge_engine/m26_aq_semantic_contract.py
- src/knowledge_engine/m26_public_api.py
- src/knowledge_engine/m26_console_api.py
- src/knowledge_engine/m26_pa7_arbitrary_query_runtime.py
- src/knowledge_engine/m26_context_compiler.py

Mitigation for the shared editable venv remains the documented one:
- use the shared interpreter for dependencies
- set PYTHONPATH to /home/ubuntu/LLM_Wiki-m27-stage2-replay/src

## 12. Remaining risks

1. Stage 1 adapters are intentionally metadata-only. Citation shape and guard outcomes
   are not adapter-normalized today, so Stage 2 can identify their absence but cannot
   prove field-level equivalence for them without a later explicit contract surface.

2. Replay coverage is deterministic and representative, not a full 523 execution.
   Master should retain the Stage 2 harness for broader future fixture coverage before
   any behavior-changing Stage 6 work.

3. M26 route/reason strings are treated as internal runtime codes. The harness does not
   accept raw user query text as a replay identifier and never serializes raw answer or
   evidence bodies.

4. The status-class mapper is deliberately conservative. Unknown statuses become OTHER
   rather than being guessed into cited answer or error.

5. LEGACY_EXPECTATION_DRIFT must remain separate from runtime behavior drift. Future
   maintainers should not make old cited-answer expectations green by weakening current
   safe-abstention behavior.

## 13. Production untouched confirmation

Production touched: NO.

This Stage 2 sub-session performed:
- read-only source/document inspection over ssh oracle-vm
- writes only inside /home/ubuntu/LLM_Wiki-m27-stage2-replay
- local compile/unit/lint execution using the shared M27 dependency venv
- deterministic in-process replay over sanitized fixtures and already-defined M26
  object shapes

It did not:
- restart or modify the production container
- restart or modify the isolated M27 container
- change nginx, Cloudflare, or public routes
- bind any production port
- write production R2
- write production Qdrant
- write production SQLite
- use production write credentials
- call a live provider
- add a provider integration
- run retrieval against production
- perform release promote or rollback
- run Docker build
- run full 523
- alter answer behavior
- alter retrieval behavior
- alter verification behavior

## 14. Recommendation whether Stage 3 can begin

Recommendation: READY_FOR_MASTER_INTEGRATION

Answer to the remaining required questions:

Are any observed differences actual runtime behavior drift, or only
missing/unavailable normalization fields?

- No M27 normalization drift was observed in represented available signals.
- The ordinary differences are missing or intentionally unavailable Stage 1 fields.
- One separately classified difference is legacy test expectation drift: old cited-answer
  expectation versus current production-reconciled safe abstention.
- That legacy expectation drift is not caused by Stage 2 or M27 normalization.

Does any drift threaten production invariants?

- No.
- UNSAFE_DRIFT count is zero.
- NORMALIZATION_DRIFT count is zero.
- Current conservative safe abstention is preserved.
- Generic extractive fallback, bad-template, and unsupported-material-claim protections
  were not loosened or bypassed.

Stage 3 may begin after Master reviews this commit and reruns its own Stage 1 baseline
plus Stage 2 integration gate.
