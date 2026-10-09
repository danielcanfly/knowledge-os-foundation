# AR09A Codex Offline Receipt

Status: implementation candidate; final command receipts are recorded after scoped checks.

## Scope and independence

- Baseline: `90bcba2d1b06f96144708abff5786d7046df0784`.
- Pure stdlib synthetic oracle. It imports neither AR04A nor AR05A candidate code,
  has no provider/network/state mutation hooks, and never executes a remote send.
- Original raw-byte SHA-256 and canonical synthetic JSON SHA-256 are separate.
- Only test labels are emitted: `EXPECTED_DENY`, `EXPECTED_UNKNOWN_PROOF`,
  `EXPECTED_UNKNOWN_EFFECT`, `EXPECTED_STREAM_FAIL`, and
  `EXPECTED_ACCEPT_FIXTURE_ONLY`; frozen runtime enums are untouched.

## Implemented oracle families

Strict JSON duplicate/type/safe-integer/timestamp checks; required and unknown
authority fields; trust-root revocation/self-verifier; tenant/task/version/audience,
delegation/consent, policy/head/lease freshness; source tenant/revision/digest;
native-versus-synthetic byte/citation/span identity; progress/substantive/terminal
stream ordering and client delivery; price/usage uncertainty; deterministic
two-writer CAS and POSSIBLY_SENT/UNKNOWN schedules. All schedules report zero sends.

## AR01V V01–V50 coverage

Implemented: V01–V02, V06–V09, V11, V14, V16–V17, V20–V22,
V26–V27, V29–V33, V35, V39–V45, V48–V50.

NOT_RUN: V03–V05, V10, V12–V13, V15, V18–V19, V23–V25, V28, V34,
V36–V38, V46–V47. These IDs are explicitly retained as `NOT_RUN`; no coverage
is inferred.

## Qualification boundary

Scoped pytest/Ruff results, log hashes, source hashes, and commit identity are
reported by the Stage 3 receipt outside this Git tree after the final commit.
The oracle is T0/T1 synthetic evidence only. It does not prove a real trust root,
native Q&A equivalence, cross-language canonicalization, hidden corpus quality,
provider economics, or close X01/X02/X09/X10/X11.
