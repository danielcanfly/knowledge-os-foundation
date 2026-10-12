# D28 | AR01 dual-envelope local candidate, not ABI ratification

This is a **feature-off**, inert local prototype added to a T27 descendant.
It neither changes ProductExecutor, M26 SSE/native citations, existing AR01D
serialized records, authority tables nor any live API.

## Proposed *single* Master ratification choice (NOT APPROVED)

Freeze two explicitly separate wire types using registry keys
`(namespace, schema_version)`:

- `LegacyBoundEnvelope: (ar01v.envelope, 1.0.0)`, carrying SHA256 and
  exact byte length of the original AR01D legacy bytes, unchanged native event
  hash, required sidecar descriptor digests, head checkpoint (seq/hash), current
  policy/revocation generation and exact field/domain hash.
- `NewRecordEnvelope: (ar01z.new-record, 1.0.0)`, carrying a new-only
  revocation-control, billing-ledger or postterminal-notice record with a
  separate body digest and head checkpoint. **Never fake a legacy byte digest.**

The local C1-subset profile uses sorted UTF-8 JSON, NFC new-only strings,
nonnegative safe JSON integers, strict shapes, no duplicate keys or floats,
and SHA256 of domain + uint32-length + canonical envelope excluding its own
digest. Legacy record bytes are **not** canonicalized. SHA256 is integrity
only, never proof of signing-key authority, source rights, an external effect
or permission. This profile is not RFC8785/JCS and has not been approved by
an external ABI consumer or Master.

The explicit `negotiate_reader` gateway rejects unknown required authority,
unknown version, wrong major and raw old-reader consumption. A native old
reader that cannot be reliably isolated behind this gateway is **not
compatible** and requires separately approved v2 migration, not a downgrade.

## Engineering boundary and test evidence

- Source: `src/knowledge_engine/m27_d28_dual_envelope_v1_experimental.py`.
- Python positive/negative: `tests/test_m27_d28_dual_envelope_v1_experimental.py`.
- Immutable golden fixture: `tests/fixtures/d28_ar01_dual_envelope_goldens.json`.
- Independent Node byte/digest oracle: `tests/d28_ar01_node_oracle.mjs`.
- No import/call from the T27 FastAPI SSE endpoint and no mutation of M26
  legacy `m26_verified_streaming` / native payloads.
- Existing `m27_cross_module_abi_experimental` covers offline X02-X08
  fixture ledger/permit/approval semantics; D28 does **not** replace it.

## Required decision and still-open gates

Master/Owner must explicitly **ratify or reject** this proposed dual-record
shape, signed canonicalization, field mapping, version migration boundary,
ownership and trust anchor requirements, with independent AR02/AR03/AR04/
AR05/AR06/AR07/native client consumer signoff before I28 product integration.
Keep X02 real delegation/consent/source rights, X03 takeover approval,
X04 serializable transaction, X05 authenticated client cursor/ACK,
X06 revocation/erasure, X07 real cost/billing, X08 independent verifier/T5,
and X09 authenticated native Q&A provenance and SSE release gate **OPEN**.
No invented signers, IdP, permission, Provider cost, external evaluator or
Production qualification is supplied.

An approved immutable AR01D v1 record is never rewritten; terminal state
cannot be reopened by a new notice; a billing ledger cannot interpret
UNKNOWN usage as zero; revocation controls are not physical deletion.
Offline golden success is `D28_LOCAL_ABI_PROVEN`, and
`FORMAL_ABI_RATIFIED=false` until written qualified authority.
