"""Distinct fail-closed offline package and import-origin fault injections."""

# ruff: noqa: E501
from __future__ import annotations

import copy
import json
import zipfile
from pathlib import Path

import pytest

from knowledge_engine.m27_w5_b11_local_package_attestor_v1_experimental import (
    FROZEN_SOURCE_ROOT,
    HEAD,
    PROBES,
    SCHEMA,
    TREE,
    AttestationError,
    OfflinePackageAttestorV1,
    archive_name,
    digest,
    inspect_archive,
    safe_member,
    validate_freeze,
    validate_import_receipt,
    validate_receipt,
    validate_relpath,
    zip_entry,
)

ROOT = Path(FROZEN_SOURCE_ROOT)  # Frozen F11 source, never mutable B11 worker HEAD
MANIFEST = Path(
    "/Users/huaihsuanhuang/Desktop/Chatgpt/M27/M27_VNEXT_MASTER_20261009/"
    "07_MASTER_REBASE_20261010/05_EVIDENCE_INDEX/W5_F11_SOURCE_FREEZE_MANIFEST_20261010.json"
)


def source_doc():
    return json.loads(MANIFEST.read_text())


def mutate_doc(doc, fault):
    f = doc["files"][0]
    variants = {
        "schema": lambda: doc.update(schema="v0"),
        "head": lambda: doc.update(git_head="0" * 40),
        "tree": lambda: doc.update(git_tree="f" * 40),
        "prod": lambda: doc.update(production_authorized=True),
        "qualified": lambda: doc.update(external_phase_b_qualified=True),
        "root": lambda: doc.update(source_worktree="/tmp/source"),
        "missing_root": lambda: doc.pop("source_worktree"),
        "extra_role": lambda: doc.update(release_role="admin"),
        "mutable_tag": lambda: doc.update(image_tag="latest"),
        "empty": lambda: doc.update(files=[]),
        "missing_one": lambda: doc["files"].pop(),
        "duplicate": lambda: doc["files"].append(copy.deepcopy(f)),
        "extra_file": lambda: doc["files"].append(
            {"path": "src/knowledge_engine/evil.py", "sha256": "0" * 64, "component": "E"}
        ),
        "duplicate_component": lambda: doc["files"][1].update(component=f["component"]),
        "wrong_sha": lambda: f.update(sha256="0" * 64),
        "short_sha": lambda: f.update(sha256=f["sha256"][:63]),
        "uppercase": lambda: f.update(path=f["path"].upper()),
        "nfkc": lambda: f.update(path=f["path"].replace("m27_", "ｍ27_")),
        "absolute": lambda: f.update(path="/tmp/evil.py"),
        "traversal": lambda: f.update(path="src/knowledge_engine/../evil.py"),
        "ancestor": lambda: f.update(path="../src/knowledge_engine/evil.py"),
        "slash_back": lambda: f.update(path="src\\knowledge_engine\\evil.py"),
        "hidden": lambda: f.update(path="src/knowledge_engine/.secret.py"),
        "nested": lambda: f.update(path="src/knowledge_engine/evil/a.py"),
        "extension": lambda: f.update(path="src/knowledge_engine/evil.sh"),
        "no_component": lambda: f.pop("component"),
        "null_path": lambda: f.update(path=None),
        "invalid_files": lambda: doc.update(files={"path": "x"}),
    }
    variants[fault]()


@pytest.mark.parametrize(
    "fault",
    [
        "schema",
        "head",
        "tree",
        "prod",
        "qualified",
        "root",
        "missing_root",
        "extra_role",
        "mutable_tag",
        "empty",
        "missing_one",
        "duplicate",
        "extra_file",
        "duplicate_component",
        "wrong_sha",
        "short_sha",
        "uppercase",
        "nfkc",
        "absolute",
        "traversal",
        "ancestor",
        "slash_back",
        "hidden",
        "nested",
        "extension",
        "no_component",
        "null_path",
        "invalid_files",
    ],
)
def test_28_freeze_faults_fail_closed(fault):
    doc = source_doc()
    mutate_doc(doc, fault)
    with pytest.raises(AttestationError):
        validate_freeze(doc)


@pytest.mark.parametrize(
    "path",
    [
        "knowledge_engine/../a.py",
        "knowledge_engine/a.py/other.py",
        "knowledge_engine/A.py",
        "knowledge_engine/a.pyo",
        "other/a.py",
        "knowledge_engine\\a.py",
        "knowledge_engine/.a.py",
        "/knowledge_engine/a.py",
        "knowledge_engine/ａ.py",
    ],
)
def test_9_untrusted_archive_paths(path):
    with pytest.raises(AttestationError):
        validate_relpath(path, archive=True)


