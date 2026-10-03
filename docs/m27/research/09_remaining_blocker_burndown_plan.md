# M27 Remaining Blocker Burn-down Plan

Status: **no open blockers for Stage 1 adapter-only / decision-trace work**.

## Cleared for Stage 1

- Source mismatch cleared.
- Console entrypoint restored.
- Production-only admin / QA / ingestion / promotion / rollback modules restored.
- Generic fallback guard present.
- M27 isolated image builds.
- M27 isolated container healthy on `127.0.0.1:18080`.
- Production container still healthy on `127.0.0.1:8080`.
- `.venv` test runner exists.
- Safe Stage 1 gate passes: `49 passed, 1 warning`.

## Safe Stage 1 gate

```bash
cd /home/ubuntu/LLM_Wiki-m27-context-runtime
.venv/bin/python -m pytest -q \
  tests/test_m26_canonical_runtime_reachability.py \
  tests/test_m26_deadline_aware_semantic_routing.py \
  tests/test_m26_public_api.py \
  tests/test_m26_production_answer_bundle.py \
  tests/test_m26_aq_surface_guard.py
```

Expected result:

```text
49 passed, 1 warning
```

## Deferred outside Stage 1

| Area | Status | Boundary |
|---|---|---|
| Full legacy arbitrary semantic expectation suite | Deferred | Remaining failures mostly expect cited-answer repair where reconciled production behavior safe-abstains. Do not loosen runtime. Revisit before Stage 2. |
| Jev / FastDecision | Deferred | Only after M26 normalized decision traces exist. |
| MCP exposure | Deferred | Only after native ToolProvider boundaries. |
| Memory / Workspace writes | Deferred | No durable memory writes in Stage 1. |
| Autonomous Learning / Meta-Harness | Deferred | Candidate-only research later, never production self-modification. |

## Next allowed work

Stage 1 may begin:

1. Add contract definitions.
2. Add `LegacyM26*Adapter` wrappers.
3. Add default-off feature flag.
4. Add sanitized decision trace in M27 isolated runtime only.
5. Re-run safe Stage 1 gate.
