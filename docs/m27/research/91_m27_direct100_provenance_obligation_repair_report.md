# Stage 30K Direct100 provenance obligation repair

## Final decision
`M27_DIRECT100_PROVENANCE_OBLIGATION_REPAIR_BLOCKED_BY_TOOL_SAFETY`

## Boundary and execution state
- VM: vm-dev-01
- Workspace: /home/ubuntu/LLM_Wiki-m27-direct100-provenance-30k
- Stage 30J base HEAD: 78de1c728c00eb28bd091ae03c5ea04b510d58cb
- Preflight: M26 :8080 HTTP 200; test backend :8081 HTTP 200; isolated M27 :18080 HTTP 200.
- Active image before and after: knowledge-engine:m27-direct100-targeted-guard-30j-2dc7990e (unchanged)
- Rollback reference: same 30J image; no replacement was attempted.
- Built image (NOT ACTIVATED): knowledge-engine:m27-direct100-provenance-30k, sha256:1acfa0a4db5f94b29b35f4462fc5ccaf580454f13a9f4803e2fc82fa82dd454b

## Diagnosis before code changes
Eight provenance cases found in Stage 30J failures, each marked answerable in the frozen Stage 30H population.
All eight independently matched exactly one concept/source provenance record in pilot/m24/canonical-release/artifacts/provenance.json.
The recorded retrieved_at is present for all eight. Source commit and release ID appear in the accepted canonical release manifest, not merely the evaluation dataset.
Canonical provenance artifact SHA256: 0593d6669661df0d639e13b3b93d744b36f6fa934ca4faf7566d05574a573a05; verified against manifest.
Canonical release ID: 20260720T160000Z-46137c97263e.
Canonical accepted source commit: acf78596ace8a7366688ccef72b507204d09d9f9.
Some provenance source records omit upstream origin_commit; that field must not be fabricated or conflated with the release source commit.
8-case diagnosis matrix: docs/m27/research/91_m27_direct100_provenance_obligation_diagnosis.csv.
Root cause is provisionally PROVENANCE_EVIDENCE_AVAILABLE_BUT_NOT_RETRIEVED; live execution has not verified complete claim-binding behavior.
No Stage 30H dataset or labels were changed.

## Repair implementation
Added a M27-native, source- and concept-bound provenance lookup using canonical release manifest and checked provenance artifact SHA.
Explicit provenance identity questions get evidence containing retrieved-at, source-commit, and release ID; unrelated and unresolved questions do not receive generic provenance evidence.
No case-ID special-casing and no hardcoded eight-case answers. Existing question-obligation guard remains unchanged.

## Offline verification
- Python compile: passed
- git diff --check: passed
- Deterministic test script: PASS; 8 mappings and 4 negative assertions.
- Host Python import through application package was unavailable (httpx missing); direct executable isolated module tests passed.
- Docker isolated candidate image build: passed.

## Runtime blocking event
Attempt to prepare an isolated candidate smoke with a narrowly selected provider environment using LocalBridge was blocked by OpenAI tool safety.
No workaround of protected owner verification material was attempted.
No candidate container was replaced or restarted, no port 18080 switch, no target8, target9, or Direct100 runtime reruns were executed.
This is a tool-safety block after successful offline tests and image build, not a provenance source absence and not a Direct100 PASS.

## Gate status
- Targeted8: NOT_RUN
- Stage30J regression9: NOT_RUN
- Same Stage30H Direct100: NOT_RUN
- Full523: NOT_RUN
- No owner-only observation, public owner-gated route, Nginx edits, M26 or test backend restarts, release pointer mutation, production datastore writes, Stage13/14 or Chunk002.
- Owner-only route certification remains pending.
