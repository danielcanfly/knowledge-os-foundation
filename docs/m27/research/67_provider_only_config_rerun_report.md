# M27 Provider-Only Config Rerun Report

Final state: `M27_PRODUCT_READINESS_NOT_READY_WITH_DIAGNOSIS`.

## Scope

This was a provider-only config isolation plus bounded product-readiness rerun. It was not canary activation, production deploy, release pointer mutation, admission/full523 rerun, Stage13/14, or Chunk002.

## Provider-only config proof

- Provider-only config path: `/home/ubuntu/.config/m27/provider-only-stage22.env`
- File mode: `600`
- Allowed key names: `MINIMAX_API_KEY`
- Raw values recorded in artifacts: `False`
- Forbidden datastore/Qdrant/R2/SQLite/owner-bypass/release/Nginx/route key categories absent: `True`
- Candidate used owner-only factory path with a read-only bundle snapshot, not a production datastore mount.

## Bounded 20-case rerun result

- HTTP success rate: `100.0`
- Cited final-answer rate: `35.0`
- Safe-terminal rate: `20.0`
- p50 final latency: `17502.827 ms`
- p95 final latency: `44915.431 ms`
- p50 first material latency: `14301.912 ms`
- p95 first material latency: `40327.837 ms`
- Timeout/error rate: `0.0`

## Product gate decision

- `p95_final_latency_lt_15s`: `False`
- `p95_first_material_lt_15s`: `False`
- `final_answer_success_rate_gt_95`: `False`
- `every_successful_final_answer_owner_rubric_ge_85`: `False`
- `false_safe_terminal_rate_zero_for_answerable_cases`: `False`
- `browser_use_warning_case_cleared`: `False`
- `multilingual_c15_pass_or_justified_safe_fail`: `False`
- `multilingual_c16_pass_or_justified_safe_fail`: `True`
- `no_production_no_secret_no_route_violation`: `True`

The product gate is not met. Latency remains above the 15s p95 target, final-answer coverage is far below >95%, false safe terminals remain on answerable cases, Browser Use is not cleared, and multilingual coverage is not product-ready.

## Special-case diagnosis

- `C01` `browser_use_warning`: cited=`False`, safe=`False`, latency_ms=`19899.914`, first_material_ms=`None`, citations=`0`, answer_len=`0`
- `C12` `ordinary_cited`: cited=`False`, safe=`False`, latency_ms=`9959.773`, first_material_ms=`None`, citations=`0`, answer_len=`0`
- `C15` `multilingual`: cited=`False`, safe=`False`, latency_ms=`44304.658`, first_material_ms=`None`, citations=`0`, answer_len=`0`
- `C16` `multilingual`: cited=`False`, safe=`True`, latency_ms=`13820.864`, first_material_ms=`13820.174`, citations=`0`, answer_len=`0`
- `C20` `safe_terminal`: cited=`False`, safe=`False`, latency_ms=`33222.029`, first_material_ms=`None`, citations=`0`, answer_len=`0`

## Owner 85 scoring artifact

- Scored successful cited final answers: `7`
- Every successful final answer >=85: `False`
- `C02` score `85` result `fail` hard_fail_codes=`SOURCE_COVERAGE_TOO_NARROW`
- `C06` score `64` result `fail` hard_fail_codes=`THIN_ANSWER_SURFACE,SOURCE_COVERAGE_TOO_NARROW`
- `C07` score `88` result `pass` hard_fail_codes=`none`
- `C10` score `73` result `fail` hard_fail_codes=`THIN_ANSWER_SURFACE,SOURCE_COVERAGE_TOO_NARROW`
- `C11` score `73` result `fail` hard_fail_codes=`THIN_ANSWER_SURFACE,SOURCE_COVERAGE_TOO_NARROW`
- `C13` score `94` result `pass` hard_fail_codes=`none`
- `C17` score `94` result `pass` hard_fail_codes=`none`

## Safety / redaction

- M27 candidate received no owner-bypass material.
- Raw owner/provider secret values were scanned in memory and were not present in the receipt artifact.
- Public routing and Nginx were not intentionally modified.
- No production datastore, Qdrant, R2, SQLite write-capable path, release pointer, or Nginx route material was passed into the M27 candidate.

## Validation

- `python3 -m compileall src scripts tests`: `PASS`
- `git diff --check`: `PASS`
- Product comparison receipt validation: `PASS`
- `ruff`: `UNAVAILABLE`

## Artifacts

- `docs/m27/research/provider_only_config_rerun_receipts.json`
- `docs/m27/research/67_provider_only_config_rerun_report.md`
- `docs/m27/handoffs/M27_PROVIDER_ONLY_CONFIG_RERUN_HANDOFF.md`
