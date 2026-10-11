"""P16 read-only security, fault and E15-contract tests (fixture-only)."""
from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from knowledge_engine import m27_w5_e15_original523_evaluator_admission_v1_experimental as e15
from knowledge_engine import m27_w5_p16_external_evidence_ingress_v1_experimental as p16

NOW = 1000
BASE = {
    "kind": "rights_custody", "path": "rights.json", "sha256": "a" * 64,
    "subject": "candidate01", "issuer_id": "independent01",
    "scope": "EVALUATION_ONLY", "revision": "rev01",
    "source_id": "source01", "grant_id": "grant01", "issued_ms": 1,
    "license_id": "license01", "run_id": "run01", "host_id": "host01",
    "candidate_commit": "a" * 40, "candidate_image_sha256": "b" * 64,
    "consent_until_ms": 30000, "acl_until_ms": 30000,
    "retention_until_ms": 30000, "revoked": False,
}
PATH_ATTACKS = [
    ("absolute", "/tmp/secret"),
    ("parent", "../secret"),
    ("embedded_parent", "sub/../secret"),
    ("dot", "./secret"),
    ("double_slash", "sub//secret"),
    ("empty", ""),
    ("home", "~/secret"),
    ("escaped_parent", "%2e%2e/secret"),
    ("escaped_slash", "sub%2fsecret"),
    ("escaped_backslash", "%5csecret"),
    ("windows_slash", "sub\\secret"),
    ("windows_drive", "C:\\secret"),
    ("blank_begin", " secret"),
    ("blank_end", "secret "),
    ("newline", "a\nb"),
    ("nul", "a\x00b"),
    ("hidden", ".secrets"),
    ("hidden_child", "sub/.secrets"),
    ("emoji_path", "safe/🗝️"),
    ("unicode_directional", "test\u202esecret"),
    ("semicolon", "name;cat"),
    ("query", "file?x=1"),
    ("hash", "file#key"),
    ("overlong", "a" * 300),
]
RECORD_FAULTS = [
    ("unknown_kind", "kind", "invented", "UNKNOWN_ARTIFACT_CLASS"),
    ("bad_subject", "subject", "different", "CANDIDATE_SUBJECT_MISMATCH"),
    ("subject_none", "subject", None, "INVALID_ARTIFACT_IDENTITY"),
    ("issuer_empty", "issuer_id", "", "INVALID_ARTIFACT_IDENTITY"),
    ("revision_space", "revision", "bad revision", "INVALID_ARTIFACT_IDENTITY"),
    ("grant_empty", "grant_id", "", "INVALID_ARTIFACT_IDENTITY"),
    ("source_broken", "source_id", "!none", "INVALID_ARTIFACT_IDENTITY"),
    ("scope_read", "scope", "READ_ONLY", "SCOPE_NOT_AUTHORIZED"),
    ("scope_prod", "scope", "PRODUCTION", "SCOPE_NOT_AUTHORIZED"),
    ("scope_none", "scope", None, "SCOPE_NOT_AUTHORIZED"),
    ("scope_empty", "scope", "", "SCOPE_NOT_AUTHORIZED"),
    ("sha_short", "sha256", "a", "INVALID_EXPECTED_SHA256"),
    ("sha_upper", "sha256", "A" * 64, "INVALID_EXPECTED_SHA256"),
    ("sha_nonhex", "sha256", "g" * 64, "INVALID_EXPECTED_SHA256"),
    ("sha_none", "sha256", None, "INVALID_EXPECTED_SHA256"),
    ("issued_bool", "issued_ms", True, "ARTIFACT_CLOCK_INVALID"),
    ("issued_negative", "issued_ms", -1, "ARTIFACT_CLOCK_INVALID"),
    ("issued_float", "issued_ms", 1.5, "ARTIFACT_CLOCK_INVALID"),
    ("issued_future", "issued_ms", 2000, "ISSUANCE_IN_FUTURE"),
    ("consent_expired", "consent_until_ms", 999, "CONSENT_ACL_OR_RETENTION_EXPIRED"),
    ("consent_equal", "consent_until_ms", 1000, "CONSENT_ACL_OR_RETENTION_EXPIRED"),
    ("acl_expired", "acl_until_ms", 999, "CONSENT_ACL_OR_RETENTION_EXPIRED"),
    ("acl_equal", "acl_until_ms", 1000, "CONSENT_ACL_OR_RETENTION_EXPIRED"),
    ("retention_expired", "retention_until_ms", 999,
     "CONSENT_ACL_OR_RETENTION_EXPIRED"),
    ("wrong_host", "host_id", "", "INVALID_ARTIFACT_IDENTITY"),
    ("fake_commit", "candidate_commit", "x" * 40,
     "EXECUTED_IMAGE_LINEAGE_INVALID"),
    ("fake_image", "candidate_image_sha256", "x" * 64,
     "EXECUTED_IMAGE_LINEAGE_INVALID"),
    ("consent_bool", "consent_until_ms", True, "ARTIFACT_CLOCK_INVALID"),
    ("acl_null", "acl_until_ms", None, "ARTIFACT_CLOCK_INVALID"),
    ("revoked", "revoked", True, "RIGHTS_OR_GRANT_REVOKED"),
    ("revoked_none", "revoked", None, "RIGHTS_OR_GRANT_REVOKED"),
    ("revoked_one", "revoked", 1, "RIGHTS_OR_GRANT_REVOKED"),
]
MANIFEST_FAULTS = [
    ("duplicate_kind", "DUPLICATE_MANIFEST_ARTIFACT"),
    ("duplicate_path", "DUPLICATE_MANIFEST_ARTIFACT"),
    ("duplicate_digest", "DUPLICATE_CONTENT_DIGEST"),
    ("grant_mismatch", "GRANT_BINDING_MISMATCH"),
    ("subject_mismatch", "CANDIDATE_SUBJECT_MISMATCH"),
    ("hash_mismatch", "FILE_CONTENT_SHA256_MISMATCH"),
    ("missing_file", "ARTIFACT_OPEN_OR_RACE_DENIED"),
    ("rights_lapsed", "CONSENT_ACL_OR_RETENTION_EXPIRED"),
    ("revocation", "RIGHTS_OR_GRANT_REVOKED"),
    ("bogus_issuer", "INVALID_ARTIFACT_IDENTITY"),
    ("unpermitted_scope", "SCOPE_NOT_AUTHORIZED"),
    ("wrong_run", "RUN_HOST_OR_EXECUTED_IMAGE_LINEAGE_MISMATCH"),
    ("wrong_host", "RUN_HOST_OR_EXECUTED_IMAGE_LINEAGE_MISMATCH"),
    ("wrong_candidate", "RUN_HOST_OR_EXECUTED_IMAGE_LINEAGE_MISMATCH"),
]


