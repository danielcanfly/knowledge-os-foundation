# M27 Blocker Register

Status: **clean for Stage 1 adapter-only / decision-trace work** after Stage 0C/0D blocker burn-down. Not clean for behavior-changing agentic retrieval, Jev, MCP, Memory, Learning Plane, or Meta-Harness work.

## Stage 1 readiness summary

Verified:

```text
source equivalence: prod_py 382, missing 0, diff 0, extra 0
py_compile: pass
M27 isolated health: 200 OK
M27 container: healthy on 127.0.0.1:18080
production container: healthy on 127.0.0.1:8080
safe Stage 1 pytest gate: 49 passed, 1 warning
```

## Blockers

| ID | Category | Status | Resolution / boundary |
|---|---|---|---|
| B001 source mismatch | UNKNOWN_SOURCE | RESOLVED | M27 package source now matches production image source: 382 Python files, missing 0, diff 0, extra 0. |
| B002 production entrypoint missing | UNKNOWN_SOURCE | RESOLVED | `src/knowledge_engine/m26_console_api.py` exists and isolated compose runs `knowledge_engine.m26_console_api:app`. |
| B003 dirty worktree source-of-truth | DIRTY_WORKTREE | RESOLVED | Dirty worktree matched production image 382/382; M27 branch now has reconciled source. Do not use dirty worktree as dev base. |
| B004 generic fallback guard | PRODUCTION_RISK | RESOLVED | Guard exists in reconciled M27 source and is captured in invariant registry. |
| B005 contract ambiguity | CONTRACT_AMBIGUITY | RESOLVED_WITH_MITIGATION | Stage 1 must wrap existing M26 behavior via `LegacyM26*Adapter`; no parallel runtime. |
| B006 production isolation | PRODUCTION_RISK | RESOLVED | M27 has separate container, image, port, volumes and env; production remained healthy. |
| B007 normalized decision trace missing | MISSING_TRACE | CLEARED_FOR_STAGE1 | This is the first Stage 1 deliverable, not a blocker. Trace must be sanitized and default-off. |
| B008 pytest unavailable | TEST_ENV_GAP | RESOLVED | `.venv` exists in M27 workspace; pytest 8.4.2 available. |
| B009 QA/eval modules missing | EVAL_GAP | RESOLVED | QA inbox and quality modules are now in M27 branch. |
| B010 rollback/promotion modules missing | ROLLBACK_GAP | RESOLVED_WITH_BOUNDARY | Modules are present. Stage 1 must not expose promote/rollback as tools. |
| B011 external harness SDK risk | PRODUCTION_RISK | RESOLVED_WITH_MITIGATION | Existing M26 runtime is the Stage 1 harness. No external harness provider. |
| B012 Jev premature | PRODUCTION_RISK | DEFERRED_OUTSIDE_STAGE1 | Jev only after normalized M26 decision traces exist. |
| B013 no no-blocker handoff | EVAL_GAP | RESOLVED_FOR_STAGE1 | `05_no_blocker_handoff.md` created. |
| B014 Dockerfile entrypoint drift | PRODUCTION_RISK | RESOLVED_WITH_MITIGATION | Do not change Dockerfile yet. Isolated compose command override uses console app. |
| B015 isolated readiness config | PRODUCTION_RISK | RESOLVED | M27 health is 200 OK using dummy non-production HMAC and isolated quota DB. |
| B016 legacy semantic expectation drift | EVAL_GAP | DEFERRED_OUTSIDE_STAGE1 | Full legacy arbitrary semantic test file still has expectation drift. Do not loosen runtime. Revisit before Stage 2 retrieval behavior changes. |

## Stage 1 allowed scope

Allowed: interface extraction, legacy adapters, sanitized decision trace, default-off feature flag, new tests/docs.

Not allowed: current production changes, production restart, nginx/Cloudflare, production R2/Qdrant/SQLite writes, Jev, MCP, Memory, Agent loop, Learning Plane, Meta-Harness.