def small_archive(tmp_path, fault=None):
    path = tmp_path / "source.zip"
    items = [
        ("knowledge_engine/__init__.py", b""),
        ("knowledge_engine/a.py", b"value=1\n"),
    ]
    if fault == "missing":
        items.pop()
    elif fault == "duplicate":
        items.append(items[-1])
    elif fault == "extra":
        items.append(("knowledge_engine/evil.py", b"x=1\n"))
    elif fault == "reverse":
        items.reverse()
    elif fault == "traversal":
        items[1] = ("knowledge_engine/../evil.py", b"value=1\n")
    elif fault == "backslash":
        items[1] = ("knowledge_engine\\a.py", b"value=1\n")
    elif fault == "payload":
        items[1] = (items[1][0], b"value=2\n")
    elif fault == "bom":
        items[1] = (items[1][0], b"\xef\xbb\xbfvalue=1\n")
    elif fault == "big":
        items[1] = (items[1][0], b"x" * 2_000_001)
    with zipfile.ZipFile(path, "w", allowZip64=False) as z:
        if fault == "comment":
            z.comment = b"mutable-metadata"
        for name, body in items:
            info = zip_entry(name)
            if fault == "time" and name.endswith("a.py"):
                info.date_time = (2026, 10, 10, 9, 0, 0)
            if fault == "mode" and name.endswith("a.py"):
                info.external_attr = 0o100755 << 16
            if fault == "symlink" and name.endswith("a.py"):
                info.external_attr = 0o120777 << 16
            if fault == "compression" and name.endswith("a.py"):
                info.compress_type = zipfile.ZIP_DEFLATED
            if fault == "extra_field" and name.endswith("a.py"):
                info.extra = b"\x01\x00\x00\x00"
            z.writestr(info, body)
    if fault == "truncate":
        path.write_bytes(path.read_bytes()[:-14])
    elif fault == "after_hash":
        with path.open("ab") as f:
            f.write(b"malicious-append")
    return path


EXPECTED = {
    "knowledge_engine/__init__.py": digest(b""),
    "knowledge_engine/a.py": digest(b"value=1\n"),
}


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "duplicate",
        "extra",
        "reverse",
        "traversal",
        "backslash",
        "payload",
        "bom",
        "big",
        "comment",
        "time",
        "mode",
        "symlink",
        "compression",
        "extra_field",
        "truncate",
        "after_hash",
    ],
)
def test_17_archive_faults_fail_closed(tmp_path, fault):
    p = small_archive(tmp_path, fault)
    with pytest.raises(AttestationError):
        inspect_archive(p, EXPECTED, digest(p.read_bytes()) if fault != "after_hash" else "0" * 64)


def test_reproducible_canonical_archive(tmp_path):
    one, two = tmp_path / "a", tmp_path / "b"
    one.mkdir()
    two.mkdir()
    att = OfflinePackageAttestorV1(ROOT, MANIFEST, tmp_path)
    sha_a, rows_a = att._build(one / "test.zip", {"knowledge_engine/a.py": b"value=1\n"})
    sha_b, rows_b = att._build(two / "test.zip", {"knowledge_engine/a.py": b"value=1\n"})
    assert sha_a == sha_b and rows_a == rows_b
    assert (one / "test.zip").read_bytes() == (two / "test.zip").read_bytes()


def good_receipt(tmp_path):
    att = OfflinePackageAttestorV1(ROOT, MANIFEST, tmp_path)
    p = tmp_path / "package.zip"
    sha, rows = att._build(p, {"knowledge_engine/a.py": b"value=1\n"})
    receipt = {
        "schema": SCHEMA,
        "git_head": HEAD,
        "git_tree": TREE,
        "archive_sha256": sha,
        "freeze_manifest_sha256": "a" * 64,
        "immutable": True,
        "release_attested": False,
        "entry_count": len(rows),
        "entries": list(rows),
        "dependencies_unfrozen": {},
        "package_root": "knowledge_engine",
        "builder": "zip-stored-1980-100644-v1",
        "import_probe_modules": list(PROBES),
    }
    return receipt, rows, sha


@pytest.mark.parametrize(
    "fault",
    [
        "schema",
        "head",
        "tree",
        "archive_sha",
        "entry_missing",
        "entry_offset",
        "entry_payload",
        "release",
        "mutable_tag",
        "signature",
        "privileges",
        "missing_version",
        "builder",
        "count",
        "not_immutable",
    ],
)
def test_15_receipt_forgery_faults(tmp_path, fault):
    receipt, rows, sha = good_receipt(tmp_path)
    rows = copy.deepcopy(rows)
    if fault == "schema":
        receipt["schema"] = "v0"
    elif fault == "head":
        receipt["git_head"] = "0" * 40
    elif fault == "tree":
        receipt["git_tree"] = "0" * 40
    elif fault == "archive_sha":
        receipt["archive_sha256"] = "f" * 64
    elif fault == "entry_missing":
        receipt["entries"] = []
    elif fault == "entry_offset":
        receipt["entries"][0]["header_offset"] += 1
    elif fault == "entry_payload":
        receipt["entries"][0]["sha256"] = "0" * 64
    elif fault == "release":
        receipt["release_attested"] = True
    elif fault == "mutable_tag":
        receipt["tag"] = "latest"
    elif fault == "signature":
        receipt["signature"] = "self-signed"
    elif fault == "privileges":
        receipt["release_role"] = "admin"
    elif fault == "missing_version":
        receipt.pop("schema")
    elif fault == "builder":
        receipt["builder"] = "untrusted"
    elif fault == "count":
        receipt["entry_count"] = 99
    elif fault == "not_immutable":
        receipt["immutable"] = False
    with pytest.raises(AttestationError):
        validate_receipt(receipt, expected_sha=sha, rows=rows)


