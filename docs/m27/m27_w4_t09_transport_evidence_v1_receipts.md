# W4 T09 | Transport Evidence Sidecar V1 | Local engineering receipts
Date: 2026-10-10. **Feature-off / fixture-only / no native route mutation.**

## Outcome and boundaries

The standalone typed validator reports `LOCAL_EVENT_VALIDATOR_PASS` for structurally correct **local fixture** traces, *never* `REAL_NATIVE_CLIENT_OBSERVED`. Even an injected callback named "independent verifier" cannot upgrade its output. The real client status is **`REAL_CLIENT_ACK_UNAVAILABLE`**, the release first-text metric is **`PRODUCT_TTFT_UNVERIFIED`** and the release latency verdict is **`PRODUCT_P95_UNVERIFIED`**. The module makes no live Client ACK, image-execution attribution, 523-corpus quality, p95<=15s, REL01/REL02 or Production claims.

Exactly three isolated worktree additions, no imports or edits to accepted S08Q/I02 or M26:
1. `src/knowledge_engine/m27_w4_t09_transport_evidence_v1_experimental.py`
2. `tests/test_m27_w4_t09_transport_evidence_v1_experimental.py`
3. `docs/m27/m27_w4_t09_transport_evidence_v1_receipts.md`

## Read-only external consumer/native transport inspection

Local source inspection (no API/network request, no Production mutation) found:
- Original M26 native SSE route exists as *source code*: `src/knowledge_engine/m26_verified_streaming.py`, `VERIFIED_STREAM_PATH="/api/m26/query/stream"`, with `verified_query_event_stream`; `src/knowledge_engine/m26_ask_api.py` registers `@app.post(VERIFIED_STREAM_PATH,...)`. Static route presence does **not** establish it is the currently running authorized original native Q&A transport.
- `m26_verified_streaming.py` serializes SSE event names such as `verified_claim_ready` and `final_answer_done`; a yielded SSE frame or `first_material` event-name flag is not an authenticated consumer's actually received first substantive byte.
- Accepted S08Q `NativeQATransportAdapter` and I02 local runtime use an **in-process** `TransportPort.enqueue/flush` seam only; `accept_client_ack` explicitly rejects unauthenticated callback; I02 `LocalOutcome.client_ack=False`. This is evidence of local callback semantics, not external client attestation.
- No currently authorized independent external consumer, signed receipt verifier, capture session, calibrated client clocks or genuine authenticated byte ACK was provided or established within this authorized local inspection. **Do not infer that such an external service does not exist elsewhere.**

Read-only evidence sources: `07_MASTER_REBASE_20261010/MASTER_STATE_V2.json`, `TOOL_ROUTING_POLICY_V5.md`, `02_ACCEPTANCE/W4_I02_E09H_MASTER_ACCEPTANCE_20261010.md`, `02_REPORTS/W4_I02_AR02_AR08_RUNTIME_INTEGRATION_REPORT.md`, `02_REPORTS/W4_E09H_AR09_INDEPENDENT_EVALUATION_REPORT.md`, `05_EVIDENCE_INDEX/REL01C_STREAM_QUALITY_COST_RECEIPTS.md`, `05_EVIDENCE_INDEX/REL01E_GATE_EVIDENCE_MATRIX.md`, accepted S08Q/I02 source, M26 SSE and endpoint source. Legacy Stage30O/P `first_material_ms` event-name-only timestamps (many within 2ms of terminal) are not converted or copied into new TTFT proof. Reported historical image `active_image` may refer to a prior Stage30O image with Stage30P code patch; this package does not pretend it is the currently executed candidate image.

## Capture and strict admission contract

- `Candidate`: full 40-lowercase-hex commit, source-tree SHA256, optional independently identified immutable `sha256:<64hex>` OCI image and separate build attestation SHA256, instrumenter+runner+dataset+source-manifest SHA256, request/run/trace/task IDs, durable task head, tenant and actor. Missing image/attestation is allowed for local analysis but provenance is **not certified**; tags or shortened commits are refused.
- `SourcePin`: exact original native citation, source ID, revision, digest, tenant+actor, rights issue/expiry and revoke state. Each answer frame carries its own 4-tuple citation/source/revision/digest binding and fresh wall-clock check; actual independent rights/entailment evidence must be issued by a separate authority, not a caller's self-declaration. No restricted source bytes read.
- `TransportEvent`: ordered unique IDs and exact consecutive sequence, request/trace/principal, monotonic clock domain and timestamp, bounded wall date for freshness, verified first payload frame bytes+SHA256, byte offsets contiguous with complete answer bytes, strict UTF-8 decoding, citation binding, verified receipt, actual observation boundary `server_write_observed` or `server_flush_observed`, terminal type. Progress/queue/event names cannot impersonate first actual answer text.
- Mandatory meaningful ordering: `request_received` -> `evidence_verified` -> `verified_substantive_utf8_first_byte_sent` -> `first_cited_segment_sent` -> `terminal(answer)`. Both substantive frames must be **strictly before** terminal, nonblank, complete, pinned to sources and verified for the same actor/tenant. Server events after terminal are refused. A well-formed `safe_abstention` has an explicit reason with verification/policy record but no answer bytes/first/cited stage and remains in denominator metadata.
- `client_received` is a separately typed proof, bound to first written frame, request/trace/principal and nonce. Without independently injected receipt validation, rejects as `UNAUTHENTICATED_CLIENT_ACK`. Fake fixture receipt validation yields only `FIXTURE_ACK_ONLY`. Any caller-supplied `fixture=False` label still yields `ACK_AUTHORITY_NOT_CERTIFIED`, NEVER live client-ready; approved, external, signed identity/clock/endpoint/session authority must be independently established in a later task.
- Clock domains: within one domain enforce monotonic order. Across domains require externally verified calibrated shared anchors and nonoverlapping uncertainty bounds for *ordering only*. The validator cannot authenticate caller-injected anchors; it refuses uncalibrated domain differences and does not subtract cross-machine clocks for reported request latency. `first_server_text_ms` and `first_cited_ms` from same process are local diagnostic metrics, not real client TTFT.
- `CaptureAdapter` accepts a clock port and capture callbacks, no direct network side effect, no ability to mint client ACK. Separate fake `FakeClock` and `FakeTransport` in tests exercise this event capture. Authoritative production sampling will require separately approved real server send/flush and trusted consumer receive observers. The current local events carry test plaintext: **only sanitized/test fixture bytes may be persisted**, never raw real prompts, keys, credentials or protected source material.

