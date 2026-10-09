# CODEX AR02–AR05 CORE | Offline cross-stage interface-gap receipts
2026-10-10. Status: **BLOCKED_INTERFACE_GAP**, not a runtime vertical PASS.
Label for EVERY demonstrated effect: `MOCK_ONLY_UNAUTHORIZED_FOR_REAL_EFFECT`.

## G0: exact accepted source identity, read-only
- X10 candidate clean Mac worktree initial HEAD `0eb5f942e7919528ce7cae68f7e68e8dd5c6e9bc`; new isolated branch `m27/codex-ar02-ar05-core-offline-vertical`, created at exactly this SHA.
- AR02C original accepted VM Git object `644114b023cadcbab3776aab00172ac436fb1f8f` at `/home/ubuntu/LLM_Wiki-m27-ar02a-a38-offline-kernel`: source SHA256 `d2261003d620e9c2b58761c32efc30c761ca1b53e1a99b09ba70f516cddad4cb`; test `cf1f1da4d408d67589764ab3fa0bc21422ffb5aa051ccbf7edab24df7dd98f7c`; docs `161fc4ad864d21a4816f2cb0b0004d61214759f9cd77f59c0501c46a60b0adcc`.
- AR03A original accepted VM Git object `d3fda2fccc17aa14d8e9badb63f552c5e8253432` at `/home/ubuntu/LLM_Wiki-m27-ar03a-a40-offline-context`: source SHA256 `b3263c8ae00d99296d449965b94fb6b40a4f70ae8d260e86133ea3b824da9d6e`; test `b49132469b2c8c60f14f87d39aeb01f6ea3c4dd6e454a109c824a829d0aefa55`; docs `a205a654f49be150257c6cb4535827d1730847f6bfdd5aec9e1e156897c4ad90`.
- Both Git object existence and object-content SHA256 verified via read-only SSH Git inspection. Read-only `git archive` transported exactly SIX committed files to new Mac worktree; post-transfer `shasum -a 256` matched all six. No substitute repo or denied worktree used.

## Actual public API handoff and decisive failure
`probe_observed_t3_cannot_terminal()` exercises imported AR02C `Kernel`, imported AR03A `select`, accepted AR04A `InertSafeActionBoundary`, accepted AR05A `VerificationPublicationGate` and accepted AR09A `remote_unknown_oracle`:
1. Synthetic context request selects pinned `source-id`/`revision-1`/source-bytes SHA under matching fixture-grant; reselect at consume. **GrantFixture.externally_authenticated=True is a caller-controlled offline assumption, not independent right.**
2. AR02 create (head 0), budget reserve (head 1), charge (head 2); AR04 T1 produces candidate, AR02 `intent(trusted=True)` (head 3); AR04 T2 claim, AR02 `claim(trusted=True)` (head 4).
3. AR04 T3 explicitly inert boundary; AR02 `possible_send` (head 5) produces `UNKNOWN_EFFECT` with no provider call.
4. AR04 T4 separate **fake** observer says `CONFIRMED_APPLIED`; AR04 T5 is a nonterminal proposal. AR05 independently configured **fake HMAC** gate denies `UNKNOWN_EFFECT` on exact synthetic JournalSnapshot; AR02 `terminal(verified_head=5, trusted=True)` denies `untrusted/stale verifier or unknown effect`. Head stays 5, terminal remains false.
5. AR09 oracle for crossed T3 + lost ack returns `POSSIBLY_SENT_NO_BLIND_RETRY` and `send_count=0`. All fake units leave `provider_calls=0`; `real_admission_authorized=False`.

**Why the required happy path is impossible with immutable accepted API:** AR02C `possible_send` unconditionally adds intent to `unknown`; `terminal` refuses any nonempty `unknown`. Its public API provides no `reconcile_effect`, acknowledged observation, or durable atomic transition removing unknown after independently validated T4 evidence. AR04A's reconciliation is in a separate in-memory object and cannot change AR02's journal. AR05A only issues proposals. Direct mutation of `kernel.runs`, fabricated JournalSnapshot `unknown_effect=False`, treating HMAC/fixture booleans as live authority, or bypassing Kernel.terminal would be invalid workarounds. Therefore no green cross-stage executable *terminal happy path*, no AR02–AR05 stage acceptance.

## RED → bounded GREEN tests
- Original RED test asserted legitimate terminal after independent fake observation. It failed as expected: `AssertionError ... diagnostic.terminal is False`; `1 failed` (exit 1 of pytest, shell wrapper exit 0), raw `05_EVIDENCE_INDEX/CODEX_AR02_AR05_CORE_RUNTIME_VERTICAL_SCRATCH/red_pytest.log`.
- Replacement acceptance-negative tests assert **denial** of that unsupported transition rather than pretend it succeeded. Focused new tests `22 passed in 0.62s` (exit 0), raw `.../green_probe.log`.
- Combined scoped suites (accepted AR02C, AR03A and five X10-base Python suites, plus new negative suite): `195 passed in 16.26s`, exit 0; raw `.../full_scoped_pytest.log`. Scope was exactly eight named Python test files; no 523/Direct100/provider/Production.
- Scoped Ruff on six imported/new Python source/test paths: `All checks passed!`, exit 0; raw `.../ruff.log`.
- Runtime: existing pyenv Python 3.11.15, existing pytest 8.4.2 / Ruff 0.15.20; no installs/network. Run `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src" python -m pytest -q -p no:cacheprovider <8 named suites>` in this worktree.
- Existing tests further cover T1 approval digest mismatch, forged T4 observer, stale AR05 snapshot, no client ACK, irreversible provisional publication, and native citation binding. New negative tests specifically cover tenant/principal/scope, missing grant, revocation between resolution and consumption, stale revision/TTL/digest, wrong epoch, digest claim mismatch, budget overdraft, duplicate billing, duplicate claim, unknown effect, immutable terminal notice, independent AR09 schedule.
- Probe log is a **diagnostic GREEN / stage BLOCKED**, not evidence of fully authorized integration.

## Minimal interface change proposal (requires new Master authorization)
1. AR02 owner introduces a versioned, immutable T4 observation reference with source identity, intent digest, run/tenant/task/epoch/head, authorized observer and freshness/revocation constraints; no caller booleans or fake signatures as external rights.
2. AR02 durable single-writer SERIALIZABLE/ACID journal operation `record_verified_reconciliation(...expected_head, expected_epoch, observation_ref, effect)`, atomically validates authority and makes previously unknown intent's confirmed effect eligible for verification while preserving original T3 unknown receipt in append-only history. Missing/ambiguous authority remains UNKNOWN, cannot clear or retry.
3. AR05 independent verifier pins new AR02 post-reconciliation head and evidence, and AR02 atomically CAS commits verification+terminal only with all hard gates/current grant/client delivery/rights. Ensure no false claim of physical ACK; post-terminal correction sidecar cannot reopen run.
4. Independently agree on AR02/AR04 atomic T1/T2 authority and outbox, real AR03 ReadGrant, actual external observer and trust grade, consent/external rights, canonical X10 formal ABI, required budget settlement, native Q&A evidence and irreversible publishing. None may be implied by present tests.

All X01–X09 external integration gates remain OPEN, X10 formal ratification OPEN, X11–X18 unresolved. No M26 Production, R2/Qdrant, VM worktree writes, denied AR02B-R/AR03B/LB tasks, live provider, remote tool dispatch, merge, PR, push, release or protected Q&A.
