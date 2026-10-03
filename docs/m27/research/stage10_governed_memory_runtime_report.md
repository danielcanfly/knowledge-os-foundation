# M27 Stage 10 Governed Memory Runtime Report

Date: 2026-10-03
Branch: `m27/stage10-governed-memory`
Base: `f2683a96`

## 1. Scope

Stage 10 establishes an isolated, default-off, candidate-only memory runtime for:

```text
EPISODIC
PROJECT
```

It intentionally does not implement semantic user memory in this stage, because the Master handoff defines Stage 10 as candidate-only episodic/project memory and requires memory never to override cited knowledge.

Stage 10 does not add:

```text
answer-path memory injection
Context Compiler memory wiring
citation/evidence authority
knowledge promotion
semantic user/profile memory
MCP memory tools
Workspace-to-memory integration
Skill-to-memory integration
tool execution
network services
production persistence
R2/Qdrant/production-sqlite mutation
release promotion/rollback/finalize
M26 behavior changes
```

## 2. Files changed

Created:

```text
src/knowledge_engine/m27_memory_contracts.py
src/knowledge_engine/m27_memory_runtime.py
tests/test_m27_memory_contracts.py
tests/test_m27_memory_runtime.py
docs/m27/research/stage10_governed_memory_runtime_report.md
```

No existing M26 or M27 runtime module was modified.

## 3. Stage 10 memory model

The contract adds:

```text
MemoryActivation
MemoryGovernancePolicy
MemoryClass
MemoryOriginKind
MemoryCandidateId
MemoryProvenance
MemoryCandidate
MemoryReviewDecision
MemoryReviewReceipt
```

The runtime adds:

```text
GovernedMemoryRuntime
```

with candidate/review operations only.

The conceptual boundary is:

```text
Workspace = temporary task state
Memory = reusable candidate experience/project state
Knowledge = durable verified source-backed truth
```

Stage 10 preserves that boundary structurally rather than relying on caller convention.

## 4. Exact admitted memory classes

Admitted:

```text
EPISODIC
PROJECT
```

Explicitly forbidden classes include:

```text
SEMANTIC_USER
USER_PROFILE
PERSONAL_PROFILE
KNOWLEDGE
PRODUCTION_KNOWLEDGE
EVIDENCE
CITATION
```

Unknown memory classes also fail closed.

This keeps the implementation aligned with the Stage 10 handoff instead of prematurely building long-lived user-profile memory.

## 5. Default-off isolated activation

Default activation:

```text
enabled = false
isolated_runtime = false
```

Enabled memory is valid only when:

```text
enabled = true
isolated_runtime = true
```

The default-off constructor does not create the backing store on disk.

No environment flag is added or changed in this sub-session.

## 6. Fixed governance policy

Every Stage 10 candidate carries the same fixed policy:

```text
candidate_only = true
candidate_store_write = true
episodic_allowed = true
project_allowed = true

semantic_user_memory_allowed = false
knowledge_authority = false
citation_eligible = false
answer_context_enabled = false
can_override_cited_knowledge = false
can_promote_to_knowledge = false

production_write = false
r2_write = false
qdrant_write = false
production_sqlite_write = false
release_control = false
mcp_exposed = false
workspace_read = false
skill_execution = false
network_access = false
```

Constructing a widened or weakened policy fails closed.

In particular, a retained memory candidate is still not evidence, not a citation source, not production knowledge, and not an answer-context authority.

## 7. Candidate identity and provenance

Candidate IDs are deterministic:

```text
mem-<32 lowercase hex>
```

The digest binds:

```text
schema version
memory class
opaque scope token
origin kind
opaque origin reference
optional source SHA-256
summary SHA-256
sorted tags
```

Free-form task/project text is not accepted as a scope token or origin reference.

Provenance is descriptive only. It does not upgrade trust.

## 8. Candidate payload boundary

Stage 10 accepts a bounded sanitized summary plus opaque metadata.

The summary validator rejects explicit forms of:

```text
raw query / raw answer
full evidence/source body
provider prompt
credentials/secrets/API keys/tokens
private-key material
sensitive environment assignments
raw R2/Qdrant/sqlite/file URIs
absolute server filesystem paths
```

Important limitation:

A syntactic sanitizer cannot prove arbitrary prose contains no sensitive information. Therefore Stage 10 remains a sanitized-input boundary, not a semantic DLP or privacy classifier.

Semantic user/profile memory remains forbidden in this stage.

## 9. Persistence model

The runtime uses an injected filesystem root only.

Layout:

```text
<root>/
  candidates/
    mem-....json
  reviews/
    mem-..../
      000001.json
      000002.json
      ...
```

Candidate records and review receipts are append-only/immutable.

Records are stored as canonical JSON envelopes with SHA-256 checksums.

Candidate reconstruction also verifies the deterministic candidate ID against canonical content. Therefore content tampering is detected even if an attacker recomputes only the envelope checksum but does not also replace the governed identity/path coherently.

The injected root is trusted host configuration. Stage 10 is not designed to defend against a fully malicious host administrator.

## 10. Review model

