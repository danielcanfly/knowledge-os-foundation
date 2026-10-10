"""F12-v2 adversarial negative proofs plus true 19-member import integration."""
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
from knowledge_engine.m27_w5_b12_dependency_complete_package_v1_experimental import (
    F12_MANIFEST,
    FROZEN_ROOT,
    I02,
    MODULE_NAMES,
    PINS,
    PROJECT,
    SOURCE_HEAD,
    SOURCE_TREE,
    OfflineDependencyCompletePackageV1,
    PackageBlocked,
    scan_imports,
    validate_import_proof,
    validate_manifest,
    validate_package_receipt,
    verify_closure,
)

# Test both before and after B12's own commit. This MUST NOT be the worker ROOT.
SOURCE = FROZEN_ROOT


def manifest():
    return json.loads(F12_MANIFEST.read_bytes())


def fail(reason, fn, *args, **kwargs):
    with pytest.raises(PackageBlocked) as error:
        fn(*args, **kwargs)
    assert str(error.value) == reason


MANIFEST_CASES = [
    ("schema", "F12_MANIFEST_SCHEMA_INVALID"),
    ("wrong_head", "F12_SOURCE_REVISION_FORGED"),
    ("wrong_tree", "F12_SOURCE_REVISION_FORGED"),
    ("old_head", "F12_SOURCE_REVISION_FORGED"),
    ("f11_hash", "F12_F11_RELABELED_OR_WRONG_COUNT"),
    ("f11_count", "F12_F11_RELABELED_OR_WRONG_COUNT"),
    ("entry_count", "F12_F11_RELABELED_OR_WRONG_COUNT"),
    ("source_root", "F12_FROZEN_ROOT_SUBSTITUTED"),
    ("source_worker_tree", "F12_FROZEN_ROOT_SUBSTITUTED"),
    ("qualification", "F12_QUALIFICATION_FORGED"),
    ("wrong_date", "F12_DATE_INVALID"),
    ("production", "F12_RELEASE_PRIVILEGE_INJECTION"),
    ("external", "F12_RELEASE_PRIVILEGE_INJECTION"),
    ("image", "F12_RELEASE_PRIVILEGE_INJECTION"),
    ("grants", "F12_MANIFEST_METADATA_FORGED"),
    ("release_pointer", "F12_MANIFEST_METADATA_FORGED"),
    ("signed_ci", "F12_MANIFEST_METADATA_FORGED"),
    ("missing_ar06", "F12_SOURCE_ENTRY_COUNT"),
    ("missing_ar07", "F12_SOURCE_ENTRY_COUNT"),
    ("extra_source", "F12_SOURCE_ENTRY_COUNT"),
    ("wrong_sha", "F12_SOURCE_PIN_MISMATCH"),
    ("short_sha", "F12_SOURCE_PIN_MISMATCH"),
    ("mutate_original_pin", "F12_SOURCE_PIN_MISMATCH"),
    ("duplicate_component", "F12_COMPONENT_COLLISION"),
    ("duplicate_file", "F12_PATH_COLLISION"),
    ("path_traversal", "F12_UNSAFE_PATH"),
    ("system_export", "F12_UNSAFE_PATH"),
    ("windows_backslash", "F12_UNSAFE_PATH"),
    ("unicode_alias", "F12_UNSAFE_PATH"),
    ("uppercase", "F12_UNSAFE_PATH"),
    ("extension", "F12_UNSAFE_PATH"),
    ("nested", "F12_UNSAFE_PATH"),
    ("extra_dependency", "F12_ADDITIONAL_DEPENDENCIES_MUTATED"),
    ("wrong_dependency_order", "F12_ADDITIONAL_DEPENDENCIES_MUTATED"),
    ("missing_component", "F12_MALFORMED_ROW"),
    ("invalid_rows", "F12_SOURCE_ENTRY_COUNT"),
    ("arbitrary_file", "F12_UNAPPROVED_SOURCE_EXPORT"),
]


