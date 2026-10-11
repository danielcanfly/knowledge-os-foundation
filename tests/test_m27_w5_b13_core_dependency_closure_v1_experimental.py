"""F13 specifically scoped, negative-case-driven tests; no external authority admitted."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from knowledge_engine.m27_w5_b11_local_package_attestor_v1_experimental import (
    AttestationError,
    digest,
    inspect_archive,
    zip_entry,
)
from knowledge_engine.m27_w5_b13_core_dependency_closure_v1_experimental import (
    AR06,
    BROKER,
    F12_MANIFEST,
    F13_MANIFEST,
    I02,
    NAMES,
    P09,
    PINS,
    ClosureBlocked,
    OfflineCoreDependencyClosureV1,
    manifest_entries,
    scan_source,
    strict_graph,
    validate_probe,
)


def fixtures():
    return json.loads(F13_MANIFEST.read_bytes()), json.loads(F12_MANIFEST.read_bytes())


def blocked(reason, callback, *args):
    with pytest.raises(ClosureBlocked) as e:
        callback(*args)
    assert reason in str(e.value)


@pytest.mark.parametrize(("field", "value", "reason"), [
    ("schema", "v2", "F13_METADATA_OR_POLICY_FORGED: schema"),
    ("date", "2026-10-10", "F13_METADATA_OR_POLICY_FORGED: date"),
    ("qualification", "ALL_FEATURES_DEPENDENCY_COMPLETE", "F13_METADATA_OR_POLICY_FORGED"),
    ("source_worktree", "/tmp/mutable", "F13_METADATA_OR_POLICY_FORGED"),
    ("git_head", "0" * 40, "F13_METADATA_OR_POLICY_FORGED"),
    ("git_tree", "1" * 40, "F13_METADATA_OR_POLICY_FORGED"),
    ("previous_f12_manifest_sha256", "f" * 64, "F13_METADATA_OR_POLICY_FORGED"),
    ("previous_source_count", 20, "F13_METADATA_OR_POLICY_FORGED"),
    ("entry_count", 19, "F13_METADATA_OR_POLICY_FORGED"),
    ("additional_dependency_path", "src/knowledge_engine/fake.py", "F13_METADATA_OR_POLICY_FORGED"),
    ("internal_ast_closure_checked", False, "F13_METADATA_OR_POLICY_FORGED"),
    ("core_optional_dependency_not_fully_implemented", False, "F13_METADATA_OR_POLICY_FORGED"),
    ("external_phase_b_qualified", True, "F13_METADATA_OR_POLICY_FORGED"),
    ("production_authorized", True, "F13_METADATA_OR_POLICY_FORGED"),
    ("real_executed_image_attested", True, "F13_METADATA_OR_POLICY_FORGED"),
    ("optional_dependency_policy", {"feature": "signed_external"}, "F13_METADATA_OR_POLICY_FORGED"),
], ids=[
    "stale_schema", "rollback_date", "fake_full_features", "mutable_root",
    "wrong_head", "wrong_tree", "historical_manifest_swap",
    "historical_count_relabel", "entry_count_relabel", "unverified_import",
    "false_ast_proof", "optional_unexcluded", "fake_phaseb", "fake_production",
    "fake_signed_oci", "forged_crypto_policy",
])
def test_manifest_metadata_negative(field, value, reason):
    doc, f12 = fixtures()
    doc[field] = value
    blocked(reason, manifest_entries, doc, f12)


@pytest.mark.parametrize(("kind", "reason"), [
    ("missing_broker", "F13_SOURCE_COUNT"),
    ("wrong_broker_digest", "F13_SHA_PIN_MISMATCH"),
    ("source_pin_drift", "F13_SHA_PIN_MISMATCH"),
    ("duplicated_component", "F13_COMPONENT_DUPLICATE"),
    ("duplicated_path", "F13_PATH_COLLISION"),
    ("traversal", "F13_UNSAFE_PATH"),
    ("rooted", "F13_UNSAFE_PATH"),
    ("windows_separator", "F13_UNSAFE_PATH"),
    ("unicode_nfkc", "F13_UNSAFE_PATH"),
    ("subfolder", "F13_UNSAFE_PATH"),
    ("unknown_source", "F13_UNAPPROVED_EXPORT"),
    ("non_python", "F13_UNSAFE_PATH"),
    ("extra_field", "F13_SOURCE_ROW_FORGED"),
    ("missing_component", "F13_SOURCE_ROW_FORGED"),
    ("malformed_entries", "F13_SOURCE_COUNT"),
    ("missing_schema_field", "F13_MANIFEST_METADATA_FORGED"),
    ("fake_issuer", "F13_MANIFEST_METADATA_FORGED"),
    ("f12_source_replacement", "F13_F12_HISTORY_PIN_DRIFT"),
    ("f12_missing_file", "F13_F12_HISTORY_PIN_DRIFT"),
], ids=lambda x: x if isinstance(x, str) else None)
def test_manifest_row_and_history_negative(kind, reason):
    doc, f12 = fixtures()
    rows = doc["files"]
    if kind == "missing_broker":
        rows[:] = [r for r in rows if not r["path"].endswith("/" + BROKER)]
    elif kind == "wrong_broker_digest":
        next(r for r in rows if r["path"].endswith("/" + BROKER))["sha256"] = "0" * 64
    elif kind == "source_pin_drift":
        rows[0]["sha256"] = "0" * 64
    elif kind == "duplicated_component":
        rows[1]["component"] = rows[0]["component"]
    elif kind == "duplicated_path":
        rows[1]["path"] = rows[0]["path"]
    elif kind in ("traversal","rooted","windows_separator","unicode_nfkc",
                  "subfolder","unknown_source","non_python"):
        rows[0]["path"] = {
            "traversal": "src/knowledge_engine/../escape.py",
            "rooted": "/tmp/export.py",
            "windows_separator": "src\\knowledge_engine\\escape.py",
            "unicode_nfkc": "src/knowledge_engine/ｍ27_fake.py",
            "subfolder": "src/knowledge_engine/other/child.py",
            "unknown_source": "src/knowledge_engine/unknown.py",
            "non_python": "src/knowledge_engine/unknown.so",
        }[kind]
    elif kind == "extra_field":
        rows[0]["owner_signed"] = True
    elif kind == "missing_component":
        rows[0].pop("component")
    elif kind == "malformed_entries":
        doc["files"] = {}
    elif kind == "missing_schema_field":
        doc.pop("date")
    elif kind == "fake_issuer":
        doc["issuer_attestation"] = True
    elif kind == "f12_source_replacement":
        f12["files"][0]["sha256"] = "f" * 64
    elif kind == "f12_missing_file":
        f12["files"].pop()
    blocked(reason, manifest_entries, doc, f12)


@pytest.mark.parametrize(("raw", "module", "reason"), [
    ("import requests", "knowledge_engine/a.py", "F13_UNPINNED_THIRD_PARTY"),
    ("from pandas import DataFrame", "knowledge_engine/a.py", "F13_UNPINNED_THIRD_PARTY"),
    ("import cryptography", "knowledge_engine/a.py", "F13_UNAUTHORIZED_EXTERNAL_CRYPTO_IMPORT"),
    ("from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey",
     "knowledge_engine/a.py", "F13_UNAUTHORIZED_EXTERNAL_CRYPTO_IMPORT"),
    ("class EvidenceIntake:\n def _verify_signature(self):\n  import cryptography",
     "knowledge_engine/" + P09 + ".py", "F13_UNAUTHORIZED_EXTERNAL_CRYPTO_IMPORT"),
    ("class EvidenceIntake:\n def other(self):\n  from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey",  # noqa: E501
     "knowledge_engine/" + P09 + ".py", "F13_UNAUTHORIZED_EXTERNAL_CRYPTO_IMPORT"),
    ("def _verify_signature():\n from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey",  # noqa: E501
     "knowledge_engine/" + P09 + ".py", "F13_UNAUTHORIZED_EXTERNAL_CRYPTO_IMPORT"),
    ("class EvidenceIntake:\n def _verify_signature(self):\n  from cryptography.exceptions import InvalidSignature",  # noqa: E501
     "knowledge_engine/" + P09 + ".py", "F13_UNAUTHORIZED_EXTERNAL_CRYPTO_IMPORT"),
    ("import knowledge_engine.a.b", "knowledge_engine/a.py", "F13_INTERNAL_IMPORT_AMBIGUOUS"),
    ("from .local import x", "knowledge_engine/a.py", "F13_RELATIVE_IMPORT_UNSUPPORTED"),
    ("importlib.import_module('os')", "knowledge_engine/a.py", "F13_DYNAMIC_IMPORT_UNSUPPORTED"),
    ("__import__('os')", "knowledge_engine/a.py", "F13_DYNAMIC_IMPORT_UNSUPPORTED"),
    ("eval('import os')", "knowledge_engine/a.py", "F13_DYNAMIC_IMPORT_UNSUPPORTED"),
    ("exec('import os')", "knowledge_engine/a.py", "F13_DYNAMIC_IMPORT_UNSUPPORTED"),
    ("def f():\n import evilthirdparty", "knowledge_engine/a.py", "F13_UNPINNED_THIRD_PARTY"),
    ("def f():\n from knowledge_engine import local\n import foo_external",
     "knowledge_engine/a.py", "F13_INTERNAL_IMPORT_AMBIGUOUS"),
    ("def f(:", "knowledge_engine/a.py", "F13_INVALID_SOURCE_SYNTAX"),
])
def test_lexical_and_optional_import_fail_closed(raw, module, reason):
    blocked(reason, scan_source, raw.encode(), module)


def synthetic_graph():
    inventory = {"knowledge_engine/" + n for n in PINS}
    deps = {n: {"internal": [], "optional": []} for n in inventory}
    deps["knowledge_engine/" + AR06 + ".py"]["internal"] = [
        "knowledge_engine/" + BROKER
    ]
    deps["knowledge_engine/" + P09 + ".py"]["optional"] = [{
        "owner": "knowledge_engine/" + P09 + ".py",
        "line": 123, "function": "EvidenceIntake._verify_signature",
        "dependency": "cryptography", "feature": "EXCLUDED",
    }]
    return deps, inventory


@pytest.mark.parametrize(("kind", "reason"), [
    ("missing_inventory", "F13_SOURCE_UNIVERSE_MISMATCH"),
    ("extra_inventory", "F13_SOURCE_UNIVERSE_MISMATCH"),
    ("missing_scan", "F13_SCAN_MISSING"),
    ("wrong_child", "F13_CORE_CLOSURE_BLOCKED"),
    ("other_hidden_child", "F13_CORE_CLOSURE_BLOCKED"),
    ("missing_deferred_edge", "F13_AR06_DEFERRED_AR03_EDGE_MISSING"),
    ("without_optional", "F13_OPTIONAL_CRYPTO_SCOPE_UNVERIFIED"),
    ("extra_optional", "F13_OPTIONAL_CRYPTO_SCOPE_UNVERIFIED"),
    ("untrusted_optional_owner", "F13_OPTIONAL_CRYPTO_SCOPE_UNVERIFIED"),
    ("bad_children", "F13_SCAN_INVALID"),
])
def test_graph_mandatory_closure_negative(kind, reason):
    deps, inventory = synthetic_graph()
    if kind == "missing_inventory":
        inventory.remove("knowledge_engine/" + BROKER)
    elif kind == "extra_inventory":
        inventory.add("knowledge_engine/hidden.py")
    elif kind == "missing_scan":
        deps.pop("knowledge_engine/" + I02 + ".py")
    elif kind in ("wrong_child", "other_hidden_child"):
        deps["knowledge_engine/" + I02 + ".py"]["internal"] = [
            "knowledge_engine/" + ("secret.py" if kind == "wrong_child" else "nested.py")]
    elif kind == "missing_deferred_edge":
        deps["knowledge_engine/" + AR06 + ".py"]["internal"] = []
    elif kind == "without_optional":
        deps["knowledge_engine/" + P09 + ".py"]["optional"] = []
    elif kind == "extra_optional":
        deps["knowledge_engine/" + I02 + ".py"]["optional"] = [{
            "owner": "knowledge_engine/" + I02 + ".py"}]
    elif kind == "untrusted_optional_owner":
        deps["knowledge_engine/" + P09 + ".py"]["optional"][0]["owner"] = "wrong"
    elif kind == "bad_children":
        deps["knowledge_engine/" + I02 + ".py"]["internal"] = None
    blocked(reason, strict_graph, deps, inventory)


def proof_fixture(root: Path):
    modules = [{"name": n, "origin": str(root / "knowledge_engine" / (n + ".py")),
                "sha256": PINS[n + ".py"], "identity": True}
               for n in (I02, *[n for n in NAMES if n != I02])]
    return {
        "isolated": True, "no_site": True, "python": [3, 11],
        "sys_path": [str(root)], "modules": modules, "unexpected_modules": [],
        "deferred": {"called": True, "count": 1,
                     "broker_path": str(root / "knowledge_engine" / BROKER),
                     "deny_first": {
                         "no_grant": True, "other_tenant": True,
                         "wrong_purpose": True, "missing_revision": True,
                         "revoked": True, "expired_consent": True,
                     }},
        "ed25519": {"unavailable": True, "crypto_import_attempts": [
            "cryptography.hazmat.primitives.asymmetric.ed25519"],
            "verified": False, "admitted": False},
    }


@pytest.mark.parametrize(("kind", "reason"), [
    ("fake_ci", "F13_IMPORT_RECEIPT_FORGED"),
    ("site", "F13_IMPORT_ISOLATION_FORGED"),
    ("not_isolated", "F13_IMPORT_ISOLATION_FORGED"),
    ("python_version", "F13_IMPORT_ISOLATION_FORGED"),
    ("site_pollution", "F13_IMPORT_HOST_OR_SITE_SHADOW"),
    ("path_pollution", "F13_IMPORT_HOST_OR_SITE_SHADOW"),
    ("extra_loaded", "F13_IMPORT_MODULE_UNIVERSE"),
    ("missing_module", "F13_IMPORT_MODULE_UNIVERSE"),
    ("second_i02", "F13_IMPORT_MODULE_UNIVERSE"),
    ("bad_origin", "F13_IMPORT_ORIGIN_OR_SHA_FORGED"),
    ("bad_sha", "F13_IMPORT_ORIGIN_OR_SHA_FORGED"),
    ("fake_identity", "F13_IMPORT_ORIGIN_OR_SHA_FORGED"),
    ("bogus_row_field", "F13_IMPORT_ORIGIN_FORGED"),
    ("fake_deferred", "F13_DEFERRED_FUNCTIONAL_UNVERIFIED"),
    ("no_deferred", "F13_DEFERRED_FUNCTIONAL_UNVERIFIED"),
    ("wrong_broker_path", "F13_DEFERRED_FUNCTIONAL_UNVERIFIED"),
    ("wrong_tenant_allowed", "F13_DEFERRED_FUNCTIONAL_UNVERIFIED"),
    ("wrong_purpose_allowed", "F13_DEFERRED_FUNCTIONAL_UNVERIFIED"),
    ("stale_source_allowed", "F13_DEFERRED_FUNCTIONAL_UNVERIFIED"),
    ("crypto_unavailable_false", "F13_OPTIONAL_ED25519_POLICY_UNVERIFIED"),
    ("crypto_fake_positive", "F13_OPTIONAL_ED25519_POLICY_UNVERIFIED"),
    ("crypto_grant", "F13_OPTIONAL_ED25519_POLICY_UNVERIFIED"),
    ("crypto_not_attempted", "F13_OPTIONAL_ED25519_POLICY_UNVERIFIED"),
])
def test_isolated_proof_forgery_negative(tmp_path, kind, reason):
    root = tmp_path / "extracted"
    root.mkdir()
    obj = proof_fixture(root)
    if kind == "fake_ci":
        obj["ci_attested"] = True
    elif kind == "site":
        obj["no_site"] = False
    elif kind == "not_isolated":
        obj["isolated"] = False
    elif kind == "python_version":
        obj["python"] = [3, 12]
    elif kind == "site_pollution":
        obj["sys_path"].append("/tmp/site-packages")
    elif kind == "path_pollution":
        obj["sys_path"].append("/tmp/host/src")
    elif kind == "extra_loaded":
        obj["unexpected_modules"].append("knowledge_engine.bad")
    elif kind == "missing_module":
        obj["modules"].pop()
    elif kind == "second_i02":
        obj["modules"][0], obj["modules"][1] = obj["modules"][1], obj["modules"][0]
    elif kind == "bad_origin":
        obj["modules"][1]["origin"] = "/tmp/sibling/fake.py"
    elif kind == "bad_sha":
        obj["modules"][1]["sha256"] = "0" * 64
    elif kind == "fake_identity":
        obj["modules"][1]["identity"] = False
    elif kind == "bogus_row_field":
        obj["modules"][1]["signed"] = True
    elif kind == "fake_deferred":
        obj["deferred"]["called"] = False
    elif kind == "no_deferred":
        obj["deferred"]["count"] = 0
    elif kind == "wrong_broker_path":
        obj["deferred"]["broker_path"] = "/tmp/host/knowledge_engine/broker.py"
    elif kind in ("wrong_tenant_allowed","wrong_purpose_allowed","stale_source_allowed"):
        obj["deferred"]["deny_first"][{
            "wrong_tenant_allowed": "other_tenant",
            "wrong_purpose_allowed": "wrong_purpose",
            "stale_source_allowed": "missing_revision"}[kind]] = False
    elif kind == "crypto_unavailable_false":
        obj["ed25519"]["unavailable"] = False
    elif kind == "crypto_fake_positive":
        obj["ed25519"]["verified"] = True
    elif kind == "crypto_grant":
        obj["ed25519"]["admitted"] = True
    elif kind == "crypto_not_attempted":
        obj["ed25519"]["crypto_import_attempts"] = []
    blocked(reason, validate_probe, obj, root,
            {"knowledge_engine/" + n: PINS[n] for n in PINS})


@pytest.mark.parametrize(("kind", "reason"), [
    ("missing", "duplicate/missing/unsorted archive entry"),
    ("duplicate", "duplicate/missing/unsorted archive entry"),
    ("reverse", "duplicate/missing/unsorted archive entry"),
    ("extra", "duplicate/missing/unsorted archive entry"),
    ("traversal", "duplicate/missing/unsorted archive entry"),
    ("payload", "payload changed"),
    ("comment", "archive comments not canonical"),
    ("timestamp", "nondeterministic date"),
    ("mode", "archive mode/symlink"),
    ("symlink", "archive mode/symlink"),
    ("compressed", "compression changed"),
    ("extra_metadata", "archive metadata injection"),
    ("torn", "invalid/truncated ZIP"),
])
def test_zip_mutation_fail_closed(tmp_path, kind, reason):
    path = tmp_path / "archive.zip"
    entries = [("knowledge_engine/__init__.py", b""),
               ("knowledge_engine/a.py", b"v = 1\n")]
    if kind == "missing":
        entries.pop()
    elif kind == "duplicate":
        entries.append(entries[1])
    elif kind == "reverse":
        entries.reverse()
    elif kind == "extra":
        entries.append(("knowledge_engine/secret.py", b"x = 1\n"))
    elif kind == "traversal":
        entries[1] = ("knowledge_engine/../a.py", b"v = 1\n")
    elif kind == "payload":
        entries[1] = ("knowledge_engine/a.py", b"v = 2\n")
    with zipfile.ZipFile(path, "w") as z:
        if kind == "comment":
            z.comment = b"forgery"
        for name, body in entries:
            info = zip_entry(name)
            if kind == "timestamp":
                info.date_time = (2026, 10, 10, 4, 0, 0)
            elif kind == "mode":
                info.external_attr = 0o100755 << 16
            elif kind == "symlink":
                info.external_attr = 0o120777 << 16
            elif kind == "compressed":
                info.compress_type = zipfile.ZIP_DEFLATED
            elif kind == "extra_metadata":
                info.extra = b"\x01\x00\x00\x00"
            z.writestr(info, body)
    if kind == "torn":
        path.write_bytes(path.read_bytes()[:-9])
    expect = {"knowledge_engine/__init__.py": digest(b""),
              "knowledge_engine/a.py": digest(b"v = 1\n")}
    with pytest.raises(AttestationError) as ex:
        inspect_archive(path, expect, digest(path.read_bytes()))
    assert reason in str(ex.value)


def test_positive_strict_manifest_graph_and_optional_scoped_ast():
    doc, f12 = fixtures()
    assert len(manifest_entries(doc, f12)) == 20
    deps, inventory = synthetic_graph()
    assert "knowledge_engine/" + BROKER in strict_graph(deps, inventory)[
        "knowledge_engine/" + AR06 + ".py"]
    sample = ("class EvidenceIntake:\n"
              " def _verify_signature(self):\n"
              "  from cryptography.hazmat.primitives.asymmetric.ed25519 "
              "import Ed25519PublicKey\n")
    found = scan_source(sample.encode(), "knowledge_engine/" + P09 + ".py")
    assert len(found["optional"]) == 1


def test_static_empty_and_nested_function_probe():
    found = scan_source(b"def f():\n from knowledge_engine.a import X\n", "test.py")
    assert found["internal"] == ["knowledge_engine/a.py"]


def test_probe_receipt_positive_shape(tmp_path):
    root = tmp_path / "extracted"
    root.mkdir()
    expected = {"knowledge_engine/" + n: PINS[n] for n in PINS}
    validate_probe(proof_fixture(root), root, expected)


def test_duplicate_and_unpinned_source_root_fail_closed(tmp_path):
    obj = OfflineCoreDependencyClosureV1(source_root=tmp_path)
    blocked("F13_FROZEN_ROOT_SUBSTITUTED", obj.verify_source)
    obj = OfflineCoreDependencyClosureV1(scratch=tmp_path)
    blocked("F13_RUN_ID_INVALID", lambda: obj.run(run_id="bad"))
