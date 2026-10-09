# AR05A Codex Offline Receipt

Status: implementation candidate; final command receipts are recorded after scoped checks.

## Scope and trust boundary

- Baseline: `90bcba2d1b06f96144708abff5786d7046df0784`.
- Pure offline verification/publication proposal service. It cannot call a provider,
  emit live SSE, publish, write an AR02 journal, or transition RunState.
- Trusted fake verifier keys and signer bindings are constructor configuration,
  outside the candidate receipt. There is no caller-controlled `verified=true`.
- The positive result is `ELIGIBLE_PROPOSAL`, always with
  `terminal_committed=false`; only a future AR02 CAS could commit terminal state.
- `NativeEvidenceFixture` models a non-mutating native view. Original synthetic
  bytes, digest, source/revision, citation order, and claim spans must match.

## Negative fixture matrix

Tests cover tenant/run/attempt/task-version mismatch, changed outcome digest,
stale journal head/lease, untrusted/self signer, invalid signature, expired proof,
UNKNOWN_EFFECT, missing/indeterminate hard gate, immutable terminal, original byte
digest mismatch, citation reorder/span loss, synthetic/native substitution,
progress-only and terminal-only timing, uncited verified text, absent client ACK,
and irreversible publication with provisional frames. Retraction/correction is an
append-only sidecar with a monotonic cursor and never reopens terminal RunState.

## Qualification boundary

Scoped pytest/Ruff results, log hashes, source hashes, and commit identity are
reported by the Stage 3 receipt outside this Git tree after the final commit.
This mock does not establish real verifier trust, native source authenticity,
client delivery, journal atomicity, Q&A no-regression, or close X05/X08/X09.