def mutate_manifest(doc, kind):
    f = doc["files"][0]
    if kind == "schema":
        doc["schema"] = "m27.w5.source_freeze_manifest/v1"
    elif kind in ("wrong_head", "wrong_tree", "old_head"):
        doc[{"wrong_head": "git_head", "wrong_tree": "git_tree",
             "old_head": "previous_f11_head"}[kind]] = "f" * 40
    elif kind in ("f11_hash", "f11_count", "entry_count"):
        doc[{"f11_hash": "original_f11_sha256", "f11_count": "original_count",
             "entry_count": "entry_count"}[kind]] = "f" * 64 if kind == "f11_hash" else 18
    elif kind in ("source_root", "source_worker_tree"):
        doc["source_worktree"] = (
            str(PROJECT / "06_WORKSITES/W5_B12_DEPENDENCY_COMPLETE_PACKAGE")
            if kind == "source_worker_tree" else "/tmp/sibling-worktree"
        )
    elif kind == "qualification":
        doc["qualification"] = "F12_FULL_RUNTIME_SIGNED"
    elif kind == "wrong_date":
        doc["date"] = "2024-01-01"
    elif kind in ("production", "external", "image"):
        doc[{"production": "production_authorized",
             "external": "external_phase_b_qualified",
             "image": "real_executed_image_attested"}[kind]] = True
    elif kind in ("grants", "release_pointer", "signed_ci"):
        doc[kind] = "attacker-supplied"
    elif kind in ("missing_ar06", "missing_ar07"):
        name = "m27_ar06_governed_memory_experimental.py" if kind == "missing_ar06" else (
            "m27_ar07_compute_policy_experimental.py"
        )
        doc["files"] = [r for r in doc["files"] if not r["path"].endswith(name)]
    elif kind == "extra_source":
        doc["files"].append({"component": "EXTRA", "path": "src/knowledge_engine/evil.py",
                             "sha256": "0" * 64})
    elif kind in ("wrong_sha", "short_sha", "mutate_original_pin"):
        f["sha256"] = "0" * 64 if kind != "short_sha" else f["sha256"][:63]
    elif kind == "duplicate_component":
        doc["files"][1]["component"] = f["component"]
    elif kind == "duplicate_file":
        doc["files"][1]["path"] = f["path"]
    elif kind in ("path_traversal", "system_export", "windows_backslash",
                  "unicode_alias", "uppercase", "extension", "nested"):
        f["path"] = {
            "path_traversal": "src/knowledge_engine/../evil.py",
            "system_export": "/etc/passwd",
            "windows_backslash": "src\\knowledge_engine\\evil.py",
            "unicode_alias": "src/knowledge_engine/ｍ27_ar02_durable_writer_v1_experimental.py",
            "uppercase": f["path"].upper(),
            "extension": "src/knowledge_engine/a.so",
            "nested": "src/knowledge_engine/inner/a.py",
        }[kind]
    elif kind == "extra_dependency":
        doc["additional_dependency_paths"].append("src/knowledge_engine/evil.py")
    elif kind == "wrong_dependency_order":
        doc["additional_dependency_paths"].reverse()
    elif kind == "missing_component":
        f.pop("component")
    elif kind == "invalid_rows":
        doc["files"] = {"file": f}
    elif kind == "arbitrary_file":
        f["path"] = "src/knowledge_engine/evil.py"


@pytest.mark.parametrize(("kind", "reason"), MANIFEST_CASES, ids=[c[0] for c in MANIFEST_CASES])
def test_manifest_forgery_fail_closed(kind, reason):
    doc = manifest()
    mutate_manifest(doc, kind)
    fail(reason, validate_manifest, doc)


def tiny_dependencies(raw, name="knowledge_engine/a.py"):
    return scan_imports(raw.encode(), name)


IMPORT_CASES = [
    ("__import__('os')", "F12_DYNAMIC_IMPORT_AMBIGUITY"),
    ("importlib.import_module('os')", "F12_DYNAMIC_IMPORT_AMBIGUITY"),
    ("from .helper import thing", "F12_RELATIVE_IMPORT_AMBIGUITY"),
    ("from knowledge_engine import helper", "F12_INTERNAL_IMPORT_AMBIGUITY"),
    ("import knowledge_engine.a.b", "F12_INTERNAL_IMPORT_AMBIGUITY"),
]


