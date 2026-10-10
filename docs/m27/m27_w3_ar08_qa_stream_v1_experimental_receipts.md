# W3 S08Q | AR08 Q&A native citation stream v1 | offline receipts

Status: **experimental / feature-off / nonmutating**. Contract `AR08NativeQAStream/1.0-test-only`. Scope is only the three newly added S08Q source, tests and docs files. Original M26 Q&A routing, corpus, native source IDs, any Provider, IdP, remote delivery or Production are intentionally **not called or modified**.

## Proven implementation

- `NativeSourceBytes` includes the original supplied UTF-8 source bytes, exact `source_id`, **native citation ID**, source revision, SHA256, actor/tenant, observation identity and source expiry. It is an AR03 *consumer* seam, not an AR03 authoritative verifier.
- `CitationByteSpan` pins original source claim bytes to exact byte offsets with UTF-8 boundary validation, source digest, revision, native citation ID. `AnswerEvidenceLink` binds answer byte ranges to those source spans. Every nonwhitespace answer byte requires an evidence link. Claim entailment **is not established here**: the injected independent AR05 proposal/verifier owns that trust decision.
- `VerificationProposal` carries frozen verified answer UTF-8 bytes, digest, linked citations, issued/expires clock, actor/tenant/run and revision. `VerificationPort` must validate the independently provided proposal at preparation and emission. Port injection in unit tests is a fixture, **never real authorization**.
- `VerifiedTextFrame` has version, immutable chunk bytes, SHA256, source **native citation IDs**, answer offsets, per-stream sequence and AR05 proposal ID. Decoder buffers split UTF-8 codepoints, emits only complete codepoints and checks the input bytes against the complete verified answer prefix. Every chunk is fail closed on fresh source/proof, exact actor and revocation, before enqueue and again between enqueue and flush. Original source data is read-only and no synthetic document converter is invoked.
- `TransportPort.enqueue` and `TransportPort.flush` are independently invoked in-process callbacks. The transport callback event log proves enqueue -> flush -> terminal ordering and `SubstantiveFirstAnswerReceipt` only records a flush of **non-whitespace** verified answer bytes before terminal. Empty/progress text never satisfies this. An exception after an ambiguous enqueue or flush quarantines the stream: **no blind replay**.
- `StreamSequenceState` models active, cancelled, quarantined and terminal transitions; `reconnect` requires correct actor/tenant and exactly next sequence and never re-emits. Terminal requires the full verified answer and at least one substantive, flushed preterminal frame. `accept_client_ack` rejects untrusted data; an in-process callback can never establish real authenticated remote client delivery.
- `ClockPort` samples `monotonic_ns` with independent wall milliseconds used only for expiry; refuses mismatched domain and clock rollback.

## Controlled evidence and limits

The positive harness observes actual Python in-memory enqueue/flush callbacks, including split multi-byte `β` and original bytes `Alpha βeta\n`. Tests cover source digest mismatch, citation substitution/drift, byte range corruption, span splitting inside UTF-8, incomplete terminal fragments, whitespace/non-substantive gate, stale/revoked AR03/AR05 proof, fake client ACK, wrong identity, clock rollback/domain, source duplication, reconnect duplication/gap/future cursor, replay initial byte, cancellation, terminal-only claims, post-terminal push, and enqueue/flush faults.

**Negative test model:** fixture authority/verifier callbacks are separately injected and can revoke mid-send; they are test seams, not cryptographic proofs or real external issuers. No 523 corpus evaluation, entailment quality score, authenticated client ACK, externally measured TTFT, first-token network latency or REL01 milestone is represented.

Every receipt explicitly returns `client_delivery_unverified` and `PRODUCT_TTFT_UNVERIFIED`. `QA_LOCAL_NONMUTATING_STREAM_COMPONENT_PASS` is only a valid worker claim **after** executable positive/negative tests, Ruff, frozen commit parent, exact allowlist and SHA verification succeed. W4/I02/E09 and REL01 remain under separate Master acceptance.

## Reproducibility

Pinned interpreter: `/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python`, version 3.11.15. From this isolated worktree, with `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, run:

```sh
/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python -B -m pytest -q -p no:cacheprovider tests/test_m27_w3_ar08_qa_stream_v1_experimental.py
/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python -B -m ruff check --no-cache src/knowledge_engine/m27_w3_ar08_qa_stream_v1_experimental.py tests/test_m27_w3_ar08_qa_stream_v1_experimental.py
```

Versioned terminal receipts, pytest/Ruff raw results, SHA256 and Git scope are stored outside this worktree in `05_EVIDENCE_INDEX/W3_S08Q_AR08_NATIVE_QA_STREAM_SCRATCH/` with summary `02_REPORTS/W3_S08Q_AR08_NATIVE_QA_STREAM_REPORT.md`. This documentation is the third and final tracked addition.
