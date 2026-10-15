# A05 Context-Native first-party retrieval candidate

Scope: 11 SHA-pinned Owner first-party Q34 architecture docs and 21 exact source byte spans from MG22 signed archive. Independent A05 worksite and isolated I37 Git clone. Never Production.

## Entrypoints
- `python3 a05_build_release.py`: pins the 11 docs, verifies 21 exact bytes and produces immutable A05 release metadata.
- `python3 a05_retrieval.py`: validates all documents and corpus release.
- `python3 a05_run_tests.py`: real child HTTP loopback server + urllib client and fail-closed tests, including 21 query-specific span retrievals, tenant ACL, expiry, revision, tamper and revoke/re-enable.
- `python3 a05_build_native.py`: creates separate I37-native, source-backed artifacts from verified MG27 lexical release, preserving zero embeddings and no Qdrant.
- `a05_i37_native.py`: real I37 default FastAPI App lifespan/routes via TestClient (run through MG09 local Python3.11 venv with test-only isolated env).
- `python3 a05_verify_sigstore.py`: genuine public GitHub OIDC Sigstore verification of MG22 approved first-party bytes.

This adapter uses BM25 plus a **locally computed corpus distributional context re-rank**. It is a real local (non-neural) semantic-affinity method, **not** pretrained semantic embeddings and **not** Product Qdrant/vector READY. Unknown terms always abstain. It returns exact source passages/citations, not model-generated answers. Authorization claims on loopback HTTP are test inputs, **not** signed IdP identity.

The native I37 legacy route has ACL (audience) but **does not itself enforce A05 document revocations or freshness**. A05 adapter enforces both and must be integrated at the source/context admission boundary by the next integration owner, with a native consumer negative test that proves no direct-route bypass. Do not promote this as release-ready.

`source/` contains immutable A05 source copies and release manifest, with independently mutable `revocations.json` used only for this isolated Nonprod test. `native_private_store/` is a separate new native test-only object store; it contains no Production channel. Evidence and original failed path logs are in `../evidence/`.
