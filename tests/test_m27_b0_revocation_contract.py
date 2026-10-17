"""B0-06 isolated SQLite fixtures. No external authority, provider, or Production."""
import concurrent.futures
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest

# Import this self-contained module directly so unrelated D01 package bootstrap
# and global tests/conftest dependency stacks are not loaded or modified.
MODULE_PATH = (Path(__file__).resolve().parents[1] / "src" / "knowledge_engine"
               / "m27_b0_revocation_contract.py")
spec = importlib.util.spec_from_file_location("m27_b0_revocation_contract", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
LocalRevocationContract = module.LocalRevocationContract
RevocationDenied = module.RevocationDenied
SourceLease = module.SourceLease


@pytest.fixture
def env(tmp_path):
    data = tmp_path / "replaceable" / "artifact.sqlite"
    auth = tmp_path / "protected" / "authority.sqlite"
    store = LocalRevocationContract(data, auth, fixture_only=True)
    return store, data, auth


def grant(store, tenant="t1", principal="p1", source="s1", *, expiry=100):
    return store.provision_fixture(
        tenant=tenant, principal=principal, source_id=source,
        source_revision="revision1", right_version=1,
        consent_expires_at=expiry, actor=principal, authorized_fixture=True)


def revoke(store, tenant="t1", principal="p1", source="s1", *,
           event="revoke01", reason="CONSENT_WITHDRAWN", inject_failure=False):
    return store.revoke(
        tenant=tenant, principal=principal, source_id=source,
        event_id=event, reason=reason, actor=principal,
        authorized_fixture=True, inject_failure=inject_failure)


def denied(code, fn, *args, **kwargs):
    with pytest.raises(RevocationDenied) as error:
        fn(*args, **kwargs)
    assert error.value.code == code


def physical_count(data):
    with sqlite3.connect(data) as db:
        return db.execute("SELECT COUNT(*) FROM entries").fetchone()[0]


def test_scope_cannot_enable_live_authority_or_collapse_protected_db(tmp_path):
    a = tmp_path / "a.sqlite"
    denied("EXTERNAL_AUTHORITY_NOT_IMPLEMENTED", LocalRevocationContract,
           a, tmp_path / "b.sqlite", fixture_only=False)
    denied("AUTHORITY_MUST_BE_SEPARATE", LocalRevocationContract,
           a, a, fixture_only=True)


def test_positive_write_read_and_post_revoke_invalidation_by_kind(env):
    store, data, auth = env
    lease = grant(store)
    items = {"source1": "source", "answer1": "answer_cache",
             "vector1": "derived_cache", "citation1": "citation",
             "memory1": "memory"}
    for key, kind in items.items():
        digest = store.put(lease, entry_id=key, kind=kind, payload=key.encode(), now=1)
        assert digest == hashlib.sha256(key.encode()).hexdigest()
        assert store.get(lease, entry_id=key, now=2) == key.encode()
    assert physical_count(data) == 5
    witness = revoke(store)
    assert witness.deleted_entries == 5
    assert dict(witness.deleted_kinds) == dict.fromkeys(items.values(), 1)
    assert witness.revocation_epoch == 1
    assert len(witness.evidence_sha256) == 64
    assert witness.local_only and not witness.external_erasure_verified
    assert physical_count(data) == 0
    for key in items:
        denied("STALE_RIGHTS_OR_EPOCH", store.get, lease, entry_id=key, now=3)
    denied("STALE_RIGHTS_OR_EPOCH", store.put, lease, entry_id="after",
           kind="answer_cache", payload=b"forbidden", now=3)
    assert store.audit_witness(tenant="t1", principal="p1", source_id="s1",
                               event_id="revoke01", actor="p1",
                               authorized_fixture=True) == witness


def test_revocation_before_first_write_deny_and_non_resurrectable(env):
    store, data, _ = env
    lease = grant(store)
    assert revoke(store).deleted_entries == 0
    denied("STALE_RIGHTS_OR_EPOCH", store.put, lease, entry_id="first",
           kind="memory", payload=b"never", now=1)
    denied("SCOPE_ALREADY_ISSUED_NO_REGRANT", grant, store)
    denied("REVOKED_OR_ACL_DOWNGRADE", store.current_lease_fixture,
           tenant="t1", principal="p1", source_id="s1", actor="p1",
           authorized_fixture=True, now=1)
    assert physical_count(data) == 0


def test_acl_downgrade_and_consent_expiration(env):
    store, data, _ = env
    lease = grant(store, expiry=10)
    store.put(lease, entry_id="cache", kind="answer_cache", payload=b"a", now=9)
    denied("CONSENT_EXPIRED", store.get, lease, entry_id="cache", now=10)
    denied("CONSENT_EXPIRED", store.put, lease, entry_id="write",
           kind="source", payload=b"b", now=10)
    assert store.downgrade_acl_fixture(
        tenant="t1", principal="p1", source_id="s1",
        actor="p1", authorized_fixture=True) == 1
    assert physical_count(data) == 0
    denied("STALE_RIGHTS_OR_EPOCH", store.get, lease, entry_id="cache", now=9)
    denied("REVOKED_OR_ACL_DOWNGRADE", store.current_lease_fixture,
           tenant="t1", principal="p1", source_id="s1",
           actor="p1", authorized_fixture=True, now=9)


def test_right_version_and_epoch_invalidate_existing_cache(env):
    store, data, _ = env
    old = grant(store)
    store.put(old, entry_id="cache", kind="derived_cache", payload=b"old", now=1)
    new = store.advance_right_version_fixture(
        tenant="t1", principal="p1", source_id="s1", new_version=2,
        actor="p1", authorized_fixture=True)
    assert new.right_version == 2 and new.revocation_epoch == 1
    assert physical_count(data) == 0
    denied("STALE_RIGHTS_OR_EPOCH", store.get, old, entry_id="cache", now=2)
    store.put(new, entry_id="cache", kind="derived_cache", payload=b"new", now=2)
    assert store.get(new, entry_id="cache", now=2) == b"new"


def test_missing_authority_wrong_actor_cross_principal(env):
    store, data, _ = env
    denied("MISSING_INDEPENDENT_AUTHORITY", store.provision_fixture,
           tenant="t1", principal="p1", source_id="s1", source_revision="r1",
           right_version=1, consent_expires_at=100, actor="p1",
           authorized_fixture=False)
    lease = grant(store)
    denied("MISSING_INDEPENDENT_AUTHORITY", store.revoke,
           tenant="t1", principal="p1", source_id="s1", event_id="x",
           reason="CONSENT_WITHDRAWN", actor="p2", authorized_fixture=True)
    denied("MISSING_INDEPENDENT_AUTHORITY", store.downgrade_acl_fixture,
           tenant="t1", principal="p1", source_id="s1",
           actor="p1", authorized_fixture=False)
    denied("MISSING_INDEPENDENT_AUTHORITY", store.audit_witness,
           tenant="t1", principal="p1", source_id="s1", event_id="revoke01",
           actor="p2", authorized_fixture=True)
    assert store.put(lease, entry_id="ok", kind="source", payload=b"ok", now=1)
    assert physical_count(data) == 1


def test_cross_tenant_identical_ids_isolation(env):
    store, data, _ = env
    a = grant(store, tenant="t1")
    b = grant(store, tenant="t2")
    store.put(a, entry_id="same", kind="answer_cache", payload=b"T1", now=1)
    store.put(b, entry_id="same", kind="answer_cache", payload=b"T2", now=1)
    forged = SourceLease("t2", "p1", "s1", a.source_revision,
                         a.right_version, a.revocation_epoch, a.consent_expires_at)
    # Same metadata is not a cross-tenant bypass: it still selects only t2 rows.
    assert store.get(forged, entry_id="same", now=2) == b"T2"
    assert revoke(store, tenant="t1").deleted_entries == 1
    assert store.get(b, entry_id="same", now=3) == b"T2"
    denied("STALE_RIGHTS_OR_EPOCH", store.get, a, entry_id="same", now=3)
    assert physical_count(data) == 1


def test_atomic_write_failure_and_revoke_failure_no_partial_commit(env):
    store, data, _ = env
    lease = grant(store)
    with pytest.raises(RuntimeError, match="INJECTED_BEFORE_ATOMIC_COMMIT"):
        store.put(lease, entry_id="failwrite", kind="memory", payload=b"x",
                  now=1, inject_failure=True)
    assert physical_count(data) == 0
    store.put(lease, entry_id="live", kind="memory", payload=b"still", now=1)
    with pytest.raises(RuntimeError, match="INJECTED_BEFORE_ATOMIC_COMMIT"):
        revoke(store, inject_failure=True)
    assert store.get(lease, entry_id="live", now=2) == b"still"
    assert physical_count(data) == 1
    denied("WITNESS_NOT_FOUND", store.audit_witness,
           tenant="t1", principal="p1", source_id="s1",
           event_id="revoke01", actor="p1", authorized_fixture=True)
    assert revoke(store).deleted_entries == 1
    assert physical_count(data) == 0


def test_restart_in_fresh_process_rechecks_authority(env):
    store, data, auth = env
    lease = grant(store)
    store.put(lease, entry_id="item", kind="answer_cache", payload=b"ok", now=1)
    revoke(store)
    script = """import sys, importlib.util
p=sys.argv[3]
spec=importlib.util.spec_from_file_location('m27_b0_revocation_contract',p)
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)
s=mod.LocalRevocationContract(sys.argv[1],sys.argv[2],fixture_only=True)
l=mod.SourceLease('t1','p1','s1','revision1',1,0,100)
try: s.get(l,entry_id='item',now=2)
except mod.RevocationDenied as e:
    print(e.code)
    sys.exit(0 if e.code=='STALE_RIGHTS_OR_EPOCH' else 2)
sys.exit(3)
"""
    cp = subprocess.run([sys.executable, "-c", script, str(data), str(auth), str(MODULE_PATH)],
                        capture_output=True, text=True, check=False,
                        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)})
    assert cp.returncode == 0, cp.stderr
    assert cp.stdout.strip() == "STALE_RIGHTS_OR_EPOCH"