def _raw_json(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def _entry(kind: str, path: str, data: bytes) -> dict:
    return dict(BASE, kind=kind, path=path,
                sha256=hashlib.sha256(data).hexdigest())


def _files(root: Path, kinds=("rights_custody", "original_index", "phase_b_index")):
    entries = []
    for k in kinds:
        payload = _raw_json({"example": k, "fixtures_only": True})
        name = k + ".json"
        (root / name).write_bytes(payload)
        entries.append(_entry(k, name, payload))
    return entries


def _write_manifest(root: Path, entries: list[dict], **changes: object):
    manifest = {
        "schema": p16.SCHEMA, "subject": "candidate01",
        "run_id": "run01", "grant_id": "grant01", "artifacts": entries,
        "host_id": "host01", "candidate_commit": "a" * 40,
        "candidate_image_sha256": "b" * 64,
    }
    manifest.update(changes)
    (root / "manifest.json").write_bytes(_raw_json(manifest))
    return manifest


def _denials(root: Path, entries: list[dict]):
    _write_manifest(root, entries)
    return p16.inspect(root, "manifest.json", now_ms=NOW)


@pytest.mark.parametrize("name,attack", PATH_ATTACKS, ids=[x[0] for x in PATH_ATTACKS])
def test_negative_path_rejection(name, attack):
    with pytest.raises(p16.Denied) as err:
        p16._relative(attack)
    assert err.value.code in {"UNSAFE_ARTIFACT_PATH", "PATH_TRAVERSAL_REJECTED"}


@pytest.mark.parametrize(
    "name,key,value,reason", RECORD_FAULTS, ids=[x[0] for x in RECORD_FAULTS]
)
def test_negative_artifact_contract(name, key, value, reason):
    specimen = dict(BASE, **{key: value})
    with pytest.raises(p16.Denied) as err:
        p16._artifact(specimen, NOW, "candidate01")
    assert err.value.code == reason


@pytest.mark.parametrize(
    "name,reason", MANIFEST_FAULTS, ids=[x[0] for x in MANIFEST_FAULTS]
)
def test_negative_manifest_reconciliation(tmp_path: Path, name, reason):
    entries = _files(tmp_path)
    if name == "duplicate_kind":
        entries.append(dict(entries[0], path="other.json", sha256="f" * 64))
    elif name == "duplicate_path":
        entries.append(dict(entries[0], kind="provider_invoice", sha256="e" * 64))
    elif name == "duplicate_digest":
        entries.append(dict(entries[0], kind="provider_invoice", path="other.json"))
    elif name == "grant_mismatch":
        entries[0]["grant_id"] = "other01"
    elif name == "subject_mismatch":
        entries[0]["subject"] = "other01"
    elif name == "hash_mismatch":
        entries[0]["sha256"] = "0" * 64
    elif name == "missing_file":
        entries[0]["path"] = "absent.json"
    elif name == "rights_lapsed":
        entries[0]["consent_until_ms"] = 1
    elif name == "revocation":
        entries[0]["revoked"] = True
    elif name == "bogus_issuer":
        entries[0]["issuer_id"] = "bad issuer"
    elif name == "unpermitted_scope":
        entries[0]["scope"] = "PRODUCTION"
    elif name == "wrong_run":
        entries[0]["run_id"] = "fakeRun01"
    elif name == "wrong_host":
        entries[0]["host_id"] = "otherHost01"
    elif name == "wrong_candidate":
        entries[0]["candidate_image_sha256"] = "f" * 64,
    result = _denials(tmp_path, entries)
    assert reason in result["denial_reasons"]
    assert result["classification"] == p16.CODE_AUTH
    assert result["official_cited_gate_pass"] is False


@pytest.mark.parametrize("name,reason", [
    ("fixture_root", "INDEPENDENT_TRUST_REGISTRY_NOT_PROVISIONED"),
    ("historical_523", "ORIGINAL523_TYPED_PROVENANCE_NOT_ADMITTED"),
    ("phase_b_not_523", "AR09_PHASE_B_TYPED_PROVENANCE_NOT_ADMITTED"),
    ("self_declared_authority", "EXTERNAL_ROOT_AUTHORITY_NOT_INDEPENDENTLY_PROVEN"),
])
def test_negative_external_authority_not_auto_proven(tmp_path, name, reason):
    result = _denials(tmp_path, _files(tmp_path))
    assert reason in result["denial_reasons"]
    assert result["original523"] == e15.REJECT_523
    assert result["ar09_phase_b"] == e15.REJECT_B
    assert result["may_execute_official_evaluation"] is False


@pytest.mark.parametrize("kind", p16.REQUIRED)
def test_negative_missing_independently_authorized_class(tmp_path, kind):
    entries = _files(tmp_path, ("rights_custody", "original_index", "phase_b_index"))
    entries = [e for e in entries if e["kind"] != kind]
    result = _denials(tmp_path, entries)
    assert "MISSING_REQUIRED_" + kind.upper() in result["denial_reasons"]


@pytest.mark.parametrize("name,reason", [
    ("subject", "EXTERNAL_REGISTRY_SUBJECT_OR_GRANT_MISMATCH"),
    ("grant", "EXTERNAL_REGISTRY_SUBJECT_OR_GRANT_MISMATCH"),
    ("sha", "EXTERNAL_AUTHORITY_SHA256_NOT_MATCHED"),
    ("issuer", "INDEPENDENT_ISSUER_NOT_NOMINATED"),
])
def test_negative_out_of_band_registry_mismatch(tmp_path, name, reason):
    entries = _files(tmp_path)
    registry = p16.TrustedAuthorityRegistry(
        authorized_artifacts={e["kind"]: e["sha256"] for e in entries},
        nominated_issuers={e["kind"]: e["issuer_id"] for e in entries},
        e15_context=e15.IndependentContext(),
        verified_out_of_band=True,
        subject="candidate01", grant_id="grant01",
    )
    if name == "subject":
        registry = replace(registry, subject="stranger01")
    elif name == "grant":
        registry = replace(registry, grant_id="different01")
    elif name == "sha":
        registry = replace(registry, authorized_artifacts={})
    elif name == "issuer":
        registry = replace(registry, nominated_issuers={})
    _write_manifest(tmp_path, entries)
    result = p16.inspect(tmp_path, "manifest.json", registry=registry, now_ms=NOW)
    assert reason in result["denial_reasons"]


@pytest.mark.parametrize("name,content,expected", [
    ("bad_json", b"{", "MALFORMED_JSON"),
    ("json_duplicate_key", b'{"a":1,"a":2}', "DUPLICATE_JSON_KEY"),
    ("nonfinite", b'{"a":NaN}', "NONFINITE_JSON_VALUE"),
    ("invalid_utf8", b"\xff", "MALFORMED_JSON"),
])
def test_negative_manifest_parser(name, content, expected):
    with pytest.raises(p16.Denied) as err:
        p16._json(content)
    assert err.value.code == expected


@pytest.mark.parametrize("name,mutator,reason", [
    ("invalid_schema", {"schema": "unknown"}, "INGRESS_MANIFEST_SCHEMA_INVALID"),
    ("missing_identity", {"run_id": ""}, "MANIFEST_IDENTITY_INVALID"),
    ("extra_field", {"secret": "disallowed"}, "INGRESS_MANIFEST_SCHEMA_INVALID"),
    ("not_a_list", {"artifacts": {}}, "MANIFEST_ARTIFACT_COUNT_INVALID"),
    ("oversized_list", {"artifacts": [{}] * 65}, "MANIFEST_ARTIFACT_COUNT_INVALID"),
])
def test_negative_manifest_top_schema(tmp_path, name, mutator, reason):
    m = _write_manifest(tmp_path, _files(tmp_path))
    m.update(mutator)
    (tmp_path / "manifest.json").write_bytes(_raw_json(m))
    with pytest.raises(p16.Denied) as err:
        p16.inspect(tmp_path, "manifest.json", now_ms=NOW)
    assert err.value.code == reason


def test_positive_three_distinct_file_bytes_and_sha256(tmp_path):
    entries = _files(tmp_path)
    result = _denials(tmp_path, entries)
    for e in entries:
        assert result["verified_content_sha256"][e["kind"]] == e["sha256"]
    assert len(set(result["verified_content_sha256"].values())) == 3
    assert result["classification"] == p16.CODE_AUTH
    assert "EXTERNAL_ROOT_AUTHORITY_NOT_INDEPENDENTLY_PROVEN" in (
        result["denial_reasons"])


def test_positive_private_exportable_request_receipt(tmp_path):
    ingress = tmp_path / "ingress"
    ingress.mkdir()
    result = _denials(ingress, _files(ingress))
    target = p16.write_receipt(tmp_path / "private", result)
    parsed = json.loads(target.read_text())
    assert len(parsed["requests"]) == len(p16.REQUIRED)
    assert parsed["verified_content_sha256"]["rights_custody"]
    assert "fixtures_only" not in target.read_text()
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    assert parsed["independent_issuer_roles"] == list(e15.ROLES)


def test_positive_cli_missing_manifest_fails_closed(tmp_path, capsys):
    scratch = tmp_path / "scratch"
    code = p16.main(["inspect", "--ingress-root", str(tmp_path),
                     "--manifest", "missing.json", "--scratch", str(scratch)])
    assert code == 0
    receipt = json.loads((scratch / "P16_REQUEST_RECEIPT.json").read_text())
    assert receipt["classification"] == p16.CODE_ABSENT
    assert "EXTERNAL_ARTIFACTS_ABSENT" in receipt["denial_reasons"]
    assert not receipt["may_execute_official_evaluation"]
    assert "EXTERNAL_ARTIFACTS_ABSENT" in capsys.readouterr().out


def test_positive_e15_inspect_real_typed_contract_rejects_unproven(tmp_path):
    from dataclasses import asdict
    image = e15.FrozenImage("a" * 40, "b" * 40, "c" * 64,
                            "d" * 64, "e" * 64, "f" * 64)
    manifest = e15.SealedManifest(
        version=e15.VERSION, cohort=e15.ORIGINAL,
        dataset_id="dataset01", sealed_dataset_sha256="d" * 64,
        nonce="nonce01", custodian_id="custodian01",
        evaluator_id="evaluator01", implementer_ids=("impl01",),
        reviewer_ids=("review01", "review02"), license_id="license01",
        license_scope="EVALUATION_ONLY", issued_ms=1, expires_ms=10000,
        rubric_id="rubric01", rubric_version="ver01", candidate=image,
        sources=(), cases=(),
    )
    packet = e15.RunPacket("run01", e15.digest(asdict(manifest)),
                            image.image_sha256, "rubric01", "ver01",
                            (), ())
    raw = {
        "original_index": _raw_json(asdict(manifest)),
        "graded_original": _raw_json(asdict(packet)),
    }
    answer = p16._e15_metadata(raw, None, NOW)["original523"]
    assert answer["status"] == e15.REJECT_523
    assert answer["may_execute_official_evaluation"] is False
    assert "FROZEN_DENOMINATOR_NOT_EXACT" in answer["reasons"]


def test_negative_symlink_and_hardlink_file_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.write_bytes(b"private")
    root = tmp_path / "root"
    root.mkdir()
    (root / "linked").symlink_to(outside)
    (root / "hard").hardlink_to(outside)
    fd = p16._open_root(root)
    try:
        with pytest.raises(p16.Denied) as err:
            p16._read_at(fd, "linked", limit=100)
        assert err.value.code in (
            "SYMLINK_TRAVERSAL_REJECTED", "ARTIFACT_OPEN_OR_RACE_DENIED"
        )
        with pytest.raises(p16.Denied) as err:
            p16._read_at(fd, "hard", limit=100)
        assert err.value.code == "NOT_SINGLE_REGULAR_FILE"
    finally:
        os.close(fd)


def test_negative_symlink_intermediate_directory(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "link").symlink_to(tmp_path, target_is_directory=True)
    fd = p16._open_root(root)
    try:
        with pytest.raises(p16.Denied) as err:
            p16._read_at(fd, "link/secret", limit=100)
        assert err.value.code in (
            "SYMLINK_TRAVERSAL_REJECTED", "ARTIFACT_OPEN_OR_RACE_DENIED"
        )
    finally:
        os.close(fd)


def test_negative_symlink_root(tmp_path):
    root = tmp_path / "real"
    root.mkdir()
    link = tmp_path / "link"
    link.symlink_to(root)
    with pytest.raises(p16.Denied) as err:
        p16._open_root(link)
    assert err.value.code == "SYMLINK_ROOT_REJECTED"


def test_negative_size_limit(tmp_path):
    file = tmp_path / "large"
    file.write_bytes(b"a" * 1025)
    fd = p16._open_root(tmp_path)
    try:
        with pytest.raises(p16.Denied) as err:
            p16._read_at(fd, "large", limit=1024)
        assert err.value.code == "ARTIFACT_SIZE_LIMIT"
    finally:
        os.close(fd)


def test_negative_toctou_inode_swap_detected(tmp_path, monkeypatch):
    file = tmp_path / "source"
    file.write_bytes(b"one")
    fd = p16._open_root(tmp_path)
    actual_stat = p16.os.stat

    def changed_stat(*a, **kw):
        res = actual_stat(*a, **kw)
        if a[0] == "source":
            class Changed:
                st_dev = res.st_dev
                st_ino = res.st_ino + 1
                st_size = res.st_size
                st_mtime_ns = res.st_mtime_ns
            return Changed()
        return res
    monkeypatch.setattr(p16.os, "stat", changed_stat)
    try:
        with pytest.raises(p16.Denied) as err:
            p16._read_at(fd, "source", limit=1024)
        assert err.value.code == "ARTIFACT_TOCTOU_CHANGED"
    finally:
        os.close(fd)


def test_negative_zip_expansion_bomb():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        zipf.writestr("bomb.txt", b"0" * 100000)
    with pytest.raises(p16.Denied) as err:
        p16._zip_safe(stream.getvalue(), "evidence.zip")
    assert err.value.code == "ZIP_EXPANSION_RATIO_LIMIT"


def test_negative_zip_path_traversal():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as zipf:
        zipf.writestr("../escaped", b"x")
    with pytest.raises(p16.Denied) as err:
        p16._zip_safe(stream.getvalue(), "evidence.zip")
    assert err.value.code == "PATH_TRAVERSAL_REJECTED"


def test_negative_zip_corruption():
    with pytest.raises(p16.Denied) as err:
        p16._zip_safe(b"PK\x03\x04not-a-real-zip", "evidence.zip")
    assert err.value.code == "CORRUPTED_ARCHIVE"


def test_negative_zip_file_signature_mismatch():
    with pytest.raises(p16.Denied) as err:
        p16._zip_safe(b"PK\x03\x04abc", "notzip.json")
    assert err.value.code == "UNDECLARED_ARCHIVE_PAYLOAD"


def test_negative_zip_member_limit():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as zipf:
        for i in range(130):
            zipf.writestr(f"member{i}", b"x")
    with pytest.raises(p16.Denied) as err:
        p16._zip_safe(stream.getvalue(), "evidence.zip")
    assert err.value.code == "ZIP_MEMBER_LIMIT"


def test_negative_zip_symlink_member():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as zipf:
        item = zipfile.ZipInfo("link")
        item.create_system = 3
        item.external_attr = (stat.S_IFLNK | 0o777) << 16
        zipf.writestr(item, "target")
    with pytest.raises(p16.Denied) as err:
        p16._zip_safe(stream.getvalue(), "evidence.zip")
    assert err.value.code == "ZIP_SYMLINK_REJECTED"


def test_negative_protected_body_never_exported(tmp_path):
    secret = b"HiddenCaseBody2026: do not leak question or answer"
    (tmp_path / "rights.json").write_bytes(secret)
    data = _entry("rights_custody", "rights.json", secret)
    receipt = _denials(tmp_path, [data])
    exported = p16.write_receipt(tmp_path / "request", receipt).read_text()
    assert "HiddenCaseBody2026" not in exported
    assert "question or answer" not in exported
    assert data["sha256"] in exported


def test_negative_empty_input_root_fails_closed(tmp_path):
    (tmp_path / "manifest.json").write_bytes(_raw_json({
        "schema": p16.SCHEMA, "subject": "candidate01",
        "run_id": "run01", "grant_id": "grant01", "artifacts": [],
        "host_id": "host01", "candidate_commit": "a" * 40,
        "candidate_image_sha256": "b" * 64,
    }))
    outcome = p16.inspect(tmp_path, "manifest.json", now_ms=NOW)
    assert p16.CODE_ABSENT in outcome["denial_reasons"]
    assert outcome["classification"] == p16.CODE_ABSENT


def test_negative_manifest_path_outside_root(tmp_path):
    result = p16.inspect(tmp_path, "../escape", now_ms=NOW)
    assert "PATH_TRAVERSAL_REJECTED" in result["denial_reasons"]


def test_negative_scratched_path_relative(tmp_path):
    with pytest.raises(p16.Denied) as err:
        p16.write_receipt("relative", {"classification": p16.CODE_AUTH})
    assert err.value.code == "SCRATCH_PATH_NOT_ABSOLUTE"


def test_positive_e15_always_requires_external_review():
    decision = e15.inspect(None, now_ms=NOW)
    assert decision.status == e15.REJECT_523
    assert not decision.official_cited_gate_pass
    assert not decision.may_execute_official_evaluation
