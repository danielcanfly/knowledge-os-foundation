# AR04A Codex Offline Receipt

Status: implementation candidate; final command receipts are recorded after scoped checks.

## Scope and trust boundary

- Baseline: `90bcba2d1b06f96144708abff5786d7046df0784`.
- Pure in-memory synthetic T1–T5 handshake. There is no provider adapter, socket,
  durable AR02 journal, production route, credential access, or terminal-state writer.
- `ActionIntent` preserves the relevant frozen AR01D fields. `IntentCandidate`,
  `DispatchClaim`, `SendBoundary`, `ObserverEvidence`, `Reconciliation`, and
  `VerificationProposal` are explicitly experimental sidecars.
- A T3 marker means only `POSSIBLY_SENT`; uncertain outcomes cannot be blindly
  retried. T4 evidence must come from a separately configured fake observer. T5 is
  a proposal and never marks a run terminal.

## Negative fixture matrix

Tests cover wrong tenant/delegation/resource scope, stale epoch, consumed or
digest-mismatched approval, unknown price, zero budget, duplicate claims, lost T1
ack idempotency, T2/T3 crash cuts, remote-apply ambiguity, executor/observer
contradiction, eventual-absence uncertainty, non-idempotent blind retry denial,
cancel before/after T3, unverified compensation, and self/forged verification.
Every path asserts or preserves zero provider calls.

## Qualification boundary

Scoped pytest/Ruff results, log hashes, the three file hashes, and commit identity
are reported by the Stage 3 receipt outside this Git tree after the final commit.
Mock checks do not close X01–X09, prove AR02 durability/serializability, authenticate
real policy/approval/observer identities, or authorize Production/provider use.
