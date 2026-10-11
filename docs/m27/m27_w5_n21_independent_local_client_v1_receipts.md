# W5 N21 | Independent loopback external-client harness

This feature-off fixture experiment is pinned to staging commit fef4447d8eeb1fcee2b10d93d7a28e6c5cbef689 in its OWN worktree. It does not edit I15/C16, Production, P16/P17/M16 canonical files, or external rights/Provider/hidden datasets.

## Actual boundary

A separate N21 external client OS subprocess is prestarted and emits a bounded, PID-checked ready handshake BEFORE the inherited I15 server binds its ephemeral 127.0.0.1 TCP listener. The parent then hands off the localhost port by private stdin, avoiding the inherited server's 4-second accept-start race under machine load. The N21 client is NOT the I15 inbuilt Receiver/client. N21 opens its own TCP socket, sends case-bound headers and repeatedly calls socket.recv(7), timestamps actual client receipt, incrementally parses raw HTTP/SSE, and independently verifies source/citation/revision/claim span, consent, proof and byte offsets, UTF-8 text, full answer and terminal hash.

Three distinct timestamps are retained: first_answer_ns (client-verified substantive answer DATA), full_answer_ns (all expected answer bytes verified), and terminal_ns (terminal receipt). first_recv_ns is header/progress receipt only and does NOT qualify as substantive first text. Raw recv bytes are NOT an authenticated app ACK.

All 28 scheduled cases count: 12 dynamic CJK/multilingual local fixtures and 16 fault modes. A missing terminal, progress-only payload, rejection or timeout remains an attempted failure. Full-denominator p95 for first text, full answer and terminal is UNKNOWN when any attempt is incomplete. Per-positive sample metrics are fixture-local only and cannot establish product p95.

The N21 suite shares C16 bounded OS flock admission: at most two server/client pairs at once per worktree, child deadlines, owned PID reaping and 127.0.0.1 endpoints. A suite run on another worktree can affect latency but never implies production concurrency. A second same-worktree suite may be run in parallel with a distinct namespace and receipt for bounded concurrency verification.

## Failure matrix

New pytest executes 19 wire/source/identity fields multiplied by four hostile values = 76 named negative mutation injections, plus 12 dynamic Unicode fixture cases, malformed responses, duplicate/dropped terminal, progress-only, invalid namespace/port and post-terminal bytes. The 76 mutations are in-process decoder tests, NOT 76 independent TCP socket tests. The 28-case CLI is the actual external OS-client socket experiment.

## Reproduction and custody

Use pinned Python /Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python and environment TMPDIR=/tmp PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1.

From the N21 worktree:
1. python -B -m pytest -q -p no:cacheprovider tests/test_m27_w5_n21_independent_local_client_v1_experimental.py
2. python -B -m ruff check src/knowledge_engine/m27_w5_n21_independent_local_client_v1_experimental.py tests/test_m27_w5_n21_independent_local_client_v1_experimental.py
3. python -B -m knowledge_engine.m27_w5_n21_independent_local_client_v1_experimental probe --worktree <N21 absolute worktree> --scratch <off-Git private scratch path> --namespace n21r01

The off-Git N21_REAL_EXTERNAL_CLIENT_RECEIPT.json is the case-level evidence. The worker REPORT records its content digest, actual exits and status. All receipts must retain fixture=true. Original refused P16 suite / B13 positive acceptance operations are out of scope.

## Explicit unknowns

REAL_APP_CLIENT_ACK_UNVERIFIED; REAL_PROVIDER_AND_RIGHTS_UNVERIFIED; ORIGINAL_523_CITED_RATE_UNVERIFIED; PRODUCT_P95_UNVERIFIED; W4_AR09_PHASE_B_BLOCKED; B13_RUNTIME_POSITIVE_BLOCKED; REL01_NOT_CERTIFIED; REL02_NOT_AUTHORIZED. No W6, release promotion or Production access is granted by N21.

## Independent observed local results (2026-10-12)

- The unmodified startup path produced two preserved failed receipts, with 10/12 and then 8/12 positives due to I15 server accept timeout / external process startup after server ready; 16/16 expected negative faults in each. Their full 28-case denominators and receipt hashes are retained in off-Git evidence. These runs are NOT PASS.
- The bounded client prewarm/PID-ready + private port-handoff correction was actually re-run: prewarm_retest N21_REAL_EXTERNAL_CLIENT_RECEIPT.json, SHA256 2e1daf8e3ae93e8ebbbd24fa672d1a3d0f2496aa0922bdfbb8cd6f1f4c89aeee, 28 attempted, 12 complete locally cited dynamic answers, 16 expected denials, fixture-only PASS, full-denominator p95 UNKNOWN.
- A distinct 8-case concurrent negative OS-child check passed, using 73 parent-child process monitor samples and observed maximum 4 directly owned child processes. Concurrency receipt SHA256 43e4eceb0778fb5e95871f62fb5e6a8fa5dd83b0b7ca936ebba0a258146ccd76. Sampling cannot prove unseen process peaks. The monitor/driver are external-private scratch, not tracked test cases.
- Narrow N21 pytest 104/104 passed, including 76 in-process fault mutations. Scoped Ruff passed. Original P16 and B13 prohibited evaluation paths were not executed. The formal worker report records all other requested raw file hashes and the final Git commit.
