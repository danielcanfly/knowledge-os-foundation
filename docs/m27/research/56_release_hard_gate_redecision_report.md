# M27 Release Hard-Gate Re-Decision Report

Status: `M27_RELEASE_HARD_GATES_READY`
Date: 2026-10-07
Workspace: `/home/ubuntu/LLM_Wiki-m27-release-hard-gate-redecision`
Branch: `m27/release-hard-gate-redecision`
Base: `a17d05b63a21b2aa4b0486fb20726ee16916cf6f`

## Scope

This session only re-decided the M27 release hard gates from accepted artifacts. It did not rerun admission/full523, modify runtime answer behavior, run Stage13/14 legacy admission, run Chunk002, deploy production, activate canary, mutate a release pointer, restart/rebuild production, or write production R2/Qdrant/SQLite.

## Accepted source workspaces and HEADs

- Admission full523: `/home/ubuntu/LLM_Wiki-m27-admission-release-rerun` @ `f406be4a07ae360655e073c4dea1e13fe2796689`
- Release hard-gate closure / streaming: `/home/ubuntu/LLM_Wiki-m27-release-hard-gate-closure` @ `e864417c2380f2ce8d6c24576fb129c37b95ccad`
- Independent quality scorer gate: `/home/ubuntu/LLM_Wiki-m27-quality-scorer-gate` @ `80b0b0ddc1ccc52ccb86b3acb1d2e9782579102a`
- Quality payload scoring: `/home/ubuntu/LLM_Wiki-m27-quality-payload-scoring` @ `a17d05b63a21b2aa4b0486fb20726ee16916cf6f`

## Source artifact SHA-256 digests

Admission:
- `docs/m27/research/52_admission_ladder_report.md`: `9d53f98dd44fb4d19120086185e519e5724c6322c7e2cb36bf27344b25a4604b`
- `docs/m27/handoffs/ADMISSION_TO_RELEASE_HANDOFF.md`: `12d8163c4246dc18c29efa65c79cb1fab14c7253353b0f150355eb6a24faa44d`
- `docs/m27/research/admission_ladder_receipts.json`: `e2f5677e1f81b056697ffea791e986efde368614e8ad296f3b5d99f173446137`

Streaming/release closure:
- `docs/m27/research/53_release_hard_gate_closure_report.md`: `4d0f4d718e7249e3415e95cae69e2c50e3c0f751e3fc08fe227cfd6d3c7be964`
- `docs/m27/handoffs/RELEASE_HARD_GATES_TO_CANARY_HANDOFF.md`: `25414d0e83e0e7cd2825ec89963fdcbcd0d9e082339cddb00cf7dd897f035a3a`
- `docs/m27/research/release_hard_gate_receipts.json`: `7d8f559110d9e6623ea21a619d52c772c63f5962f348692e003045b7c923b3c8`

Independent quality scorer gate:
- `docs/m27/research/54_independent_quality_scorer_gate_report.md`: `a7e9b1871cc1f717b95ecf2562fc39ca90b747af86a594bbd31abdaa8e0cbaaa`
- `docs/m27/handoffs/QUALITY_SCORER_TO_RELEASE_GATE_HANDOFF.md`: `fdce3a4e5263117244d3dfb834971c0b3e171c2278656e6f38b007485f9a7c32`
- `docs/m27/research/independent_quality_score_receipts.json`: `f7932d74e25815177454afb487d0ca41857e58af74b5e90ed6669d0515367dfa`

Quality payload scoring:
- `docs/m27/research/55_quality_payload_scoring_report.md`: `9bade7ee8fe96667c627407d2cd905b85a78532a3590db2f3598eddbefb0cac2`
- `docs/m27/research/quality_payload_score_receipts.json`: `057122e7733283a0f4b0f40f5836ce6c860a2596a27f59a7da1c6199019324da`
- `docs/m27/research/55_quality_payload_sampling_policy.md`: `310345bc1343ba502fa04c172102025a823f42a2055d3ba8217803adf06342da`
- `docs/m27/handoffs/QUALITY_SCORING_TO_RELEASE_HARD_GATES_HANDOFF.md`: `4cf2cf21aa76539b775ea02a940c1236f3a67b8f573d8a98250c7a57f34f0ae5`

