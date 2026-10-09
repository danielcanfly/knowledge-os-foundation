# M27 X01–X09 P0 Binding Hardening | Offline Test Receipts

Date: 2026-10-10. **Feature-off synthetic code only; not Production or authority acceptance.**

## G0 and exact owned scope
- New independent Mac Git worktree: `/Users/huaihsuanhuang/Desktop/Chatgpt/M27/M27_VNEXT_MASTER_20261009/06_WORKSITES/CODEX_X01_X09_P0_BINDING_HARDENING`
- New branch: `m27/codex-x01-x09-p0-binding-hardening`
- Verified source branch: `m27/codex-x01-x09-offline-closure`; clean HEAD `b22ed8ddbb2316b69e4b23a7f7d2e25ccd701832`.
- Original AR01R baseline `90bcba2d1b06f96144708abff5786d7046df0784` is a verified ancestor. AR04A/AR05A/AR09A equivalents present in integration history.
- Only two existing files edited: `src/knowledge_engine/m27_cross_module_abi_experimental.py` and `tests/test_m27_cross_module_abi_experimental.py`; this receipt is the sole new tracked file. Imported AR04A, AR05A and AR09A files unchanged.
- No VM / Production / provider / IdP / protected native Product Q&A / benchmark / network / production integration. No refused AR02B-R, AR03B or LB07 action retried.

## RED before code edit
Five distinct regression tests were added to the new isolated test file **before editing source**.
Command: `PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=<new-worktree>/src python3.11 -B -m pytest -q -p no:cacheprovider tests/test_m27_cross_module_abi_experimental.py -k test_p0_`.
Result **5 failed, 13 deselected**, completed exit **1**. All five failures are genuine: ghost permit accepted, wrong action/ledger identity accepted as success, charge ID double-added, effective-principal keyword unsupported, caller-owned native oracle label accepted. RED log: `/Users/huaihsuanhuang/Desktop/Chatgpt/M27/M27_VNEXT_MASTER_20261009/05_EVIDENCE_INDEX/CODEX_X01_X09_P0_BINDING_HARDENING_SCRATCH/red_pytest.log`, SHA256 `7647c07e4ebacf3cedfebe2d2d6aa2ce7ac56a5dfc446b99d6cf8aadadcf36a3`.

## Actual repairs and remaining truth boundary

| Finding | New test-only hard gate | Result |
|---|---|---|
| X03/X04 ghost T2/T3 | T1 immutable `(tenant, run, command, intent_id, intent_digest, epoch, quote)` ledger; independently preconfigured approval fixture scoped to that T1; T2 exact approval/command/lease; T3 consumed, single-use, ambiguous concurrent active intent denied | PASS offline |
| X04/X08 detached identities | T5 verifies exact T1/T2/T3/T4 receipt, ledger effect, configured independent AR04 action source, separately configured AR05 outcome/head/epoch/verification/content source, native AR09 evidence, fresh CAS, known settled budget. Confirmed not-applied cannot silently become SUCCEEDED. Exact verified terminal replay idempotent; changed identity conflicts | PASS offline |
| X07 duplicate charge | Immutable ledger entry by charge ID plus tenant/run/command/usage version/source/amount digest; same invoice replay is no-op even with stale CAS version; changed amount/source/version conflicts; different late invoice accumulates append-only incident and preserves separate outstanding reservation | PASS offline |
| X02 principal | Explicit trusted effective principal and delegation bound outside signed authorization payload; separate HMAC-signed synthetic consent policy snapshot, scoped purpose, tenant/run, current revocation/policy generation, time window | PASS offline |
| X09 arbitrary string | Naked oracle label does not authorize success; independently injected test port supplies typed original/observed native source bytes/citations and binding to run, verification and content SHA; native comparison computed using AR09 oracle; missing or contradictory source denies | PASS offline |

Deterministic negative vectors cover unregistered/foreign permits, wrong approval tenant/run/epoch/command and stale epoch, cross-tenant/run action or snapshot proofs, mismatched action intent digests, mutated observer/permit, forged AR05 outcome/verifier/head, ledger NOT_DISPATCHED and UNKNOWN_EFFECT, native citation/byte changes and absent oracle, duplicate charge ID same/different value/version, distinct late invoice and economic incident, current/expired/revoked/missing consent, stale head, and immutable terminal replay. Separate same-command positive permits on distinct mocked tenant/run ledgers are not conflated.

## GREEN completed tests
- Runner: pre-existing `/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python`, pytest 8.4.2, Ruff 0.15.20. No installation.
- Execution: `PYTHONPATH=<new-worktree>/src`, `PYTHONDONTWRITEBYTECODE=1`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `-B`, `-p no:cacheprovider`, task-owned HOME/TMPDIR/XDG cache; no network or plugins.
- All four focused suites run together: `test_m27_ar04_safe_action_experimental.py`, `test_m27_ar05_verification_experimental.py`, `test_m27_ar09_oracle_experimental.py`, `test_m27_cross_module_abi_experimental.py`.
- Result **110 passed in 1.61s**, complete pytest exit **0**. Log: `/Users/huaihsuanhuang/Desktop/Chatgpt/M27/M27_VNEXT_MASTER_20261009/05_EVIDENCE_INDEX/CODEX_X01_X09_P0_BINDING_HARDENING_SCRATCH/full_pytest.log`.
- Ruff exactly four source and four test modules, `ruff check --no-cache`. **All checks passed!**, complete exit **0**. Log: `/Users/huaihsuanhuang/Desktop/Chatgpt/M27/M27_VNEXT_MASTER_20261009/05_EVIDENCE_INDEX/CODEX_X01_X09_P0_BINDING_HARDENING_SCRATCH/full_ruff.log`.
- `git diff --check`: exit 0. Tracked ownership and commit/HASH checks captured in Master report/evidence index.

## Limits and non-closure
**OFFLINE_IDENTITY_BINDING_PROOF only. REAL_AUTHORITY_UNPROVEN.** The port, HMAC keys, independent approval/observer, revocation and native source are deterministic synthetic fixtures. The ledger is *in-memory single-writer CAS*, not SERIALIZABLE durable DB, recovered journal, multi-process outbox, actual provider or live native Q&A evidence. There is no legal/privacy/IdP consent decision, trusted Product-native source, real AR05 signing root, externally approved price authority, irreversible publication/delivery guarantee, crash/replay proof or release qualification. **All X01–X09 Master blockers remain OPEN.** No branch promotion, integration or Production release is authorized by this result.
