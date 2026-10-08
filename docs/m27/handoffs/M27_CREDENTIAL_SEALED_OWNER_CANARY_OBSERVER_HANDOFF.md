# Stage 29T handoff

State: `M27_CREDENTIAL_SEALED_OBSERVER_BLOCKED_BY_RUNTIME`.

Runner: `python3 scripts/m27_sealed_observer_29t.py` from the Stage 29T VM worktree. Run on oracle-vm only. Runtime sanitized JSONL: `/home/ubuntu/m27_owner_canary_operator_observation_29t.jsonl`. The credential stays on the VM, is never displayed, and is only read in process memory by the runner.

Six HTTP 200 results do not prove routing. Resolve missing SSE route-identification, independently verify non-forwarding, and enforce product success/quality and p95 gates before certifying HEALTHY. No public mutation authorized.
