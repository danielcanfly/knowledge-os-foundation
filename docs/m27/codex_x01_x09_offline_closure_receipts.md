# M27 X01-X09 Offline Blocker Resolution Receipt

Date: 2026-10-10 (Asia/Ho_Chi_Minh)

Status: `OFFLINE_ENGINEERING_GATES_IMPLEMENTED`; production integration remains
locked pending the named external authorities below.

## Source and isolation

- Baseline commit: `90bcba2d1b06f96144708abff5786d7046df0784`
- Branch: `m27/codex-x01-x09-offline-closure`
- Worksite: `CODEX_X01_X09_OFFLINE_CLOSURE`
- Git remotes: none
- AR04A imported commit: source `8d371026306d26b0efa49c947552c64f4d468a02`,
  integration equivalent `28414e77`
- AR05A imported commit: source `612665c5be4c7212f6a39c5656f6e7c7b3eb8a02`,
  integration equivalent `8ad6c409`
- AR09A imported commits: source `255abee49b4dd4be93441877292d54f9002e78f4`
  and `d560764eb9fa7863024bb456b6cb9359b25cdea0`, integration equivalents
  `f8141a54` and `11f50e00`
- Cross-module implementation commit:
  `5ae7f84a82e6b3c9143e40bdec0e81a0a6fd7a63`

The worksite was cloned directly from the verified AR01R full-history bundle.
No earlier wrong checkout, Production checkout, provider, credential, network
adapter, or previously refused AR02B-R/AR03B/LB07 operation was used.

## Implemented files in the cross-module commit

- `src/knowledge_engine/m27_cross_module_abi_experimental.py`
- `tests/test_m27_cross_module_abi_experimental.py`

The imported AR04A, AR05A, and AR09A files retain their separately reviewed
history. The cross-module commit adds no production import or runtime wiring.

## Executed acceptance

Final pytest command:

```text
PYTHONPATH=src python -m pytest -q \
  tests/test_m27_ar04_safe_action_experimental.py \
  tests/test_m27_ar05_verification_experimental.py \
  tests/test_m27_ar09_oracle_experimental.py \
  tests/test_m27_cross_module_abi_experimental.py
```

Result: `80 passed in 0.16s`, exit 0.

Final Ruff command was limited to the four M27 source modules and four focused
test modules. Result: `All checks passed!`, exit 0.

The new cross-module file contributes 13 collected tests, including five
parameterized X02 denial cases. Tested boundaries include:

- exact legacy raw-byte digest and byte-length preservation;
- explicit separation of legacy-bound and new-only records;
- configured fake trust root, HMAC integrity, tenant/run/audience/purpose,
  delegation, consent, expiry, policy generation, and revocation generation;
- idempotent command lookup after a simulated lost acknowledgement;
- CAS conflict, command digest conflict, immutable intent/approval binding,
  stale epoch denial, and one-time permit consumption;
- conservative reservation, unknown-price denial, double-reserve denial,
  immutable late overrun accounting, and economic incident gate;
- `POSSIBLY_SENT`/independent observation semantics without a provider call;
- fresh journal head and epoch, independently signed AR05 proof, and separate
  AR09 native-byte/citation oracle acceptance before terminal commitment;
- deny-first exclusion generation and no stale read/replay;
- immutable terminal plus a separate monotonic post-terminal notice stream.

Observed repair history, preserved for audit:

1. Initial pytest without `PYTHONPATH=src` exited 2 during collection because
   this repository does not add `src/` to pytest's import path.
2. First correctly configured run produced `78 passed, 1 failed`; the failing
   assertion expected a digest error after changing byte length. The fixture
   was corrected to mutate bytes without changing length.
3. After that repair the suite produced `79 passed`; a missing sidecar case,
   notice precondition case, and economic incident terminal guard were added.
4. Final result is the 80-pass receipt above.

No Stage 3 validator profile exists for this newly authorized fourth workstream,
so no profile result is claimed. The original AR04A/AR05A/AR09A validator
receipts remain independently recorded in their source worktrees.

## X01-X09 disposition

| ID | Implemented resolution | Truthful remaining boundary |
|---|---|---|
| X01 | External `LegacyBoundEnvelope` preserves exact v1 bytes; `NewRecordEnvelope` cannot carry a legacy ref; sidecars fail closed | Formal schema/canonical-signature ratification still belongs to Master/trust owners |
| X02 | Signed, scoped, expiring effective authorization; absent delegation/consent and stale generation deny | Real IdP trust root, lawful basis, and privacy/legal approval are external and were not fabricated |
| X03 | Immutable digest, exact approval binding, stale takeover denial, one-time permit | Any approval carryover policy requires explicit Owner authority; default remains DENY |
| X04 | Single-writer CAS model combines intent, budget reserve, permit and pre-send marker; lost ACK requires lookup | A real serializable durable backend and crash/fault proof remain required; refused AR02B-R was not resumed |
| X05 | Terminal cannot reopen; correction/retraction uses separate monotonic notice stream | Client cursor/backfill/reach policy and real delivery receipts remain external |
| X06 | Monotonic deny-first generation blocks stale reads and replay without mutating terminal run head | Legal subject/hold/store inventory and real storage deletion authority remain external |
| X07 | Unknown price denies; reserve cap is atomic; late overrun is immutable and blocks terminal | Approved price source, currency/FX, numeric caps, and provider invoices remain external |
| X08 | Fresh head/epoch, resolved action effect, independent AR05 signer, and AR09 acceptance are all hard gates | Real verifier trust root and durable AR02 terminal CAS remain external |
| X09 | Original native bytes, source revision, citation order/spans, and pre-terminal verified text are tested | Production native Q&A/image/live evidence remains locked and was not simulated as closure |

Therefore the best safe resolution is not to label all P0s `CLOSED`. The
engineering uncertainty is reduced to executable offline gates, while every
missing external authority is represented by an explicit denial rather than a
mock success.
