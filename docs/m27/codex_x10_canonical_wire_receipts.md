# CODEX X10 | Independent Python + Node Canonical Wire Oracle

2026-10-10 · **X10_INTEROP_SUBSET_PROOF_PASS** (offline, proposed C1-subset only)

## G0 and source isolation
- Existing accepted Git commit: `bdab5819a74dfa1d7502ae3bddeba322b9c1f0ac`, parent `b22ed8ddbb2316b69e4b23a7f7d2e25ccd701832`, AR01R `90bcba2d1b06f96144708abff5786d7046df0784` ancestor.
- New isolated Mac worktree `06_WORKSITES/CODEX_X10_CANONICAL_WIRE_ORACLE`, branch `m27/codex-x10-canonical-wire-oracle`.
- Four and only four new tracked files: `src/knowledge_engine/m27_canonical_wire_experimental.py`, `tests/test_m27_canonical_wire_experimental.py`, `tests/m27_wire_oracle.mjs`, this document. Existing X01–X09, AR01D v1, AR04A, AR05A and AR09A modules remain read only.
- No Production, VM, Node package installation, network, provider, IdP, native ProductExecutor, SSE, real signature keys, or hidden benchmark.

## Proposed canonical **C1-subset** (NOT ratified and NOT full RFC8785/JCS)
- New-only document with exactly required `schema_id,tenant_id,run_id,task_id,attempt,issued_at,expires_at,consent_ref,payload,sidecars`; optional `memo` only. Schemas `m27.c1.envelope` / `m27.c1.sidecar`, not AR01D v1 structures. Missing required and unknown authority-bearing fields rejected. `consent_ref:null` is typed absence without permission, **not** the same bytes/semantics as omitted. `sidecars` nonempty and duplicate-free.
- Raw input strict UTF-8 without BOM, strict JSON with no duplicate key, unpaired UTF-16 surrogate or invalid Unicode, <=65536 bytes, max nesting depth 20. Keys at *all depths* constrained to ASCII regex `[a-z][a-z0-9_]*`; explicitly denies non-ASCII key normalization collision and UTF-16 versus code-point sorting ambiguity rather than pretending to implement full JCS key ordering.
- All new-body string values must already be NFC. NFD is **rejected**, never silently normalized. Objects sorted recursively by ASCII key, arrays retain input order, `JSON.stringify`/Python `json.dumps(ensure_ascii=False,sort_keys=True,separators)` independently emit canonical UTF-8; new-only escapes and supplementary UTF-8 have interop fixture coverage. No floating-point, decimals, exponent or nonfinite values. Unsigned safe integers `0..9007199254740991`; no negatives or `-0`; named monetary/counter fields require integer *not* bool. No signed fields have been ratified.
- Proposed UTC timestamp grammar `YYYY-MM-DDTHH:MM:SS.sssZ`, actual calendar validation, required issued_before_expires; reject naive time, offsets, leap seconds, year<0100. This is an intentionally narrow candidate, **not** full UTC policy/clock consensus.
- Original AR01D v1 byte digest stays `SHA256(original_bytes)` exactly, including key order, escapes, whitespace, omitted historical fields and Unicode forms. No migration/reparse-and-rewrite or original event-hash recomputation. Optional read-only legacy structural scan rejects duplicate fields or bad UTF-8 but does not change raw bytes.
- Digest input: ASCII magic `M27-C1-LP-V1\x00` followed by **eight** ordered fields, each `big-endian uint32 byte_length || bytes`: (1) domain `m27.envelope.binding.c1` or `m27.sidecar.binding.c1`, (2) exact schema ID, (3) canonical new C1 bytes, (4) **32 original v1 SHA-256 digest bytes**, (5) tenant UTF-8, (6) run UTF-8, (7) task UTF-8, (8) attempt canonical ASCII decimal. SHA256 of full framed sequence is **integrity only**. All emitted statuses are `CANDIDATE_DIGEST_UNRATIFIED`, never signed/authorized.
- Caller-supplied domain, identity, attempt and expected legacy SHA must exactly match independent parsed new document and raw legacy digest. Changed domain, wrong schema, swapped tuple elements, wrong run/tenant/task/attempt and legacy SHA mismatch all deny or yield distinct framed digests.

## Real test-first RED and GREEN
- Before implementation, executed stdlib-baseline test file: **4 failed, complete pytest exit 1**: default Python JSON last-key-wins, permissive `datetime.fromisoformat` offset, permissive floats/unsafe integers, unordered Python JSON differing from independently serialized Node bytes. This demonstrates **baseline stdlib pitfalls**, not alleged bugs in previous accepted M27 source. Raw receipt: `05_EVIDENCE_INDEX/CODEX_X10_CANONICAL_WIRE_SCRATCH/red.log`.
- Implemented independent Python parser/canonical serializer and **separately authored Node native recursive JSON parser** (not a wrapper around Python), Node crypto SHA256 and binary framing. Tests run actual `node --batch` and compare exact byte hex, legacy digest, canonical digest, framed binding hex and hash from two implementations, including rejects.
- Final focused **five M27 suites**: AR04A, AR05A, AR09A, X01–X09 ABI and new X10, **146 pytest passed**, completed exit **0**. Node `--selftest` independent 6 assertions/Golden, exit **0**. Scoped Ruff new Python source + tests **All checks passed**, exit **0**. No npm/pip installation.
- Validated 12 positive cross-language vectors (controls, slash/backslash/quotes, emoji, NFC, nested maps/arrays, max JS safe integer, optional memo null versus absent, multiple sidecars, schema isolation, whitespace), 28 parameterized negatives plus distinct domain/scope/sidecar/legacy/identity mutations and malformed non-JSON tokens. Single-token differences in errors for Python nonfinite `NONFINITE_NUMBER` versus Node `INVALID_JSON` are documented as **UNSUPPORTED as an error-code ABI**, both reject and never enter signed data.

## Fixed Golden C1 candidate (independently computed)
- Synthetic original legacy JSON raw UTF-8: `7b2276223a31207d` (literal `{"v":1 }`).
- Original raw legacy SHA-256: `9446bfa2cb28a077174a507bb777f8a9b9935864e27631102ce19d9ab9891fc1`.
- Exact new-body canonical SHA-256: `2b49b1965ede0f59c4908732576408292499760d565fa71ebf08242652b2519d`.
- Exact length-prefixed binding SHA-256: `b865539b7ccf3490726c33688ae4db68dd83461594302ffbe2cdadc26346b339`.
- Python and Node canonical `hex`, full framed `binding_hex`, SHA256 and byte equality all recorded and compared in task-owned **`05_EVIDENCE_INDEX/CODEX_X10_CANONICAL_WIRE_SCRATCH/golden_parity.json`**. Node's separately hardcoded Golden SHA and Python's independently hardcoded SHA both assert this digest. The full bytes are on disk, not truncated in this receipt.

## STOP / unresolved
**X10_INTEROP_SUBSET_PROOF_PASS; X10 FORMAL WIRE RATIFICATION OPEN**. For broad JSON interoperability, full RFC8785/ECMAScript floats, Unicode key sorting, high precision/signed integers, timestamp policy, cross-runtime canonical errors, trust/signature/key rotation, actual authoritative reader, real legacy source identity and durable signed-anchoring / migrations remain **UNSUPPORTED / UNPROVEN**, not implicitly accepted.
All X01–X09 real authority and durable backend P0 gates remain OPEN; X11–X18 remain OPEN. No production promotion, real client compatibility or release readiness proven.
