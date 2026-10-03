# M27 Stage 1B Sub-session Report: Decision Trace + Feature Flag

## 1. Summary of files changed

Created only new Stage 1B files:

- `src/knowledge_engine/m27_decision_trace.py`
- `src/knowledge_engine/m27_feature_flags.py`
- `tests/test_m27_decision_trace.py`
- `docs/m27/research/stage1_subsession_B_report.md`

No existing M26 runtime file was modified. In particular, this sub-session did not modify
`m26_public_api.py`, `m26_console_api.py`, `m26_aq_semantic_contract.py`, or any
production deployment/configuration file.

## 2. Exact behavior impact

**NONE.**

The new modules are not wired into the M26 answer path, retrieval path, verifier,
publication path, or API entrypoints.

With the feature flag effectively disabled, `emit_decision_trace_if_enabled(...)`
returns `False` before calling the supplied sink, so there is no trace side effect.

No provider call, retrieval round, answer mutation, routing decision, publication
decision, or security decision was added.

## 3. Feature flags added or used

Environment variable:

```text
M27_CONTEXT_RUNTIME_SHADOW_TRACE_ENABLED
```

Default effective value:

```text
false
```

Resolution rules:

- Missing environment variable => disabled.
- False/unrecognized value => disabled.
- Requested true outside an explicitly identified isolated M27 runtime => disabled.
- Requested true plus `isolated_runtime=True` => enabled.
- Raw environment values are reduced to a boolean and are not retained in the
  resolved feature-flag object.

`M27FeatureFlags.context_runtime_shadow_trace_enabled` is derived from both
`shadow_trace_requested` and `isolated_runtime`, so a direct request without the
isolated-runtime gate remains disabled.

## 4. Trace schema / dataclasses / protocols

Added immutable, slotted dataclasses:

- `DecisionTraceEvent`
- `GuardObservation`
- `M27FeatureFlags`

Added fixed `StrEnum` domains:

- `DecisionRoute`
- `DecisionReasonCode`
- `ComputeTier`
- `BudgetClass`
- `ProviderAttemptClass`
- `ContextSource`
- `StatusClass`
- `SafeAbstentionOutcome`
- `TraceGuard`
- `GuardOutcome`

`DecisionTraceEvent` contains only:

- canonical UUID trace id
- route enum
- reason code enum
- compute tier enum
- deadline budget class
- provider budget class
- provider attempt count and derived attempt class
- context-source enums
- evidence count
- citation count
- status class
- safe-abstention outcome
- fixed guard observations

No persistence protocol or runtime wiring was introduced in Stage 1B. The emission
API accepts an injected callable sink only when the effective feature flag is enabled.
The trace has no routing, security, publication, promotion, or rollback authority.

## 5. Trace privacy guarantees

The schema intentionally has no arbitrary `payload`, `metadata`, or free-form text
container.

It cannot directly represent:

- raw query
- raw answer
- full evidence text
- full source text
- secret
- API key
- token
- credential
- environment value
- private payload
- production write credential

Privacy-hardening details:

- `trace_id` must be a canonical lowercase UUID; free-form text is rejected.
- route/reason/compute/budget/context/status/abstention/guard fields use fixed enums.
- counts must be non-negative integers.
- duplicate context-source enums and duplicate guard observations are rejected.
- constructor tests prove forbidden sensitive kwargs are rejected.
- serialization has a fixed allowlisted shape.
- feature-flag parsing does not persist the raw environment value.

No raw-query hash or raw-answer hash was added. Stable hashes were intentionally
omitted in Stage 1B because they were not required for the minimum safe trace and can
create avoidable privacy/linkability risk if derived from low-entropy private text.

## 6. Tests run with exact command and output

### Baseline compile command

```bash
cd /home/ubuntu/LLM_Wiki-m27-stage1-b

python3 -m compileall -q \
  src/knowledge_engine/m27_decision_trace.py \
  src/knowledge_engine/m27_feature_flags.py \
  tests/test_m27_decision_trace.py
```

Result:

```text
PASS
```

### Shared-venv import-path discovery

The exact pytest command using the shared M27 venv without an explicit worktree
`PYTHONPATH` initially failed at collection because that venv is editable-installed
against `/home/ubuntu/LLM_Wiki-m27-context-runtime/src`, not this Stage 1B worktree.

Observed:

```text
ModuleNotFoundError: No module named 'knowledge_engine.m27_decision_trace'
```

Verified venv package root:

```text
/home/ubuntu/LLM_Wiki-m27-context-runtime/src/knowledge_engine/__init__.py
```

No venv or runtime installation was modified to work around this.

### Final Stage 1B pytest command

```bash
cd /home/ubuntu/LLM_Wiki-m27-stage1-b

PYTHONPATH=/home/ubuntu/LLM_Wiki-m27-stage1-b/src \
  /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest -q \
  tests/test_m27_decision_trace.py
```

Result:

```text
......................                                                   [100%]
22 passed in 0.22s
```

The tests explicitly prove:

- feature flag default is false
- requested true cannot become effective outside explicit isolated M27 runtime
- raw query is not represented and cannot be placed in the UUID trace id
- raw answer field is rejected/not represented
- full evidence text field is rejected/not represented
- full source text field is rejected/not represented
- secret/API-key/token/credential/env/private-payload fields are rejected/not represented
- fixed sanitized enums/counts/ids serialize as expected
- trace disabled is inert and does not call the sink
- trace enabled emits only the sanitized event

### Ruff

```bash
/home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/ruff check \
  src/knowledge_engine/m27_decision_trace.py \
  src/knowledge_engine/m27_feature_flags.py \
  tests/test_m27_decision_trace.py
```

Result:

```text
All checks passed!
```

## 7. Blockers encountered and status

No functional Stage 1B blocker remains.

Resolved environment issue:

- The shared venv's editable package path points to the master M27 workspace.
- Final tests therefore use an explicit Stage 1B `PYTHONPATH`.
- No package installation, shared venv mutation, Docker build, or runtime restart was
  performed.

## 8. Remaining risks

- Stage 1B intentionally has no runtime wiring. Master integration must decide the
  inert insertion point after Stage 1A contracts/adapters are merged.
- Integration must use the feature-flag resolver and preserve the explicit
  `isolated_runtime` gate.
- New legacy routing/reason categories may require enum extension during later
  adapter/replay work. They must remain fixed sanitized codes, not free-form payloads.
- If a future sink persists data, the sink/store must preserve the same fixed-schema
  privacy boundary. Stage 1B does not add a persistent store.
- The isolated M27 container was not started or restarted by this sub-session.

## 9. Suggested next step

Master should inspect this report and the four Stage 1B files, integrate alongside
Stage 1A, and run the full Stage 1 integration gate from the canonical M27 workspace.

Do not start Stage 2 until Stage 1A + Stage 1B are merged and the master-owned safe
gate passes.

## 10. Confirmation production was untouched

**Production was untouched.**

This sub-session did not:

- restart or modify `llm_wiki-knowledge-engine-1`
- modify a production container or image
- change nginx / Cloudflare / public routing
- write production R2 pointers
- write production Qdrant aliases/collections
- write production SQLite
- use production write credentials
- run Docker build
- start Stage 2 or any deferred M27 capability

A read-only `docker ps` check at the end showed current production still healthy:

```text
llm_wiki-knowledge-engine-1|knowledge-engine:f7468225-generic-fallback-guard-20261003T061416Z|Up 3 hours (healthy)|127.0.0.1:8080->8080/tcp
```