def test_restored_stale_artifact_snapshot_cannot_restore_rights(env, tmp_path):
    store, data, auth = env
    lease = grant(store)
    store.put(lease, entry_id="source", kind="source", payload=b"private", now=1)
    store.put(lease, entry_id="cache", kind="derived_cache", payload=b"derived", now=1)
    snapshot = tmp_path / "old_artifact.sqlite"
    with sqlite3.connect(data) as src, sqlite3.connect(snapshot) as dst:
        src.backup(dst)
    witness = revoke(store)
    assert physical_count(data) == 0
    # Simulate ONLY the untrusted data store being restored; authority is separate.
    shutil.copy2(snapshot, data)
    assert physical_count(data) == 2
    restarted = LocalRevocationContract(data, auth, fixture_only=True)
    denied("STALE_RIGHTS_OR_EPOCH", restarted.get, lease, entry_id="source", now=3)
    denied("STALE_RIGHTS_OR_EPOCH", restarted.get, lease, entry_id="cache", now=3)
    denied("STALE_RIGHTS_OR_EPOCH", restarted.put, lease, entry_id="new",
           kind="answer_cache", payload=b"leak", now=3)
    assert restarted.audit_witness(
        tenant="t1", principal="p1", source_id="s1", event_id="revoke01",
        actor="p1", authorized_fixture=True) == witness
    assert restarted.recover_restored_artifacts_fixture(
        tenant="t1", principal="p1", source_id="s1",
        actor="p1", authorized_fixture=True) == 2
    assert physical_count(data) == 0
    assert restarted.recover_restored_artifacts_fixture(
        tenant="t1", principal="p1", source_id="s1",
        actor="p1", authorized_fixture=True) == 0


