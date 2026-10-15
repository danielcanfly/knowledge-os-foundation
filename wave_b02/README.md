# M27 Wave B02 Nonprod authority preflight

This package consumes only Master-accepted B01 commit
`f47400fea3858260c9c34691af99b592f2f5c89b` (tree
`006d55fb59d58d701f68047afe45953e6676bde4`). It builds an unsigned,
content-only local OCI layout and runs local authority, cross-module, real-model,
recovery, revocation, replay and rollback checks.

`NONPROD_PREFLIGHT_ENGINEERING_PASS` is intentionally distinct from formal
Product GO and C28 launch. Missing formal issuer, IdP, external Provider,
signature coverage, CI staging, remote rollback and launch authority always fail
closed. Production, frozen Q34, sealed evaluation and previously refused
equivalent operations are never touched.

Run from the repository root with:

```sh
PYTHONPATH=src:. /opt/homebrew/bin/python3.11 -B wave_b02/run_b02.py
```
