"""I01 true local SQLite/rights/permit/verifier integration; synthetic proof ONLY."""
from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import subprocess
import sys
from dataclasses import replace

import pytest

from knowledge_engine import m27_ar05_independent_verifier_v1_experimental as v5
from knowledge_engine.m27_ar02_durable_writer_v1_experimental import (
    DurableWriterV1,
    FenceError,
    RunIdentity,
)
from knowledge_engine.m27_ar03_verified_rights_v1_experimental import (
    CHECKPOINT_VERSION,
    PIN_VERSION,
    SCHEMA_VERSION,
    ClaimSpanV1,
    EffectiveActor,
    IssuerKeyRegistry,
    NativeCitationPinV1,
    ReadIntent,
    RightsDenied,
    RunCheckpointV1,
    ScopeSet,
    SourceAuthorityEvidenceV1,
    TrustedIssuerKey,
    VerifiedAuthorityClaim,
    VerifiedRightsConsumer,
    VerifiedSourceObservation,
)
from knowledge_engine.m27_ar04_permit_sandbox_v1_experimental import (
    CapabilityRule,
    Denied,
    InProcessFixtureObserver,
    Registry,
)
from knowledge_engine.m27_i01_core_local_vertical_v1_experimental import (
    EXTERNAL_AUTHORITY_REQUIRED,
    TEST_FIXTURE_SUCCESS,
    UNKNOWN_EFFECT,
    I01CoreVerticalV1,
    I01Denied,
    LocalRequest,
)

ORIGINAL = "Alpha βeta source.\n".encode()
DIGEST = hashlib.sha256(ORIGINAL).hexdigest()
ROLE_KEYS = {
    ("runner", "ci"): b"synthetic-runner",
    ("rights", "fixture-rights"): b"synthetic-rights",
    ("citation_oracle", "oracle"): b"synthetic-citations",
    ("server_transport", "server"): b"synthetic-server",
    ("client_ack", "client"): b"synthetic-client",
    ("observer", "independent-effect"): b"synthetic-effect",
    ("billing", "invoice"): b"synthetic-billing",
    ("verifier", "validator"): b"synthetic-validator",
}
ISSUER = TrustedIssuerKey("fixture-idp", "fixture-k1", "offline", "TEST", 1)
VERIFIER_KEY = b"test-local-terminal-key-do-not-deploy"


def proof(role, issuer):
    return v5.SignedProof(issuer, "local-test-key", role, "")


class LocalTrust:
    def sign(self, item):
        domain = item.proof.domain
        key = ROLE_KEYS.get((domain, item.proof.issuer_id), b"wrong-key")
        mac = hmac.new(key, v5._message(domain, item), hashlib.sha256).hexdigest()
        return replace(item, proof=replace(item.proof, signature=mac))

    def verify(self, issuer_id, key_id, domain, message, signature):
        key = ROLE_KEYS.get((domain, issuer_id))
        return (key_id == "local-test-key" and key is not None
                and hmac.compare_digest(
                    hmac.new(key, message, hashlib.sha256).hexdigest(), signature
                ))


def seal(bundle, trust):
    bundle = replace(
        bundle,
        execution=trust.sign(bundle.execution),
        rights=tuple(trust.sign(x) for x in bundle.rights),
        reviews=tuple(trust.sign(x) for x in bundle.reviews),
        server=trust.sign(bundle.server),
        client_acks=tuple(trust.sign(x) for x in bundle.client_acks),
        operation=trust.sign(bundle.operation) if bundle.operation else None,
        cost=trust.sign(bundle.cost),
    )
    bundle = v5.finalize_test_fixture(bundle)
    return replace(bundle, verifier=trust.sign(bundle.verifier))


