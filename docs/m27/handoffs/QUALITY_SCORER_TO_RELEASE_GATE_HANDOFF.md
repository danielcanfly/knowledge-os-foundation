# QUALITY_SCORER_TO_RELEASE_GATE_HANDOFF

State: `M27_INDEPENDENT_QUALITY_GATE_NOT_READY_WITH_DIAGNOSIS`

## What is complete

- Independent quality artifact schema and validator added.
- Source receipt SHA-256 linkage enforced.
- Evaluator identity/provider/model, rubric version, scoring policy, per-case evidence digest, scored-case count, and production-no-mutation requirements are fail-closed.
- Release quality hard gate no longer accepts a bare numeric score as sufficient independent quality evidence.
- Prior isolated first-answer-text streaming gate remains passed and unchanged.
- Focused tests pass.

## Remaining blocker

No real semantic quality score was computed. The configured repo evaluator seam is MiniMax-backed, but evaluator credentials are unavailable in this session. The accepted full523 receipts contain 237 verified-answer rows but no answer/evidence payloads, so they cannot be semantically rescored without rerunning answer generation, which this session forbids.

Required next input is either:

1. a real independent evaluator plus accepted payload-bearing answer/evidence records linked to the current full523 receipt SHA-256, or
2. a deterministic human-review artifact with reviewer identity, rubric version, scoring policy, per-case scores, digest, source linkage, and no-production-mutation proof.

Do not substitute 523/523 admission pass, citation rate, safe-terminal correctness, or latency for the semantic quality score.

Canonical source receipt SHA-256: `e2f5677e1f81b056697ffea791e986efde368614e8ad296f3b5d99f173446137`.
