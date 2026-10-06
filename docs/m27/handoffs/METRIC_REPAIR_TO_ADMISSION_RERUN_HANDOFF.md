# Metric Repair to Admission Rerun Handoff

Upstream state: M27_ADMISSION_NOT_READY_WITH_DIAGNOSIS

Repair scope completed:

- cited final-answer denominator now contains only verified_cited_answer expected rows
- expected safe terminals are evaluated separately
- safe-terminal answer/citation leakage fails closed
- verified-answer rows without citations still fail coverage
- aggregate metric gate requires citation coverage >= 95% and safe-terminal correctness = 100%
- feature-off and production no-mutation invariants remain enforced

Use knowledge_engine.m27_admission_metric_contract.summarize_admission_metrics in the next admission runner.

The next runner must emit an explicit safe-terminal visible-answer leakage signal such as answer_leaked; do not use legacy answer_present as a leakage proxy.

The next 10R session must still perform its own fresh live preflight before question 1. This handoff does not authorize 100-case, full523, release, canary, or production mutation except under the original ladder rules.

admission_ladder_may_rerun: YES
