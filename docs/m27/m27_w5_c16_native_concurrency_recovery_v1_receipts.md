# M27 W5 C16 | Fixture-only native concurrency hardening receipts

**Scope:** isolated feature-off branch `m27/w5-c16-native-concurrency-recovery-v1`, direct parent `bc1246382852b5fc15e1bf3f70325ea7c1f1275c`. Three tracked paths only: existing I15 experimental source, new C16 pytest, this receipt. No modification to original I15 worker, T14, E15, Production or external accounts.

## Reproducible initial condition

Original G15 exhibited a single local fixture child-process 8s timeout when it overlapped another 28-attempt socket probe (548 passed, 1 failed). G15's next isolated rerun was 549 passed. This observation does **not** establish a causal relationship or a production defect. C16's untouched inherited I15 implementation was separately run against **real localhost kernel sockets** before edits, with 28 attempts, 12 valid positive receptions and 16 expected denials. Raw baseline receipt, stdout, stderr are held under `05_EVIDENCE_INDEX/W5_C16_NATIVE_CONCURRENCY_RECOVERY_SCRATCH/baseline`; baseline child-process stderr and startup stages were not observable in inherited I15.

## Actual implementation

- Replaced the **unbounded server stdout `readline()` and potential unbounded boot stderr read** with unbuffered `select` + `os.read` and an explicit monotonic boot deadline; a dead boot cannot block the suite forever.
- Replaced opaque `subprocess.run(...timeout=8)` with separately owned bounded `Popen` processes, stage-specific client/full response and server exit deadlines, bounded output inspection, stderr/exit telemetry and an explicit reaper. On timeout or error, only the two children actually owned by that case are terminated and reaped; any failure stays a recorded attempt.
- Each launcher receives an OS-backed `fcntl.flock` admission slot from two shared slots keyed to resolved worktree, limiting concurrent admitted cases to two and direct child count to four **across independent same-worktree process parents**. Slots release on parent exit; timeout is a named denial, not an indefinite queue.
- Every probe now uses a distinct ASCII-limited namespace that binds its case, request, run, trace, tenant and actor identifiers, reducing replay/cross-suite contamination.
- Real source and cited substantive UTF-8 `socket.recv(7)` verification remains in separate server/client processes; progress never becomes first text, AR08 source pins remain local fixtures and every completed client requires verified answer DATA preceding terminal in its own monotonic clock.
- Structured per-attempt diagnostics record parent spawn/ready/child exit/cleanup, child receive/first verified DATA/terminal ordering, separate clock domains, local child stderr and returncodes. Failure/abstention rows remain in the denominator; p95 remains UNKNOWN when any failed attempts exist.

## Adversarial tests and known limits

C16's new parametrized pytest injects 19 individually named wire fields multiplied by four hostile values, **76 distinct executed denials**; cross-suite replay, source-revision/consent drift, invalid UTF-8, HTTP 500, replayed/duplicated frames, fake Client ACK, malformed/infinite boot, fork/resource exhaustion, child kill, stalled socket receive and injected subprocess deadlines are additional tests. Older I15/T14/T09/AR08/I02/B13R regressions are still run unchanged with the exact pinned Python 3.11.15 interpreter.

This is local experimental engineering only. **No** external source rights, IdP, original 523, true unseen Phase B, real Provider, authenticated production Client ACK, signed CI/OCI, B13 positive evidence, product p95, release or Production admission is supplied here. Every receipt is `fixture=true`; no W6 promotion.

## Replay

From C16's worktree, export `TMPDIR=/tmp PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`. Use `/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python -B -m pytest -q -p no:cacheprovider --basetemp=/tmp/m27_w5_c16_replay` followed by the C16, I15, T14, T09, AR08 QA, I02 and B13R test files. Use the pinned interpreter with `-m ruff check` on the modified I15 Python file and new C16 test. Real socket receipts are produced by the I15 `probe` CLI with unique `--namespace` and separate off-Git `--scratch` directories. The off-Git `STRESS_DRIVER.py` independently starts three overlapping 28-case suites and samples direct server/client process counts with `ps`, retaining all raw suite JSON and per-case child diagnostics.

**Status:** final verdict, observed stress denominators, source SHA256, scoped pytest/Ruff and Git hashes recorded in the external worker REPORT only after they are actually obtained. Root cause must remain `ROOT_CAUSE_NOT_ESTABLISHED` unless repeatable causal evidence is found.


## Measured sequential and overlapped receipts (2026-10-11, fixture=true)

- Original inherited baseline was recorded before modification in off-Git \`baseline/\` and \`BASELINE_original_stdout.log\`. The historical G15 simultaneous 548/1 failure remains a real non-reproducibly explained timeout; **ROOT_CAUSE_NOT_ESTABLISHED**.
- Early C16 three-suite stress \`STRESS_SUMMARY.json\` (before final bounded-admission adjustments) ended **C16_CONCURRENCY_NOT_VERIFIED**, 84 planned cases and 4 observed direct child processes. Admission timeouts and some client non-receipts were retained, not discarded. This failure is preserved in off-Git receipts, not rebranded a PASS.
- After hardening, independently run sequential 28-case wire suite \`sequential_after_fix/I15_REAL_MULTICASE_SOCKET_RECEIPT.json\` SHA256 \`460c754e0354f2e09d9dd61ed6f663f3f6dcd331941d403b6e86a30c4bc0c454\`: 12 COMPLETE, 16 expected fault denials, 28/28 denominator, p95 UNKNOWN.
- Three deliberately overlapped 28-case suites under one fixed \`PROCESS_CHILD_LIMIT=4\` returned **PASS/PASS/PASS**, SHA256 respectively \`28597ad5f5b56debbdf04649e8a93cbf6186245703bdec24e93522f2287bc276\`, \`66134a2b35f9c4e011a96cea2ce4394d52792f9542107ec6befeba0e209e7e97\`, \`92a619a878a81fb43c30295d75234b86888d6b703fa6242eddc848616586f420\`. The three original JSON receipts are \`stress_overlap_0/1/2\`; combined 84 actual OS-child attempts, 36 complete cited first-text-before-terminal, 48 expected deny; all 84 server/client children cleanly reaped.
- Independent receipt audit verified no unexpected fault modes, boot/admission/process failures or unreceived failures in any three suites, each suite has 28 distinct localhost endpoint ports and child receive calls. Maximum measured admission delay per suite: 10,536.714 ms, 10,437.91 ms, and 12,633.402 ms, below the independent bounded admission deadline. Sampling monitor \`STRESS_MONITOR.json\` contains 614 samples; maximum observed direct children 4; sampling does not imply that unknown external system process counts are controlled.
- \`STRESS_DRIVER_RETEST_STDOUT.log\` confirms stress execution exit0; the driver checks fixed 28-attempt denominators, 12 complete, 16 expected denials, child reaping, independent namespaces and SHA256. All values describe synthetic locally generated source/citation claims. Product first-text/final-answer p95, 523 cited gate, independent evaluator and real Client ACK remain unverified.
- Two initially failing new tests (overly narrow deadline expectation and Python default-argument boot timeout binding) and four unused client lifecycle timestamp variables were corrected in the **same C16 worktree**, followed by successful focused 4-case regression and Ruff. The clock domains in child receipts are never subtracted against parent monotonic values.
