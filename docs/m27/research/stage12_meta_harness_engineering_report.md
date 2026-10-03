# M27 Stage 12 Meta-Harness Engineering Report

## Status

READY_FOR_MASTER_INTEGRATION

Stage 12 implements an isolated, candidate-only Meta-Harness Engineering lab. It can draft
candidate harness plans, candidate patch intent metadata, candidate offline evaluation plans,
candidate validation reports, promotion proposals, rollback plans, and risk matrices. It
does not apply any candidate to runtime or production.

## Base and workspace

- Master workspace: `/home/ubuntu/LLM_Wiki-m27-context-runtime`
- Master branch at start: `m27/context-native-runtime-spec`
- Master base at start: `b245a808`
- Stage 12 worktree: `/home/ubuntu/LLM_Wiki-m27-stage12-meta-harness`
- Stage 12 branch: `m27/stage12-meta-harness-engineering`
- Stage 12 base: `b245a808`

The Stage 12 worktree was created from the exact requested base after verifying that Master
was clean.

## Files added

- `src/knowledge_engine/m27_meta_harness_contracts.py`
- `src/knowledge_engine/m27_meta_harness_runtime.py`
- `tests/test_m27_meta_harness_contracts.py`
- `tests/test_m27_meta_harness_runtime.py`
- `docs/m27/research/stage12_meta_harness_engineering_report.md`

No Stage 1 through Stage 11 source file was modified.

## Candidate authority boundary

The only Stage 12 authority enum value is:

`MetaHarnessAuthority.CANDIDATE_ONLY`

Every `MetaHarnessCandidate` is structurally fixed to:

- `candidate_only = True`
- `requires_human_review = True`
- `requires_offline_gate = True`
- `auto_apply = False`
- `auto_merge = False`
- `auto_promote = False`
- `production_write = False`

The contracts reject any attempt to widen or weaken these values.

No authority enum or runtime method exists for automatic patch application, branch merge,
release promotion, production mutation, runtime patching, or source-of-truth promotion.

## Candidate kinds

Stage 12 supports the required candidate artifact classes:

- `HARNESS_PLAN`
- `TEST_PLAN`
- `PATCH_INTENT`
- `EVAL_PLAN`
- `VALIDATION_REPORT`
- `PROMOTION_PROPOSAL`
- `ROLLBACK_PLAN`
- `RISK_MATRIX`

These values represent reviewable metadata artifacts only.

## Contract model

The Stage 12 contract layer contains:

- `MetaHarnessInput`
- `MetaHarnessPlan`
- `MetaHarnessCandidate`
- `MetaHarnessCandidateKind`
- `MetaHarnessAuthority`
- `MetaHarnessRiskClass`
- `MetaHarnessGateRequirement`
- `MetaHarnessPatchIntent`
- `MetaHarnessEvalPlan`
- `MetaHarnessReport`
- `MetaHarnessCandidateStatus`

Candidate IDs are deterministic and content-bound:

`mhc-<32 lowercase hex>`

The identity binds candidate kind, sanitized source references, failure class, reason codes,
artifact IDs, bounded summary, expected improvement class, risk class, candidate file
labels, test names, and required gate names. Lifecycle status is intentionally excluded so
review transitions do not alter candidate identity.

## Sanitized input boundary

Stage 12 accepts only bounded, sanitized metadata shapes:

- opaque source references
- safe failure class codes
- reason codes
- opaque artifact IDs
- summary counts
- bounded candidate summaries
- repository-relative candidate file labels
- test names
- offline gate names
- risk classes
- expected improvement classes

The contract rejects raw/private/backend markers including the required classes for raw
queries, raw answers, evidence/source bodies, provider prompts, secrets and credentials,
environment material, backend names and URIs, production paths, release pointers,
traversal paths, and private payload labels.

Candidate file labels are metadata only. They must be sanitized repository-relative labels.
They are never opened or written by Stage 12.

## Patch intent boundary

`MetaHarnessPatchIntent` stores only:

- candidate file labels
- a bounded sanitized description

It has no diff field, patch bytes, source replacement content, repository writer, or apply
operation. Its serialized metadata explicitly reports `patch_material_present = False`.

## Offline eval boundary

`MetaHarnessEvalPlan` stores only:

- test names
- `MetaHarnessGateRequirement` metadata
- a bounded description

Every gate requirement is structurally fixed to required, offline-only, and human-reviewed.
The eval plan has no process execution or provider authority.

## Runtime and store

`MetaHarnessCandidateStore` is pure in-memory state. It has no filesystem root, path,
workspace dependency, persistence adapter, provider, network, database, or production
backend.

`MetaHarnessRuntime` exposes only the requested review-oriented operations:

- `draft_harness_plan()`
- `draft_patch_intent()`
- `draft_eval_plan()`
- `record_candidate_report()`
- `list_candidates()`
- `inspect_candidate()`
- `mark_candidate_rejected()`
- `mark_candidate_superseded()`
- `mark_candidate_ready_for_review()`
- `render_meta_harness_report()`

There is no code execution path in this runtime.

## Candidate lifecycle

Allowed active states:

`PROPOSED -> READY_FOR_REVIEW`

Terminal inactive states:

- `REJECTED`
- `SUPERSEDED`

A proposed or ready-for-review candidate may be rejected or superseded. A rejected or
superseded candidate cannot return to an active state. Repeating
`READY_FOR_REVIEW -> READY_FOR_REVIEW` is idempotent.

Candidate lists are deterministically sorted by candidate ID.

## Report boundary

`render_meta_harness_report()` emits sanitized candidate metadata, safe source/artifact
identifiers, reason codes, candidate file labels, test names, gate names, counts, risk class,
status, and fixed governance flags.

It does not embed raw query text, raw answer text, evidence/source bodies, provider prompts,
credentials, environment values, production backend internals, patch material, or private
payload bodies.

## Explicitly absent authority APIs

The Stage 12 runtime and store expose none of the following prohibited methods:

- `apply_patch`
- `auto_apply_patch`
- `merge_branch`
- `auto_merge`
- `promote_release`
- `auto_promote`
- `write_runtime_config`
- `patch_code`
- `write_to_qdrant`
- `write_to_r2`
- `write_to_production_sqlite`
- `execute_skill`
- `invoke_mcp`
- `write_workspace`
- `start_agent_loop`
- `apply_learning_proposal`

## Cross-stage isolation

Static tests and final scope audit confirm that Stage 12 imports none of:

- Stage 7 skill runtime
- Stage 8 workspace contracts/store
- Stage 9 MCP contracts/exposure
- Stage 10 memory contracts/runtime
- Stage 11 learning contracts/runtime

Existing M27 source modules do not import Stage 12, so Stage 12 is not wired into the answer
path or any earlier execution path.

Stage 9 MCP source has no Meta-Harness exposure.

Stage 12 also has no filesystem/process/network imports and no provider call surface.

## Verification

### Focused compile

Command:

`python3 -m compileall -q src/knowledge_engine tests`

Result: PASS

### Focused Stage 12 pytest

Files:

- `tests/test_m27_meta_harness_contracts.py`
- `tests/test_m27_meta_harness_runtime.py`

Result:

`90 passed in 0.69s`

The focused suite covers:

- sanitized input validation
- deterministic safe candidate IDs
- fixed candidate-only authority
- blocked auto-apply, auto-merge, auto-promote, and production-write flags
- raw/private/backend payload rejection
- candidate lifecycle and terminal-state enforcement
- deterministic candidate listing
- report sanitization
- absence of prohibited authority methods
- absence of Stage 7 through Stage 11 integration imports
- absence of MCP exposure
- absence of filesystem/process integration

### Focused Ruff

Command scope:

- `src/knowledge_engine/m27_meta_harness*.py`
- `tests/test_m27_meta_harness*.py`

Result: PASS

### Safe regression pytest

The exact package-specified M26 and M27 regression set, including Stage 12 tests, was run.

Result:

`513 passed, 1 warning in 13.49s`

The warning is an existing Starlette/FastAPI test-client deprecation warning from the
environment and is unrelated to Stage 12.

### Safe regression Ruff

Command scope:

- `src/knowledge_engine/m27_*.py`
- `tests/test_m27_*.py`

Result: PASS

### Existing M26 semantic-contract Ruff

Command:

`ruff check src/knowledge_engine/m26_aq_semantic_contract.py --ignore F841`

Result: PASS

## Gate finding repaired during construction

The first focused run correctly detected two Stage 12-local implementation defects:

1. regex escaping introduced during encoded SSH transfer prevented several required
   backend/environment markers from being rejected;
2. an injected empty in-memory store was treated as false because it implements
   `__len__`, causing the runtime to replace it with a new store.

Both defects were fixed within Stage 12 only. The sanitizer tests were not weakened. The
second and final focused run passed all 90 tests, followed by the full safe regression pass.

## Production and runtime impact

- production touched: NO
- M26 answer path touched: NO
- M27 answer path changed: NO
- runtime behavior changed: NO
- retrieval policy changed: NO
- compute policy changed: NO
- routing policy changed: NO
- runtime config changed: NO
- code patch application added: NO
- branch auto-merge added: NO
- release auto-promotion added: NO
- R2 write added: NO
- Qdrant write added: NO
- production sqlite write added: NO
- provider calls added: NO
- autonomous agent loop added: NO
- Stage 7 skill execution added: NO
- Stage 8 workspace dependency added: NO
- Stage 9 MCP exposure added: NO
- Stage 10 memory truth promotion added: NO
- Stage 11 proposal auto-apply added: NO
- full523 run: NO
- Docker build/restart: NO

## Remaining risks

Stage 12 intentionally does not prove that a candidate patch is correct or safe to apply.
It only creates sanitized candidate metadata and offline review plans. Actual patch material,
test execution, integration, merge, release promotion, and rollback execution remain outside
Stage 12 authority and require a later explicitly governed human/master workflow.

The candidate store is intentionally in-memory and non-durable. This avoids premature
coupling to Stage 8 workspace or production persistence. Durability, if ever required,
needs a separately reviewed boundary.

## Recommendation

READY_FOR_MASTER_INTEGRATION