@pytest.mark.parametrize(("source", "reason"), IMPORT_CASES)
def test_import_ambiguity_fails_closed(source, reason):
    fail(reason, tiny_dependencies, source)


@pytest.mark.parametrize(("source", "expected"), [
    ("import knowledge_engine.m27_ar06_governed_memory_experimental",
     "knowledge_engine/m27_ar06_governed_memory_experimental.py"),
    ("from knowledge_engine.m27_ar03_context_broker_experimental import Request",
     "knowledge_engine/m27_ar03_context_broker_experimental.py"),
])
def test_actual_static_dependency_discovery(source, expected):
    internal, third = tiny_dependencies(source)
    assert internal == (expected,) and third == ()


@pytest.mark.parametrize("source", [
    "import cryptography", "from requests import get", "import numpy as np",
    "from cryptography.hazmat.primitives import hashes",
])
def test_forbidden_third_party_dependency(source):
    internal, third = tiny_dependencies(source)
    fail("F12_FORBIDDEN_THIRD_PARTY: " + ",".join(third),
         verify_closure, {"knowledge_engine/" + I02 + ".py": {
             "internal": [], "third_party": list(third)}},
         {"knowledge_engine/" + I02 + ".py"})


def test_real_f12_missing_twentieth_dependency_and_optional_crypto():
    sources, dependencies = OfflineDependencyCompletePackageV1().verify_source()
    assert len(sources) == len(PINS) == 19
    fail("F12_DEPENDENCY_CLOSURE_BLOCKED: knowledge_engine/m27_ar03_context_broker_experimental.py",
         verify_closure, dependencies, set(sources))


@pytest.mark.parametrize(("internal", "reason"), [
    (["knowledge_engine/missing.py"],
     "F12_DEPENDENCY_CLOSURE_BLOCKED: knowledge_engine/missing.py"),
    (["knowledge_engine/outside.py"],
     "F12_DEPENDENCY_CLOSURE_BLOCKED: knowledge_engine/outside.py"),
])
def test_missing_transitive_dependency(internal, reason):
    key = "knowledge_engine/" + I02 + ".py"
    fail(reason, verify_closure, {key: {"internal": internal, "third_party": []}}, {key})


def fake_import(tmp_path):
    root = tmp_path / "extracted"
    root.mkdir()
    names = [I02, *MODULE_NAMES]
    entries = [{
        "name": name,
        "file": str(root / "knowledge_engine" / (name + ".py")),
        "origin": str(root / "knowledge_engine" / (name + ".py")),
        "sha256": "a" * 64, "dict_identity": True,
    } for name in names]
    proof = {
        "isolated": True, "no_site": True, "sitecustomize": False,
        "python": [3, 11], "sys_path": [str(root)], "modules": entries,
        "unexpected_modules": [], "i02_class": True, "ar06_ar07_classes": True,
    }
    expect = {"knowledge_engine/" + name + ".py": "a" * 64 for name in MODULE_NAMES}
    return root, proof, expect


PROOF_CASES = [
    ("site", "F12_ISOLATION_INVALID"),
    ("not_isolated", "F12_ISOLATION_INVALID"),
    ("customize", "F12_ISOLATION_INVALID"),
    ("python", "F12_ISOLATION_INVALID"),
    ("precedence", "F12_IMPORT_PATH_SHADOWED"),
    ("developer_src", "F12_IMPORT_HOST_SOURCE_LEAK"),
    ("unexpected_cache", "F12_UNEXPECTED_PACKAGE_MODULE"),
    ("missing", "F12_IMPORT_MODULE_COUNT"),
    ("shadow", "F12_IMPORT_ORIGIN_UNVERIFIED"),
    ("origin", "F12_IMPORT_ORIGIN_UNVERIFIED"),
    ("hash", "F12_IMPORT_SOURCE_HASH_MISMATCH"),
    ("module_dict", "F12_IMPORT_ORIGIN_UNVERIFIED"),
    ("i02_false", "F12_ABI_ORIGIN_UNVERIFIED"),
    ("ar06_false", "F12_ABI_ORIGIN_UNVERIFIED"),
    ("wrong_first", "F12_I02_NOT_IMPORTED_FIRST"),
    ("fake_extra", "F12_IMPORT_RECEIPT_FORGED"),
]


