# 63 Test Page Owner-Bypass Side-by-Side Report

## Final state

`M27_TEST_PAGE_OWNER_BYPASS_BLOCKED`

Workspace: `/home/ubuntu/LLM_Wiki-m27-test-page-owner-bypass-rerun`  
Branch: `m27/test-page-owner-bypass-side-by-side-rerun`  
Base HEAD: `4395de2a6d21707d0ced8958d7a22d853428a1dd`

## Diagnosis

Stage 18 comparison code sends the M26 baseline request with only `Content-Type: application/json`. The M26 test backend quota path accepts owner bypass only when the approved owner bypass header is present and its SHA-256 digest matches the configured digest. Therefore Stage 18 fell through to ordinary per-IP quota and returned `429 DAILY_IP_LIMIT_EXCEEDED`.

The test backend confirms only that an owner-bypass digest is configured. Inspection of the live test container, host shell environment, repository scripts, deployment workflow, and Git history found no approved server-side mechanism that exposes or injects the raw owner-bypass material to this comparison harness. The VM-side `.env` and container configuration contain the digest only. No raw bypass value was read, printed, logged, serialized, committed, or reconstructed.

Per the Stage 19 boundary, the session stopped rather than inventing a new secret path, copying bypass material into the harness, resetting quota, raising limits, or using production 8080.

## Owner-bypass safety booleans

- `owner_bypass_configured_on_m26_test_backend`: true
- `owner_bypass_safe_injector_available_to_harness`: false
- `owner_bypass_used_for_m26_baseline`: false
- `redaction_passed`: true
- `m26_429_avoided`: false
- `m26_preflight_executed`: false
- `bounded_20_case_comparison_executed`: false

## Why no preflight or 20-case rerun ran

The prompt authorizes the M26 preflight only through an existing approved non-disclosing owner-bypass injection path. None was found. Running a preflight without bypass would only consume the blocked public quota path again, while obtaining or moving raw secret material would violate the explicit secret-handling boundary. Therefore the legal stop is `M27_TEST_PAGE_OWNER_BYPASS_BLOCKED` before answer traffic.

## Side-by-side metrics

No new live M26-vs-M27 product comparison was run. Consequently there are no valid new Stage 19 success-rate, quality, TTFT, p50/p95, citation, safe-terminal, retrieval-hard, multilingual, or Browser Use comparison metrics. Historical Stage 18 metrics were not promoted as Stage 19 evidence.

## Browser Use warning

Unresolved in this stage because the bounded side-by-side rerun was legally blocked before answer traffic. The Stage 18 warning remains open and no claim of resolution is made.

## Production safety proof

Before Stage 19 mutation work:

- production `127.0.0.1:8080/v1/health`: `status=ok`
- production build SHA: `7d4b2358464654bf3de7d9561ec89de841d279bd`
- production entrypoint: `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`
- M26 test backend build SHA: `f746822503b7b27b2f5d4bb98ad406b15f558732`
- M26 test backend owner bypass configured: true
- Nginx checksum: `48c6a4ec1e1fd28ccf968490f07e34a1d7f755793b2108a3ed8670b1ee2a0aa2  /etc/nginx/nginx.conf`
- port `18080`: free

No production deploy, canary activation, release-pointer mutation, public-route mutation, live Nginx edit, production restart/rebuild, production datastore write, quota reset, rate-limit increase, admission/full523 rerun, Stage13/14, or Chunk002 occurred.

## Decision

`M27_TEST_PAGE_OWNER_BYPASS_BLOCKED`

Unblock condition: provide or restore an already-approved server-side owner-only injection mechanism that can attach the M26 bypass credential without exposing it to stdout/stderr, reports, receipts, source, shell history, M27 candidate, or production 8080. Stage 19 can then rerun its preflight and bounded 20-case comparison.

## Validation

- `python3 -m compileall -q src scripts tests`: PASS
- focused owner-bypass test via existing venv: PASS (`1 passed, 9 deselected`)
- receipts JSON parse: PASS
- `git diff --check`: PASS
- `ruff`: unavailable on host
- system Python `pytest`: unavailable; existing M27 venv pytest was used successfully

## Production safety proof after

- production health: OK
- production build SHA unchanged: `7d4b2358464654bf3de7d9561ec89de841d279bd`
- production entrypoint unchanged: `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`
- M26 test backend build unchanged: `f746822503b7b27b2f5d4bb98ad406b15f558732`
- Nginx checksum unchanged: `48c6a4ec1e1fd28ccf968490f07e34a1d7f755793b2108a3ed8670b1ee2a0aa2`
- Stage-19-owned M27/eval containers after cleanup: none
- port `18080`: free
