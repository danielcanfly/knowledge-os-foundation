# M27 W4 D09 | Corpus admission v1 evidence receipts
Date: 2026-10-10. Scope: independent metadata-only admission. **W4_D09_CORPUS_NOT_ADMITTED**.

## Safety and bounded read-only inventory

- G0 input: worktree W4_D09_CORPUS_ADMISSION; required clean parent bbcd019a787114bbde327b2b3eafb0d73935e963.
- This lane inspected already-approved policy and Master evidence text, the existing AR09B/C/E09H public source interfaces, and historical Stage30O local results in the isolated checkout. It did not inspect any protected hidden questions, seeds, gold labels, private corpus bytes, unpublished I02 worker answers, or real source bodies.
- Bounded filename inventory was restricted to 05_EVIDENCE_INDEX, 03_HANDOFFS and 07_MASTER_REBASE_20261010/02_ACCEPTANCE, max depth 2, filenames only. It surfaced AR00A_SOURCE_MANIFEST, REL01B_BLIND_HOLDOUT_PROTOCOL, REL01D_CORPUS_ELIGIBILITY, and REL01D_REVIEWER_AND_ACCESS_PLAN. All are historical/source identity or protocol/design documents, **not a qualified independently signed sealed holdout corpus manifest**.
- REL01B is explicitly DESIGN ONLY; REL01D independently says corpus metadata UNVERIFIED; REL01E gates G06 through G13 are insufficient for real unseen product QA. No global nonexistence claim is made: externally protected escrow, license records, and evaluator-held manifests were not accessible or authorized for inspection.
- No live Provider, IdP, network crawling, protected route, production, independent holdout execution, label extraction, or sibling worktree write.

## Historical 523: recomputed from approved local rows

The existing checked-in Stage30O results file docs/m27/research/97_m27_mixed_full523_admission_results.json has 523 persisted rows. An independent read-only aggregation of row metadata and in-memory normalized-question fingerprints produced:

| Measure | Recomputed |
| --- | ---: |
| Total rows | 523 |
| execution_mode: live_answer_stream | 341 |
| execution_mode: contract_replay | 182 |
| Live verified_cited_answer | 237 |
| Live safe_abstention | 52 |
| Live rejected_before_provider | 52 |
| Replay budget_terminal | 26 |
| Replay m26_invariant | 26 |
| Replay governance_contract | 130 |
| Distinct normalized questions across all rows | 20 |
| Distinct normalized cited-answer questions | 9 |

No normalized question or question fingerprint is persisted to the documentation or report. Lexical dedup is **not proof of semantic intent diversity**. The 523 row total includes 182 contract replays, so must not be marketed as 523 independently unseen Q&A cases. Direct100, Stage30O and 30P contain historically developer-visible questions and are ineligible to become a new blind holdout. Historical proxy cited flags do not provide independently graded final answer, source-span entailment, true first substantive answer text byte, authoritative cost or approved release denominator.

## Two separate gates

**Original product 523 gate:** actual candidate and denominator, cited final-answer >=95% on approved original 523, p95 <=15s, genuinely streamed first answer text. Nothing in this D09 task executes or certifies that gate.

**AR09 Phase B independent holdout design:** exactly 200 fresh unseen questions, at least 140 genuinely independent intents, at least 100 independently originated sources actually used, at least 20 docs, at least 5 families, at least 40 long-tail and 60 explicit paraphrase probes, at least 30 negative pairs and 20 supported positives plus 20 provenance positives. Maximum per document 20 cases, family 40, Graphology 30, historical topics 40. Nine disjoint primary strata have counts 32/26/28/18/20/18/16/14/28. External reviewers, source rights, independent sealed case custody and evaluator separation are mandatory. A true E09B run requires separately authorized frozen candidate, rubric and cost caps, score >=85 per answerable, strictly >95% answerable success, strictly <15s p95, real first answer text byte, provenance/citation binds, all planned cases in denominator and zero critical breach. No hidden case run is launched here.

## Versioned scanner and trust boundaries

Source: src/knowledge_engine/m27_w4_d09_corpus_admission_v1_experimental.py

- API scan_manifest(manifest, registry=None, now=None) -> aggregate-only machine-readable verdict, fixed schema m27-w4-d09-corpus-admission-v1, per-gate statuses exactly ELIGIBLE, NOT_ELIGIBLE, MISSING, ACCESS_RESTRICTED or NOT_VERIFIED. The verdict is W4_D09_CORPUS_NOT_ADMITTED unless all metadata admission gates pass.
- API audit_historical_rows(rows) -> metadata-only row/mode/lexical counts, never returns question text.
- TrustedCustodyRegistry must be authenticated by a genuinely independent provisioner out of band. Never trust a registry created by the implementer or manifest self-claims. Approval signature HMAC verification is a narrow testable interface, not complete real-world proof of independent custodial identity. sign_fixture is **strictly synthetic tests only**, not third-party attestation.
- The scanner requires independent source digest/revision/origin/family/document evidence, license and valid ACL/retention/consent, evaluator-only access ledger, independent reviewer roster and case-level dual-review attestations, sealed dataset ID/digest plus opaque secure storage reference, frozen candidate identity and independent case intent/dedup attestation. It enforces numeric/dedup/topic/stratum/source diversity limits.
- It rejects unrecognized metadata keys (including embedded hidden prompts, answers, labels or seed material), signature tampering, contaminated cases, repeated semantic intent without explicit paraphrase, forged source snapshots or metadata, implementer access, missing reviewer proofs, and expired scopes.
- The result always has may_launch_test=false, even for a synthetic metadata-eligible fixture. E09B actual holdout execution and original product 523 scoring remain explicitly separate gates.
- Tests are synthetic guard exercising only. Test-key fixtures and boolean trust attributes must never be installed as genuine custodian credentials; this task has **zero independent external corpus authority**.

## Evidence debt and minimal lawful next action

1. Owner appoints an independent rights steward and dataset custodian, approves evaluation license and PII/exclusion, source scope, consent and deletion deadline.
2. Steward delivers a **nonsecret metadata-only**, independently issued signed inventory of 100+ usable approved sources across 20+ docs and 5+ true origins/families, including source revisions/SHA256/span indices, ACL and license/retention cutoffs.
3. Independent custodian stores unseen cases, seeds, answer keys and labels only in protected escrow, and furnishes a verifiable signed opaque sealed dataset ID/digest/storage alias, no sensitive bytes, access ledger, dual-review records and signed intent-dedup and historical/dev exclusion evidence.
4. Master freezes and attests the real candidate and evaluator contracts and authorizes a new, separately isolated E09B official blind run. Without this, status stays **W4_D09_CORPUS_NOT_ADMITTED**, regardless of unit-test success. REL01 remains NOT CERTIFIED and REL02 NOT AUTHORIZED.