@pytest.mark.parametrize(("kind", "reason"), PROOF_CASES, ids=[c[0] for c in PROOF_CASES])
def test_import_origin_adversaries(tmp_path, kind, reason):
    root, receipt, expected = fake_import(tmp_path)
    if kind == "site":
        receipt["no_site"] = False
    elif kind == "not_isolated":
        receipt["isolated"] = False
    elif kind == "customize":
        receipt["sitecustomize"] = True
    elif kind == "python":
        receipt["python"] = [3, 12]
    elif kind == "precedence":
        receipt["sys_path"].insert(0, "/tmp/untrusted")
    elif kind == "developer_src":
        receipt["sys_path"].append("/tmp/host/src")
    elif kind == "unexpected_cache":
        receipt["unexpected_modules"] = ["knowledge_engine.malicious"]
    elif kind == "missing":
        receipt["modules"].pop()
    elif kind == "shadow":
        receipt["modules"][1]["file"] = "/tmp/sibling/knowledge_engine/fake.py"
    elif kind == "origin":
        receipt["modules"][1]["origin"] = "/tmp/site-packages/fake.py"
    elif kind == "hash":
        receipt["modules"][1]["sha256"] = "0" * 64
    elif kind == "module_dict":
        receipt["modules"][1]["dict_identity"] = False
    elif kind == "i02_false":
        receipt["i02_class"] = False
    elif kind == "ar06_false":
        receipt["ar06_ar07_classes"] = False
    elif kind == "wrong_first":
        receipt["modules"][0], receipt["modules"][1] = receipt["modules"][1], receipt["modules"][0]
    elif kind == "fake_extra":
        receipt["signed_ci"] = True
    fail(reason, validate_import_proof, receipt, root, expected)


def package_receipt():
    return {
        "schema": "m27.w5.b12.dependency.complete.package/v1",
        "builder": "zip-stored-1980-100644-f12-v1",
        "source_head": SOURCE_HEAD, "source_tree": SOURCE_TREE,
        "manifest_sha256": "051dafba045515350d0908886fcc9d46da30262df5839cb383c685574a47f751",
        "archive_sha256": "a" * 64,
        "entries": [{"entry": "x", "header_offset": 0}], "source_count": 19,
        "archive_entry_count": 20, "dependency_graph": {"x": []},
        "closure_reason": "F12_DEPENDENCY_CLOSURE_BLOCKED: knowledge_engine/missing.py",
        "run_id": "worker-0001", "release_attested": False,
        "production_authorized": False, "complete_workload_verified": False,
        "ci_oci_image_verified": False, "isolated_import_verdict": "IMPORT_ORIGIN_UNVERIFIED",
    }


RECEIPT_CASES = [
    ("version", "F12_BUILDER_VERSION_FORGED"),
    ("builder", "F12_BUILDER_VERSION_FORGED"),
    ("head", "F12_RECEIPT_PROVENANCE_FORGED"),
    ("tree", "F12_RECEIPT_PROVENANCE_FORGED"),
    ("manifest", "F12_RECEIPT_PROVENANCE_FORGED"),
    ("sha", "F12_ARCHIVE_OR_OFFSETS_FORGED"),
    ("count", "F12_ARCHIVE_OR_OFFSETS_FORGED"),
    ("source_count", "F12_ARCHIVE_OR_OFFSETS_FORGED"),
    ("offset", "F12_ARCHIVE_OR_OFFSETS_FORGED"),
    ("graph", "F12_DEPENDENCY_RECEIPT_FORGED"),
    ("closure", "F12_DEPENDENCY_RECEIPT_FORGED"),
    ("runner", "F12_RUN_ID_INVALID"),
    ("release", "F12_FAKE_RELEASE_OR_CI_CERTIFICATION"),
    ("production", "F12_FAKE_RELEASE_OR_CI_CERTIFICATION"),
    ("workload", "F12_FAKE_RELEASE_OR_CI_CERTIFICATION"),
    ("ci", "F12_FAKE_RELEASE_OR_CI_CERTIFICATION"),
    ("self_claimed_pass", "F12_SELF_CLAIMED_IMPORT_PASS"),
    ("signed_image", "F12_PACKAGE_RECEIPT_FORGED"),
    ("grant_injection", "F12_PACKAGE_RECEIPT_FORGED"),
    ("tenant_secret", "F12_PACKAGE_RECEIPT_FORGED"),
]