class SourceFixture:
    fixture_kind = "TEST_FIXTURE_ONLY"

    def __init__(self):
        self.clock = 100
        self.checkpoint = None
        self.tokens = {}
        self.used = set()
        self.source = VerifiedSourceObservation(
            "fixture-provider", "account", "t1", "/tenants/t1/items/one",
            "native:one", "r1", ORIGINAL, frozenset({"delegate"}),
            frozenset({"qa"}), frozenset({"read", "cite"}),
            "consent", True, 0, 4, 5, 99, 200,
        )
        self.enabled = True

    def bind(self, checkpoint):
        self.checkpoint = checkpoint
        self.tokens[b"fixture-secret-token"] = VerifiedAuthorityClaim(
            ISSUER.issuer_id, ISSUER.key_id, ISSUER.audience, ISSUER.algorithm,
            ISSUER.trust_store_version, 90, 90, 150, "jti/test-read",
            EffectiveActor("owner", "delegate", "t1", "owner", ("owner", "delegate")),
            ScopeSet("t1", "/tenants/t1/items/one", "qa",
                     frozenset({"read", "cite"})),
            "task", "run", checkpoint.sequence, checkpoint.head_sha256,
            "fixture-provider", "account", "native:one", "r1", DIGEST,
            "consent", 0, 4, 5,
        )

    def trusted_now(self):
        return self.clock

    def verify_authority(self, assertion, key):
        return self.tokens.get(assertion) if self.enabled and key == ISSUER else None

    def observe_source(self, pin):
        return self.source if self.enabled else None

    def checkpoint_is_current(self, checkpoint):
        return checkpoint == self.checkpoint

    def reserve_once(self, issuer, jti, checkpoint):
        nonce = (issuer, jti, checkpoint.head_sha256)
        if not self.checkpoint_is_current(checkpoint) or nonce in self.used:
            return False
        self.used.add(nonce)
        return True

    def has_reservation(self, issuer, jti, checkpoint):
        return (issuer, jti, checkpoint.head_sha256) in self.used


