# M27 W5 T14: Local First-Text Wire, Fixture-Only Receipt Contract

**Component:** `W5T14LocalFirstTextWireProbeV1`. This is an isolated non-Production experiment on an existing B13R-derived worktree. It neither invokes nor rebuilds the explicitly refused B13 source-bundle path.

## Executable route

`python -B -m knowledge_engine.m27_w5_t14_loopback_first_text_wire_v1_experimental probe --worktree <isolated-worktree> --scratch <external-private-evidence-dir>`

* A standalone fixture server process binds the kernel-assigned TCP port on **127.0.0.1 only**. Server prints its PID and listener endpoint to the controlling process. A **different** fixture client PID makes HTTP/1.1 `GET /fixture-sse` with fixed local-only request/tenant IDs; it executes real `socket.recv(19)` calls. No in-memory stand-in can satisfy the positive probe.
* Server uses the accepted AR08 `NativeQATransportAdapter` public contract with synthetic AR03 SourceAuthorityPort and AR05 VerificationPort fixtures. It independently checks exact fixture source SHA, revision, byte offsets, verifier proposal and citation spans before passing a verified frame to the `enqueue` and `flush` transport callbacks. The verified answer contains multibyte UTF-8; SSE `data:` embeds literal UTF-8 JSON text (not base64-only metadata). First progress-only frame, then verified answer frame, then completed terminal frame are emitted over the socket.
* Client incrementally parses strict HTTP headers and SSE frames from arbitrary TCP boundaries, validates exact pinned source/citation binding, per-frame SHA256 and contiguous whole-answer prefix, sequence, verifier ID, run/request/tenant/actor/trace, UTF-8, terminal complete digest, and receive-clock preterminal ordering. `progress` has no content-bearing semantics. Missing, early or duplicate terminal fails closed. Every receipt is from a separate fixture process and is **not** a real authenticated application ACK.
* Bounded payload: maximum 1 MiB cumulative wire bytes; 64 KiB pending SSE event; 32 events; 8 KiB HTTP headers; finite socket/read subprocess deadlines. Child stdout/stderr is captured, SHA256-hashed and not promoted to independently authenticated evidence. Only ephemeral unprivileged loopback ports; subprocesses have restricted environment and working directory. Files written only to the designated external scratch root with 0700 directory / 0600 receipt.
* **Clock separation:** server enqueue/flush/terminal timestamps are `time.monotonic_ns()` in the server process; client request/first TCP receive/first complete verified answer frame/terminal timestamps are in the **client process**. Client first-text latency subtracts only *client own* timestamps. No uncalibrated cross-process subtraction or synthetic claim of real Provider latency is attempted.

## Operational invariants

- `T14_LOOPBACK_ACTUAL_CLIENT_BYTES_RECEIVED_LOCAL_PASS` requires real separate-PID endpoint/recv witness and native cited answer digest match.
- `T14_LOCAL_PRETERMINAL_FIRST_SUBSTANTIVE_TEXT_PASS` additionally requires first client-verified answer DATA earlier than client terminal. Progress-only + terminal must be rejected with `PROGRESS_ONLY_NO_FIRST_TEXT`.
- Rejected cases (`5xx`, timeout, disconnection, safe abstention, nonterminal stream and source mismatch) **remain in the latency denominator**. Nearest-rank local first-text p95 is `UNKNOWN` if any attempt is incomplete; local 15-second classifier is diagnostic only. Injected delayed values are not passed off as 15-second real wall-clock sessions.
- Permanently unverified without authenticated external, independent evaluation:
  `REAL_AUTHENTICATED_CLIENT_ACK_UNVERIFIED`,
  `PRODUCTION_PRODUCT_P95_UNVERIFIED`,
  `REAL_PROVIDER_AND_SOURCE_RIGHTS_UNVERIFIED`,
  `ORIGINAL_523_FINAL_CITED_GATE_UNVERIFIED`,
  `REL01_NOT_CERTIFIED`,
  `REL02_NOT_AUTHORIZED`.
- No other AR08, T09, I02, B13R sources/tests/docs or frozen manifests are edited. No signed source-rights attestation, protected Provider/IdP, hidden evaluation corpus, real customer data, paid API, external network, OCI, GitHub, or Production connection exists in this experiment.

## Evidence artifacts

Local scratch receipt: `05_EVIDENCE_INDEX/W5_T14_LOOPBACK_FIRST_TEXT_WIRE_SCRATCH/T14_REAL_LOOPBACK_SOCKET_RECEIPT.json`. Contains real per-case fixture server/client PIDs, socket endpoints, actual recv counts/bytes, local clocks, source pins, stage flags, success/failure denominator and all six non-promotion qualifications. SHA256 is verified in the worker report. Scratch is **not** staged or tracked in Git.

Run new adversarial test suite and scoped accepted AR08/T09/I02/B13R regression with Python 3.11.15 and disabled pytest plugin autoload. Run `ruff check --no-cache` on **only** the two new T14 Python paths; repeat tests and Ruff after the exact-three-files Git commit. Worker report contains exact terminal process exits and command receipts.

## Interpretive limits

This proof demonstrates **genuine local separate-process socket delivery of a synthetic cited UTF-8 answer**, not real app client delivery, externally authoritative source rights, real 523 cited-final performance, product p95, REL01, REL02, or W6 authorization. Master must replay the receipt and verify code SHA, tests and Git scope independently before local acceptance.
