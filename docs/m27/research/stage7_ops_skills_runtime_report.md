# M27 Stage 7 Ops Skills Runtime Report

Date: 2026-10-03
Branch: `m27/stage7-ops-skills-runtime`
Base: `bbb29ed7`

## Scope

Stage 7 introduces an ops-only skill runtime boundary.

A Stage 7 skill answers:

```text
How should this class of operational task be performed?
```

It does not execute tools, grant authority, mutate state, write artifacts, expose MCP, create workspace state, or change the answer path.

## Files changed

```text
src/knowledge_engine/m27_skill_contracts.py
tests/test_m27_skill_contracts.py
docs/m27/research/stage7_ops_skills_runtime_report.md
```

## Implemented model

Stage 7 adds:

```text
SkillDescriptor
SkillStep
SkillPlan
SkillRegistry
```

The registry can:

```text
register
resolve
list
plan
```

The registry intentionally has no:

```text
run
execute
invoke
call
write
persist
```

surface.

## Included skills

Only these ops skills are registered:

```text
investigate-answer-failure
investigate-retrieval-failure
diagnose-latency
run-quality-gate
```

These skills produce descriptive plans and candidate follow-up/report guidance only.

## Deferred skills

These are explicitly deferred beyond Stage 7:

```text
answer-from-knowledge
deep-research
ingest-and-update-knowledge
promote-knowledge-release
```

They are not registered and cannot be registered through the Stage 7 default registry.

## Capability boundary

Stage 7 can reference only Stage 5 read-only native capabilities:

```text
knowledge.search
knowledge.expand
evidence.inspect
evidence.verify
runtime.get_trace
runtime.get_budget
runtime.get_health
```

Each referenced capability must remain:

```text
read_only = true
requires_authorization = true
supports_mutation = false
exposes_raw_infra = false
```

Stage 7 does not call these capabilities. It only references them in a descriptive plan.

## Authority boundary

Every Stage 7 plan reports:

```text
authority_status = NO_AUTHORITY_GRANTED
execution_status = DESCRIPTIVE_ONLY
```

Every step must be:

```text
report_only = true
grants_authority = false
supports_mutation = false
production_write = false
```

## Prohibited actions

Each plan declares these prohibited actions:

```text
invoke_tool
execute_skill
write_workspace
write_production
promote_release
rollback_release
mutate_r2
mutate_qdrant
mutate_sqlite
store_raw_query_or_answer
```

## Privacy boundary

Skill plans contain only sanitized names, step kinds, capability identifiers, and report/candidate output kinds.

They do not contain raw query, raw answer, full evidence body, full source body, provider prompt, credentials, secrets, environment values, or production object paths.

## Relationship to Stage 8

Stage 7 does not depend on Stage 8 workspace.

```text
Stage 7 = procedure / descriptive plan
Stage 8 = isolated state / artifact boundary
```

Stage 7 does not write workspace artifacts. Stage 8 must not execute Stage 7 skills.

## Tests

Focused Stage 7 gate:

```text
10 passed
Ruff: All checks passed
```

Combined Stage 1–7 safe gate:

```text
compileall: PASS
pytest: 202 passed, 1 warning
Ruff M27 files: PASS
Ruff patched M26 file with known pre-existing F841 ignored: PASS
```

The warning is the existing Starlette/httpx deprecation warning from FastAPI TestClient.

## Production safety

No production deployment, production restart, production pointer write, Qdrant alias write, production sqlite write, release promotion, rollback, MCP exposure, workspace state, or memory runtime was added.

## Verdict

```text
STAGE7_IMPLEMENTATION: READY_FOR_MASTER_INTEGRATION
PRODUCTION_ENABLEMENT: NOT_APPLICABLE
```

Stage 7 is ready for Master review/integration as an ops-only descriptor/planning layer.
