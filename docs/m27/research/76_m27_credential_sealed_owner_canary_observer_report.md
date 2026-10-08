# Stage 29T Credential-Sealed Owner Canary Observer

**Final state: M27_CREDENTIAL_SEALED_OBSERVER_BLOCKED_BY_RUNTIME**

## What was installed

A workspace-local Python sealed observer at `scripts/m27_sealed_observer_29t.py` on oracle-vm. It loads the mode-0600 credential locally in process memory, calls the public Nginx HTTPS entrypoint (loopback, correct Host), performs non-owner and owner POST requests, and emits allowlisted sanitized JSONL only. No credential content was sent to ChatGPT, the Mac, git, or reports. Credential authentication and M27 routing are **not** confirmed by this trial.

The runner deliberately fails closed: the only implemented final state is blocked, because it does not yet have independent M27 route, non-forwarding telemetry and product-quality proof.

## Trial results

Six POST smoke cases returned HTTP 200: non-owner fallback, owner ordinary, Browser Use warning, multilingual, safe-terminal, underspecified. SSE M27 marker detection was absent in all six responses, so neither successful M27 ownership nor a proven M26 fallback can be asserted. A seventh credential non-forwarding check verified a configured Nginx header-stripping directive but cannot prove runtime absence in the candidate or telemetry. It is unverified, not PASS.

Environment: production 8080, test 8081 and candidate 18080 health HTTP 200; sidecar 18081 without credential HTTP 401; candidate Docker healthy. Nginx not edited. No production data writes, release pointer mutation, route-to-zero, or public routing changes.

Owner HTTP 200 latency (ms): p50 **172.32**, p95 **2856.53**, max **3506.04**. These latencies alone do not satisfy the p95 and product gate, because route identity is unverified. The non-owner probe latency is not included in these owner-only values.

## Gaps and next action

The current Nginx public endpoint returned content without recognized M27 SSE event markers. Add a privacy-safe route-identification proof using candidate-side counters / validated response contract, check the actual active Nginx site and authenticating sidecar behavior without disclosing any credential, verify owner-auth stripping at the candidate boundary and telemetry, then rerun sealed smoke. A HTTP-200-only result may be M26 fallback and must never pass. Avoid manual Owner credential operations. No confirmed stop condition requiring route-to-zero was established; no rollback executed.
