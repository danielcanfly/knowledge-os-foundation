# K04P | PermitSandboxV1 isolated component receipts

2026-10-10 | VERSION 1 | FEATURE OFF | NOT RELEASED

## Isolation and immutable boundaries

Exactly three newly allowlisted files: new m27_ar04_permit_sandbox_v1_experimental source, adversarial tests, and this document. No accepted AR01/AR02/AR04A/C02/T02 module or native route is rewritten; no access to historical refused K04 environment inspection, AR02B-R patch, AR03B grant, V05 patch, another worktree, Production or real Provider.

SANDBOX_BOUNDARY_LOCAL_COMPONENT_ONLY. This is an in-process deterministic component, NOT an OS sandbox nor a real process isolation layer. FEATURE_ENABLED=False and REAL_DISPATCH_AUTHORIZED=False are constants; policy compile rejects enabling either one. No shell, subprocess, network, arbitrary file mutation, remote IdP/Provider or live executor is implemented. The synthetic adapter is an allowlisted ID, not a callable provider. simulate_fixture creates SIMULATED_NOT_DISPATCHED records; it does not cross T3.

## Versioned contract and controls

- ActionRequest.digest() commits run/tenant/principal/delegation, operation, capability/version, resource, recipient, arguments digest, idempotency key, intent version and lease epoch under local domain separator. This is a synthetic hash, not a signature.
- Registry compiles exact allowlisted capability/operation/version and conservative per-tenant resource namespace. Denies mapping gaps, traversal, encoded escape, separators, aliases, wildcard operations, invalid budget and adapter not prelisted.
- AuthoritySnapshot is frozen and carries effective actor/delegation, worker, tenant/run, lease epoch/expiry, consent expiry/generation, revocation generation, head and positive budget; authority is rechecked at every state transition.
- ApprovalDecision binds issuer, approval ID, exact intent digest/version, tenant/run, lease epoch, consent/revocation generations and expiry. One-time approval is consumed after checks. Fixture issuer labels are not authenticated IdP signatures.
- Permit binds request, frozen head, worker, cost, consent/revocation, expiry and issuer. Mutation or stale head fails closed.
- DispatchClaim always includes typed DurableWriterReceipt from WriterPort. MockWriterPort returns durable_verified=False, outbox_ack=None, mock_only=True. Bare booleans/mismatches are denied. There is NO real AR02 atomic journal transaction in this component.
- attempt_external checks claim/current fence/receipt; missing durable ACK denies T3. Even a forged verified ACK cannot enable external dispatch because real_dispatch_authorized is always False.
- MockAttempt and ObservedEffect are independent contracts. An observer identity, issuer and grant separate from fake adapter must bind exact claim/tenant/resource/digest. Incomplete visibility, unknown absence and missing provider ACK are UNKNOWN_EFFECT. Synthetic CONFIRMED_APPLIED_FIXTURE never means real success or external T4 certificate.
- No blind retries: positive, negative or unknown fixture outcomes never permit physical retry. Local idempotency sets are not crash-durable or distributed exactly-once.
- Nonempty observation citation IDs are rejected to block synthetic source citation laundering. Composite partial results remain incomplete/unknown and no fixture can authorize terminal.

## Future I01 adapter seam (DESIGN ONLY)

1. AR02 sole writer atomically validates actual issuer/consent/budget, freezes T1 intent, one-time approval, claim and outbox under serializable head/epoch CAS.
2. AR02 returns authentic, durable commit and claim/outbox ACK. Missing or lost ACK means no T3; reconcile claim on restart instead of repeat send.
3. Separately approved physical AR04 adapter checks provider capability, exact permit and current lease at attempt boundary, with real process sandbox and provider idempotency scoped by contract. Unknown remote effects do not trigger resend.
4. Independent authorized observer reads actual post-resource/version under scoped source grant with complete negative visibility. AR02 sole writer commits T4 under current CAS.
5. Independent AR05 verifier checks real artifact execution, source bytes/citation spans, outcome and authenticated client receipt. AR02 alone commits T5 verified terminal. AR09 independent holdout and invoice evaluation remain external.
6. Missing actual durable backend, signer/IdP, provider authorization, consent governance, observer/read rights, real OS sandbox, client transport and production release approvals are OPEN. I01 NOT AUTHORIZED.

## Acceptance

Positive deterministic fixture and adversarial deny/crash tests are in the new tests module. Scoped test count, relevant regressions, Ruff, Git show --check, commit, SHA256 and clean worktree are independently captured in the external K04P scratch logs and worker report.

Bounded local code PASS is conditional on real exit-zero logs. Even if green, AR04 REAL INTEGRATION NOT ACCEPTED; STAGE NOT DONE. Historical safety refused actions remain frozen.