## Latency denominator and percentile

`duration_denominator` takes unique frozen case/request IDs and status `completed | timeout | missing | safe_abstention`, with externally sourced final-answer request duration as an *input* only. Invalid/nonfinite/negative duration is rejected. The count includes every case, including safe terminal, timeout and missing; a missing/timeout/abstention forces percentile `None` rather than silently dropping rows. Complete fixture sets use explicit nearest-rank `ceil(.95*n)` and `<=15000 ms` **only as a synthetic diagnostic**. 15,000ms versus 16,000ms adversarial examples exercise the threshold. No caller-supplied duration, fake clock or pytest runtime certifies a product p95. Actual release assessment needs separately verified final-answer terminal timestamps/denominator and timeout policy from a recognized external observer.

## Adversarial tests and known non-claims

Tests independently instantiate >35 negative mutation vectors plus separate malformed denominator/client/clock tests. Matrix categories:
- Provenance: 8-char/uppercase commit, wrong tree/runner/dataset/instrumentation/manifest SHA, mutable image tag, invalid OCI image, missing/unbound attestation, missing durable task head/trace.
- Actual bytes: missing first byte, terminal only, event name `first_material` only, `final_answer_done` event name only, whitespace-only first frame, split UTF-8 codepoint, invalid answer UTF-8, frame hash mismatch, answer incompleteness, replayed frame ID, duplicate/offset gaps and no verified flush/write boundary.
- Ordering/time: repeated event ID, duplicate/out-of-order sequence, monotonic rollback, uncalibrated cross-machine clock, invalid/missing timestamp, terminal before text, calibrated uncertainty overlap, invalid terminal type.
- Rights/identity: expired/future-issued/revoked source, invalid source digest, wrong source tenant, wrong event actor/tenant/request, missing/duplicate/unsupported citation, source ID/revision/digest drift, missing verifier or incompatible receipt.
- Client: ACK callback without independent verifier, changed frame/tenant/digest, unsigned proof, rejected signature, wrong actor; fixture signed-like ACK never asserts real.
- Outcome and denominator: safe-as-answer, missing/timeout/abstention counted, duplicates, nonfinite/negative durations, one-second-too-late, wrong status and fabricated timeout duration.

No hidden AR09 labels, original 523 answers, paid Provider, external IdP, remote verifier, external authorized consumer, VM, Docker image, production source, rollback or route mutation is used. No actual independent source authority or SSE client bytes are claimed.

## Reproduction (worktree-local, before external Master acceptance)

Use existing pinned interpreter and no extra dependency installation:
```sh
cd /Users/huaihsuanhuang/Desktop/Chatgpt/M27/M27_VNEXT_MASTER_20261009/06_WORKSITES/W4_T09_STREAM_EVIDENCE
export PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python -B -m pytest -q -p no:cacheprovider tests/test_m27_w4_t09_transport_evidence_v1_experimental.py tests/test_m27_w3_ar08_qa_stream_v1_experimental.py tests/test_m27_w4_i02_local_runtime_v1_experimental.py
/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python -B -m ruff check --no-cache src/knowledge_engine/m27_w4_t09_transport_evidence_v1_experimental.py tests/test_m27_w4_t09_transport_evidence_v1_experimental.py
```

Raw pytest/Ruff, exact Git parent/scope, SHA256 and validation outputs belong in the **separate** `05_EVIDENCE_INDEX/W4_T09_STREAM_EVIDENCE_SCRATCH` and `02_REPORTS/W4_T09_STREAM_EVIDENCE_REPORT.md` Mac locations; they are *not* additional tracked worktree files.

**Gate conclusion:** transport instrumentation *can be locally validated*; `REAL_NATIVE_CLIENT_OBSERVED` is NOT established. Separate true source/license/client/billing authority, original authorized native consumer and independently frozen candidate/corpus are still required.
