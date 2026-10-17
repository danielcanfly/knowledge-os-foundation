# B1-06 H02/G02 first native Research Task and durable Outcome, bounded Nonprod

2026-10-17. Source-owned opt-in local bridge only, NOT Product default route.

## Current provenance and live route
- Accepted D01 parent HEAD 97a5d18ffcada39632426146d7f73681a054bd54; TREE 50d6e6bb59f4c3864978fcbbe39ee2198a405d62.
- B0-02 original HEAD 361a5c724f92f0b4dbce0bce9a6d526f9c08f6f7; TREE 34b6174461889cb412abe7b6265e2660c5ec4c6f. Cherry-picked only the two G02 additive commits; original tracked delta exactly three files.
- New opt-in native ingress is the standalone m27_b1_g02_native_bridge.py. It listens exclusively on 127.0.0.1 ephemeral port, POST /nonprod/h02/research, without a public App, M26 /v1/answers, default import or D01 runtime registration.
- First-party local caller sends strict m27-h02-g02-first-party-nonprod/v1 with request_id, run_id, task_id/version, tenant_id, principal_id, TaskContract SHA, source registry SHA, outcome_id. Unknown fields, wrong rights/scope/identity, bad pins, malformed ABI and run/request mismatched replay are denied.
- Every call validates the ORIGINAL native TaskContract v1, uses G02's real Charter/Audit source bytes with SHA, ACL, expiration, revocation and source-line checks, writes the same-run SQLite four-event journal and fsync/atomic MD+JSON artifact, runs the standalone independent checker in a distinct Python process and validates a durable native OutcomeReceipt. Independent Client reads back original persisted bytes and SHA; no fixture substitutes for real outcome.
- Request replay binding persists in its NEW isolated Nonprod SQLite DB. Original B0 evidence SQLite is NEVER written. This listener has no independently verified IdP. A pinned local delegation is not valid external identity proof; do not expose publicly.
- No paid Provider or local LLM needed and none was used.

## Later compatibility, WITHOUT importing unfinished branches

| Later input | Identity/contract required | Permitted future action; current status |
| --- | --- | --- |
| Existing TaskContract and Research workflow | same task_id, tenant, principal, run, source SHA and rights | CONNECTED now, local first-party research only |
| Frozen CACHE-01 ingress | per-user cache ON/OFF, policy, principal/tenant, source rev | NOT IMPORTED, default feature OFF |
| CACHE-02 durable store | partition by tenant/principal, exact source revision, verified answer | NOT IMPORTED. Similarity Candidate is NOT HIT |
| CACHE-03 invalidation and rights | revoked/expired sources, ACL, policy and version epoch | NOT IMPORTED, deny before use |
| CACHE-04 consumer adapter | user may opt out; qualified verified answer/citation on cache hit | NOT IMPORTED, no Cache HIT activation |
| G04 revocation | explicit rights/epoch and governed invalidation | NOT IMPORTED; G02 itself rechecks revocation locally |
| F01 online semantic | independently qualified issuer and live entailed claim/source | NOT IMPORTED; Provider gate HOLD |
| F02 online streaming | real generated verified material before terminal and client receipt | NOT IMPORTED; Product streaming gate HOLD |

Research report output is not a formally qualified semantic answer. Do not cache it as confirmed semantic answer, turn on cache globally, or claim semantic HIT. Next H02 slice requires separate Master review of accepted CACHE-02/03/04, G04, F01/F02 frozen commits and compatibility before any integration.

## Boundaries and limitations
- Scope: fixed two first-party M27 owner documents, deterministic multi-stage comparison with real citations, not open-web retrieval, general research, semantic LLM entailment, public identity, or external actions.
- Only exact unchanged TaskContract module and G02 real source are imported directly. Package initialization of unrelated mature M26 modules requires dependency-equipped runtime with httpx; do not substitute stubs or call this a broad D01 smoke PASS.
- External Owner/IdP grant, third-party rights, signed publication, F35, H01/X01-X09, F04, H03/C28, official523, sealed blind200, REL01 and Production remain HOLD.
- D01, Q34, shared Composer/API, CACHE-01/02/03/04 branches, other workers, original B0 evidence and Master gate state are not modified.
