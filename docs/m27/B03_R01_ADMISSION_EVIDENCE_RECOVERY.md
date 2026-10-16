# B03-R01 Admission Evidence Recovery

This package is a Nonprod-only, source-only recovery layer bound to B02 commit
`9744b19141371ecc69b463118accfc29df18565d` and tree
`5d47914335f5bef884017dbdd01441d9dcb8e1a0`.

It provides:

- mutually exclusive abnormal execution classification with PID, timeout, exit-code,
  stdout/stderr digest, principal, and refusal evidence;
- a read-only Ed25519 public acceptance receipt verifier requiring an independently
  authorized issuer and physical byte observation;
- an unsigned, non-secret witness packet and scoped access request;
- an offline F35/REL01 fail-closed matrix and positive/negative fixture coverage.

It does not inspect the B03 worktree. Publicly reported B03 values remain worker claims
until a distinct, authorized witness issues a valid receipt. Fixture keys and signatures
are test-only and cannot open that gate. This package does not run official 523/200
evaluation, access protected items, authorize release, deploy, or touch Production.

Run the focused suite:

```shell
PYTHONPATH=src /Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python \
  -m pytest -q tests/test_m27_b03_r01_recovery.py
```

Generate local R01 evidence:

```shell
PYTHONPATH=src /Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python \
  scripts/m27_b03_r01_generate_evidence.py --output evidence/b03_r01
```
