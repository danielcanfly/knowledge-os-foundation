# F03 S03 | Client-bound local source-candidate verification, not Product IdP

Work ID: P0-S03-F03-20261018. Baseline parent: F03 scoped 2fdf5bb87780f03a83bc28e7d9eae7dd92134193. Changes are additive stage-owned only.

## Security intent and new gap
Old F03 verified actual A05 Owner-local source retrieval, 11 file-byte digests and 21 exact spans, one OS principal and owner-internal tenant, local epoch fence. That was not a second independently authenticated Product client. The new independent boundary covers:
- Inter-client/session provenance: even identical OS identity cannot silently transfer an A05 source-candidate receipt to another client/session/tenant.
- Delivery-time TTL: no frozen read-time clock reused after the local lease expires; reject at exact expiry and expired A05 release.
- Version + citation revalidation: 21-frozen-span allowlist, original physical A05 bytes and exact revision/release; refusal on citation/source drift and forged cache flags.
- Post-restore monotonic fencing: when the local revocation file AND local fence are both restored to an older epoch, an independently preserved higher epoch *would* reject the stale candidate. Current test provides that floor as a simulated harness parameter. It is **not** genuine independent Controller/Remote Store escrow.
- G04 explicit boundary: no path in this module grants remote IdP, JWKS authority, Store write/delete, restore, production source admission, cache HIT/WRITE, signed issuer, or H01 attestation.

## Authoritative real local version
- Owner A05 release `a05context-7835ec95cee63972`, release expires 2027-01-11T21:36:23.210892+00:00.
- 11 actual tracked first-party documents, 21 real citation spans. Frozen manifest SHA256 `7835ec95cee639722f89a0520336283f7e226358ad7be003a2a906635d1200e3`.
- Local ACL `owner-internal -> internal`, actual retrieval actor OS UID, A05 revocation epoch 1, first-party only, Product-licensed grant not supplied.
- F03 source candidate BASE H02 `7966e9c766a38a22cd91432edb5dbf2115eff305`, inherited F03 scoped parent above. No replacement of H02 current native worktree.

## Test classification
All new tests use genuine on-disk original A05 local documents and existing BM25/local rerank, and isolated OS-temp copies only for revocation/tamper negatives. Client A/B identities, session-nonce differences, independent high-watermark, and stale backup are **local synthetic security test inputs**, not actual OIDC/remote store identities. Every positive is `LOCAL_DELIVERY_CONTEXT_BOUND_SOURCE_CANDIDATE_ONLY`; `product_authenticated=false`, `product_admitted=false`, `verified_final=false`, `cache_mode=BYPASS`, `answer_cache_hit=false`, `answer_cache_write=false`.

## Product gate decisions for G04
- `PRODUCT_RIGHTS_HOLD` until real Owner/Controller-approved separate Product Data Rights grant is verifiable with authentic independent root trust/JWKS, actual tenant/principal/allowed source IDs/digest/release/license/retention/TTL and revocation watermark.
- Remote G04 revoke/backup/restore NOT_RUN until independently authorized target (not denied Qdrant equivalent), specific disposable namespace/read/write/delete/restore grants, independent observer, epoch high-watermark custody, rollback and stop conditions.
- The local Source Candidate and synthetic replay tests are **not** a G04 permit. No Product Cache HIT/WRITE or external network calls.
