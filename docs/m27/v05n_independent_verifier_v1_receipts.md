# V05N | Fresh local independent-verifier test component

Status target: **INDEPENDENT_VERIFIER_LOCAL_COMPONENT_ONLY**. Feature off, offline test fixtures, no production, no network, no provider, no durable AR02 journal terminal, no real client publication. All eligible statuses are the literal ELIGIBLE_TEST_FIXTURE_ONLY. Every decision hardcodes can_terminalize/can_publish/real_client_delivery_proven/ar02_mutated to false.

## Interface and trust envelope

The independently versioned API is propose_eligibility(bundle, ctx, *, trust) -> VerifierDecision. The context must originate outside the generator as a current independently scoped journal/head, principal/audience, trusted issuer allowlist, source revisions, sandbox path and pinned HEAD. No automatic runtime integration exists.

- ArtifactEvidenceV1 is compared against bytes read using directory-relative O_NOFOLLOW and exact byte size/hash, Git HEAD checked with fixed read-only argv, ZIP directory entries checked for symlink/traversal and oversized unpacked sums. This does not replace a sandbox, no-TOCTOU workspace attestation or a full ZIP decompression guard.
- ExecutionReceipt binds actual digest, pinned HEAD, exact runner argv/CWD, separate runner issuer, signed execution ID, stdout/stderr digests, PID, start/end, test counts, exit code zero. Locally signed HMAC fixtures do not prove an external CI runner. Real acceptance requires an independently executed runner and independently authenticated logs.
- SourceRights and NativeSource bind exact signed original-byte SHA256, issuer-checked scoped revision, tenant, principal, audience, expiry, revocation. NativeCitationProof binds an exact nonempty span of original bytes. CitationReview separately signed semantic support is mandatory per span; research requires explicitly checked counterevidence source references. Tests use mock oracle, never model-claimed quality.
- VerifiedFrame, ServerTransportProof and TransportAckProof distinguish QUEUED, FLUSHED and signed client receipt, with identical session/nonce/segment/revision/payload hash and preterminal clock order. Caller supplies previously seen authenticated ACK and terminal IDs, which must be maintained by a future durable transport/writer, not trusted from a model.
- OperationObservation rejects incomplete/UNKNOWN and requires independent observer for ACTION. CostEvidence rejects unpriced, unreconciled, duplicated and overspent costs. Neither is a provider observer/invoice.
- VerifierAttestation must be separately signed and cover a canonical digest of every evidence field, current journal head, trusted signer identity. AuthenticatingTrust is deliberately injected; no embedded signing key, issuer fabrication or permissive fall-through. The test signer is a local synthetic HMAC only. No real issuer claims follow from fixture green.

## Integration gaps

A real independent IdP/source policy registry, revocation stream, read grant, signed source byte custody, external CI runner with authenticated reproducible logs, separately managed verifier keys/rotation/revocation, independent effect observer and negative-visibility authority, authenticated client session/ACK replay cursor, real billing, atomic AR02 compare-and-swap, and external AR09 hidden oracle remain **UNIMPLEMENTED**. Local Git checks do not imply an immutable remotely attested build workspace. Artifact decompression limits are based on ZIP directory sizes, without archive extraction. Real release and I01 remain NOT ACCEPTED.

## Evidence and execution policy

Tests must be run via the actual scoped pytest interpreter, then separately reproduced, plus accepted AR05/AR09B/AR09C regressions and scoped Ruff, recording original terminal stdout/stderr/exit codes to the named V05N evidence directory. Neither a source claim nor this document is test evidence. Raw test exits, commit, git show --check and SHA256 live in the worker report and its evidence directory, not in model assertions. Earlier V05 untracked WIP and all historically refused equivalent patches remain unmodified.
