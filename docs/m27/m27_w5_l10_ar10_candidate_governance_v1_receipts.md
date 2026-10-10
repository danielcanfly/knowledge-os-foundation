# M27 W5 L10 | AR10 Governed Learning Candidate-Only Offline Receipts

## Contract and scope
- New namespace: ar10.proposal/v1, distinct from AR06 user-content memory and AR01D ABI.
- Executable: AR10CandidateGovernanceV1. Accepts an operator-provided disposable local SQLite path; no network, Provider/IdP, real action adapter, hidden corpus, external signing, runtime policy pointer or release interface.
- Immutable synthetic ImprovementProposal separates tenant/source/subject/purpose, consent and tombstone generations, retention/expiry, frozen base/control/runner/candidate/source/rubric/manifest SHA256 pins, independent reviewer reference and bounded effect.
- Type-to-effect mapping is allowlisted. Evaluator proposals are design-only and never grade themselves. Tool-policy proposals only suggest tightened permissions. ACL, AR02 journal authority, AR04 grants, consent, budgets and REL release gates cannot be modified.
- RightsSnapshot is a *local fixture assertion*, not an independently signed AR03 source authority. No local receipt certifies real source rights or independent identities.
- Durable admission DRAFT → ELIGIBILITY_REVIEW → OFFLINE_REVIEW. Later states, including BLIND_EVAL, signed version, canary, production and REL02 return G09_EXTERNAL_BLOCKED and zero effects.
- No owner ACK, security approval, finance review or authenticated reviewer signature is synthesized. Reviewer identifiers here are fixture labels, not real approvals.

## Algorithm and replay proof
1. Registration checks strict identity, digests, namespace and types, expiry, source/tenant/purpose/subject consent scope, revised source, taint, contamination and lineage. No raw user source or hidden benchmark is consumed.
2. SQLite BEGIN IMMEDIATE, UNIQUE(tenant,run), compare-and-swap versions, leased owner+epoch+expiry. Every committed journal event is append-only and digest-chained over previous head, sequence, ID, request key, version and transition. Duplicate request keys are idempotent and cross-proposal replay is rejected. Startup and inspection verify journal integrity.
3. record_fence persists monotonic consent/exclusion/tombstone generations or changed revisions and quarantines all matching tenant/purpose/source/subject derivatives. Persisted revocation cannot be cleared by stale replay after restart. REVOCATION, LEAK, TAINT and UNKNOWN_EFFECT are local quarantine reasons.
4. Crash after separately committed lease preparation is recoverable from actual local SQLite. Stale owner, lease epoch, version or expiry fails closed. Local rollback changes only the prior candidate review status, never a live runtime pointer.
5. evaluate_matched_offline consumes only synthetic frozen MatchedOfflineCohort and concrete accepted-W4 fixture structures: E09H DenominatorLedger, D09 verdict dictionary, T09 StreamVerdict, P09 Admission and E09B AdmissionDecision. No genuine independent authority is inferred from their shapes or self-reported PASS.
6. The full preassigned denominator preserves failure, abstain, partial, timeout, UNKNOWN and missing cases. Version, source, control/candidate pin, rubric, assignments, paired strata, attempts, economic evidence, safety and source rights are checked. Missing invoice or safety regressions make results INELIGIBLE.
7. Local comparison is never promotion eligible, even if synthetic candidate wins. No learned threshold, measured real-world uplift, sealed hidden score, independently certified cost per accepted task, verified client TTFT or actual product p95 is asserted.

## External barriers
W4_ENGINEERING_LOCAL_ACCEPTED_PHASE_B_EXTERNAL_BLOCKED remains binding. D09 lawful independent corpus not admitted; T09 real authenticated client ACK and first verified substantive answer text unverified; P09 genuine role/source/cost authority absent; E09B true independently blind Phase B not run. Real immutable runner/image attestation, independent score custody, security/privacy/finance approval, release authority, canary, verified rollback and REL01/REL02 remain externally gated.

## Reproduction and evidence
Pinned interpreter: /Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python, PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, -B -m pytest -q -p no:cacheprovider. Ruff checks only the new source/test files. Tests include distinct proposal injection and matched comparison adversarial cases, release forgery, concurrent leases, actual SQLite restart, lease prepare/crash, derivative revocation, journal tamper, and local rollback. Raw terminal exit codes, SHA256 and Git parent/scope are recorded in the separate worker REPORT. Only local engineering with independently reproduced green tests and clean Git can be called AR10_OFFLINE_CANDIDATE_ENGINEERING_PASS. Production effects = 0.
