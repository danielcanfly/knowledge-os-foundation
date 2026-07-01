# M1 Reference Knowledge Engine

This reference implementation proves the contracts as a complete local vertical slice:

```text
reviewed OKF bundle
  -> validation
  -> graph + lexical index + provenance aggregate
  -> deterministic bundle archive
  -> immutable release manifest
  -> channel pointer
  -> ACL-aware Wiki-first query
```

It is not the final production service. It deliberately uses a filesystem store and a small lexical retriever so release, integrity, ACL, and query contracts can be tested before cloud and model dependencies enter the room.

## Run

```bash
python reference/knowledge_engine.py build \
  --bundle examples/okf-bundle \
  --output .artifacts \
  --release-time 2026-07-02T12:00:00Z

python reference/knowledge_engine.py query \
  --store .artifacts \
  --channel staging \
  --query "knowledge compiler" \
  --audience internal
```

Promotion to R2 must upload the immutable release prefix first, verify object hashes, and update the channel pointer last.
