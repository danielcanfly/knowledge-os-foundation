# M27 Stage 11 Autonomous Agent Learning / Proposal Plane Report

Date: 2026-10-03
Branch: `m27/stage11-autonomous-agent-learning`
Base: `ee36444a`

## 1. Scope

Stage 11 implements a candidate-only autonomous learning proposal plane.

The implemented flow is:

```text
already-sanitized observations
-> LearningSignal
-> deterministic LearningProposal
-> proposal lifecycle governance
-> report-only proposal metadata
```

Stage 11 does **not** apply, promote, activate, execute, publish, persist to production, invoke tools/providers, write workspace state, expose MCP tools, promote memory to truth, or start Stage 12 Meta-Harness work.

The governing rule is:

```text
Learning may propose.
Learning may not apply.
```

## 2. Files changed

Created only:

```text
src/knowledge_engine/m27_learning_contracts.py
src/knowledge_engine/m27_learning_runtime.py
tests/test_m27_learning_contracts.py
tests/test_m27_learning_runtime.py
docs/m27/research/stage11_autonomous_agent_learning_report.md
```

No Stage 1-10 shared runtime file was modified.

## 3. Learning contract

Stage 11 adds:

```text
LearningSignal
LearningSignalKind
LearningSignalSource
LearningEvidenceBinding
LearningProposal
LearningProposalKind
LearningProposalStatus
LearningAuthority
LearningRiskClass
LearningPolicyArea
LearningDecision
```

The only authority value is:

```text
LearningAuthority.PROPOSAL_ONLY
```

The following authority concepts do not exist in the enum:

```text
AUTO_APPLY
AUTO_PROMOTE
AUTHORITATIVE_POLICY
PRODUCTION_POLICY
SOURCE_OF_TRUTH
```

## 4. Supported proposal kinds

Stage 11 supports exactly:

```text
SKILL_POLICY_CANDIDATE
RETRIEVAL_POLICY_CANDIDATE
COMPUTE_POLICY_CANDIDATE
ROUTING_POLICY_CANDIDATE
MEMORY_POLICY_CANDIDATE
EVAL_GATE_CANDIDATE
GUARDRAIL_HARDENING_CANDIDATE
```

Each proposal kind maps to a fixed policy area. A caller cannot construct a retrieval proposal and relabel it as compute, memory, or another policy area.

## 5. Proposal-only governance

Every proposal structurally requires:

```text
proposal_only = true
requires_human_review = true
requires_offline_gate = true
auto_apply = false
production_write = false
authority = PROPOSAL_ONLY
```

Any attempted widening or weakening of those values fails validation.

There is no runtime API for policy activation, code patching, runtime configuration changes, release promotion, provider invocation, production persistence, skill execution, workspace writes, MCP invocation, autonomous loops, or Meta-Harness execution.

## 6. Signal model and deterministic identity

A `LearningSignal` contains only bounded sanitized metadata:

```text
signal kind
signal source
opaque source reference
policy area
classification code
non-negative count
reason codes
opaque artifact IDs
```

It contains no arbitrary payload/body field.

Signal identity is deterministic:

```text
lsig-<32 lowercase hex>
```

The digest binds the schema version and all canonical sanitized signal fields.

Stage 11 intentionally does not retain original runtime/evidence/memory payload objects. Upstream sanitized observations must be reduced into `LearningSignal` metadata before entering the proposal runtime. This keeps Stage 11 disconnected from Stage 7/8/9/10 execution paths and prevents accidental retention of raw bodies.

## 7. Proposal identity and evidence binding

Proposal identity is deterministic:

```text
learn-<32 lowercase hex>
```

The proposal ID binds:

```text
schema version
proposal kind
fixed policy area
observed issue class
sorted unique signal IDs
candidate change summary hash
expected benefit class
risk class
required offline gate
```

Proposal lifecycle status is deliberately excluded from proposal identity, so governance status changes do not create a new semantic proposal.

A proposal requires at least one previously observed signal. Unknown signal IDs fail closed.

## 8. Proposal lifecycle

Implemented lifecycle:

```text
PROPOSED
  -> READY_FOR_REVIEW
  -> REJECTED

PROPOSED
  -> REJECTED

PROPOSED
  -> SUPERSEDED

READY_FOR_REVIEW
  -> SUPERSEDED
```

`REJECTED` and `SUPERSEDED` are terminal and inactive.

A rejected or superseded proposal cannot return to `READY_FOR_REVIEW`.

## 9. Proposal store

`LearningProposalStore` is pure in-memory only.

It has:

```text
register
inspect
list
```

plus a private lifecycle status replacement helper used only by `LearningRuntime`.

It has no:

```text
filesystem root
WorkspaceStore dependency
MCP dependency
Skill runtime dependency
Memory runtime dependency
provider dependency
network backend
production backend
R2/Qdrant/sqlite backend
```

No filesystem persistence was added in Stage 11.

## 10. Runtime surface

`LearningRuntime` exposes:

```text
observe_signal()
propose_from_signals()
list_proposals()
inspect_proposal()
mark_proposal_rejected()
mark_proposal_superseded()
mark_proposal_ready_for_review()
render_proposal_report()
```

It intentionally does not expose:

```text
apply_proposal
auto_apply
promote_proposal
activate_policy
write_runtime_config
patch_code
write_to_qdrant
write_to_r2
write_to_production_sqlite
execute_skill
invoke_mcp
write_workspace
start_agent_loop
run_meta_harness
```

Tests assert these names do not exist on either the runtime or proposal store.

## 11. Sanitization boundary

Stage 11 accepts bounded codes, counts, safe IDs, opaque artifact IDs, and bounded candidate summaries.

The sanitizer rejects raw/private/backend markers including:

```text
raw_query
raw_answer
full_evidence_body
full_source_body
provider_prompt
secret
credential
api_key
auth_token
env
environment
qdrant
r2://
sqlite
postgres
mysql
s3://
/home/ubuntu/
../
production_path
release_pointer
```

The proposal report embeds only proposal metadata and supporting signal IDs. It never embeds source signal payload metadata such as source references, reason-code bodies, or artifact details.

Important limitation: this remains a structural sanitizer, not semantic DLP. Callers must supply already-sanitized summaries and opaque IDs.

## 12. Stage 7 / 8 / 9 / 10 isolation

Repository/import negative controls prove that Stage 11 does not import:

```text
m27_skill*
m27_workspace*
m27_mcp*
m27_memory*
```

Existing Stage 1-10 modules also do not import the new learning modules.

Therefore Stage 11 is not wired into:

```text
Stage 7 skill execution
Stage 8 workspace storage
Stage 9 MCP exposure
Stage 10 memory truth/promotion
M27 answer path
M26 answer path
```

## 13. Focused Stage 11 gate

Compile:

```bash
python3 -m compileall -q src/knowledge_engine tests
```

Result:

```text
PASS
```

Focused pytest:

```bash
PYTHONPATH=src /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest -q   tests/test_m27_learning_contracts.py   tests/test_m27_learning_runtime.py
```

Result:

```text
88 passed in 0.67s
```

Focused Ruff:

```bash
/home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/ruff check   src/knowledge_engine/m27_learning*.py   tests/test_m27_learning*.py
```

Result:

```text
All checks passed!
```

Construction note: the first focused run exposed one test assumption about hash sort order. The test was corrected to reverse the canonical sorted tuple explicitly. No production/runtime code behavior change was required. The final focused gate is fully green.

## 14. Safe regression gate

The required safe regression population was run:

```text
5 M26 safe baseline files
Stage 1-11 specified M27 test files
```

Result:

```text
423 passed, 1 warning in 12.32s
```

The one warning is the existing FastAPI/Starlette TestClient deprecation warning already present in earlier stages.

M27 Ruff:

```bash
/home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/ruff check   src/knowledge_engine/m27_*.py   tests/test_m27_*.py
```

Result:

```text
All checks passed!
```

Known M26 lint gate:

```bash
/home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/ruff check   src/knowledge_engine/m26_aq_semantic_contract.py   --ignore F841
```

Result:

```text
All checks passed!
```

No full523, Docker build, container restart, external provider call, or production invocation was run.

## 15. Behavior impact

```text
M26 answer behavior change: NONE
M27 answer path change: NONE
retrieval policy change: NONE
compute policy change: NONE
routing policy change: NONE
memory truth promotion: NONE
skill execution added: NONE
workspace dependency added: NONE
MCP exposure added: NONE
provider calls added: NONE
production mutation authority added: NONE
Stage 12 Meta-Harness started: NO
```

## 16. Remaining risks / deliberate deferrals

1. Sanitization is syntactic/structural, not semantic DLP.
2. Stage 11 has no live ingestion wiring from trace/eval stores. This is deliberate: callers must first reduce allowed sanitized observations into `LearningSignal` metadata.
3. The proposal store is process-local in-memory only. Persistence is intentionally deferred to avoid coupling Stage 11 to Stage 8 or production storage.
4. Stage 11 does not run offline evals itself. It only records the required gate name; actual evaluation remains an external deterministic/human-governed step.
5. Stage 11 does not generate patches. Patch/harness candidate generation belongs to Stage 12 and was not started.

These are deliberate scope boundaries, not blockers for the Stage 11 proposal plane.

## 17. Production safety

```text
production touched: NO
production restarted: NO
production routes changed: NO
production credentials used: NO
production R2/Qdrant/sqlite writes: NO
M26 answer path touched: NO
M27 answer path touched: NO
runtime behavior changed: NO
policy auto-apply added: NO
release promote/rollback authority added: NO
Stage 7 skill execution added: NO
Stage 8 workspace dependency added: NO
Stage 9 MCP exposure added: NO
Stage 10 memory truth promotion added: NO
Stage 12 Meta-Harness started: NO
```

## Verdict

```text
M27_STAGE11_AUTONOMOUS_AGENT_LEARNING: READY_FOR_MASTER_INTEGRATION
PRODUCTION_ENABLEMENT: NOT_APPLICABLE
```
