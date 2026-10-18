# M27 G05 | AR07 Cost Governance + AR10 Governed Learning

**Scope:** exact B3-05 HEAD `7966e9c766a38a22cd91432edb5dbf2115eff305`, additive isolated Nonprod module/tests/doc only; no live adapter, billing credential, Q34, Product, deployment, integration merge or model call.

## Real observed versus synthetic

- Historical **actual MiniMax-M3** B1-01 bounded Nonprod online 12-case experiment: its *original bulk* `online_12_case_summary.json` records **1,787 input / 504 output tokens**, 12 attempted, 11 explicit model-identity rows, sum reported per-request latency **13,151 ms** (not percentile or end-to-end client timings). SHA256 original summary `9dcad462f1672e00655b015b081e2574c6d01da0ecf79a0e53728140c40e10e3` and source raw receipts `bd7f640f3ecd6a55b7db47a121890d815623e226d33f986b102c9703a4233473`.
- B1-01 final selected/corrected 12 cases separately documented **1,788 input / 548 output tokens** after one bounded replay and recalibration, but not an original-bulk denominator; do **not** combine them or treat as an invoice. Final reparse JSON SHA256 `f86bd3af11b1f60ad49d30342a0587278c8624eb83af81c0cc3e6eaf1a2e0a11`; external issuer still missing. No renewed request made for G05.
- B1-02 separately demonstrates actual MiniMax-M3 streaming and independent local Client ACK; cannot use its latency as paired identical OFF/AUTO/REFRESH/BYPASS cost ablation. Primary Cloudflare custom Worker Gateway has no authenticated live route certificate, and its earlier equivalent diagnostics were explicitly refused.
- B3-05/06's `0.01 USD`, synthetic route usage, synthetic Provider 502/503 and fixture token counts are **fixtures, not billed charges**, no evidence of Provider failover billing.
- No authenticated tariff version, independent invoice/billing export or approved Product Cache HIT exists. **Actual bill USD UNKNOWN**, realized USD savings UNKNOWN, cross-provider live failover overhead UNKNOWN, real p95 cost and end-to-end latency UNKNOWN. Do not replace with USD 0.

## Isolated policy behavior

`CostGovernor` fences task fingerprint, tenant/principal, source revision, ACL epoch, provider order, explicit source/price identity, bounded token/attempt/time/money **quotes**, and circuit-open. Concurrency uses an in-process lock. Quoted amounts are **reservations**, never inference of invoice; unverified or missing tariff rejects billed reservation, and a fixture has no actual monetary authority even when test-injected as verified. The external adapter and trust/issuer validation needed for authoritative tariff would be separate H02-owned work.

`MeterObservation` keeps source revision/timestamp, model, provider, request/attempt, provider-reported input/output tokens, immutable receipt SHA and same-clock request-start/first-text/terminal samples. Bill remains null unless the caller already possesses a separately externally authenticated invoice (the constructor flag **does not verify its signature**, and cannot be used as independent proof). Unknown usage/billing remains unknown, including when only some attempts have receipts. Failed PRIMARY attempts and FALLBACK reservations are both counted in cost/token commitments; no illegitimate fallback on auth, ACL, revoked rights, verifier failures, budget or unclassified errors.

`cost_ablation` rejects absent/unpaired modes or actual invoice; when mathematically demonstrated with deterministic fixture observations, verdict stays `HOLD`, with arithmetic strictly labelled `hypothetical_unadmitted_savings`, not real Product evidence. Product Cache default remains OFF. The real equivalent workload and invoice-priced comparison is an H03 independent experiment after authentic Gateway and rights admission.

`GovernedLearning` requires evidence/hypothesis digests rather than raw source or prompt payloads; independent evaluator and separate reviewer identities; explicit evaluate/approve/rollback, source revocation fencing, tenant/principal fencing, replay protection, negative safety check, no automatic PRODUCTION path. The nonprod approval argument models a trusted boundary but is **not a cryptographic signed external Owner or evaluator attestation**; test approval must never be passed off as formal admission.

## Evidence and formal gates

New tests cover positive and adversarial scope identity, token caps, quoted monetary caps, attempt/concurrency caps, circuit, eligible/forbidden provider fallback, meter chronology, missing/forged bills, synthetic matched/unmatched cost comparison, candidate evaluation, false improvement, tenant leakage, revoked source restore, replay, independent review and nonprod rollback. Offline tests may establish **SCOPED_PASS** only.

**G05 FULL AR07/AR10 HOLD:** same G01-G03 qualified coherent TaskContracts and actual outcomes not yet attached to this worktree, real pinned tariff/invoice and representative matched ablation not available, Cloudflare PRIMARY live deployment qualification HOLD, independent actual learning evaluation/effect + signed approval and authentic nonprod rollback unproven. No permission to promote Production. Next: H02 single integrator may inspect candidate with independent Master acceptance; H03 independently admitted live Provider/IdP/Client and billing permission required before real economic qualification.


Invoice reconciliation hard stop: once an independently authenticated bill observation exceeds a previously reserved quote, the scoped ledger sets `invoice_overrun_hold` and blocks further attempts pending independent reconciliation. The local governor is an in-process module only; it does not claim a durable distributed multi-worker counter or remote exactly-once billing.


## G05 continuation hardening (2026-10-18)

- Provider meter observations must match reservation **provider, exact upstream model ID, source revision, TaskContract fingerprint and tenant/principal**. Excess observed tokens or alleged invoice spend above reserved quote fences subsequent dispatch until external reconciliation.
- Learning candidates are now independently canonical-sealed across state, roles, evidence digests and transition history within the isolated process; externally forged candidate objects and out-of-band status/evidence mutation fail closed.
- FALLBACK cannot reserve using a caller's bare error claim. An earlier reserved PRIMARY attempt must first record a matching operational failure classification, with zero answer text emitted; the failure receipt is single-use, cannot be forged or replayed, and no new retry is allowed solely due to auth, ACL, revocation, obligations or verifier failures. This is **local typed process evidence**, NOT cryptographically authenticated custom Gateway failure proof.
- Paired fixture invoices flagged by test input cannot qualify real pricing: the ablation function now always returns HOLD and an explicitly hypothetical arithmetic field even when four modes and test billing flags are supplied. An admitted separate external verifier is required before a successor may implement real savings admission.
- Cross-version test strategy is explicitly `PYTHON 3.14 -m pytest --noconftest` with a manually scoped `knowledge_engine` import package and reused pure-Python pytest from 3.11. This tests G05 and B3-02 router isolated modules on 3.14; it does **not** qualify full inherited Knowledge Engine initialization or Production.
