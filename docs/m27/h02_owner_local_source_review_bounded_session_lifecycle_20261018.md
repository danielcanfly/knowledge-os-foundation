# H02 Nonprod firstparty Source Review | bounded concurrent sessions and rights-memory lifecycle

**Authoritative:** Desktop `/Users/huaihsuanhuang/Desktop/06_M27_VNEXT_MASTER_ARCHITECTURE_AND_CONSTRUCTION_CHARTER_V1_20261014.md` (Task/Outcome-native Context-Native Runtime). Owner-authenticated local Nonprod only. The old generated-answer Product and Q34 refused equivalent routes remain unchanged.

## True versioned defect and intended scoped fix

Against parent H02 `b001a9389b93369158dde7d7b561378d9de2d533`, the local A05 reader legitimately accepted **nine simultaneous outstanding** Context Planner sessions without a configured in-flight ceiling, and after explicit Client CANCEL the session still held **4,735 characters** of excerpts, citations and claims in process memory. This was physically reproduced, not inferred from reading code. Concurrently authenticated but stalled clients could grow in-memory source state; timeout/terminal did not actively erase source-bearing state.

New limited Owner-private policy:
- Maximum **8 simultaneous `AWAITING_ACK`** Source Review sessions per server. Deny the ninth before source retrieval / OS verifier work; no silent eviction of legitimate active Client.
- Current source TTL is **120s**; on ACK or during new session admission, expired unacknowledged sessions become `EXPIRED_NO_REPLAY`, with audit terminal receipt, source-bearing content removed and quota freed.
- On authenticated Client TERMINAL or CANCEL, retain only `state` and non-secret `task_sha`, erase `sources`, `excerpts`, `claims`, source rights/revocation context, identity/nonce/TTL and ACK collection.
- Retain at most **128 bounded non-secret completed/expired tombstones**, never evict active reviews; an evicted replay becomes `UNKNOWN_SESSION_NO_REPLAY`, safely DENY. The journal keeps real immutable audit events; no attempt to rewrite older historical entries.
- Local bootstrap bearer, strict Host and no Origin, current epoch fencing, independent OS source proof and human-Client challenge SHA remain mandatory. No test disables remote IdP, Product signer or semantic authority requirements.

## Regression acceptance

New six focused cases: eight genuine A05 sources accepted and ninth denied, cancellation releases quota, post-terminal and post-cancel source removal and replay denial, expiry fencing/recovery of quota, and bounded tombstone pruning without evicting active. Existing 12 Source Review security/rights tests, 3 independent OS HTTP Client tests, 6 local bootstrap Client authorization, 20 original H02 Client and 4 F03 source delivery tests must remain green in Python 3.11/3.14. No outbound model calls, Action Effect, Provider grants, protected official 523/200 or Product OCI/Sigstore is asserted.

**Outcome scope:** this fixes a genuine Owner-local reliability/sensitive-memory lifecycle defect, not the required standalone signed full Product App. Formal P0/P1 HOLD remains E01 0/3, E02 0/12, F01 new real0/17, true remote Source Rights, G03 signed Effect, G05 independent finances, F04 signed Product Image not built, H01 true9/9; H03 C28 0/28. Owner three AND gates real success >95%, rubric quality >85, complete-answer p95 <15sec remain NOT_VERIFIED.
