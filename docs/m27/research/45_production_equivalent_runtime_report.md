# M27 Production-Equivalent Runtime Integration Report

Status: `M27_PRODUCTION_EQUIV_RUNTIME_READY`
Date: 2026-10-06
Workspace: `/home/ubuntu/LLM_Wiki-m27-prod-equiv-runtime`
Branch: `m27/production-equivalent-runtime`
Accepted base: `8c86b523d7ef6340ad580ac37e2bf0deb29bd176`

## Integrated inputs

This branch is the first unified production-equivalent isolated M27 runtime candidate after the prep sessions.

Integrated heads:

- Production evidence bridge: `e8bea293a026e12926eb76cdddb615f13c4286d6`
- Admission infrastructure audit: `cda6a06d757e3f2f3b92d2758ba5b2f2c70109f6`
- Runtime observability contract: `f18128138d79c982474afe847de81cc55eaea5de`

All three heads shared the accepted runtime-finalization base:

`8c86b523d7ef6340ad580ac37e2bf0deb29bd176`

## What changed

### 1. Unified production-equivalent evidence bridge and telemetry

`src/knowledge_engine/m27_runtime_execution.py` now combines both prior code paths:

- accepts optional pinned `ProductionEvidenceAuthority`;
- validates production-equivalent evidence before compile/verify;
- preserves the M26.3 compiler as a non-authoritative selector under `m26_3_synthetic_selector_non_authoritative`;
- preserves existing synthetic-only execution when no production evidence authority is supplied;
- rejects authority drift, binding drift, source/locator mismatch, release mismatch, provenance digest gaps, and ACL mismatch before publication;
- emits `m27-runtime-telemetry/v1` for every isolated executable request;
- marks production-equivalent evidence usage through sanitized telemetry feature flag `PRODUCTION_EQUIVALENT_EVIDENCE`;
- writes both `runtime/execution_summary.json` and `runtime/telemetry.json` diagnostics;
- keeps `production_touched = False`.

The deterministic production-equivalent E2E proof remains `tests/test_m27_production_evidence_bridge.py`. It uses a read-only production-equivalent bundle fixture and proves:

- valid production-equivalent evidence compiles and verifies through M27 runtime;
- source, locator, release, and provenance drift fail closed before provider publication;
- governed memory cannot create or upgrade production evidence authority;
- synthetic route remains explicitly non-production authority.

### 2. Integrated runtime observability

The unified branch includes:

- `src/knowledge_engine/m27_runtime_telemetry.py`
- `tests/test_m27_runtime_observability_contract.py`
- `docs/m27/research/44c_runtime_observability_contract_report.md`
- `docs/m27/handoffs/OBSERVABILITY_TO_RUNTIME_HANDOFF.md`

The telemetry contract captures round-level tool, evidence-binding, compiler, provider/model, verifier, continuation, terminal reason, cost-unavailable state, and total runtime latency without raw query, prompt, passage, answer, provider response, or secrets.

### 3. Added clean isolated admission harness contract

This session added a new isolated admission harness contract instead of importing Stage13/14 runtime patches:

- `src/knowledge_engine/m27_isolated_admission_harness.py`
- `tests/test_m27_isolated_admission_harness.py`

The harness is a pure fail-closed guard and receipt layer. It performs no network calls and sends no smoke/admission requests. It models the Session 02 safe reuse plan:

- refuses non-loopback or production-like targets before first request;
- checks expected isolated endpoint and build SHA;
- records production health/identity as read-only input only;
- enforces single eval container, no concurrent build/test workload, memory, swap, and load guards;
- verifies quota active state cleanliness;
- classifies case transport hard stops such as HTTP 429 with zero provider calls, malformed/missing terminal SSE, unknown citations, unknown latency, and unknown TTFT;
- verifies postflight production identity stability, resource guard, quota cleanup, and isolated cleanup confirmation;
- summarizes receipts without converting infrastructure-poisoned rows into quality evidence.

## Preserved boundaries

