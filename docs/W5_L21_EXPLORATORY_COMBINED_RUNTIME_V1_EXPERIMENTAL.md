# W5 L21: exploratory combined 127.0.0.1 runtime (nonproduction only)

## Isolation and intended scope

This is an **experimental staging integration**, on branch `m27/w5-l21-exploratory-staging-20261012` only. It does not replace or mutate canonical `W5_M16_COMBINED_RUNTIME_INTEGRATION`, any production image, or any independently owned worktree. It never performs an external evaluation or claims independent external rights.

The sole source bytes are the reproducible in-repository *synthetic* Unicode fixtures supplied by I15. Those fixtures cannot establish permission for real source data, original 523 questions, AR09 Phase B, or a real provider.

## Integrated mechanisms

1. `i15.run_case` starts a distinct server subprocess bound to ephemeral `127.0.0.1` and a distinct client subprocess. The client receives HTTP/SSE UTF-8 over real TCP `recv()`. Non-progress answer frames must arrive before terminal.
2. `validate_case` reconstructs the **local fixture's actual source bytes**, independently hashes them and compares the source/revision/answer pins, receipt status, per-client monotonic timestamps, process PIDs/exits, thread admission cap and child cleanup. This check is NOT external provenance.
3. The 28-case plan contains precisely **12 synthetic positive cases** plus **16 independent socket fault modes** inherited from I15. Failure cases remain failures in the denominator. If any case is misclassified or evidence cannot be validated, the integrated run fails closed.
4. Bounded `ThreadPoolExecutor(max_workers=2)` uses I15's process admission ceiling of **4 child processes**. The test module also runs a separate bounded mixed positive/fault pressure sample. Because a busy Mac produced a real `SERVER_BOOT_TIMEOUT` under I15's six-second child boot window, L21 uses an **L21-scoped** limited deadline extension (18s boot, 16s client, 12s server exit). The original I15 deadline constants are restored afterward; no unbounded waits or silent retries are allowed. A startup failure remains a failed attempt.
5. Each 28-case real run writes a **private, explicitly unverified** attempt log before validating case receipts. The log includes attempted mode, status, child PID/exit and failure stage. A validation failure cannot be quietly converted to a good case and the log remains available for investigation.
6. `p17_denial_only` supplies a temporary synthetic *empty* external-evidence manifest. The existing P17 CLI must return nonzero authority-denied, and must write a private receipt validated by both exact file-content SHA256 and the P17 denial validator. An intact denial receipt remains a **denial**, not an independent acceptance or authorization.
7. A separate machine-readable experiment receipt records the exact attempted denominator, typed case records, local denial digest and hard nonproduction limitations. The ordinary safe path is a scratch directory **outside** the Git worktree.

## Trust and measurement limitations

* I15 and L21 source/citation pins are synthetic. Their content SHA256 ties local bytes to a receipt; it does not authenticate an independent issuer.
* Server and client use distinct process-local monotonic clocks. Only timestamps **within the same client** or **within the same server** are compared. Do not subtract server timestamps from client timestamps or claim calibrated cross-process latency.
* The all-outcome denominator is 28, with 12 completed and 16 injected failures only if actually executed and independently checked. There is **no valid all-outcome product p95** where failures lack durations. A per-success local first-text timing diagnostic cannot be relabeled production p95.
* The P17 synthetic manifest deliberately has **zero external artifacts**, so P16 source rights and B13 runtime positive admission remain unresolved, not silently inherited.
* Original P16 seven-suite/AST and B13 complete positive work which encountered explicit platform refusal are **not retried** here, nor reconstructed through an equivalent path.

## Tests and refusal behavior

The dedicated L21 pytest suite includes 51 distinct local evidence mutations, additional malformed namespace/index/plan and forged-completion cases, actual digest-bound *denial* receipt-content tampering, a real 28-case independent client/server run, and a separate 6-case concurrency/fault sample. These newly authored tests do not run the prohibited original P16 seven-suite or B13 positive batch.

All staging reports and code must label the unresolved boundaries:

- `NOT_CANONICAL_M16_ACCEPTED`
- `NOT_ORIGINAL523_OFFICIAL_PASS`
- `NOT_AR09_PHASE_B_ADMISSION`
- `NOT_P16_EXTERNAL_RIGHTS_AUTHORITY`
- `NOT_B13_POSITIVE_ADMISSION`
- `NOT_PRODUCT_P95`
- `NOT_REAL_PROVIDER`
- `NOT_PRODUCTION_OR_RELEASE`

The module's local success marker `L21_EXPLORATORY_LOCAL_ENGINEERING_COMPLETE_OR_PARTIAL` is **not** `W5_FULL_COMPLETE`, `V17_PASS`, `REL01`, `REL02`, `W6`, or a production go decision. The authoring and execution report must quote actual commands, exit codes, and hashes; no test is assumed to pass merely because it exists.

## L22 isolated RDC concurrency / cold-start repair (2026-10-12)

This separate follow-up branch starts from committed L21
`6fcc6790eaf7e8ae45731944aebdf01636f7fffb`.
Its copy of the **synthetic-only I15 fixture server** has a bounded 20-second
listener accept window, rather than the inherited 4-second timeout that could
expire while a fresh Python client process was importing on a busy Mac.
In L22 only, scoped L21 subprocess limits are boot 24s, client 24s, exit 16s.

An explicit `M27_L22_SYNTHETIC_DELAY_CONNECT=5` opt-in test marker causes
exactly five seconds of late client connect in L22's isolated fixture process.
The real 127.0.0.1 subprocess regression must verify client `recv_calls>0`,
byte-exact cited content, first verified substantive answer before terminal,
distinct server/client PIDs and both owned child processes reaped.

The old L21 and underlying I15 production-independent source are not
mutated in their original worktrees. No implicit retry or silently dropped
case is allowed; failures must remain visible. All external rights, official
523, Phase B, authenticated real-app ACK, product p95, B13 positive,
M16 canonical admission, W6/REL01/REL02 and Production remain blocked.
