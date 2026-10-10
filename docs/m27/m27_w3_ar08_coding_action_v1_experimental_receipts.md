# S08C | AR08 Coding/Action Controlled Runner v1 | 2026-10-10

## Claim and envelope

**CODING_LOCAL_CONTROLLED_RUNNER_PASS** means a new feature-off, local ephemeral arithmetic coding fixture can be admitted against an existing SQLite AR02 run, receive an AR04 fixture-only permit with an approval provided by the caller, commit AR02 reserve/approval/intent/outbox/claim, record durable UNKNOWN before one real subprocess launch, observe actual file bytes and Python exit status, use separate AR05-style evidence types and a separately provisioned local HMAC reviewer, reconcile an in-process independent fixture observer, and commit LOCAL_VERIFIED_APPLIED in the local journal.

No real CI, real client ACK, remote tool execution, real IdP, external policy approval, filesystem containment by the OS, network/provider action, Git push, release, or external quality outcome is asserted.

- Contract version: S08C-CODING-LOCAL-v1.
- Task: immutable CodingTaskV1 including RunIdentity, expected AR02 HEAD, operation/args, source revision/hash, single idempotency key, exact program and command IDs.
- Intent: immutable CodingIntentV1 contains AR04 ActionRequest, program byte hash, initial AR02 head.
- Receipt: immutable CodingReceiptV1 preserves identity, intent digest, claim, journal head, launch count, real exit code, output bytes and hashes, source SHA, sandbox removal indication and zero real provider/effect counters.
- Program allowlist: exactly fixed-arithmetic-fixture-v1, generating answer.py from two validated integers and add/mul.
- Command allowlist: exactly python-isolated-fixture-test-v1, invoking pinned sys.executable with -I -B test_fixture.py, no shell, with fixed generator-owned test script and sanitized child environment.
- Workspace: new TemporaryDirectory nested in a caller-supplied, canonical, non-world-writable subdirectory strictly under OS temp root. Never accepts repository path, original source tree, sibling worktree, arbitrary output path, symlink temp root, caller code or caller argv. O_EXCL/O_NOFOLLOW regular-file checks defend replacement and traversal. Files deleted after execution.
- Action: AR04 PermitSandboxV1 with single fixed rule, strictly feature-off registry, caller-provided ApprovalDecision and AuthoritySnapshot, and bound AR02 durable writer receipt. attempt_external is NEVER called.
- Durable: AR02 SQLite WAL/FULL, reserve=1, fixture approval, one-time outbox ACK, T3 UNKNOWN before process, reconciled fixture T4, one charge and locally HMAC-authorized T5. No relaunch after UNKNOWN; a failing process, timeout, forged or missing evidence or unexpected interruption remains nonterminal. AR02 local HMAC is not an external issuer or signer.
- Verifier: caller-provisioned non-generator IndependentLocalFixtureVerifier implements an AR05 typed evidence review port consuming ArtifactEvidenceV1 / ExecutionReceipt and yielding VerifierDecision. It re-opens actual source and independently checks hash, length, command, cwd, exit, stream hashes and exact stdout. Separate in-process observer identity and independently provisioned AR02 fixture HMAC are required for local T5. AR05 full propose_eligibility authenticated transport/citation/client-ACK gate is NOT run or satisfied. No AR05 real publishing authority is claimed.

## Real regression proof and negative categories

The scoped pytest exercises actual generated source, actual isolated Python child exit0, multiplication, deliberate failing test exit1, and independent evidence re-open. More than 30 negative/fault tests cover contract/version/program/argv injection, tenant/principal escape, stale AR02 head, approval/permit/worker lease drift, symlink and repository path rejection, duplicate file, claim or billing, forged CI flags, tool stdout prompt injection, reviewer impersonation, missing durable ACK, command timeout, simulated interrupted spawn, simulated ENOSPC, invalid local HMAC and unverified server ACK.

The executable negative faults remain nonterminal when the outbox has entered POSSIBLY_SENT; runner never replays effects. An AR05 mock verdict or runner-generated output cannot independently self-approve an external outcome. Successful local HMAC fixture is precisely NOT genuine signed real authority.

## Explicit OPEN gates

1. AR03 authenticated IdP/provider grants and original protected source rights, provenance, TTL and external revocation.
2. AR04 OS-level confinement, independently authenticated policy issuer, real effect observer and remote coding-action permissions.
3. AR05 external trust/signer/CI provenance, process attribution independent of this fixture, true server/client ACK.
4. AR06 real memory deletion/retention consent; AR07 real provider billing; AR08 external TaskOutcome and AR09 outcome grading.
5. REL01 523-case cited final-answer/p95/first-text gate; REL02 rollout and W4 I02/E09 independent integration acceptance.

REPORT.md is evidence handoff, not Master acceptance. Source/tests are additive feature-off in the named worker worktree.
