# K03V | Verified Rights Adapter v1 (offline-only)

**Status:** `VERIFIED_RIGHTS_ADAPTER_OFFLINE_PASS` is available **only after**
the three-file commit + independent Master review. This module is explicitly
**feature-off**, **not AR03_STAGE_DONE**, and is not real Provider/IdP authority.

## Code contracts (not signed Provider rights)

The new isolated module
`src/knowledge_engine/m27_ar03_verified_rights_v1_experimental.py` adds:

- `SourceAuthorityEvidenceV1` holds an *untrusted* opaque assertion and
  untrusted metadata. `externally_authenticated`, `manifest_signed`,
  `citation_offsets_safe` and arbitrary untrusted descriptions have **zero**
  authorization effect. In particular, the legacy AR03A fixture boolean is
  **never** consulted.
- `IssuerKeyRegistry` pins issuer, key ID, audience, algorithm, trust-store
  version and active status at a trusted composition root.
- `ProviderAuthorityVerifier` defines the independently configured boundary:
  verify opaque issuer evidence, obtain a trusted time, fetch independent
  original-source bytes and current Provider ACL/consent, verify current AR02
  checkpoint/head, and atomically reserve and find nonce/checkpoint uses.
- `VerifiedAuthorityClaim` carries effective actor/delegation chain, exact
  resource/purpose/operation, task/run/checkpoint, source revision/native IDs,
  original digest, consent identity and generation fences. This object is
  meaningful **only** if returned by the configured trusted verifier.
- `NativeCitationPinV1` and `ClaimSpanV1` bind provider/account/resource,
  native source ID, revision, original SHA256 and literal UTF-8 byte offsets.
  Original source bytes are never normalized, rewritten, or reordered.
- `AuthorizedReadPlan` records only a validated local read/cite decision.
  `publication_authorized` is **always False**. Nothing in a read plan or
  in an AR03A/X11 metadata decision can grant publish rights.
- `PublicationDecision` needs a **second, separately verified** publish
  assertion, an exact intended publication audience, a previously reserved
  read proof, a current independent AR02 head and renewed current byte/ACL
  checks. It is **not** an AR02 terminal commit or release authorization.

The verifier is injected by trusted server configuration, never provided
by a model, tool, skill, memory store, prompt, or caller-controlled object.
Absent verifier, invalid/unknown/inactive issuer/key, absent or malformed
claim, stale time/nonce, source/consent/ACL/head drift, unsafe citation byte
offset or unavailable original bytes all deny. Authenticated effective actor
is compared to the request, including exact (subject, delegated principal,
delegated_by, chain). Operations intersect by resource and purpose, with
no `execute`, memory-write/delete, or publication upgrade.

## Synthetic offline fixture, NOT a security proof of a real Provider

`tests/test_m27_ar03_verified_rights_v1_experimental.py` contains
`IndependentFixtureVerifier`, marked `TEST_FIXTURE_ONLY`. It is deliberately
implemented **outside** the application module, with a sealed deterministic
mapping from exact opaque fixture bytes to fixture claims. Its trusted
observations contain independently held test bytes and ACL/consent state,
and its nonce/checkpoint fence is an in-memory fake. This mapping is **not
cryptography**, signature validation, an IdP token, trusted transport or a
Provider ACL service. It may be used exclusively for offline deterministic
positive/negative tests.

The new test cases cover issuer/audience/key/algorithm/TTL, delegated actors,
cross-tenant/source/resource/purpose, scope/right narrowing, replay, consent
and revocation, source ETag/revision, byte tamper, invalid UTF-8 and claim
offsets, forged skill/tool/memory descriptions and safety booleans, race/fault
injection, old checkpoint, and read-to-publish escalation. Current assertion
count and scoped command terminal receipts are in the worker report and
`05_EVIDENCE_INDEX/K03V_AR03_VERIFIED_RIGHTS_SCRATCH/`. Existing
`test_m27_ar03_context_broker_experimental.py` runs as a regression only;
its permissive mock fixture remains unchanged and is not a right.

## Bounded acceptance and missing production validator

Not accepted or deployed: a real IdP/Provider issuer and key/JWKS trust
configuration; approved JWT/COSE/token introspection verifier and strict
algorithm, signature and rotation rules; authenticated resource ownership,
ACL/consent observation/freshness/revocation endpoint; owner-approved lawful
purpose and data-subject consent; AR02 durable transactional nonce reservation,
signed checkpoint/head and atomic compare-and-swap; actual source-fetch
transport, time source and snapshot attestation; AR05 independent citation
verifier/publication signer/hard gate; AR06 exclusion/retention propagation;
production credential/transport or live tenant; I01 ABI and Release gates.

The offline fake's in-memory nonce reservation has **no multi-process or
crash durability**. The verifier Protocol defines the atomic boundary but
does not implement crash-recovery, revocation subscriptions, trust store or
distributed race guarantees. Multiple sequential source observations do
not replace a Provider atomic snapshot or AR02 CAS. Treat any exception as
denial or fail the request; never silently fallback to metadata-only access.
`PublicationDecision.authorized_offline` is a synthetic proof decision, **not**
a production publication permit. No real rights may be inferred from it.

**Safe integration requirement:** I01 may import DTOs under an explicit
disabled feature flag, but MUST fail closed until separately reviewed,
configured and attested real verifier/Provider/IdP/AR02/AR05 components are
present. Keep existing AR01/AR02 wire and accepted AR03A/X11 untouched.

## Independent authority matrix mapping

The A03 35-item audit
`05_EVIDENCE_INDEX/A03_AR03_AUTHORITY_SOURCE_MATRIX.md` motivates:
1-14 issuer/actor/scopes/expiry/replay; 15-24 original bytes,
revision/namespace, consent and exclusions; 25-29 forged descriptions/native
citation spans; 30-33 unsupported budget/atomic plan protections; and
34-35 separate publish authority. **Budget ownership, real durable replay,
provider transport, trust rotation and independent publish signing remain
external**, not reclassified as accepted through a local fixture.
