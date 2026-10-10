# M27 W5 B12 | F12-v2 19-source offline diagnostic receipts

This worker performs **real source-byte checking and isolated import**, but F12-v2 is **NOT dependency closed**. Its B12 validator **must refuse a full-package qualification**, even though the 19 pinned modules import under the isolated interpreter.

## Immutable input and source-of-truth

- Frozen source root (READ ONLY): `06_WORKSITES/W5_B11R_POSTCOMMIT_REGRESSION_REPAIR`, commit `f81e1ef4642624e9f28f6a314f18d1bcc2e1a3a9`, tree `16ef7e807a28c3a6d884351bf66dca042b72fa33`.
- Manifest: `07_MASTER_REBASE_20261010/05_EVIDENCE_INDEX/W5_F12_19_SOURCE_FREEZE_MANIFEST_20261010.json`, SHA256 `051dafba045515350d0908886fcc9d46da30262df5839cb383c685574a47f751`.
- Previous frozen F11 original 17 pinned SHA entries unchanged. F12 adds exactly `m27_ar06_governed_memory_experimental.py` and `m27_ar07_compute_policy_experimental.py`.
- B11R code/tests untouched. F11 historical 17-file artifact (SHA256 `2c2403849f159458c09485df8e462d403477ad6dabe54663d7737e7e45ff2531`) is not full I02.
- Scope: only two B12 Python files and this file; no other tracked files, Production, Provider, privileged source data, CI or release.

## Executed evidence and strictly qualified status

Using pinned `/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python -I -S -B` for the import witness, in an extracted disposable root outside source Git:

- `B12_LOCAL_19_SOURCE_BYTES_REPRODUCIBLE_PASS`: two builds in different temporary directories, canonical sorted ZIP, 20 members (19 original byte-identical pinned Python sources plus deliberately empty `knowledge_engine/__init__.py`), deterministic metadata and offsets, full SHA256 read-back.
- `B12_FULL_I02_ISOLATED_MODULE_IMPORT_PASS`: independent fresh subprocess imported I02 first and all other 18 modules; validated `__file__`, `__spec__.origin`, loaded module dict identity, complete Python module inventory and extracted payload SHA256 for every 19 originals. This is strictly a **module-load proof**, not a usable complete dependency closure or executed end-to-end workflow.
- `F12_DEPENDENCY_CLOSURE_BLOCKED: knowledge_engine/m27_ar03_context_broker_experimental.py`: the frozen `m27_ar06_governed_memory_experimental.py` includes function-local `from knowledge_engine.m27_ar03_context_broker_experimental import Candidate, Request, select`. Lexically scanning every AST scope finds this missing **20th source** even when a top-level Python import succeeds. **No new source added, no stub manufactured, no source manifest changed.**
- Additional unbundled third-party dependency: `cryptography` is imported in a function-local branch of pinned `m27_w4_p09_external_evidence_v1_experimental.py`. The 19-source-only isolated `-I -S` interpreter cannot import `cryptography`. Future freeze needs an explicitly authorized vendoring/versioning decision, or an approved core-vs-optional dependency contract. This is **not** secretly assumed resolved.
- `B12_COMPLETE_I02_WORKLOAD_RUN_UNVERIFIED`. No actual complete I02 workload with all paths and fixtures was executed.
- `B12_REAL_EXECUTED_OCI_CI_IMAGE_UNVERIFIED`: no independent CI or OCI signer, no real image, Provider billing, native client, signed authority, Phase B or release.

## What the implementation enforces

Pinned manifest metadata and original bytes; exact source tree and clean state; `git show` blob parity, tracked mode and symlink rejection; 19 original file hashes; sorted canonical archive, offsets and permissions, duplicate and replay detection; AST walk including deferred local imports, dynamic import rejection and unbundled third-party handling; extracted source import and origin hashes; only feature-off diagnostic sidecar emission outside Git; fail-closed qualified `run()` when closure is incomplete.

The B12 worker HEAD necessarily advances after its commit. All positive inputs stay pinned to the **separate clean B11R source worktree**, avoiding the predecessor B11 postcommit test-root regression.

## Next gate

Master must issue a **new separately versioned freeze manifest** naming `src/knowledge_engine/m27_ar03_context_broker_experimental.py` and any dependency policy decisions for optional `cryptography`. B12 cannot automatically add a 20th source or relabel F12-v2 as fully dependency closed. Only Master may independently review full postcommit tests, immutable SHA digests and whether to issue a new dispatch. REL01 and REL02 remain NOT CERTIFIED / NOT AUTHORIZED.
