# M27 Deep Root-Cause Diagnostic Handoff

Final state: `M27_DEEP_ROOT_CAUSE_DIAGNOSIS_READY`

Workspace: `/home/ubuntu/LLM_Wiki-m27-deep-root-cause-diagnostic-23`
Final HEAD: `cf3ef730afdac327b72d361f051bcd9d4aca0aee`
Base HEAD: `ee720858b380c87cc3f49f55aa064e2029b923d4`

This session produced diagnosis-only artifacts and implemented no repair.

Primary findings:

1. Stream publication is post-hoc. Verified material events are emitted only after `await worker`, so first material latency tracks final latency.
2. Verifier-gap handling is all-or-nothing, creating false safe terminals and empty nonterminal finals on answerable cases.
3. Product answer planning is immature: only 3/20 cases are good cited answers >=85; four cited answers fail or hard-fail Owner scoring.
4. Provider compute policy permits 60s and 4 attempts in the owner-only product path, incompatible with p95 <15s.
5. Multilingual normalization is brittle: C15/C16 fail while related English topics are answerable.

Next recommended session should be a repair design/implementation session focused on native M27 claim graph + live claim-level stream publication + product answer planner. It should not rebase to M26 mature composer.

Artifacts:

- `docs/m27/research/68_m27_deep_root_cause_diagnostic_report.md`
- `docs/m27/research/m27_deep_root_cause_diagnostic_receipts.json`
- `docs/m27/research/68_case_failure_matrix.csv`
- `scripts/m27_deep_root_cause_diagnostic_23.py`

Validation:

- compileall PASS
- git diff --check PASS before commit
- receipts JSON load PASS
- ruff unavailable in isolated shell
