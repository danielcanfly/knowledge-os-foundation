# M27 W5 P17 | Fail-closed P16 ingress CLI denial contract

**Contract version:** `m27-p17-ingress-cli-denial-v1`. **Scope:** P17's dedicated isolated branch only. P16 remains source-data hashing and denial classification, never an external trust authority or official evaluator. No external keys, genuine original 523 or blind Phase B bodies, Provider, IdP or network action may be used. The original P16 scoped pytest and AST commands were explicitly platform-refused: they are **not** resumed by this change.

## OS exit codes are authoritative denials

| Exit | Meaning | Product authority |
|---|---|---|
| `20` (`EXIT_AUTHORITY_DENIED`) | Local ingress inspected and an atomic private **denial** receipt written and independently SHA-revalidated | **DENIED** |
| `21` (`EXIT_INPUT_DENIED`) | Ingress denied, unavailable, malformed, untrusted, or producer result invalid; no receipt for this attempt | **DENIED** |
| `22` (`EXIT_RECEIPT_DENIED`) | Cannot create or verify current private denial receipt | **DENIED** |
| `0` | **Never** emitted by the P17-enabled P16 `inspect` CLI. This tool does not possess official authority and cannot independently admit evidence | **Do not infer any approval** |

All successful **local byte inspection** is deliberately reported with **nonzero** status. Even an otherwise sound local hash and separately supplied `verified_out_of_band=True` are not official product proof. All CLI dispositions, including input exceptions and receipt errors, carry machine-readable stdout JSON with `schema` and `decision="DENIED"` (not a Python traceback). A future independent authenticator/evaluator must use its own explicitly authorized protocol, signed roles, and original cohorts. No change to `inspect()` promotes synthetic or historical inputs.

## Strict top-level stdout JSON

```json
{
  "schema": "m27-p17-ingress-cli-denial-v1",
  "decision": "DENIED",
  "transport_ok": true,
  "receipt_written": true,
  "receipt_path": "/private/outside-git/P16_REQUEST_RECEIPT.json",
  "receipt_sha256": "64-lowercase-hex-actual-file-digest",
  "classification": "P16_EXTERNAL_AUTHORITY_NOT_ADMITTED",
  "original523": "ORIGINAL523_EVIDENCE_NOT_ADMITTED",
  "ar09_phase_b": "AR09_PHASE_B_BLOCKED",
  "official_cited_gate_pass": false,
  "may_execute_official_evaluation": false,
  "denial_reasons": ["EXTERNAL_ROOT_AUTHORITY_NOT_INDEPENDENTLY_PROVEN"]
}
```

The example is illustrative, not a genuine receipt. `transport_ok` says `inspect()` produced a response. `receipt_written` says a **denial** receipt was atomically created for the invocation, and `receipt_sha256` binds its actual disk bytes. **Neither is an admission result.** A failed read or receipt write sets `receipt_written=false` and `receipt_path=null`, `receipt_sha256=null`, even if an older receipt happens to remain on disk. Consumers must not infer product approval from a 0600 receipt, process ability to read a file, private scratch folder, hash equality, or prior historical `exit 0`. Consumers **MUST** gate on `decision`, exact `classification`, both `original523` and `ar09_phase_b`, and the nested E15 cohort `status` and official flags; absent/unknown/malformed fields are DENIED.

For an inspected invocation, the persisted `P16_REQUEST_RECEIPT.json` preserves original P16 fields and adds `cli_schema`, `decision`, `transport_ok`, `receipt_written`. Its `e15.original523` and `e15.phase_b` retain typed negative/review statuses, but **neither independently admits a cohort**. All `official_cited_gate_pass` and `may_execute_official_evaluation` fields are forced false. `validate_denial_receipt(path, expected_sha256)` compares whole bytes against the independently captured CLI hash and checks old/new and nested denial fields. A returned `True` means *a structurally valid, SHA-matching DENIAL receipt*, never a product or rights approval. Reject a missing hash, stale/changed bytes, forged approval, invalid cohort, missing client proof or malformed nested data. This API cannot verify independently provisioned rights roots.

## Representative offline diagnostic

```bash
TMPDIR=/tmp PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 \
/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python -B \
-m knowledge_engine.m27_w5_p16_external_evidence_ingress_v1_experimental \
inspect --ingress-root /separately-nominated/ingress \
--manifest manifest.json --scratch /private/scratch/outside-git
```

Expected when the nominated manifest or independent authority is missing: nonzero, `decision=DENIED`, original 523 NOT ADMITTED, Phase B BLOCKED; when a receipt is written, its original evidence must remain segregated from any official authorization. **Never use the exit status as a shortcut for rights or evaluation acceptance.**

## Test and release boundaries

The new P17-specific isolated tests target the changed CLI denial path, forged producer fields and nested cohort reports, stale/tampered receipt SHA, ZIP/path/manifest/rights guard and fixture-local hashes. They do **not** replay the explicitly refused original P16 seven-suite pytest operation or standalone AST command. Any newly explicitly platform-denied test stays **NOT VERIFIED** and must not be retried via shell aliases, wrappers, RDC or Codex. All fixture-generated negative and positive (bytes-only) results are local mechanics, never original full-523 citation ≥95%, real p95 ≤15s, never-seen AR09 Phase B, signer roots, authentic client ACK, Provider invoice, or B13 positive release evidence.

**Downstream gate:** P17 is separately reviewed by V17. M16 is not permitted to merge P17 or assume P16 complete until V17 independently qualifies all required original P16 tests and authority gates. W5 FULL, W6, REL01, REL02, and Production remain closed.
