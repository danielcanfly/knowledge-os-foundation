# C02 | Versioned AR02 reconciliation v2 | Isolated offline receipts

**Scope:** C02 experimental, no runtime or release integration. Base Git `76962a7466b9abb8241fbdcb4a2af867716a0ae0` (C01). Exactly five new paths, zero accepted-file edits. Signed test fixtures are NOT real authentication.

## Architectural boundary and post-T3 ownership

Accepted AR02C `Kernel` performs public `reserve`, `charge`, `intent`, `claim`, `possible_send` with its own head 0→5 and `UNKNOWN_EFFECT`. Old `terminal` still correctly denies. C02's versioned `ReconciliationKernelV2` captures this public read-only T3 snapshot and starts **a separate in-memory successor head**, not an undisclosed mutation of accepted `Kernel.runs`. Its head 5 is the inherited T3 event; head 6 is T4 reconciliation and head 7 is terminal. The original remains terminal=false and UNKNOWN, intentionally.

A single-process `threading.RLock` serializes v2 CAS checks and append-only tuple events. The original head/epoch/intents/charges snapshot is verified unchanged at each operation. Original T1 digest is retained in every immutable event; observer receipt and publication proposal reference post-reconciliation current head/hash, with per-step hash chaining. The original accepted AR02C has **no public reconciliation method**. This is thus NOT a durable-current-head transition in AR02C, NOT recovery semantics, and does NOT claim ACID, linearizability across processes, authoritative observer or real dispatch. A real integrated successor must own the original T1/T2/T3 durable writer in one transaction domain before migration. Until then: **AR02_DURABLE_BACKEND_GATE_OPEN = TRUE**.

## T4 proof gate

The public `record_verified_reconciliation` consumes `ObservationV2` carrying run, tenant, immutable T1 digest, source id/revision/digest, exclusion generation, epoch, expected head, observer id/key, capture and expiry times, AR04 `ObserverEvidence`, mock HMAC. Server-configured test observer key + independently configured AR04 fixture observer must agree; executor text, booleans or untrusted observer cannot raise trust grade. Original AR04 `reconcile` public method must report matching effect. Only `CONFIRMED_APPLIED` and visibility-complete authoritative mock `CONFIRMED_NOT_APPLIED` settle an unknown. Ambiguous, unsigned, forged, stale, contradictory and replayed facts remain denied; no retry is performed. Idempotent identical observation returns original v2 receipt. Conflicting observations cannot overwrite the first. T3 unknown entry remains immutable history, and the original AR02C UNKNOWN persists.

AR03 accepted `select` re-evaluates fixture grant, source bytes pin/revision/TTL/consent at both T4 and terminal. A separately supplied **test-only mock context authority** provides a stable snapshot with mutable test controls for revoke, revision and exclusion generation; any drift fails closed. `GrantFixture.externally_authenticated=True` is *only a fake flag* and does not verify real Provider rights. Consent/exclusion/revision changes must be attested outside C02 for a real pipeline. Neither mock HMAC nor fake independent observer has IdP/Provider-issued identity.

## AR05 and terminal

The new v2 `current_snapshot` binds configured task/version/attempt/outcome id/digest (not fields adopted from a verifier request) to actual v2 head/epoch/hash. The public accepted AR04 T5 `propose_verification` must match the observed effect; accepted AR05 `VerificationPublicationGate.evaluate` is invoked internally with configured **test verifier keys**, exact post-T4 snapshot, native fixture evidence/citation identity and all required hard gates. `status=SUCCEEDED` requires applied proof, with no unreconciled effect, no unapproved AR04 action, no missing claimed fixture client ACK and no stale observer/consent/source. `terminal_cas` increments the separate successor head once. Accepted AR02C `terminal` is deliberately never bypassed or called with private-state changes. AR05 only provides `ELIGIBLE_PROPOSAL`; fake client ACK is NOT a real delivery receipt and there is no actual publication.

Postterminal correction/retraction is generated using accepted AR05 `append_terminal_notice` as an append-only sidecar; it leaves terminal and journal head immutable.

## Deterministic mock loop and negatives

C02 versioned adapter executes real accepted **public** APIs: AR03A `select`, AR02C budget/T1/T2/T3, AR04A T1/T2/T3/T4/T5, AR09A unknown-effect oracle, AR05A verification/publication proposal, plus versioned v2 T4 reconciliation, terminal CAS and AR05A notice. Source bytes/citations and grant are strictly synthetic. A verified substantive fake text frame precedes terminal frame, with fake ACK. A failure of the old accepted `Kernel.terminal` is explicitly tested RED first. The positive mock closed loop is an additional test, not a replacement for C01 failure diagnostics.

Adversarial suites cover cross-tenant, T1/epoch/head, signature/observer, applied versus uncertain-negative proof, stale capture/proof clock, duplicate receipt/conflict/replay, grant/exclusion/consent/revision drift between T4 and terminal, legacy drift, unknown effect, bogus task/attempt/outcome, stale AR05 head/hash, forged verifier, duplicate/missing/failing hard gates, native citation and first-text/ACK gate, double charge and terminal/sidecar immutability. Raw specific test counts/exits, SHA256 and commit are preserved in sibling C02 evidence index.

## Explicit non-claims and follow-on ABI

- **NO** real durable AR02 transition, ACID backend, WAL/outbox, restart/checkpoint or crash-replay guarantee.
- **NO** real Provider/IdP/source/observation authorization, actual external tool effect, approval service, client ACK, independent scorer or trusted signer.
- **NO** M26/Product wiring, VM writes, real Q&A, external provider network, release pointer, tool safety refusal bypass or deployment.
- **Open ABI:** one transactional AR02 append-only journal must own T1 intent, budget/permit/outbox, T3 unknown, authenticated T4 observer receipt, atomic source/consent/exclusion fencing, AR05 hard-gate current-head compare-and-swap, plus replay/late billing. Signer/observer roots and client ACK must be independently authorized. C02's in-memory successor is only evidence for versioned interface feasibility.