class Rig:
    def __init__(self, path):
        self.folder = path
        self.path = path / "journal.sqlite"
        self.source = SourceFixture()
        self.writer = DurableWriterV1(
            self.path, fixture_approval_mode=True,
            verifier_keys={"fixture-terminal-verifier": VERIFIER_KEY},
        )
        self.registry = Registry(
            "fixture-policy", frozenset({"fixture-approver"}),
            frozenset({"fixture-observer"}), "fixture-ar02-writer",
            frozenset({"fake-adapter"}),
            (CapabilityRule("cap.items", "1", "update",
                            "/tenants/t1/items/", "fake-adapter", 12),),
        )
        self.identity = RunIdentity("t1", "run", "task", 1, "delegate")
        self.consumer = VerifiedRightsConsumer(
            IssuerKeyRegistry((ISSUER,)), self.source,
        )
        self.tamper_bundle = None
        self.probe = None
        self.engine = self.engine_for()
        self.head = self.engine.prepare(
            self.identity, budget=20, source_revision="r1",
            consent_generation=4, exclusion_generation=5,
        )
        self.checkpoint = RunCheckpointV1(
            CHECKPOINT_VERSION, "task", "run", self.head.seq, self.head.digest,
        )
        self.source.bind(self.checkpoint)
        self.pin = NativeCitationPinV1(
            PIN_VERSION, "fixture-provider", "account",
            "/tenants/t1/items/one", "native:one", "r1", DIGEST,
            (ClaimSpanV1(0, 5, "Alpha"), ClaimSpanV1(6, 11, "βeta")),
        )
        self.req = LocalRequest(
            self.identity, ReadIntent("task", "run", "owner", "delegate", "t1", "qa"),
            SourceAuthorityEvidenceV1(
                SCHEMA_VERSION, ISSUER.issuer_id, ISSUER.key_id, ISSUER.audience,
                b"fixture-secret-token",
            ),
            self.pin, self.checkpoint, "intent-1", "approval-1",
            "claim-1", "reserve-1", "charge-1",
            "/tenants/t1/items/one", "recipient", "idempotency-1", 5, 100, 180,
        )

    def engine_for(self, *, fixture=True, probe=None):
        return I01CoreVerticalV1(
            writer=self.writer, rights=self.consumer,
            source_verifier=self.source, registry=self.registry,
            worker_id="fixture-worker",
            observer=InProcessFixtureObserver(
                "fixture-observer", "fixture-observer", "fixture-grant",
            ),
            fixture_bundle=self.bundle if fixture else None,
            local_signer=self.sign_terminal if fixture else None,
            stage_probe=probe,
        )

    @staticmethod
    def sign_terminal(identity, head, evidence_ref, verification_ref, status):
        message = DurableWriterV1.verification_message(
            identity, head, evidence_ref=evidence_ref,
            verification_ref=verification_ref, status=status,
        )
        return hmac.new(VERIFIER_KEY, message, hashlib.sha256).hexdigest()

    def bundle(self, head, original, outcome, digest):
        work = self.folder / "fixture-workspace"
        work.mkdir(exist_ok=True)
        data = b"LOCAL fixture artifact; no external effect\n"
        (work / "result.txt").write_bytes(data)
        subprocess.run(["git", "init", "-q", str(work)], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(work), "add", "result.txt"], check=True,
                       capture_output=True)
        subprocess.run([
            "git", "-C", str(work), "-c", "user.name=Fixture",
            "-c", "user.email=fixture@example.invalid",
            "commit", "-q", "-m", "local-test",
        ], check=True, capture_output=True)
        githead = subprocess.check_output(
            ["git", "-C", str(work), "rev-parse", "HEAD"], text=True,
        ).strip()
        ctx = v5.VerificationContext(
            "t1", "task", 1, "run", "outcome", digest,
            head.digest, head.epoch, head.digest, str(work), githead,
            ("python", "-m", "pytest", "offline"),
            "ACTION", (("native:one", "r1"),),
            "delegate", "offline", 1000, trust_issuers=tuple(ROLE_KEYS),
        )
        source = v5.NativeSource("native:one", "r1", original, v5.sha(original))
        right = v5.SourceRights(
            "native:one", "r1", v5.sha(original), "t1", "delegate",
            "offline", True, False, 2000, proof("rights", "fixture-rights"),
        )
        citations = tuple(v5.NativeCitationProof(
            "cit-" + str(n), "native:one", "r1", v5.sha(original),
            span.start_byte, span.end_byte,
            original[span.start_byte:span.end_byte],
            v5.sha(original[span.start_byte:span.end_byte]),
        ) for n, span in enumerate(self.pin.spans))
        reviews = tuple(v5.CitationReview(
            c.citation_id, c.claim_sha256, True, False, (),
            proof("citation_oracle", "oracle"),
        ) for c in citations)
        frame = v5.VerifiedFrame(
            "verified_text", b"fixture verified response", tuple(
                c.citation_id for c in citations
            ), "validator", "session", "nonce", "segment", 1, 700, 950,
        )
        server = v5.ServerTransportProof(
            "FLUSHED", "session", "nonce", "segment", 1,
            v5.sha(frame.content), 750, proof("server_transport", "server"),
        )
        ack = v5.TransportAckProof(
            "synthetic-ack", "session", "nonce", "segment", 1,
            v5.sha(frame.content), 1, 800, proof("client_ack", "client"),
        )
        bill = v5.CostEvidence(
            ("charge-1",), 5, 5, 5, True, proof("billing", "invoice"),
        )
        runner = v5.ExecutionReceipt(
            str(work), githead, v5.sha(data), ctx.required_command, str(work),
            True, 0, 1234, 400, 600, 1, 35, v5.sha(b"out"), v5.sha(b"err"),
            "test-run", proof("runner", "ci"),
        )
        attestation = v5.VerifierAttestation(
            "validator", "", head.digest, 900, proof("verifier", "validator"),
        )
        bundle = v5.EvidenceBundle(
            v5.ArtifactEvidenceV1(
                str(work), "result.txt", len(data), v5.sha(data), githead,
                "t1", "task", "run", "outcome",
            ),
            runner,
            v5.VerifierIdentity("generator", "validator", "verifier", "runner"),
            (source,), (right,), citations, reviews, frame, server, (ack,),
            v5.OperationObservation(
                ("claim-1",), ("claim-1",), "APPLIED", "r1", True,
                proof("observer", "independent-effect"),
            ),
            bill, attestation, "t1", "task", 1, "run", "outcome", digest,
            head.digest, head.epoch, "terminal-1",
        )
        trust = LocalTrust()
        if self.tamper_bundle is not None:
            bundle, ctx, trust = self.tamper_bundle(bundle, ctx, trust)
        return seal(bundle, trust), ctx, trust


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def test_actual_four_module_sqlite_success_path_and_recovery(rig):
    result = rig.engine.execute(rig.req)
    assert result.status == TEST_FIXTURE_SUCCESS
    assert result.trace == (
        "AR02_DURABLE_HEAD", "AR03_VERIFIED_NATIVE_READ",
        "AR04_POLICY_AND_AR02_T1_T2_DURABLE_CLAIM",
        "AR02_T3_UNKNOWN_FENCE_LOCAL_ONLY",
        "AR04_IN_PROCESS_FIXTURE_OBSERVER",
        "AR02_T4_OBSERVER_REFERENCE_UNATTESTED",
        "AR05_INDEPENDENT_FIXTURE_PROPOSAL",
        "AR02_LOCAL_TEST_TERMINAL_CAS",
    )
    assert result.provider_calls == 0 and not result.published
    with sqlite3.connect(rig.path) as a, sqlite3.connect(rig.path) as b:
        assert a.execute("select state from runs").fetchone()[0] == (
            "LOCAL_VERIFIED_APPLIED"
        )
        assert b.execute("select state from outbox").fetchone()[0] == "T4_RECORDED"
        assert a.execute("select count(*) from events").fetchone()[0] >= 9
        assert b.execute("select spent,reserved from runs").fetchone() == (5, 0)
    reopened = DurableWriterV1(
        rig.path, fixture_approval_mode=True,
        verifier_keys={"fixture-terminal-verifier": VERIFIER_KEY},
    )
    assert reopened.recover(rig.identity)["head"] == result.head
    with pytest.raises((FenceError, I01Denied)):
        rig.engine.execute(rig.req)


