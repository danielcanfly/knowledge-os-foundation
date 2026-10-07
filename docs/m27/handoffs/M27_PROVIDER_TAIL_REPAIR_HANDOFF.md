# M27 Provider Tail Repair Handoff

Final state: `M27_PROVIDER_TAIL_REPAIR_BLOCKED`

Workspace: `/home/ubuntu/LLM_Wiki-m27-provider-tail-product-answer-repair`
Base HEAD: `7c0b28552605457c5856bfe742a88e663a0f5a20`

## What changed

- Deterministic evidence-bound product surface candidate added before provider fallback.
- Missing-provider fail-closed path added; absent provider credentials now produce safe terminal instead of stream error.
- Verification standards were not lowered.

## Blocker

Provider-valid bounded 20-case rerun is blocked because the isolated candidate needs provider-only credentials to evaluate provider-tail repairs. Full env injection was rejected because it brought production datastore/Qdrant settings and triggered `PA7_QDRANT_COLLECTION_MISMATCH`. No secret value was printed or committed.

## Next legal continuation

Provide a provider-only env injection path for the isolated candidate, without owner-bypass and without production datastore keys, then rerun the exact same Stage 19R/20 20-case side-by-side.

## Artifacts

- `docs/m27/research/66_m27_provider_tail_product_answer_repair_report.md`
- `docs/m27/research/m27_provider_tail_product_answer_repair_receipts.json`
- `docs/m27/handoffs/M27_PROVIDER_TAIL_REPAIR_HANDOFF.md`
