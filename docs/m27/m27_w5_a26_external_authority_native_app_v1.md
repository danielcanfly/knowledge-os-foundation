# W5 A26 | Executable external authority and real native app custody v1

## Final boundary
A26 is a separately owned N25-child local engineering addition. Source: src/knowledge_engine/m27_w5_a26_external_authority_native_app_v1_experimental.py. It uses the original C24 native source SHA/revision/byte-span verifier through N25's portable client receive SDK. It never opens endpoints, calls Provider, fetches protected case bodies, self-appoints external roots or authorizes production.

Current real external legal authority: A26_AUTHORITY_NOT_PROVISIONED.
Genuine native App: NOT CONNECTED. E26 official: NOT RUN 0/523.
B26 sealed blind: NOT RUN 0/200. Real product p95: null.
W5_FULL_COMPLETE, W6, REL01, REL02, Production: FALSE.

## 1. Exact signed-input schema and source of trust

Independently issued external trust registry JSON schema:
m27.w5.external_trust_roots.v1.
Properties: schema, independent_issuer=true, roots array. Each root:
key_id, public_key_b64 (Ed25519 raw 32 bytes), roles (exactly one),
not_before (epoch), expires_at (epoch), revoked=false.

Authority packet JSON properties: payload and signatures array.
Payload schema: m27.w5.a26.signed_evaluation_authority.v1.
Required immutable metadata: purpose (current523 or phaseb200), run_id, nonce,
issued_at, expires_at, revocation_checked_at (fresh <=3600s), revoked=false,
app_id, opaque endpoint_id, app_build_sha256, client_instrumentation_sha256,
candidate_image_sha256, runner_sha256, source_roster_sha256,
source_revision_index_sha256, source_rights_grant_sha256, rubric_sha256,
assignment_roster_sha256, role_counts, assignments, nonproduction=true,
one_shot=true. For Phase B200 also unseen_independent=true.

Rights block: consent=true, revoked=false, permission_scope=nonprod_evaluation,
retention_expires_at, source_revision_index_sha256 matching immutable payload.
Budget block: positive integer max_cost_cents (<=1000000), max_attempts
exactly roster size, provider_price_attestation_sha256 from effective-dated
approved real billing evidence. These declared fields by themselves NEVER
prove actually granted license, source consent, independent appointment, or
authority to spend. Validate actual owner registry and revocation out of band.

Signatures: detached Ed25519 over canonical sorted-key compact UTF-8 payload.
Each signature item: role, key_id, signature_b64. Must include seven
distinct independent keys for current523: source_rights, app_controller,
evaluation_controller, grader, native_observer, candidate_builder,
budget_controller. For phaseb200 an EIGHTH independent blind_custodian signer
is required. Each root only authorizes its single role. Verify real
principal/control relationship independently, not by developer assertions.

Both actual registry and full authority packet must have independently
authenticated SHA256 pins supplied through an out-of-band trusted
authority channel. Self-generated fixture keys or recomputed pins are
cryptographic test inputs ONLY, NOT real entitlement.

## 2. Immutable assignment denominators

Current523: 341 live including live_cited=237, live_safe_abstain=52,
live_preprovider_deny=52, plus 182 replay: replay_budget=26,
replay_invariant=26, replay_governance=130. EXACTLY 523 case IDs.
PhaseB200: blind=200 EXACT, separately held by independent custodian.
Each assignment row contains only case_id and role. No bodies/prompts/answers.
IDs unique. Ordered canonical JSON roster digest must equal signed
assignment_roster_sha256; role_counts must match exact role cardinality.

The actual blind custodian must separately prove immutable source origin,
sealing and exclusion/non-overlap with M26 frozen200, original523 and exposed
development/replayed cases. A locally reconstructed 200 is NOT unseen.

## 3. Runnable non-network CLI contract

Only independently qualified custodians may provision genuine signed files.
Private files mode 0600 under existing private 0700 non-symlink directory,
max 2MB and strict JSON (duplicate keys / NaN denied). Example from A26
isolated worktree (replace examples ONLY with authentic signed values):

    export PYTHONPATH=src
    python -m knowledge_engine.m27_w5_a26_external_authority_native_app_v1_experimental \
      --packet /secure/w5/a26/e26/current523-authority.json \
      --registry /secure/w5/a26/external-trust-roots.json \
      --packet-sha256-from-independent-channel AUTHENTICATED_PACKET_SHA256 \
      --registry-sha256-from-independent-channel AUTHENTICATED_ROOTS_SHA256