def test_absent_real_issuer_fixture_fails_closed_before_reserved(rig):
    head = rig.writer.read_head(rig.identity)
    result = rig.engine_for(fixture=False).execute(rig.req)
    assert result.status == EXTERNAL_AUTHORITY_REQUIRED
    assert result.head == head
    assert rig.writer.recover(rig.identity)["outbox"] == []


@pytest.mark.parametrize(
    "field,bad", [
        ("version", "forged"), ("issuer_id", "forged-idp"),
        ("key_id", "stolen"), ("audience", "wrong-audience"),
        ("opaque_assertion", b"impostor"), ("opaque_assertion", b""),
        ("opaque_assertion", b"tool-approved-true"),
        ("opaque_assertion", b"self-authorized"),
    ],
)
def test_independent_read_rejects_forged_claims(rig, field, bad):
    r = replace(rig.req, evidence=replace(rig.req.evidence, **{field: bad}))
    with pytest.raises(RightsDenied):
        rig.engine.execute(r)
    assert rig.writer.read_head(rig.identity) == rig.head


@pytest.mark.parametrize(
    "change", [
        {"task_id": "another"}, {"run_id": "another"},
        {"tenant_id": "other"}, {"principal_id": "stranger"},
        {"task_version": 2},
    ],
)
def test_run_identity_is_pinned_to_sqlite(rig, change):
    r = replace(rig.req, identity=replace(rig.identity, **change))
    with pytest.raises((I01Denied, FenceError, KeyError)):
        rig.engine.execute(r)