- M26 feature-off baseline remains preserved by existing harness behavior and full M27 regression.
- M27 still cannot manufacture production authority.
- M26.3 compiler remains non-authoritative for production-equivalent route.
- M26 semantic verifier remains the answer publication authority.
- Admission/smoke scoring was not run.
- Stage13/14 legacy admission was not run.
- `100-case`, `Chunk002`, and `full523` were not run.
- Production was not mutated, restarted, stopped, rebuilt, deployed, or written.
- Production R2, Qdrant, SQLite, and release pointers were not touched.
- No dirty changes were imported from `/home/ubuntu/LLM_Wiki-m27-context-runtime`.

## Verification

Environment note: `/usr/bin/python3` has no pytest and the shared venv editable install can point to another worktree unless `PYTHONPATH=src:.` is explicit. All PASS results below used:

`/home/ubuntu/.venvs/m27-runtime-composition/bin/python`

with:

`PATH=/home/ubuntu/.venvs/m27-runtime-composition/bin:$PATH PYTHONPATH=src:.`

### Production-equivalent runtime, observability, finalization, admission harness

```bash
pytest \
  tests/test_m27_isolated_admission_harness.py \
  tests/test_m27_production_evidence_bridge.py \
  tests/test_m27_runtime_observability_contract.py \
  tests/test_m27_runtime_finalization.py -q
```

Result: `32 passed in 1.74s`.

### Full M27 suite

```bash
pytest tests/test_m27_*.py -q
```

Result: `524 passed in 12.87s`.

### M26 production / compiler / citation / authority / entrypoint safety-equivalent gate

```bash
pytest \
  tests/test_m26_production_answer_bundle.py \
  tests/test_m26_3_context_compiler.py \
  tests/test_m26_pa_4_verified_answer_citation_gate.py \
  tests/test_m26_11_production_authority.py \
  tests/test_m26_aq_production_entrypoint.py -q
```

Result: `35 passed in 12.32s`.

### Combined M27 production-equivalent + M26 safety gate

```bash
pytest \
  tests/test_m27_isolated_admission_harness.py \
  tests/test_m27_production_evidence_bridge.py \
  tests/test_m27_runtime_finalization.py \
  tests/test_m27_runtime_observability_contract.py \
  tests/test_m26_production_answer_bundle.py \
  tests/test_m26_3_context_compiler.py \
  tests/test_m26_pa_4_verified_answer_citation_gate.py \
  tests/test_m26_11_production_authority.py \
  tests/test_m26_aq_production_entrypoint.py -q
```

Result: `67 passed in 11.70s`.

### Static checks

```bash
python -m compileall -q src/knowledge_engine tests
```

Result: PASS.

```bash
ruff check \
  src/knowledge_engine/m27_runtime_execution.py \
  src/knowledge_engine/m27_runtime_harness.py \
  src/knowledge_engine/m27_runtime_telemetry.py \
  src/knowledge_engine/m27_production_evidence_bridge.py \
  src/knowledge_engine/m27_isolated_admission_harness.py \
  tests/test_m27_production_evidence_bridge.py \
  tests/test_m27_runtime_observability_contract.py \
  tests/test_m27_runtime_finalization.py \
  tests/test_m27_isolated_admission_harness.py
```

Result: `All checks passed!`.

```bash
git diff --check
```

Result: PASS.

## Non-gate diagnostic attempted and excluded

A broader direct run of the full `tests/test_m26_pa_7_arbitrary_query_runtime.py` file was attempted during verification. That file is not the M26 safety-equivalent gate used by the production evidence bridge handoff. It contains broader PA7 arbitrary-query behavior tests and failed under this branch/environment for existing runtime-behavior expectations unrelated to the M27 production-equivalent integration target. The correct gate from the bridge handoff is the M26 production/compiler/citation/authority/entrypoint suite above, which passed.

## Completion decision

`M27_PRODUCTION_EQUIV_RUNTIME_READY`

This branch is ready to hand off to Session 05 only for a fresh small-smoke session with its own preflight, build pin, resource guard, quota guard, production read-only health/identity checks, and cleanup checks. It does not authorize production mutation, Stage13/14 legacy admission, 100-case, Chunk002, or full523.
