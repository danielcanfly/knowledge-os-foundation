# M27 W5 M24 | Canonical M16 admission firewall (EXPERIMENTAL)

## Authority separation

M24 is a new, independently owned nonproduction preflight wrapper. It never
promotes the accepted I23 local socket/fixture results to M16. It always returns
`decision=NOT_ADMITTED` and `local_state=M24_LOCAL_INTEGRATION_STAGING_ONLY`.
`RELEASE_ADMISSION_ENABLED=False` is a non-overridable code constant; neither
command arguments nor an input manifest can override it.

Exact baseline is I23 commit `52c18e9979ec24dedaed35cae4ca8690d8dfddcd`,
tree `2fb1400b486938ea6b94c76d1e38c49f73b74506`. The original untouched
canonical M16 head is `19c73028c9689c250e756987d1f2598e5f1fc891`.
M24 is intentionally a sibling branch with parent I23, not a canonical M16 patch.

## Source provenance and explicit limitations

Physical source digest pins cover I15 bounded local client (including C16
amendments), original E15 evaluator, P16 ingress with P17 corrected CLI
nonzero denial policy, L21/L22 bounded local fixture runtime, N22 independent
external OS-client and I23 merged coordinator. The lineage labels I15, C16,
E15, P16, P17, L21, L22, N22, I23 are recorded for review. Their inclusion
in I23 via local source import is NOT proof that original separate V17/P16
seven-suite/AST or B13 20-source positive tests were admitted.

The pins are physical file SHA256, not simply Git commit metadata. Baseline
commit and tree, branch parent and owned-only changed files are checked with
Git. Source reads open only predefined files with no-follow regular-file,
size and mutation checks. A test checks concurrent writes; no source data
bytes, hidden cases, secrets, or external corpus is copied into receipts.

## Hard gates which remain externally controlled

The typed `AuthorityEvidence` maps the following individually:
original P16 seven-suite plus AST; original B13 full-positive; genuine rights
controller; independently approved frozen original 523 grader and 341-live /
182-replay denominator; separately controlled Phase B200; real authenticated
native app/client ACK; signed current candidate build/image; genuine
all-outcome final-answer p95 ≤ 15s; authenticated Provider usage/invoice;
signed OCI/CI and rollback; explicit Owner canonical-M16 admission.

All are missing/unverified until an independent authority provides authentic
proof. A caller-provided `status=APPROVED`, arbitrary signature text, issuer,
nonce or locally generated key is never an independently authenticated grant.
Duplicate gate records/replayed witness IDs/nonces and wrong 523/Phase B
denominators are rejected. Mock p95, missing Provider receipts, forged CLI
exit0 + JSON denial, bad Git tree, stale source hash and arbitrary authority
fields cannot lift this firewall.

A future separately audited admission system must implement genuine
authenticated roots, independently verified evidence custody, signed
current candidate and independent grading. Merely changing the feature flag
or editing an input JSON is explicitly not a legitimate authority upgrade.

## Executable nonproduction preflight

Invocation from the isolated M24 worktree with its approved Python
environment:

```sh
PYTHONPATH=src /Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python -B -m \
  knowledge_engine.m27_w5_m24_m16_admission_boundary_v1_experimental \
  --worktree /absolute/path/to/W5_M24_ADMISSION_BRIDGE \
  --scratch /absolute/path/outside/git/M24_LOCAL_01 \
  --namespace m24-local-01
```

The preflight imports I23's actual source audit and launches one genuine
separate 127.0.0.1 native fixture server + external OS-client through N22's
`run_case` path. This is not a production native app, not independent
client-ACK, and not a 28-case benchmark. A successful isolated local probe
returns OS exit0 but the JSON decision remains `NOT_ADMITTED`; an invalid
local probe exits20. An exclusively created 0600 JSON receipt appears
outside the worktree, containing only enumerated gate states, code hashes
and an intentionally minimized local-client receipt. No receipt is
silently overwritten.

## Admission invariants

- `W5_FULL_COMPLETE=false`, `W6_AUTHORIZED=false`
- `REL01_CERTIFIED=false`, `REL02_AUTHORIZED=false`
- `PRODUCTION_AUTHORIZED=false`, canonical `M16_NOT_ADMITTED`
- Existing P16/B13 historical explicitly refused operations are never
  replayed under the guise of an M24 test.

This is **new engineering-only code** with independent M24-negative tests;
G23's historical 271 scoped tests are not counted as new M24 coverage.