@pytest.mark.parametrize(
    "bad", [
        "/tenants/t1/items/../escaped",
        "/tenants/t1/items/%2e%2e/escaped",
        "/tenants/t1/items//escaped",
        "/tenants/t1/items/./escaped",
        "/tenants/t1/items/é",
        "/tenants/t2/items/one",
        "/tenants/t1/items/",
        "/tenants/t1/items/one;rm -rf /",
    ],
)
def test_ar04_blocks_malicious_and_cross_tenant_resources(rig, bad):
    r = replace(rig.req, resource_id=bad)
    with pytest.raises((Denied, I01Denied)):
        rig.engine.execute(r)
    assert rig.writer.recover(r.identity)["outbox"] == []


@pytest.mark.parametrize(
    "change", [
        {"cost": 0}, {"cost": -1}, {"cost": 21},
        {"now": 180}, {"expires_at": 100},
    ],
)
def test_budget_and_consent_fences(rig, change):
    with pytest.raises(I01Denied):
        rig.engine.execute(replace(rig.req, **change))
    assert rig.writer.recover(rig.identity)["outbox"] == []


@pytest.mark.parametrize(
    "source_change", [
        {"consent_active": False},
        {"source_revision": "revoked-r2"},
        {"original_bytes": b"tampered native bytes"},
        {"acl_principals": frozenset()},
        {"purposes": frozenset()},
        {"valid_until": 100},
    ],
)
def test_source_denied_before_any_local_effect(rig, source_change):
    rig.source.source = replace(rig.source.source, **source_change)
    with pytest.raises((RightsDenied, I01Denied)):
        rig.engine.execute(rig.req)
    assert rig.writer.read_head(rig.identity) == rig.head


@pytest.mark.parametrize(
    "stage", ["after_read", "before_claim", "after_claim",
              "after_t3", "before_t4", "before_ar05", "before_terminal"],
)
def test_lease_cancel_and_stale_head_never_terminalize(rig, stage):
    def cancel(label, head):
        if label == stage:
            rig.writer.takeover(rig.identity, head)
    rig.engine = rig.engine_for(probe=cancel)
    with pytest.raises(I01Denied, match="STALE_OR_CANCELLED"):
        rig.engine.execute(rig.req)
    assert rig.writer.read_head(rig.identity).state == "OPEN"


def test_source_revoked_between_read_and_claim(rig):
    def revoke(stage, head):
        if stage == "after_claim":
            rig.source.source = replace(
                rig.source.source, source_revision="r2",
                consent_active=False,
            )
    rig.engine = rig.engine_for(probe=revoke)
    with pytest.raises(I01Denied, match="SOURCE_REVOKED"):
        rig.engine.execute(rig.req)
    assert rig.writer.recover(rig.identity)["head"].state == "OPEN"


@pytest.mark.parametrize("effect", ["unknown", "not_applied"])
def test_unknown_effect_remains_durable_and_unreplayable(rig, effect):
    result = rig.engine.execute(replace(rig.req, effect=effect))
    assert result.status == UNKNOWN_EFFECT
    assert result.head.state == "OPEN"
    recovered = rig.writer.recover(rig.identity)
    assert recovered["outbox"][0]["state"] == "POSSIBLY_SENT"
    with pytest.raises((FenceError, I01Denied)):
        rig.engine.execute(rig.req)