@pytest.mark.parametrize(("kind", "reason"), RECEIPT_CASES, ids=[x[0] for x in RECEIPT_CASES])
def test_receipt_forgery_adversaries(kind, reason):
    rec = package_receipt()
    if kind == "version":
        rec["schema"] = "v0"
    elif kind == "builder":
        rec["builder"] = "untrusted"
    elif kind in ("head", "tree", "manifest"):
        rec[{"head": "source_head", "tree": "source_tree",
             "manifest": "manifest_sha256"}[kind]] = "0" * 64
    elif kind == "sha":
        rec["archive_sha256"] = "0" * 64
    elif kind == "count":
        rec["archive_entry_count"] = 21
    elif kind == "source_count":
        rec["source_count"] = 17
    elif kind == "offset":
        rec["entries"][0]["header_offset"] = 1
    elif kind == "graph":
        rec["dependency_graph"] = {"malicious": ["x"]}
    elif kind == "closure":
        rec["closure_reason"] = ""
    elif kind == "runner":
        rec["run_id"] = ""
    elif kind in ("release", "production", "workload", "ci"):
        rec[{"release": "release_attested", "production": "production_authorized",
             "workload": "complete_workload_verified",
             "ci": "ci_oci_image_verified"}[kind]] = True
    elif kind == "self_claimed_pass":
        rec["isolated_import_verdict"] = "FULL_PROVIDER_CERTIFIED"
    elif kind in ("signed_image", "grant_injection", "tenant_secret"):
        rec[kind] = "fake"
    original = package_receipt()
    fail(reason, validate_package_receipt, rec, tuple(original["entries"]),
         original["archive_sha256"], original["dependency_graph"],
         original["closure_reason"])


def small_zip(tmp_path, kind):
    archive = tmp_path / "test.zip"
    entries = [("knowledge_engine/__init__.py", b""),
               ("knowledge_engine/a.py", b"v = 1\n")]
    if kind == "missing":
        entries.pop()
    elif kind == "duplicate":
        entries.append(entries[-1])
    elif kind == "reverse":
        entries.reverse()
    elif kind == "extra":
        entries.append(("knowledge_engine/secret.py", b"secret = 'x'\n"))
    elif kind == "traversal":
        entries[1] = ("knowledge_engine/../a.py", b"v = 1\n")
    elif kind == "payload":
        entries[1] = ("knowledge_engine/a.py", b"v = 2\n")
    with zipfile.ZipFile(archive, "w") as z:
        if kind == "comment":
            z.comment = b"forged"
        for name, body in entries:
            info = zip_entry(name)
            if kind == "time":
                info.date_time = (2026, 10, 10, 4, 6, 0)
            elif kind == "mode":
                info.external_attr = 0o100755 << 16
            elif kind == "symlink":
                info.external_attr = 0o120777 << 16
            elif kind == "compression":
                info.compress_type = zipfile.ZIP_DEFLATED
            elif kind == "extra_metadata":
                info.extra = b"\x01\x00\x00\x00"
            z.writestr(info, body)
    if kind == "truncated":
        archive.write_bytes(archive.read_bytes()[:-10])
    return archive


