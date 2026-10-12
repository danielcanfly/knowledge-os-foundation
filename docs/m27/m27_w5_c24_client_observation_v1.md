# C24 Native Client Observation v1: evaluation-ready, not certified

## Authority boundary

C24 is a new **client-observed capture SDK** on the exact I23 parent. Its public
`ClientCapture.admit() → feed(bytes) → close(reason)` sequence must be invoked
**inside the real client**: admit on the client's monotonic clock immediately before
request send; feed only bytes actually returned by its own recv/webview/IPC callback;
close on completion, disconnect, timeout, cancellation or rejection. The SDK is
not a server trace, progress-only timing or externally authenticated app by itself.
It does not invoke providers, deploy services, mutate protected benchmarks, read
original 523 case bodies or authorize production.

A real app attachment must be separately provisioned with an approved endpoint,
client identity, legal source snapshots, current immutable candidate/runner digests,
independent controller grant and independent authenticated client ACK. **None are
presently established by this C24 synthetic CLI.** The only network CLI uses
`--synthetic-loopback-port` to **127.0.0.1**, strictly marked synthetic and
never changes `official_qualified=false`. An actual app may embed the SDK as a
Python client library, but attaching a real endpoint remains an independently
authorized integration, not an implicit C24 execution permission.

## Streaming protocol / wire contract

HTTP/1.1 status 200 and `Content-Type: text/event-stream; charset=utf-8`
followed by strict SSE records `event: progress|answer|terminal|error` and a
single `data: <JSON>` line terminated by two LF bytes. Parsing is incremental,
including splits inside UTF-8 multibyte code points. Only a complete UTF-8
`answer` event whose `text` is non-whitespace, sequence/byte ranges match,
SHA256 matches, and whose source-native citations are bound to current local
`SourcePin` source revision/digest/byte range/quote digest, counts as first
substantive text. Progress and terminal do not count. The full completion
requires a terminal with actual concatenated answer digest/byte count and a
strictly later monotonic client timestamp. Partial answers without terminal
are recorded as failures and **not** included in a successful p95 numerator.

Identity on **every** frame: case_id, request_id, nonce, runner_sha256,
candidate_sha256. `answer` adds sequence, start, end, text, sha256, citations.
Each citation links native source id/revision/SHA, source_start/end,
quote_sha256 and answer_start/end. `terminal` adds status=completed,
answer_bytes and answer_sha256. Source snapshots must have consent/rights
verified by caller and must not be revoked. The SDK verifies structural byte
custody, **not semantic answer factuality** or independent source ownership.

Record includes receipt schema, client process PID and fresh process nonce,
frame counts, raw received byte count, wire transcript digest, source-native
citation spans, local monotonic admit/receive/first substantive/terminal/close
timestamps, final answer digest and bytes, and a record even for an empty
timeout/disconnect/error. No raw source bodies are exported in receipts.

## External attestation limitations

`verify_ed25519` checks a detached cryptographic signature if cryptography is
available. `independent_custody` checks different **pre-approved** controller
and independently signed client signer keys, nonce, identity, digest, process,
evaluation scope and receipt binding. It deliberately returns at most
`SIGNATURE_VERIFIED_EXTERNAL_REVIEW_REQUIRED`. First-party signatures or SHA
alone never prove legal authority, independent reviewer rubric or product
qualification. The independent admission authority must set
`INDEPENDENTLY_ADMITTED` on a separately reviewed ledger only once original
controller rights, sealed rubric/holdout, runner/candidate deployed identity,
replay protection, all outcome completeness and actual client provenance are
established. Users must not edit the local synthetic receipts into credentials.

## Percentiles and calibration

For all 341 authentic live outcomes, nearest rank 1-based:
`ceil(341*0.95)=324`. For 237 eligible cited-expected outcomes,
`ceil(237*0.95)=226`. `evaluate_cohort` matches the exact planned case roster
and nonce, client process and case IDs and *every* outcome. Timeout, error,
disconnect, missing result, nonresponsive client, duplicate, inauthentic timing,
missing citation, wrong runner or candidate returns `UNKNOWN`, not success.
Wall clocks from different processes are never subtracted. A 341-row or 237-row
synthetic mock calibration may report a
`synthetic_calibration_p95_ms` with explicit label; the real product
`all_outcome_p95_ms` remains null until all real authenticated outcomes have
been independently admitted. Synthetic sampling and successes are **not**
official 523 cited quality scores. A 15s gate is not declared passed here,
regardless of synthetic ranks.

## CLI synthetic loopback and testing

```sh
PYTHONPATH=src python -m knowledge_engine.m27_w5_c24_client_observation_v1_experimental \
  --synthetic-loopback-port 12345 --plan-json /path/to/test_manifest.json \
  --output /path/to/private/test_receipt.json
```

The CLI requires a synthetic plan and `source.bytes_b64` for a LOCAL authorized
test snapshot, and connects only to the caller's localhost fixture. For a real
application use `ClientCapture` in its own independently approved client
receive loop, and have a separate authorized controller seal results after
review. Do not pass hidden data or credentials to this synthetic CLI.

## Current engineering / release state

The I23/G23 prior local wire evidence remains genuinely observed synthetic
localhost data only. This new C24 code is a candidate ready for I24 source
integration and independent G24 acceptance, not canonical M16. The original
V17 P16 seven tests/AST and B13 positive external evidence remain unadmitted.
`W5_FULL_COMPLETE=false`; `W6_AUTHORIZED=false`;
`REL01_CERTIFIED=false`; `REL02_AUTHORIZED=false`;
`PRODUCTION_AUTHORIZED=false`. Real app attachment and every actual product
metric remain `UNKNOWN`.