@pytest.mark.parametrize(
    "mutation", [
        "wrong_artifact_bytes", "no_client_ack", "fake_observer", "self_verifier",
        "wrong_sign_domain", "late_invoice", "wrong_source", "broken_span",
        "wrong_current_head", "untrusted_runner", "unknown_operation",
        "duplicate_terminal", "missing_actual_cost",
    ],
)
def test_ar05_negative_seam_never_commits_terminal(rig, mutation):
    def tamper(b, ctx, trust):
        if mutation == "wrong_artifact_bytes":
            b = replace(b, artifact=replace(b.artifact, sha256="f" * 64))
        elif mutation == "no_client_ack":
            b = replace(b, client_acks=())
        elif mutation == "fake_observer":
            b = replace(b, operation=replace(
                b.operation, proof=proof("observer", "fake-executor"),
            ))
        elif mutation == "self_verifier":
            b = replace(b, identity=replace(b.identity, verifier_id="generator"))
        elif mutation == "wrong_sign_domain":
            b = replace(b, cost=replace(
                b.cost, proof=proof("runner", "ci"),
            ))
        elif mutation == "late_invoice":
            b = replace(b, cost=replace(
                b.cost, late_billing_reconciled=False,
            ))
        elif mutation == "wrong_source":
            b = replace(b, sources=(replace(
                b.sources[0], original_bytes=b"changed"),
            ))
        elif mutation == "broken_span":
            b = replace(b, citations=(replace(
                b.citations[0], claim_start=99,
            ), *b.citations[1:]))
        elif mutation == "wrong_current_head":
            ctx = replace(ctx, current_journal_head_sha256="a" * 64)
        elif mutation == "untrusted_runner":
            b = replace(b, execution=replace(
                b.execution, proof=proof("runner", "forged-ci"),
            ))
        elif mutation == "unknown_operation":
            b = replace(b, operation=replace(b.operation, effect="UNKNOWN_EFFECT"))
        elif mutation == "duplicate_terminal":
            ctx = replace(ctx, committed_terminal_ids=frozenset({"terminal-1"}))
        elif mutation == "missing_actual_cost":
            b = replace(b, cost=replace(b.cost, actual_microunits=None))
        return b, ctx, trust
    rig.tamper_bundle = tamper
    try:
        outcome = rig.engine.execute(rig.req)
        assert outcome.status == EXTERNAL_AUTHORITY_REQUIRED
    except I01Denied:
        pass
    assert rig.writer.read_head(rig.identity).state == "OPEN"


def test_atomic_t1_t2_reject_duplicate_reserve_claim_and_charge(rig):
    result = rig.engine.execute(replace(rig.req, effect="unknown"))
    assert result.status == UNKNOWN_EFFECT
    with pytest.raises((FenceError, sqlite3.IntegrityError)):
        rig.writer.reserve(rig.identity, result.head, reserve_id="reserve-1", amount=5)
    with pytest.raises(FenceError):
        rig.writer.claim_outbox(rig.identity, result.head, claim_id="claim-1")
    with pytest.raises(FenceError):
        rig.writer.charge(rig.identity, result.head, reserve_id="reserve-1",
                          charge_id="charge-1", amount=500)


def test_ar02_crash_restart_preserves_committed_transaction(tmp_path):
    path = tmp_path / "hard-kill.sqlite"
    source = (
        "import os,sys;"
        "from knowledge_engine.m27_ar02_durable_writer_v1_experimental "
        "import DurableWriterV1,RunIdentity;"
        "w=DurableWriterV1(sys.argv[1],fixture_approval_mode=True);"
        "i=RunIdentity('t1','run','task',1,'delegate');"
        "h=w.create_run(i,budget=10,source_revision='r1',"
        "consent_generation=4,exclusion_generation=5);"
        "w.reserve(i,h,reserve_id='r1',amount=5);"
        "os._exit(23)"
    )
    child = subprocess.run([sys.executable, "-c", source, str(path)],
                           check=False, env=os.environ.copy())
    assert child.returncode == 23
    writer = DurableWriterV1(path, fixture_approval_mode=True)
    identity = RunIdentity("t1", "run", "task", 1, "delegate")
    assert writer.recover(identity)["head"].reserved == 5
    with sqlite3.connect(path) as a, sqlite3.connect(path) as b:
        assert a.execute("select count(*) from events").fetchone()[0] == 2
        assert b.execute("select amount from reservations").fetchone()[0] == 5


def test_durable_sqlite_rejects_uncommitted_torn_transaction(rig):
    with sqlite3.connect(rig.path) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE runs SET budget=999 WHERE run='run'")
        db.rollback()
    assert rig.writer.recover(rig.identity)["head"].budget == 20


def test_external_dispatch_never_authorized(rig):
    result = rig.engine.execute(rig.req)
    assert result.status == TEST_FIXTURE_SUCCESS
    assert not result.published and result.provider_calls == 0
    assert rig.writer.recover(rig.identity)["dispatch_authorized"] is False
