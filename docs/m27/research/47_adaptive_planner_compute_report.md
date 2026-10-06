# M27 06 Adaptive Planner + Compute Controller Report

State: `M27_ADAPTIVE_POLICY_READY`
Date: 2026-10-06
Workspace: `/home/ubuntu/LLM_Wiki-m27-adaptive-planner`
Branch: `m27/adaptive-planner-compute`
Approved base: `4c348d569364c8783ae72abd73e28d1f6ead7914`

## 1. Preconditions and boundary

Phase 05 was confirmed complete before runtime-policy mutation: `M27_FRESH_SMALL_SMOKE_COMPLETE`, 12/12 bounded fresh-smoke cases passed, and `SMOKE_TO_NEXT_PHASE_HANDOFF.md` authorized the next policy-work phase.

This session did not run Stage13/14 legacy admission, Chunk002, 100-case, or full523. It did not restart, stop, rebuild, deploy, or write production R2, Qdrant, SQLite, or release pointers.

## 2. Adaptive task taxonomy

The stable top-level task kinds remain `NO_CONTEXT`, `KNOWLEDGE`, `TOOL`, and `OPS`. A second explicit workload profile taxonomy was added so callers can select adaptive behavior without breaking legacy callers:

- `GENERAL`
- `DIRECT_KNOWLEDGE`
- `MULTILINGUAL_KNOWLEDGE`
- `RETRIEVAL_HARD`
- `DEADLINE_PRESSURE`
- `SAFE_ABSTENTION`
- `TOOL_LOOKUP`
- `OPS_DIAGNOSTIC`

`GENERAL` is the default and preserves existing bounded continuation semantics for callers that have not opted into a richer profile.

## 3. FAST / STANDARD / DEEP policy

New module: `src/knowledge_engine/m27_adaptive_compute.py`

The controller emits an authoritative bounded `AdaptiveComputeBudget` with compute tier, maximum continuation rounds, maximum tool calls, maximum provider calls, and privacy-safe reason codes.

Deterministic policy summary:

- `NO_CONTEXT` and simple tool lookup use `FAST`.
- Direct and multilingual knowledge use `STANDARD`.
- Healthy-budget retrieval-hard work can use `DEEP`.
- Retrieval-hard with constrained budget deterministically downgrades to `STANDARD`.
- Deadline pressure uses `FAST` with no continuation.
- Explicit safe-abstention or exhausted budget fails closed.
- `GENERAL` keeps existing caller-requested bounded continuation/tool limits, still under hard caps.

Hard ceilings: at most 2 continuation rounds, 6 tool calls, and 12 provider calls. No tier can request unbounded compute.

## 4. Telemetry-guided continuation

The executable runtime now evaluates continuation from measured privacy-safe signals after every round: verification status, evidence delta, round latency, tool-call consumption, provider-call consumption, and completed rounds.

Rules:

- verified answer terminates;
- exhausted adaptive budget terminates;
- a first empty retrieval may receive one bounded probe to preserve verifier-gap recovery;
- a later round with no evidence gain terminates with `TELEMETRY_NO_EVIDENCE_GAIN`;
- latency pressure terminates;
- measurable progress with remaining budget may continue.

The initial implementation was too strict and stopped immediately on first-round no-evidence telemetry. Existing runtime-finalization tests caught this. The final controller preserves first-round bounded probing and only early-stops stale later rounds.

## 5. Runtime integration

Modified:

- `src/knowledge_engine/m27_context_orchestrator.py`
- `src/knowledge_engine/m27_runtime_harness.py`
- `src/knowledge_engine/m27_runtime_execution.py`
- `tests/test_m27_runtime_finalization.py`

The harness computes adaptive budget from explicit task profile plus normalized legacy budget signals and passes it into isolated executable execution. Adaptive reason codes are added to privacy-safe telemetry. Runtime-finalization tests now assert that large budgets do not force every possible continuation when telemetry says a later round is stale.

Feature-off behavior remains unchanged because `M27RuntimeHarness.run` returns `M26_BASELINE_UNCHANGED` before planner, compute controller, tools, or executable work when `m27_enabled` is false.

## 6. Privacy and safety

The controller consumes only enums, normalized budget observations, counters, and numeric telemetry. It does not consume raw query, answer, passage, provider prompt, secret, or credential fields. Tests inject private values and confirm they do not appear in serialized adaptive decisions.

Production mutation was not introduced. Tool execution remains read-only and this worktree stayed isolated.

## 7. Validation

Commands run in `/home/ubuntu/LLM_Wiki-m27-adaptive-planner` using local `.venv`:

- `.venv/bin/ruff check src/knowledge_engine/m27_adaptive_compute.py src/knowledge_engine/m27_context_orchestrator.py src/knowledge_engine/m27_runtime_execution.py src/knowledge_engine/m27_runtime_harness.py tests/test_m27_adaptive_compute.py tests/test_m27_runtime_finalization.py` → PASS
- `.venv/bin/python -m compileall -q src tests scripts` → PASS
- `.venv/bin/pytest -q tests/test_m27_adaptive_compute.py tests/test_m27_context_orchestrator.py tests/test_m27_compute_policy.py tests/test_m27_runtime_finalization.py tests/test_m27_runtime_observability_contract.py` → 50 passed
- `.venv/bin/pytest -q tests/test_m27*.py` → 542 passed, 1 warning

The single warning is an existing Starlette/httpx deprecation warning unrelated to this session.

## 8. Completion

`M27_ADAPTIVE_POLICY_READY`

M27 now has explicit workload profiles, deterministic FAST/STANDARD/DEEP policy, bounded compute budgets, telemetry-guided continuation, feature-off preservation, and private-payload trace protection. This is not a production rollout or broad admission result.
