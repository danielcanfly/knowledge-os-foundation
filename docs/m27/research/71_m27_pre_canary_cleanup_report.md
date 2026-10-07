# 71 M27 Pre-Canary Cleanup Report

Final state: `M27_PRE_CANARY_CLEANUP_READY_FOR_ACTIVATION_SESSION`

## Scope

Stage 27 performed cleanup and readiness closure only. It did not activate canary, deploy production, mutate a release pointer, change public routing/Nginx, restart/rebuild production M26, write production datastores, rerun admission/full523, run Stage13/14, or run Chunk002.

## 1. Legacy tail cleanup

The unreachable block after the Stage 25 `build_agent_native_product_answer(...)` return in `m27_test_page_executor.py` was removed. Dead imports and legacy runtime-harness/provider helpers used only by that tail were removed as well. The product path still uses the pinned read-only production snapshot and existing safety/pre-retrieval helpers.

A Stage 27 AST/source test proves the product-result return is the final statement in `run_execution` and rejects direct delegation tokens for `run_owner_arbitrary_query`, `synthesize_and_verify`, `_synthesize_and_verify`, and `M27RuntimeHarness`.

## 2. Raw same-run provenance

The Stage 25 raw pointer `docs/m27/research/m27_2027_agent_product_gate_repair_receipts.raw_compare2.json` was searched in the active Stage 25 workspace, the M27 common repository, and `/tmp`, and was not recovered. No raw evidence was fabricated or reverse-generated.

`docs/m27/research/m27_stage25_raw_compare_provenance_repair.json` preserves the missing-artifact warning and the committed aggregate/per-case evidence that Stage 26 already judged sufficient for canary authorization. This remains a provenance warning that must be carried into the activation receipt.

## 3. Telemetry identity hooks

Added `src/knowledge_engine/m27_canary_telemetry.py` with fail-closed candidate identity fields and a JSONL persistence hook. Required fields include route id, candidate id, candidate git SHA, optional immutable runtime identity/image digest, canary mode, request id, terminal kind, first-material latency, final latency, product-gate outcome, and stop-condition flags. The helper chooses no network or production datastore by itself.

## 4. Route-to-zero

Added `docs/m27/canary/M27_ROUTE_TO_ZERO_RUNBOOK.md`. The dry run identified the authoritative site path and exact production/test answer locations, captured pre-change checksums, and defines route-to-zero, M26-only verification, candidate cleanup, port 18080 verification, and Owner authorization. No Nginx file was modified or reloaded.

## 5. Production safety proof

Stage 27 observed:
- production 8080 health OK
- production build SHA `7d4b2358464654bf3de7d9561ec89de841d279bd`
- production entrypoint `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`
- test backend 8081 health OK
- port 18080 free
- no active M27 canary/eval container
- Nginx main SHA `48c6a4ec1e1fd28ccf968490f07e34a1d7f755793b2108a3ed8670b1ee2a0aa2`
- Nginx site SHA `1d1c4edfddca4da6c89a054a0ddf33179bbe3265e21666f2e8a49a1606045219`

No production datastore write path was introduced. No secret values are stored in Stage 27 artifacts.

## Validation

- `python3 -m compileall -q src scripts tests`: PASS
- `git diff --check`: PASS
- system `pytest`: unavailable
- system `ruff`: unavailable
- direct import smoke through the package was blocked by missing dependency `httpx` in the system Python environment; this is recorded as environment limitation, not a product test failure
- AST/source validation: PASS
- JSON validation: PASS
