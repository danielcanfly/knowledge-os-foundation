# 09｜Governance, Eval, and Release

## Production boundary

```text
Agent proposes.
Infrastructure enforces.
```

## Deterministic enforcement owns

```text
ACL
hard policy
release locking
authorization
transactions
production promotion
destructive actions
```

## M27 acceptance criteria

```text
final_answer_success >= current production gate
quality >= 85
p95 <= 15s
bad_template = 0
unsupported_material_claims = 0
citation correctness no regression
retrieval recall no regression
cost per successful answer bounded
feature flag can disable M27 layer
```

## Required ablations

```text
Context Router ON/OFF
ComputePolicy adaptive/fixed
Skills ON/OFF
JevProvider ON/OFF
Agentic Retrieval ON/OFF
Memory ON/OFF
```
