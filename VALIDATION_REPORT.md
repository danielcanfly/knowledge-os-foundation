# Validation Report

- Package: `knowledge-os-foundation-m1`
- Validation date: 2026-07-02
- Result: PASS

## Executed checks

```text
python scripts/validate_contracts.py
CONTRACT_VALIDATION_PASSED

python -m pytest -q
9 passed

python -m compileall -q scripts tests reference
PASS
```

## Vertical slice verified

- Compiles the reviewed OKF fixture into immutable release artifacts.
- Produces `graph.json`, lexical index, provenance aggregate, build report, manifest, bundle archive, and channel pointer.
- Returns the `Knowledge Compiler` concept for an authorized internal query.
- Returns a structured non-answer for a public caller blocked by ACL.
- Rejects a tampered graph artifact by SHA-256 validation.

## Negative cases verified

- Dirty source manifest is rejected.
- ACL downgrade from restricted to public is rejected.
- Missing provenance source reference is rejected.
- Broken internal Markdown link is rejected.
- Invalid release and provenance fixtures do not accidentally pass.

## Remaining external integration

A production Cloudflare R2 bucket and deployed Oracle VM Runtime were not tested because credentials and infrastructure endpoints are not stored in this repository.
