# M27 Stage 8 Isolated Workspace Report

Date: 2026-10-03
Branch: `m27/stage8-isolated-workspace`
Base: `bbb29ed7`

## 1. Scope

Stage 8 establishes the isolated task workspace boundary for temporary M27 task state, sanitized artifacts, and checkpoint metadata.

It does not add:

```text
MCP exposure
Memory runtime
Skill execution
Skill-to-workspace integration
Production persistence
R2/Qdrant/sqlite mutation
Release promotion/rollback/finalize
Answer-path behavior changes
Public runtime behavior changes
```

Stage 7 was inspected read-only from its parallel worktree at commit `60ba735d`. No Stage 7 file was modified and Stage 8 does not import the Stage 7 skill contract.

## 2. Files changed

```text
src/knowledge_engine/m27_workspace_contracts.py
src/knowledge_engine/m27_workspace_store.py
tests/test_m27_workspace_contracts.py
tests/test_m27_workspace_store.py
docs/m27/research/stage8_isolated_workspace_report.md
```

No M26 core file, tool registry, read-only tool implementation, skill file, compose file, production env file, or deployment file was changed.

## 3. Workspace contract

Stage 8 adds:

```text
WorkspaceId
WorkspaceScope
WorkspaceArtifactKind
WorkspaceArtifactFormat
WorkspaceWritePolicy
WorkspaceArtifactRef
WorkspaceCheckpoint
WorkspaceManifest
WorkspaceStore
```

Workspace IDs are generated deterministically from:

```text
schema version + workspace scope + pre-sanitized opaque task token
```

using SHA-256 and are materialized only as:

```text
ws-<32 lowercase hex>
```

Raw free-form task text is not accepted as a workspace token because the token contract allows only a bounded opaque identifier alphabet.

## 4. Fixed Stage 8 write policy

The manifest carries a fixed policy that cannot be widened:

```text
isolated_task_workspace = true
production_write = false
r2_write = false
qdrant_write = false
production_sqlite_write = false
release_control = false
mcp_exposed = false
memory_runtime = false
skill_execution = false
answer_path_change = false
public_runtime_change = false
```

Constructing a policy with any forbidden authority enabled fails closed.

## 5. Allowed and blocked artifact kinds

Allowed:

```text
REPORT
EVAL_SUMMARY
CANDIDATE_PATCH
CHECKPOINT
HANDOFF
DIAGNOSTIC
```

Explicitly blocked:

```text
PRODUCTION_RELEASE
R2_OBJECT
QDRANT_COLLECTION
SQLITE_DB
SECRET
ENV_DUMP
RAW_EVIDENCE
RAW_ANSWER
RAW_QUERY
```

Unknown artifact kinds are also rejected rather than implicitly admitted.

## 6. Store surface

The isolated store exposes:

```text
create_workspace()
describe_workspace()
write_json_artifact()
read_json_artifact()
list_artifacts()
write_text_artifact()
read_text_artifact()
record_checkpoint()
list_checkpoints()
```

The root is dependency-injected as a `Path`. There is no hard-coded production path and no backend/network provider.

Artifact files are immutable once created. The manifest stores only artifact metadata:

```text
workspace id
scope
fixed write policy
artifact kind/format
workspace-relative artifact ref
SHA-256
size
artifact/checkpoint counts
```

Artifact payload bodies and checkpoint metadata are not copied into the manifest.

## 7. Path safety

Public artifact refs must be normalized workspace-relative paths.

Rejected:

```text
../ traversal
absolute paths
~/ expansion
backslash paths
drive-like paths
dot-relative paths
hidden/dot path components
unsafe path characters
symlink traversal
symlink targets
workspace directory symlinks
metadata directory symlinks
```

Every resolved target is checked to remain under the injected workspace root. Parent directories are created only after containment and symlink checks.

Writes use exclusive creation for user artifacts, making existing artifact refs immutable. Registered reads verify both size and SHA-256 against the manifest.

## 8. Privacy and payload boundary

JSON artifacts are recursively validated and reject explicit private/raw fields including:

```text
raw query / raw answer
evidence/source bodies
provider prompt
credentials/secrets/API keys/auth tokens
environment values
production object paths
raw Qdrant/R2/SQL/sqlite internals
```

Text artifacts reject explicit raw/private payload labels, private-key material, common secret token forms, raw storage/database URIs, absolute server filesystem paths, and sensitive environment assignments.

JSON payloads are bounded by nesting, collection-size, finite-number, key-shape, and text-size rules.

Important remaining limitation: no local syntactic sanitizer can prove that arbitrary natural-language prose is semantically non-sensitive. Stage 8 therefore remains a sanitized-input boundary, and future callers must pass only already-sanitized report/task content. The store adds structural fail-closed checks but is not a data-loss-prevention classifier.

## 9. Relationship to Stage 7

The separation is preserved:

```text
Stage 7 = descriptive procedure / plan
Stage 8 = isolated state / artifact boundary
```

Stage 8 has no import or execution dependency on:

```text
m27_skill_contracts
MCP
Memory runtime
Qdrant/R2/sqlite clients
production promotion code
```

No `execute`, `invoke`, `run_skill`, `promote`, `rollback`, or production backend write surface exists on `WorkspaceStore`.

## 10. Tests

Required compile gate:

```bash
python3 -m compileall -q src/knowledge_engine tests
```

Result:

```text
PASS
```

Focused Stage 8 gate:

```bash
PYTHONPATH=src /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest -q \
  tests/test_m27_workspace_contracts.py \
  tests/test_m27_workspace_store.py
```

Result:

```text
31 passed in 0.56s
```

Ruff:

```bash
/home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/ruff check \
  src/knowledge_engine/m27_workspace*.py \
  tests/test_m27_workspace*.py
```

Result:

```text
All checks passed!
```

Coverage includes:

```text
workspace id determinism/validation
path traversal rejection
absolute/home/backslash/dot path rejection
symlink escape rejection
artifact kind allow/block
JSON roundtrip
text roundtrip
immutable artifact refs
checkpoint append/list
metadata-only manifest
private/raw JSON field rejection
private/raw text marker rejection
fixed no-authority write policy
no Stage 7/MCP/Memory/production backend import dependency
no skill/release execution surface
```

## 11. Behavior impact

```text
M26 answer behavior: unchanged
M27 public runtime behavior: unchanged
Stage 6 bounded retrieval: unchanged
Stage 7 skill runtime: unchanged
Production deployment/runtime: untouched
```

Stage 8 is not wired into any canonical answer/runtime path in this sub-session.

## 12. Remaining risks

1. Sanitized prose is structurally screened but cannot be semantically proven non-sensitive without a separate policy/classification layer.
2. The filesystem store is designed for isolated single-task/single-writer use. Cross-process transaction/locking semantics are intentionally not introduced in Stage 8.
3. The injected root remains a trusted host-level configuration choice. Artifact refs themselves cannot escape it.

These are integration considerations, not blockers for the isolated Stage 8 boundary.

## 13. Production safety

No production container was restarted or modified.

No production R2 pointer, Qdrant alias/collection, production sqlite, release state, public route, docker compose, or env file was written.

No Stage 7 file was changed.

## Verdict

```text
M27_STAGE8_WORKSPACE: READY_FOR_MASTER_INTEGRATION
PRODUCTION_ENABLEMENT: NOT_APPLICABLE
```