B26 uses /secure/w5/a26/b26/phaseb200-authority.json plus its own
independently issued packet pin, sealed corpus and external evaluator.
CLI always exits code 20 and emits redacted machine status:
A26_AUTHORITY_NOT_PROVISIONED when missing, tampered, expired or unauthorized;
A26_MECHANICAL_SIGNATURE_PREFLIGHT_ONLY if valid cryptographically.
Neither result launches actual network evaluation. Independent real-world
authority appointment must be verified OUTSIDE the development process.
One-shot claim_nonce(private_dir,run_id,nonce) creates exclusive 0600
fsynced nonce record; collision/replay denied even after an interrupted run.
Call it only at an authorized external host, not during local preflight.

## 4. Native actual-client receive/ACK output contract

Instrument the truly authorized nonproduction native application's real
/api/m26/query/stream receive path. AppAttachment binds opaque app/endpoint
ID, build/instrumentation SHA and externally signed grant/ACK/roster refs.
In actual client process, call NativeTrial.before_send() immediately before
the real request, on_recv(raw_bytes) for each client receive, and close(reason)
on every successful/ERROR/TIMEOUT/DISCONNECT/CANCELLED/REJECTED terminal.
observe_client_chunks is available for an already controlled receive iterable
and deliberately makes no network calls.

C24/N25 capture only client monotonic request admit, first recv, first
substantive UTF-8 source-cited text BEFORE terminal and full terminal/close.
Progress-only SSE does not count. Citation source ID/revision/original SHA256,
source-byte offset/span/quote SHA and answer span are preserved in redacted
metadata. If substantive text and terminal arrive in one recv timestamp,
first-before-terminal is unprovable and must NOT be certified.

A26 client wrapper output:
a26_schema=m27.w5.a26.client_observation.v1, case_id,
client_receipt_sha256, client_receipt, independent_client_ack=null initially,
official_qualified=false. It retains N25 outcome latency for all outcomes and
full-final-answer latency NULL on failed/incomplete terminal.
cohort_integrity requires all 523 or all 200 uniquely mapped receipts to
prevent dropping timeout/error/deny cases. 341 live nearest-rank p95 index=324;
237 cited expected index=226; missing or unverified results are not PASS.
No synthetic or unsigned metrics may become product p95.

An independent native_observer must sign its own client ACK packet with
schema m27.w5.a26.independent_client_ack.v1. Payload:
observer_role=native_observer, observer_key_id, case_id, request_id, nonce,
status, client_receipt_sha256, source_native_citations_sha256, terminal_ns,
client_closed_ns, issued_at, expires_at, revoked=false. Signature:
signature_b64 of canonical payload Ed25519. Root public key and SHA256 must
arrive from an authenticated independent channel, not the packet itself.
verify_independent_client_ack checks signature, source/case/digest and clock
binding. Even crypto PASS says EXTERNAL_ADMISSION_REQUIRED, not an actual
externally accepted real Client trace.

## 5. Independent E26/B26 outputs and grader separation

E26 must separately receive actual P16/B13/source permission and current
M16 candidate admission, signed current523 roster, frozen independently
approved rubric, protected 523 bodies in lawful evaluator host, actual
App/Provider and bounded authorized cost. Execute 341 live plus 182 replay;
retain 52 safe abstentions, 52 verifiable preprovider zero-dispatch denials,
237 source-qualified cited finals, 182 replay contracts, all failures,
independent real Client ACK and source-native rights/revocation through
answer terminal. Export signed redacted E24/E25 evidence for E25 post-hoc
zero-dispatch regrader and signed current owner/source quality decision.
Draft >=226/237 cited, grader >=85/100, zero critical, full 341/237
nearest-rank p95 <=15000ms are NOT signed formal acceptance yet.

B26 must separately seal an actual new unseen 200-case corpus and signed
non-overlap roots under an independent custodian; use B25R evaluator-host
one-shot contract, immutable tested runner/candidate App, separate approved
cost, actual 200/200 attempts, signed failures, client ACK and independent
source span grader. Developer fixture crypto, inherited M26 frozen200 and
local B25R suite do not qualify.

Required immutable outputs per run: signer principal/root identity and
validity/revocation, source rights/consent/current index SHA/span/version,
original assigned case ID/role roster hash, candidate image/build/runner
and instrumentation SHA, each client request/terminal/error/ACK signature,
independent source grader and rubric SHA, actual Provider meter/price/usage/
invoice and (separate release stage) signed OCI rollout/rollback and owner
grant. Keep all official/release flags false until authenticated.

## 6. Narrow local-engineering evidence

Test module: tests/test_m27_w5_a26_external_authority_native_app_v1_experimental.py.
Separate top-level reporting:
02_REPORTS/W5_A26_EXTERNAL_EVAL_AUTHORITY_AND_NATIVE_APP_REPORT.md
05_EVIDENCE_INDEX/W5_A26_NATIVE_REAL_CUSTODY_20261012/
This is executable custody engineering, not proof that a real App is connected.