def good_import(root: Path):
    modules = []
    hashes = {}
    for name in PROBES:
        rel = "knowledge_engine/" + name + ".py"
        p = (root / rel).resolve()
        hashes[rel] = digest(b"trusted")
        modules.append(
            {"name": name, "file": str(p), "origin": str(p), "sha256": digest(b"trusted")}
        )
    return {
        "isolated": True,
        "no_site": True,
        "sitecustomize": False,
        "python": [3, 11],
        "sys_path": [str(root.resolve())],
        "modules": modules,
        "other_package_modules": [],
    }, hashes


@pytest.mark.parametrize(
    "fault",
    [
        "not_isolated",
        "site_enabled",
        "sitecustomize",
        "wrong_python",
        "path_precedence",
        "import_previous_tree",
        "origin_mismatch",
        "sha",
        "module_missing",
        "module_duplicate",
        "sideload",
        "missing_sys_path",
        "not_dict",
    ],
)
def test_13_import_faults_fail_closed(tmp_path, fault):
    root = tmp_path / "runtime"
    root.mkdir()
    rec, hashes = good_import(root)
    if fault == "not_isolated":
        rec["isolated"] = False
    elif fault == "site_enabled":
        rec["no_site"] = False
    elif fault == "sitecustomize":
        rec["sitecustomize"] = True
    elif fault == "wrong_python":
        rec["python"] = [3, 12]
    elif fault == "path_precedence":
        rec["sys_path"].insert(0, "/tmp/host/src")
    elif fault == "import_previous_tree":
        rec["modules"][0]["file"] = "/tmp/previous/knowledge_engine/a.py"
    elif fault == "origin_mismatch":
        rec["modules"][0]["origin"] = "/tmp/site-packages/knowledge_engine/a.py"
    elif fault == "sha":
        rec["modules"][0]["sha256"] = "0" * 64
    elif fault == "module_missing":
        rec["modules"].pop()
    elif fault == "module_duplicate":
        rec["modules"][0]["name"] = rec["modules"][1]["name"]
    elif fault == "sideload":
        rec["other_package_modules"] = ["knowledge_engine.shadow"]
    elif fault == "missing_sys_path":
        rec["sys_path"] = []
    elif fault == "not_dict":
        rec = "forged"
    with pytest.raises(AttestationError):
        validate_import_receipt(rec, root, hashes)


@pytest.mark.parametrize("fault", ["bom", "null", "bad_syntax", "oversized", "missing_class"])
def test_5_source_faults(fault):
    name = "src/knowledge_engine/m27_w5_l10_ar10_candidate_governance_v1_experimental.py"
    cases = {
        "bom": b"\xef\xbb\xbfclass AR10CandidateGovernanceV1: pass\n",
        "null": b"class AR10CandidateGovernanceV1: pass\x00\n",
        "bad_syntax": b"class :\n",
        "oversized": b"x" * 2_000_001,
        "missing_class": b"class Unapproved: pass\n",
    }
    with pytest.raises(AttestationError):
        safe_member(name, cases[fault])


def test_approved_manifest_and_source_abi():
    entries = validate_freeze(source_doc())
    assert len(entries) == 17
    assert archive_name(entries[0][0]).startswith("knowledge_engine/")


def test_true_source_archive_and_isolated_runtime_origin(tmp_path):
    att = OfflinePackageAttestorV1(ROOT, MANIFEST, tmp_path / "b11_scratch")
    result = att.run()
    assert result["source_files"] == 17
    assert result["package_entries"] == 18
    assert result["verdict_local"] == "B11_LOCAL_REPRODUCIBLE_BYTES_PASS"
    assert result["verdict_fixture"] == "B11_IMPORT_ORIGIN_FIXTURE_VERIFIED"
    assert result["verdict_release"] == "B11_REAL_RUNTIME_IMAGE_ATTESTATION_UNVERIFIED"
    assert result["verdict_full_i02_runtime"] == "IMPORT_ORIGIN_UNVERIFIED"
    pkg = Path(result["archive_path"])
    assert digest(pkg.read_bytes()) == result["package_sha256"]
    assert result["missing_unfrozen_dependencies"] or isinstance(
        result["missing_unfrozen_dependencies"], dict
    )