def test_concurrent_repeat_revoke_idempotent_and_single_epoch(env):
    store, data, auth = env
    lease = grant(store)
    store.put(lease, entry_id="item", kind="memory", payload=b"m", now=1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        receipts = list(executor.map(lambda _: revoke(store), range(8)))
    assert all(r == receipts[0] for r in receipts)
    assert receipts[0].deleted_entries == 1
    with sqlite3.connect(auth) as db:
        epoch = db.execute("SELECT epoch FROM scope WHERE tenant='t1'").fetchone()[0]
        audit_count = db.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
    assert epoch == 1 and audit_count == 1
    assert physical_count(data) == 0
    denied("EVENT_ID_REUSED_WITH_DIFFERENT_REASON", revoke, store,
           reason="SUBJECT_ERASURE")
    denied("ALREADY_REVOKED_OTHER_EVENT", revoke, store, event="new_event")


def test_racing_write_after_revocation_cannot_commit(env):
    store, data, _ = env
    lease = grant(store)
    revoke(store)
    def attempt(i):
        try:
            store.put(lease, entry_id=f"item{i}", kind="answer_cache",
                      payload=b"late", now=2)
        except RevocationDenied as error:
            return error.code
        return "UNSAFE_WRITE"
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(attempt, range(12)))
    assert set(results) == {"STALE_RIGHTS_OR_EPOCH"}
    assert physical_count(data) == 0


def test_unknown_scope_invalid_scope_and_consent_negative(env):
    store, _, _ = env
    lease = grant(store)
    denied("UNKNOWN_SOURCE_RIGHTS", store.revoke,
           tenant="t1", principal="p1", source_id="missing",
           event_id="evt", reason="CONSENT_WITHDRAWN",
           actor="p1", authorized_fixture=True)
    denied("INVALID_SCOPE_ID", store.put, lease, entry_id="../escape",
           kind="source", payload=b"x", now=1)
    denied("INVALID_ENTRY", store.put, lease, entry_id="ok",
           kind="not_a_kind", payload=b"x", now=1)
    denied("INVALID_TIME", store.get, lease, entry_id="ok", now=-1)
    denied("INVALID_REASON", revoke, store, reason="ANYTHING")


def test_corrupt_local_entry_digest_fails_closed(env):
    store, data, _ = env
    lease = grant(store)
    store.put(lease, entry_id="item", kind="citation", payload=b"valid", now=1)
    with sqlite3.connect(data) as db:
        db.execute("UPDATE entries SET payload=? WHERE entry_id='item'", (b"tampered",))
    denied("CORRUPT_ENTRY", store.get, lease, entry_id="item", now=2)


def test_tampered_local_audit_witness_is_not_accepted(env):
    store, _, auth = env
    grant(store)
    revoke(store)
    with sqlite3.connect(auth) as db:
        row = db.execute("SELECT witness_json FROM audit").fetchone()[0]
        tampered = row.replace("CONSENT_WITHDRAWN", "SUBJECT_ERASURE")
        db.execute("UPDATE audit SET witness_json=?", (tampered,))
    denied("CORRUPT_AUDIT_WITNESS", store.audit_witness,
           tenant="t1", principal="p1", source_id="s1",
           event_id="revoke01", actor="p1", authorized_fixture=True)
    denied("CORRUPT_AUDIT_WITNESS", revoke, store)