ZIP_CASES = [
    ("missing", "duplicate/missing/unsorted archive entry"),
    ("duplicate", "duplicate/missing/unsorted archive entry"),
    ("reverse", "duplicate/missing/unsorted archive entry"),
    ("extra", "duplicate/missing/unsorted archive entry"),
    ("traversal", "duplicate/missing/unsorted archive entry"),
    ("payload", "payload changed"),
    ("comment", "archive comments not canonical"),
    ("time", "nondeterministic date"),
    ("mode", "archive mode/symlink"),
    ("symlink", "archive mode/symlink"),
    ("compression", "compression changed"),
    ("extra_metadata", "archive metadata injection"),
    ("truncated", "invalid/truncated ZIP"),
]


@pytest.mark.parametrize(("kind", "reason"), ZIP_CASES, ids=[x[0] for x in ZIP_CASES])
def test_real_zip_fault_injection(tmp_path, kind, reason):
    path = small_zip(tmp_path, kind)
    wanted = {"knowledge_engine/__init__.py": digest(b""),
              "knowledge_engine/a.py": digest(b"v = 1\n")}
    with pytest.raises(AttestationError, match=reason.replace("/", r"\/")) as exc:
        inspect_archive(path, wanted, digest(path.read_bytes()))
    assert reason in str(exc.value)


def test_positive_f12_manifest_source_19_pins_and_frozen_root():
    att = OfflineDependencyCompletePackageV1()
    doc = manifest()
    assert len(validate_manifest(doc)) == 19
    assert att.source_root == SOURCE and SOURCE_HEAD != "0" * 40
    sources, deps = att.verify_source()
    assert len(sources) == len(deps) == 19
    assert all(digest(sources["knowledge_engine/" + name]) == hashval
               for name, hashval in PINS.items())
    assert "knowledge_engine/m27_ar03_context_broker_experimental.py" in (
        deps["knowledge_engine/m27_ar06_governed_memory_experimental.py"]["internal"])


def test_two_disposable_builds_all_19_real_sources_and_full_i02_import(tmp_path):
    att = OfflineDependencyCompletePackageV1(scratch=tmp_path / "diagnostics")
    result = att.diagnose(run_id="B12-test-unique-0001")
    assert result["archives_equal"] is True
    assert result["source_count"] == 19 and result["entry_count"] == 20
    assert result["byte_verdict"] == "B12_LOCAL_19_SOURCE_BYTES_REPRODUCIBLE_PASS"
    assert result["import_verdict"] == "B12_FULL_I02_ISOLATED_MODULE_IMPORT_PASS"
    assert result["dependency_closure"] == (
        "F12_DEPENDENCY_CLOSURE_BLOCKED: knowledge_engine/m27_ar03_context_broker_experimental.py"
    )
    zip_path, receipt_path, import_path = map(Path, result["paths"])
    assert digest(zip_path.read_bytes()) == result["archive_sha256"]
    assert digest(receipt_path.read_bytes()) == result["receipt_sha256"]
    assert digest(import_path.read_bytes()) == result["import_receipt_sha256"]
    proof = json.loads(import_path.read_bytes())
    assert proof["modules"][0]["name"] == I02
    assert len(proof["modules"]) == 20
    assert len({m["name"] for m in proof["modules"]}) == 19
    assert all(m["dict_identity"] for m in proof["modules"])
    assert result["workload_verdict"] == "B12_COMPLETE_I02_WORKLOAD_RUN_UNVERIFIED"
    assert result["ci_verdict"] == "B12_REAL_EXECUTED_OCI_CI_IMAGE_UNVERIFIED"


def test_duplicate_invocation_and_forged_runner_fail_closed(tmp_path):
    att = OfflineDependencyCompletePackageV1(scratch=tmp_path / "one")
    fail("F12_RUN_ID_INVALID", att.diagnose, run_id="")  # type: ignore[arg-type]


def test_worker_source_substitution_is_rejected_after_commit():
    own = PROJECT / "06_WORKSITES/W5_B12_DEPENDENCY_COMPLETE_PACKAGE"
    att = OfflineDependencyCompletePackageV1(source_root=own)
    fail("F12_FROZEN_ROOT_SUBSTITUTED", att.verify_source)
