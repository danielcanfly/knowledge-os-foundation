# AR09C | Independent C02 T4/terminal Outcome Probe (T0/T1 MOCK_ONLY)
2026-10-10 | Additive experimental branch only, no real admission.

## Authority / ownership
- Frozen parent C02 commit: `122d85642254e541e2a745ea814c2255f3bb3253`, parent `76962a7466b9abb8241fbdcb4a2af867716a0ae0`.
- Imported exact accepted AR09B E01 three files from `1b2dde51296448a1c5c466f50af45f06a45c142a`, byte hashes retained. The source evaluator is NOT modified.
- No K03, V05, AR02B-R, AR03B, LB04/07/08, Original VM, Production, real source/credential, remote provider, actual client delivery, native product route, live SaaS or release authorization.
- 3 imported E01 new tracked files + exactly 3 new AR09C tracked files only.

## Real (bounded) public API composition
`prepare_mock_loop` / `complete_mock_loop` exercise accepted public AR02C, AR03A, AR04A, AR05A and v2 successor. AR09C reads public `Kernel.read`, `ReconciliationKernelV2.history/head/head_hash/terminal_receipt`, source state, versioned ObservationV2, signed mock VerificationReceipt and publication frames. It independently recomputes:
1. Legacy accepted head5, tenant/lease, UNKNOWN/nonterminal, charge id and total; no network/provider calls.
2. V2 T3→T4→terminal event hash chain/head, applied observation, fixture-HMAC signatures, source snapshot/revision/consent/exclusion/TTL, verifier task/attempt/outcome/lease/current-head and mandatory hard gates.
3. Frozen **synthetic** source original bytes and revision/citation binding, substantive frame content, frame ordering and fake ACK identifier; postterminal correction sidecar and no terminal reopening.
4. Invoice charge identity and amount. Cross-case duplicates are **not** silently renamed by manifest assembly.

Then construct AR09B's public `OutcomeEvidence`, `TrustedObservation`, `EvaluationContext`, call `evaluate_case` and `evaluate_batch` directly. Frozen expected source bytes, frame digest and citation are independent from the submitted generator `outcome_id`. Faults force rights/unknown fail-closed before AR09B; AR09B independently enforces evaluator identity, oracle eligibility, source rights, digest, verified stream, charge and manifest.

**Semantics warning:** AR09B's field `terminal_durable=True` is used *only* as the synthetic v2 head7 fixture terminal-commit marker. This does **not** attest disk durability, ACID or recovery. AR09C's immutable result states `no_durable=True`, `no_provider=True`, `no_real_tool=True`, `authorized_task_success=False` for every case; real grade, provider cost and blinded holdout remain `UNVERIFIED`. C02 frames have no real timestamps. Logical positions from frame order produce synthetic `at_ms` values for AR09B tests, not real latency / first-byte streaming measurement. No genuine independent signer or independent delivery attestation is produced.

Positive outcome: `MOCK_ONLY_FUNCTIONAL_SUCCESS` with `AR09B.ACCEPTED_OFFLINE_FIXTURE_ONLY` when all independent local predicates are satisfied, plus original AR02C still remains UNKNOWN and nonterminal.

Negative outcomes: `MOCK_ONLY_REJECTED` on stale/missing/mock-forged evidence, wrong tenant/head/epoch/verifier, observer contradiction/expiry/replay, source revocation/revision/citation/source bytes drift, fake ACK missing, progress-only, altered late notice, charge mismatch/duplicate/missing price. The test matrix uses actual falsification and denied C02 methods, not just fixture labels.

## Admissions deliberately OPEN
- Durable serializable AR02 writer/journal/outbox and crash replay/recovery; current C02 is in-process-only.
- Real observer IdP/rights, source consent/revision authority; synthetic HMAC is not a cryptographic independent proof.
- AR05 actual independent source and outcome attestation, independently observed effect, real client transport ACK and native Q&A.
- Real provider spend/invoice and charge duplication boundary; cross-case fixture IDs require genuine scoped identifiers, not automatic assumption.
- Hidden holdout + calibrations, independent real rubric/grade; >95%, >=85 and p95<15s release gates never inferred.
- Master acceptance and REL01/02 remain independent gates.

Validation on 2026-10-10 UTC: RED module-absent pytest exit2; first behavioral run 27 PASS / 1 FAIL (AR09B correctly flagged repeated `charge-fixture` across separate manifest cases as `DUPLICATE_FEE`); repaired the negative/denominator fixture without disabling duplicate detection; full 12 scoped suites **365 PASS, exit0, 18.23 s**; scoped Ruff on four (two imported + two new) Python files **exit0, All checks passed!**. Full command/exit/log hashes, diff, exact six-source SHA256 and commit are in external scratch and evidence receipts.

This is an explicitly narrow `AR09C_OFFLINE_C02_EVAL_COMPONENT_PASS` after clean Git commit and receipts. Master acceptance remains separate.
