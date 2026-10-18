# G01 QA TaskContract-to-independent Client Outcome (isolated candidate)

**Scope:** owner-controlled local first-party M27 rules, fully fail-closed standalone G01
implementation and separate-OS-process verifier/client. These files are not merged into
H02, Q34, Production, or any official Product. No network model transport is implemented
or invoked. A deterministic fixture harness is provided solely to test HTTP mechanics.

## Actual grounded first-party source
- Input: `01_DISPATCH/REPLAN_B0_20261017/B0-00_SHARED_RULES_20261017.md` on the
  authorized MacBook, bytes SHA256 `137009ea0618710222bef118c3ca258dfe98b5f8911e8dc588ac154dd4d17fb9`.
- QA TaskContract uses `workload_kind=qa`, `max_side_effect=read`,
  `definition_of_done.mode=all`, independent verifier required, budget/deadline,
  tenant/principal, local ACL epoch and exact pinned source SHA.
- Claim A `cache_initial_mode`: bytes [6582,6635), citation `B0-OWNER-RULES/cache`,
  "Initial semantic answer cache remains OFF in Nonprod."
- Claim B `macbook_first_tool`: bytes [5145,5212),
  citation `B0-OWNER-RULES/commander`,
  "All new engineering uses Remote Desktop Commander first on MacBook."
- Source is genuinely owner-controlled local document and SHA verified on disk on
  each preflight and before terminal. **This is not proof of H01 signed Product rights,
  IdP tenancy, a licensed external issuer, or remote revocation authority.**
  A local mutable flag supplies only unit-test revocation semantics.

## Publication mechanics and explicit boundaries
- G01-owned verifier is a *separate OS Python process*, re-reads the original byte
  spans and narrows allowable entailment to a whitelisted, exact two-fact QA.
  It is not a broad multilingual semantic proof or a signed external authority.
- Fixture-only HTTP server is an actual OS listening endpoint on ephemeral
  127.0.0.1; the independent client runs as a separate OS process, connects using
  HTTP, consumes NDJSON stream, reads two substantive answer_text events
  with source citations, POSTs both claim-bound ACKs, receives terminal in
  the same request. It also attempts a replay ACK and expects 409.
- No Python harness output from this fixture is treated as model-generated.
  Fixed frame text, usage, tokens, cost, gateway route, model identities are
  never claimed to be live data. No live Cloudflare or MiniMax calls occur in G01.
- Product/real entry point is deliberately **HOLD** in `Session.preflight`:
  without both genuinely authenticated custom Worker Gateway and independent
  first-party signed rights, no candidate frames may become live answer text.
  A client-supplied boolean cannot promote it to a Product admission.
- Owner's custom Cloudflare Worker Gateway remains PRIMARY; Direct Workers AI
  is not that Gateway. The separate bounded policy decision permits MiniMax only
  for qualified pretext operational failure, with consent, no already published
  claim, no auth/ACL/rights/entailment/cancellation failure. This is a policy
  guard, not a live Cloudflare failover receipt.
- No answer cache is imported or used by any G01 module. Source revocation
  halts publication, local journal is append-only fsync-per-event and restart
  after a crash returns INCOMPLETE_NO_REPLAY rather than replaying a result.
  No original G02 Research modules or storage modified.

## Reproduction (RDC on Owner MacBook, explicitly synthetic)

Use the G01 isolated worktree and stage-owned evidence directory. Set
`G01_OWNER_RULES_PATH` to the exact B0 shared-rules document and
`PYTHONPATH=src/knowledge_engine:tools`, then run:

```bash
/opt/homebrew/bin/python3.11 -m unittest discover -s tests -p 'test_m27_g01_qa_outcome.py' -v
/opt/homebrew/bin/python3.14 -m unittest discover -s tests -p 'test_m27_g01_qa_outcome.py' -v
/opt/homebrew/bin/python3.11 tools/m27_g01_fixture_http_receipt.py \
  --source "$G01_OWNER_RULES_PATH" --case happy --journal /tmp/g01_demo_unique.jsonl
```

Eight fixture HTTP scenarios: happy, second_missing, revoke_midstream,
bad_numeric, bad_citation, cancel_before, no_ack, progress_only. Unit negatives
also cover tenant/principal/ACL/source version, unsupported denial/number, fake
ACK/replay, preterminal invalidation, contract, deadline and true OS process
crash followed by journal recover.

## Strict status
Engineering fixture is reproducible but this is a **G01 PARTIAL** toward actual
QA outcome: custom Cloudflare PRIMARY live attestation, standalone authorized
MiniMax live fallback on distinct legally permitted route, real independent
Product rights/issuer and Client authentication, and real provider cost are
unproven. Formal H01/F04/H03, original523, blind200, REL01/02, Production hold.


## G01 bounded continuation audit (same standalone branch)
- Stage own code now deep-copies the validated QA TaskContract at Session start:
  caller-side actor/policy edits cannot silently change a running challenge-bound task.
- An arbitrary unsigned \`external_signed_grant\` object is **rejected**.
  A true H01 signer/IdP authorization path is NOT implemented or emulated.
- The exact TaskContract deadline is rechecked alongside monotonic request
  wall ceiling on every fixture publication.
- ACK verifies original source bytes, tenant/principal, policy/source version,
  and local ACL epoch again; stale/revoked source cannot receive a new ACK.
- Terminal cannot be appended twice, avoiding duplicate receipt mutation.
- Six additional negatives: revoke before ACK, changed source before ACK,
  duplicate Terminal, mutable caller contract spoof, fake 'signed' grant,
  and deadline shortening. Total G01 tests now 43/43 on both Python versions.
- Still no permissible live custom Cloudflare PRIMARY, genuine same-request
  fallback trigger, source-rights issuer, or real model delta. Prior explicit
  Cloudflare/Q34 refusal remains binding. G01 remains PARTIAL, not fake PASS.


## G01 third-stage bounded hardening: per-claim independent ACK

The original fixture implementation used a common session challenge for both
claims. The stage-owned Session now binds each claim to a distinct random
challenge using session challenge, obligation ID, text SHA256, and 24-byte
cryptographically random per-claim nonce. A valid first-claim challenge does
not authorize an ACK for the second claim, even if the text hash is correct.
The original request challenge from /session is not a valid claim ACK token.

Every publication rechecks source/ACL/current deadline and cancellation after
the independent verifier returns and *again under the local Session condition
lock*, rejecting cancellation that races with the verifier. Every claim stores
an immutable copy of citation metadata. ACK remains refused after a source
version change or revocation, or after Terminal. No network side effects
outside isolated loopback, and no Product-origin client authentication implied.

Added tests include wrong claim challenge, hash, and obligation sent via actual
HTTP POST /ack from a separate OS client (all refused before answer completion),
and a two-claim cross-challenge swapping test. G01 now runs 47/47 on both
Python 3.11 and 3.14. This is a local safety qualification, not a live-model
G01 PASS. Actual Cloudflare custom Gateway route/rights signed issuer still HOLD.