## Gate 1: admission full523

PASS.

Accepted receipt evidence:
- full523 gate pass: true
- passed: 523 / 523
- cited final-answer rate under corrected metric: 100% (237 / 237), threshold >=95%
- safe-terminal correctness: 100% (130 / 130)
- citation/provenance integrity: 100%
- p95 latency: 2365.529 ms, threshold <=15000 ms
- errors: 0
- HTTP 429 rate: 0
- provider failure rate: 0
- production_no_mutation: true

The deterministic admission harness's null quality score is not used as semantic quality evidence.

## Gate 2: first-answer-text streaming

PASS.

Accepted streaming evidence:
- isolated endpoint: `POST /v1/answers/stream`
- stream schema: `m27-isolated-first-answer-stream/v1`
- event sequence includes `request_started`, `verified_claim_ready`, `cited_segment_ready`, `final_answer_done`
- first material event index 1 precedes final-answer-done index 3
- final-answer parity checked: true
- safe terminal emits no material text: true
- unverified answers emit no material text, as proven by the focused streaming contract/tests
- no production endpoint behavior was changed
- production_touched: false

## Gate 3: independent semantic quality

PASS.

The earlier quality-scorer gate correctly failed closed because accepted admission receipts lacked semantic payload and evaluator execution evidence. The later payload-scoring artifact closes that blocker without rewriting accepted admission authority.

Accepted quality evidence:
- schema: `m27-independent-quality-score/v1`
- evaluator identity: `repo-qualified-minimax-answer-quality-evaluator`
- provider/model: `minimax / MiniMax-M3`
- evaluator contract: `aq-semantic-evaluator/v3`
- rubric: `ANSWER_QUALITY_RUBRIC_v1`
- scoring policy: `m27-independent-quality-scoring-policy/v1`
- source admission HEAD: `f406be4a07ae360655e073c4dea1e13fe2796689`
- source admission receipts SHA-256: `e2f5677e1f81b056697ffea791e986efde368614e8ad296f3b5d99f173446137`
- eligible verified-answer rows: 237
- unique semantic cases scored: 9 / 9
- payload-bearing answer/evidence records: present and digest-linked
- aggregate quality score: 91.222 / 100
- release threshold: 85 / 100
- per-case score digest: `a527790fb37e27142709f7b782cf67fe9f0bf5f53b3bbab03890b74549a1abf3`
- deterministic admission result substituted for quality score: false
- safe terminals excluded from semantic-quality average and retained under separate correctness evidence
- production_touched: false

## Gate 4: production safety

PASS.

Fresh read-only proof during this re-decision:
- production `GET /v1/health`: HTTP success, `ok=true`
- production build SHA: `7d4b2358464654bf3de7d9561ec89de841d279bd`
- production entrypoint: `knowledge_engine.m26_aq_semantic_contract.run_owner_arbitrary_query`
- production identity matches the accepted admission, release-closure, and quality-scoring lineage
- production containers observed read-only: `llm_wiki-knowledge-engine-1`, `knowledge-engine-test-answers`
- owned M27 eval containers: 0
- port 18080 listeners: 0
- no release pointer mutation
- no production R2/Qdrant/SQLite writes
- no production restart/rebuild
- no deploy
- no canary activation

## Combined decision

All four required release hard gates pass simultaneously from digest-linked accepted evidence plus a fresh read-only production safety check.

Final combined decision:

`M27_RELEASE_HARD_GATES_READY`

This state authorizes only a separate future canary-authorization session. It is not a deployment, canary activation, or release-pointer mutation.

## Validation

Focused release/quality/streaming/admission-contract test suite: PASS.
Additional required compile, Ruff, diff, and final repository-status checks are recorded at closure.

## Safety statement

No deployment, canary activation, release pointer mutation, production runtime answer-behavior change, production datastore write, admission rerun, full523 rerun, Stage13/14 run, or Chunk002 run occurred in this session.
