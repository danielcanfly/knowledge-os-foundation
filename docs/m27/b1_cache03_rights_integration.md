# M27 B1-04 CACHE03: eligibility, ACL, TTL and revocation semantics

## Admission boundary

This is **scoped isolated Nonprod source code**, branched from frozen CACHE01
`1ac91967f6760edf0e0934be2f4dc7f71f404ead`. No shared M26/M27
API/composer, CACHE01 ABI, CACHE02/04, D01, Q34, Product route, or public
cache publication was modified.

- Default `feature_enabled=False`; BYPASS/REFRESH, non-QA, LIVE and RELATIVE
  requests never do a cache lookup.
- `evaluate_candidate(...)` always returns a non-releasing `Decision`.
  `cache_hit_admitted=False` and `store_write_admitted=False` universally.
  It never calls CACHE02, exposes a cached answer, writes, or signs.
- The only deliberate positive scoped result is `VERIFIED_FIXTURE_ONLY`
  for a complete synthetic claim proof and explicit test issuer callback.
  It does **not** qualify as an authenticated Product/issuer HIT.
- An `EXTERNAL_QUALIFIED` string + permissive callback still returns
  `FORMAL_ADMISSION_HOLD`. Hashes/fixture booleans do not authenticate
  external signers.

## Contract handoff for H02

File: `src/knowledge_engine/m27_b1_cache_policy.py`.

`Actor(tenant_id, principal_id, actor_id, auth_context_sha256,
authenticated, issuer)` is **trusted server-side context only**; never accept
those fields from the UI. Actor must equal tenant/principal and authenticated
context in CACHE01 request. Real IdP/auth-context binding remains unimplemented.

`FixtureAuthority(path, fixture_only=True)` holds an isolated SQLite
source-rights registry. `provision_fixture` accepts an exact parsed CACHE01
envelope, one current independently supplied citation binding per source,
and UTC consent expiration. This is test-only intake, not external source
proof. Rights rows use composite `(tenant, principal, source_id)` scope,
full identity/source/policy fingerprints, ACL, consent, status, and
monotonic local revocation epoch/generation. Duplicate scope registration
is disallowed. Source revisions transition to `SOURCE_REFRESH_PENDING`
with ACL disabled until a **new** external custody path exists.

`snapshot` performs current rights, actor, source manifest, source revision,
corpus/rights/ACL SHA, policy/verifier/admission/embedding versions, epoch,
source presence and consent checks. It returns a fingerprint and current
citation bindings. The evaluator additionally executes CACHE01
`screen_candidate` (including candidate lifecycle TTL), explicit semantic
collision rejection (negation, numbers, currencies, dynamic/relative/current
questions, source-injection commands), exact citation binding, and
claim-level proof & question-obligation validations. A fresh
`is_unchanged` authority read guards revocation/refresh between verifier
work and final policy decision.

`mutate_fixture` supports `REVOKE`, `DELETE`, `ACL_DOWN`,
`CONSENT_WITHDRAW` keyed by tenant/principal/source/event. Events are
persisted and idempotent by key, conflict on reused event IDs, increment
source generation, and disable ACL. `update_source_fixture` is an
atomic CAS that increments epoch and refuses revoked source updates;
fresh revised source cannot inherit older citation authority. All
source rows and event receipts are **local fixture records**.

## Verified semantic revalidation envelope

`PROOF_SCHEMA=m27.cache03/claim-proof/v1` is strict, with issuer and
distinct verifier/generator labels, exact request/candidate/question/answer
and source-manifest digests, bounded proof time, equivalence, complete
claim coverage, each claim's normalized text hash and `ENTAILED` decision,
one or more exact current citations, and each requested answer obligation
bound to supported claim IDs. Text overlap, embedding similarity, same
language or client-controlled booleans are **never** enough to release.

An independent trained/qualified semantic issuer must actually
**re-evaluate** entailment for every answer claim against current source
evidence and independently validate question-specific answer obligations
and coverage. This source module can validate its receipt structure, but
cannot locally establish semantic truth or a real signature. Do not
mistake proof objects fabricated by a local test callback for an actual
verifier, or MiniMax synthetic evaluation for independent Product authority.

## Backup restore and revocation consistency

The authority SQLite file MUST be separate from replaceable cached
artifact bytes. Test 1 persists candidate bytes, commits a source revoke,
restores the **old artifact only**, reopens the authority after restart,
and rejects the restored descendant. Test 2 races authority mutation
after claim verification and before final read, requiring failure.
Source-update CAS also refuses stale citation reuse. This is a local
durability test, **not** proof of secure erasure of external stores,
other descendants, replica media, WALs, snapshots, or disaster restores.

A restore of the authoritative SQLite DB itself could roll back epochs:
**not addressed here**. Production requires a nonrollbackable custody
register or externally authoritative epoch high-water mark, cross-store
revoke fanout/reconciliation, complete source deletion receipts,
transactional refresh/CAS, and an audit of every cache/materialized
view before any HIT. Never use G04 local fixture as live authority.

## Independent gates still HOLD

1. H01/C02 registered external issuer, genuine independently checked
   signature and authorization, real source/ACL/IdP proof, consent and
   deleted-source version custody. VM-side provider keys remain on VM.
2. Model qualification and separation of generation/verifier issuers,
   real claim decomposition/coverage validation, anti-injection tests
   with current licensed sources. F01 MiniMax online tests alone
   are neither an independent issuer nor native Product admission.
3. Atomic integration with CACHE02 durable storage and CACHE04 native
   UI/mode is **H02-only**. The local SQLite fixture cannot be
   connected directly to the Product as a privileged authority.
4. Restore safety beyond local artifact backup, external revocation
   propagation, persistent nonrollbackable epochs and citation invalidation.
5. Owner/H01 source custody, signed X01-09, blinded eval, staged gate
   and separate Product/Production authorization.

## Test command

`python3 tests/test_m27_b1_cache_policy.py -v`
and frozen CACHE01 regression
`python3 tests/test_m27_b0_cache_contracts.py -v`.

Only Python standard library is used. No local LLM, GPU, paid inference,
Cloudflare probe, VM secret, live model, protected signer or Product route
is required. Synthetic fixture test positives are clearly labeled.
