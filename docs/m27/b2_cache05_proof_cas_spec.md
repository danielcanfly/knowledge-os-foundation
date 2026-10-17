# B2-01 CACHE05 | Nonprod final-proof → rights → atomic CAS specification

## Source identity / owned additions
- Exact parent is CACHE01 commit `1ac91967f6760edf0e0934be2f4dc7f71f404ead`.
- CACHE02 committed `6b7f71cc7a60695916c1444447923fe60f548b80` is inspected/read-only at `m27_b1_cache_store.py`.
- CACHE03 committed `adf7ed74079a78c3ad6cca4be1079cd782ff0e01` is inspected/read-only at `m27_b1_cache_policy.py`.
- CACHE04 committed `dccb84d4e10894d86ff6658bc9f268ea01de0b64` is inspected/read-only at `m27_b1_cache_native_adapter.py`.
- No existing shared source/API/Composer/TaskContract touched. No branch merged. All execution on local fixture data, no model or Cloudflare/MiniMax calls.

## Strict boundary: NO real product write or semantic HIT
This module is *not* a public writeback API and provides **no signed Product permission**.
`FinalWriteGate.product_write` always gives `FORMAL_ADMISSION_HOLD`.
`FinalWriteGate` constructor refuses invocation absent fixture environment,
an actual CACHE02 fixture store, CACHE03 fixture authority, the separate in-memory
TEST verifier key, and explicit fixture_only. `admit_fixture` writes TEST data
through CACHE02's **private fixture-only** `_fixture_cas` (real SQLite WAL, FULL
synchronous, BEGIN IMMEDIATE, integrity MAC, CAS), not public
`compare_and_swap_verified` (which intentionally always returns false).
Fixture HMAC is a *test assertion authenticity mechanism*; it does not verify
semantic truth or qualify signer/issuer, nor does it implement H01 formal signoff.
No client can obtain cache HIT or released answer using these test receipts.

## Minimal H02 integration ABI (not yet joined)
Prerequisite: H02 exact native authenticated internal envelope from CACHE01 and
an independently verified actor, source/citation snapshot, consent and policy.
Only **H02** can join CACHE02, CACHE03, CACHE04, CACHE05 and G04 into a new
nonprod successor branch. Consumer must NOT invoke `admit_fixture` from API.
A future **separate H01-authorized product implementation** must be designed
with externally signed qualified proof and public `CacheStoreV1` write authority,
including commit-time atomic revocation/rights fencing and current source custody.
Do **not** copy fixture secret, actor, test provisioner or fixture env into Product.

The current test call shape:
```python
gate.FinalWriteGate(store=cache02_fixture, authority=cache03_fixture,
                    actor=fixture_actor, fixture_verifier_secret=test_key,
                    fixture_only=True, feature_enabled=True).admit_fixture(
    internal_request, finalized_answer_with_claims, signed_test_proof,
    source_bytes=immutable_fixture_source_bytes, now=trusted_utc,
    previous_revision=old_record_body_sha256_or_none)
```
The returned frozen `WriteReceipt` always has
`fixture_only=True, product_write_admitted=False, product_hit_admitted=False`.
`states` shows each reached stage; no raw prompts/keys/source bytes are logged.

## Two-phase state machine
1. `CANDIDATE`: parse CACHE01 strict authenticated envelope. BYPASS (even
   feature ON) and disabled or non-static/non-QA return with ZERO cache IO.
   AUTO and REFRESH may proceed in explicit fixture mode; REFRESH never
   looks up prior semantic candidates and requires old revision for replace.
2. `CURRENT_SOURCE_ACL_CONSENT`: CACHE03 physically reads persisted authority.
   Bind actor, tenant/principal/auth context; current source manifest/corpus,
   SHA/rights/ACL, generation/epoch and consent expiry; snapshot fingerprint.
3. `INDEPENDENT_TEST_FIXTURE_PROOF`: verify SHA256 HMAC on exact canonical
   proof envelope with fixture verifier identity distinct from generator.
   Bind exact request ID and digest, question/answer/final, actor auth SHA,
   source/manifest SHA, source bytes digest, rights snapshot fingerprint.
   Enforce <=60s signed proof time, UTC, source SHA, immutable citation-source
   offsets/text hashes, each claim's cited span, entailment assertion and
   explicit mapping of every question obligation to supported claims.
   Signature alone is **not real entailment**.
4. `RIGHTS_RECHECK`: replay current CACHE03 authority snapshot, including
   source revision, policy, ACL, consent, epoch and revocation. A revoke or
   changed source during verifier work cancels before CAS.
5. `ATOMIC_CAS_ATTEMPT`: form CACHE01-valid candidate record with hash-bound
   provenance class `FIXTURE_ONLY`, cap record TTL below both request TTL and
   signed proof validity; use CACHE02 physical SQLite private fixture CAS.
   Inserts require prior NULL, REFRESH replaces only exact body revision;
   unknown/stale revision, revoked watermark and injected crashes roll back.
6. `FIXTURE_CAS_COMMITTED`: post-CAS authority snapshot checks again. If
   a postcommit revoke is detected, physically invalidate fixture identity rows
   and raise `RIGHTS_CHANGED_POST_COMMIT`. Otherwise return only
   `FIXTURE_WRITE_COMMITTED`, never an HIT.

### Scope limitation that cannot be solved by fixture tests
CACHE03 authority and CACHE02 store use **separate SQLite files**, with no
distributed revocation lock or shared transaction. Post-commit/next-read rechecks
reduce but cannot eliminate the crash interval or revocation race. External
epoch-high-water mark, real authenticated H01 issuer/signature registry, source
custody, recovery/rollback fencing, encryption/KMS, and cross-store deletion
are required before actual Product acceptance. A full rollback of the separate
authority database cannot be safely admitted. A single model evaluating its
own answer, a caller bool, `EXTERNAL_QUALIFIED` string, proof digest, and this
fixture MAC are ALL insufficient.

## Tests and physical evidence
Run under both Python 3.11 and Python 3.14:
```sh
python3.11 -m unittest discover -s tests -p test_m27_b2_cache_writeback_gate.py -v
python3.14 -m unittest discover -s tests -p test_m27_b2_cache_writeback_gate.py -v
```
Tests import **actual committed CACHE02/CACHE03 source on their own paths**
without cherry-picking or modifying their worktrees. The suite includes:
physical AUTO insert, real REFRESH CAS replacement, wrong old revision,
two concurrent refresh writers with one winner, before-write/after-write-before-
commit fault injection, actual separate-interpreter restart, OS SIGKILL during
uncommitted SQLite write and recovery, postcommit revoke purge, revoke during
proof, backed-up stale artifact denial after independent revoke, source refresh,
tenant/principal/auth/ACL/corpus/rights/policy drift, proof expiry and TTL,
wrong/same/self issuer, forged signature and formal label, request replay,
claims/obligations tamper, source span/hash poisoning, final prompt-injection,
cache-payload corruption, no Action/Research/Coding side-effect replay,
and disabled/BYPASS zero-cache IO.

Evidence is scoped to B2-01 report directory. Tests use only synthetic text
and never prove authenticated current Product, generator/verifier cloud independence,
claim truth for real material or formal CACHE HIT/WRITE.
