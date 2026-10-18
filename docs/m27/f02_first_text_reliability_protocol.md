# F02 Stage: independent Nonprod reliability experiment
Parent: B2-03 a9ba93080402c885bcd3d6917d5ba487e4c9546c.
This is a new additive standalone runner, not Q34 native Product or Cloudflare custom Gateway qualification.

## Outcome / decision
- One actual VM MiniMax-M3 streaming request only per run, never a silent second provider, model_identity required before publishing.
- Real separate OS HTTP/SSE client sees two distinct material claim texts, each source-byte verified and ACKed before terminal.
- Full final answer must satisfy both frozen obligations; no terminal answered without actual provider_done.
- Sentence punctuation OR newline may delimit the two generated claims, with no substitution of fixed model outputs.
- Unsupported claim, out-of-scope speculation, extra negative tail, false identity, missing ACK, missing provider_done, revoked/expired source and client cancellation abort truthfully.
- All exact source rights are self-owned Nonprod and narrow fact verifier, not a third-party signed semantic issuer.

## Precommitted A/B experiment
- Identical question/obligations, two predeclared prompt variants F02_CASE_VARIANT=A|B.
- Run order A1,B1,A2,B2 (four single-call bounded trials). Per call maximum generated model output 320 tokens, VM 45 s HTTP provider timeout, no retry, 6 s per-claim ACK, whole client time cap 85 s.
- This is a small targeted exploratory series, not broad statistical reliability or formal first-answer p95. A stronger release-grade result requires sufficiently large independent unseen and authorized cases.
- All failures count in the denominator. Safety fail-closed (partial or abstention) is not a success.
- Server/client/VM logs, SHA256 and full attempt receipts are preserved. No live Cloudflare request.