Review decisions are limited to:

```text
RETAIN_CANDIDATE
REJECT_CANDIDATE
```

Review receipts are immutable and monotonically sequenced.

A later rejection supersedes an earlier retain decision for the runtime's retained-candidate listing.

Even after `RETAIN_CANDIDATE`:

```text
knowledge_authority = false
citation_eligible = false
answer_context_enabled = false
can_promote_to_knowledge = false
```

No "approve as truth" or "promote to knowledge" state exists.

## 11. Runtime surface

The runtime exposes:

```text
propose_candidate()
read_candidate()
list_candidates()
record_review()
list_reviews()
latest_review()
list_retained_candidates()
```

It intentionally exposes no method for:

```text
promote
promote_to_knowledge
publish
to_evidence
bind_citation
compile_context
inject_context
execute
invoke
run_skill
start_server
write_r2
write_qdrant
write_sqlite
release
rollback
```

## 12. Dependency isolation

The Stage 10 modules have no import dependency on:

```text
Stage 8 workspace modules
Stage 9 MCP modules
Stage 7 skill modules
Context/Evidence runtime modules
Qdrant
R2
sqlite
production promotion code
```

A repository-level negative test also proves that no pre-existing M27 module imports the new Stage 10 memory modules.

Therefore Stage 10 is not wired into the answer path or any existing execution path.

## 13. Focused Stage 10 gate

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
PYTHONPATH=src /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest -q   tests/test_m27_memory_contracts.py   tests/test_m27_memory_runtime.py
```

Result:

```text
57 passed in 0.72s
```

Focused Ruff:

```bash
/home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/ruff check   src/knowledge_engine/m27_memory*.py   tests/test_m27_memory*.py
```

Result:

```text
All checks passed!
```

## 14. Negative controls covered

Focused tests explicitly prove:

```text
default-off runtime performs no store creation
enabled memory requires isolated runtime
semantic user/profile memory is rejected
knowledge/evidence/citation memory classes are rejected
governance authority cannot be widened
candidate IDs cannot be forged
raw/private/infra payload markers are rejected
candidate records are immutable/idempotent
candidate and review symlink substitution is rejected
checksum tamper is rejected
canonical-ID/content tamper is rejected
authority-field tamper is rejected
review sequence gaps fail closed
retained candidates remain non-authoritative
no promotion/evidence/context/execution surface exists
no Workspace/MCP/Skill/backend import dependency exists
no existing M27 module imports Stage 10 memory
```

## 15. Safe regression gate

Population:

```text
5 M26 safe baseline test files
all Stage 1-10 M27 test files
```

Command:

```bash
env -u M27_BOUNDED_AGENTIC_RETRIEVAL_ENABLED -u M27_ISOLATED_RUNTIME   PYTHONPATH=src   /home/ubuntu/LLM_Wiki-m27-context-runtime/.venv/bin/python -m pytest -q   tests/test_m26_canonical_runtime_reachability.py   tests/test_m26_deadline_aware_semantic_routing.py   tests/test_m26_public_api.py   tests/test_m26_production_answer_bundle.py   tests/test_m26_aq_surface_guard.py   tests/test_m27_*.py
```

Result:

```text
335 passed, 1 warning in 12.95s
```

The warning is the existing FastAPI/Starlette TestClient deprecation warning.

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

No full523, Docker build, container restart, production invocation, or external provider call was run.

## 16. Behavior impact

```text
M26 answer behavior change: NONE
M27 answer path change: NONE
retrieval behavior change: NONE
verification behavior change: NONE
context compiler change: NONE
provider calls added: NONE
tool execution added: NONE
skill execution added: NONE
workspace integration added: NONE
MCP memory exposure added: NONE
network listener/server added: NONE
production mutation authority added: NONE
```

## 17. Remaining risks / deliberate deferrals

1. Candidate summary sanitization is structural, not semantic DLP.
2. Review authorization is not implemented here; Stage 10 records opaque reviewer tokens only. Any future live caller must apply its own authenticated authorization gate.
3. The filesystem runtime assumes a trusted injected host root and isolated single-writer usage. Cross-process transaction/locking semantics are deferred.
4. Candidate retention has no time-based expiry/GC in Stage 10.
5. Memory is intentionally not injected into the Context Compiler. Any later answer-path memory use requires a separate trust-priority, privacy, citation, ablation, and regression gate.
6. Semantic user memory remains explicitly out of scope.

These are deliberate boundaries, not blockers for the Stage 10 candidate-memory contract/runtime.

## 18. Production safety

```text
production touched: NO
production restarted: NO
production routes changed: NO
production credentials used: NO
production R2/Qdrant/SQLite writes: NO
M26 answer path touched: NO
M27 answer path touched: NO
Context Compiler touched: NO
Stage 7 skills touched: NO
Stage 8 workspace touched: NO
Stage 9 MCP touched: NO
```

## Verdict

```text
M27_STAGE10_GOVERNED_MEMORY_RUNTIME: READY_FOR_MASTER_INTEGRATION
PRODUCTION_ENABLEMENT: NOT_APPLICABLE
```
