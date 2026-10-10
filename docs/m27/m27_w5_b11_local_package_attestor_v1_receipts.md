# M27 W5 B11 | Local reproducible source package and import fixture receipts

## Frozen local identity

- G0 clean initial branch `m27/w5-b11-offline-package-provenance-v1`, exact HEAD `e0ceb7e564b81597bfd54eba72fd38edae92311e`, tree `eff5db48057a03442f4270e2f4f10bbf7d93831b`.
- Approved F11 `SourceFreezeManifest` JSON SHA256 `6612fa1b6782f524b274025bad471cc3b66d70b6961aeda84d380cb1c7ae8721`.
- 17 exact frozen .py modules, independently SHA256 checked from this local Git worktree; source mode, Git tree, symlinks, path traversal, manifest claims and source changes fail closed.
- Two distinct, disposable temporary build roots; ZIP_STORED, sorted entry order, fixed 1980 timestamp, 100644 permissions, no ZIP comments, exact contents and byte hashes. The 18th entry is a deliberately **synthetic empty** `knowledge_engine/__init__.py` fixture, not an attested original init file.

## True local package bytes

- Both nonprod builds: SHA256 `2c2403849f159458c09485df8e462d403477ad6dabe54663d7737e7e45ff2531`; exact byte equality, not just equivalent source names.
- Canonical sidecar JSON SHA256 `4c8d82dab49278b58e44203d974d0872bfb99826095973f2eb6dbabdb50ef608`. Includes pinned HEAD/tree, manifest digest, builder version, each ZIP entry name/hash/byte length/header and data offset, packaging SHA, unfrozen dependency inventory and release_attested=false.
- Independently extracted all 18 entries with SHA comparisons against pinned original source digests (and zero-byte fixture initializer). ZIP tamper/replay/metadata/alias/duplicate path checks enforced.
- Isolated pinned Python 3.11.15 `-I -S -B` child process imported **three approved stdlib-only pinned fixture modules**, not original source files: AR02 `DurableWriterV1`, AR09 `IndependentOutcomeHarnessV1`, AR10 `AR10CandidateGovernanceV1`. The import receipt records `sys.path` priority, `__file__`, `__spec__.origin`, resolved path and SHA256.
- Import receipt SHA256 `3775f6f316d656fd3e3c358e7f66e9e25ac3b1a20b961ad347b6fa83b21e4ea0`.
- **Important limit**: I02 was NOT imported as a fully closed runtime. Frozen 17-file manifest lacks `m27_ar06_governed_memory_experimental.py`, also required by W3 AR06; it lacks `m27_ar07_compute_policy_experimental.py`, required by W3 AR07. Full I02 runtime remains `IMPORT_ORIGIN_UNVERIFIED` even though the three isolated import fixtures are verified. Do not substitute synthesized stand-ins for the missing dependencies.

## Verdict boundaries

- `B11_LOCAL_REPRODUCIBLE_BYTES_PASS`: two real local builds, byte-identical, zip entries byte-verified against frozen source.
- `B11_IMPORT_ORIGIN_FIXTURE_VERIFIED`: only three named, controlled fresh-interpreter modules.
- `IMPORT_ORIGIN_UNVERIFIED`: entire I02 runtime/module-closure import from this 17-file package.
- `B11_REAL_RUNTIME_IMAGE_ATTESTATION_UNVERIFIED`: no signed OCI executed image, no live candidate, signer/CI/runner provenance, externally authorized source, provider, hidden eval, deployment, route or rollback.
- This is not the Stage30P mutable image tag / Stage30O + source patch execution; old historical host/package SHA mismatch cannot be closed by these new local ZIP bytes.

## Hostile suites and engineering scope

- **87 distinct parametrized fail-closed negative/fault injection cases**, grouped as 28 manifest, 9 archive-path, 17 ZIP/payload, 15 receipt forgery, 13 import origin/path, 5 malicious source parser/ABI cases. Also real deterministic package/actual isolated import positive integration tests.
- Combined B11/AR10/I02/AR09/D09/T09/P09/E09B/AR06/AR07 regression suite: **895 passed, 1 harmless intentional duplicate ZIP warning**, on the pinned 3.11.15 interpreter, with `TMPDIR=/tmp` to meet the preexisting AR08 ephemeral sandbox allowlist; pytest cache and third-party plugin auto-load disabled.
- First discovery reruns exhibited 3 B11 test failures (two aliased comparison objects and one empty sys.path IndexError); fixed. The first combined I02 rerun revealed 10 preexisting sandbox temp-root rejections due to the worker-specific external pytest basetemp. Reconfigured *only the test runner environment*, no AR08 source or policy edited. Keep original red logs and successful terminal receipts.
- Ruff scoped solely to the two new Python files, PASS. Three new tracked files only, one add-only Git commit, exact HEAD parent and SHA verified in final worker REPORT.

## Evidence directory (outside worker Git tree)

`/Users/huaihsuanhuang/Desktop/Chatgpt/M27/M27_VNEXT_MASTER_20261009/05_EVIDENCE_INDEX/W5_B11_REPRODUCIBLE_PACKAGE_ATTESTATION_SCRATCH/`

Expected immutable local-only outputs: `B11_LOCAL_SOURCE_PACKAGE.zip`, `B11_LOCAL_SOURCE_PACKAGE_MANIFEST.json`, `B11_IMPORT_ORIGIN_FIXTURE.json`; raw initial/green pytest and Ruff terminal logs. No secret, hidden corpus or production material included.
