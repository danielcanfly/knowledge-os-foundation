"""P17-specific CLI denial invariants; only offline synthetic inputs, no P16 rerun."""
from __future__ import annotations

import hashlib
import io
import json
import os
import stat
import zipfile
from pathlib import Path

import pytest

from knowledge_engine import m27_w5_e15_original523_evaluator_admission_v1_experimental as e15
from knowledge_engine import m27_w5_p16_external_evidence_ingress_v1_experimental as p17


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _fixture(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    payload = b'{"fixture_only":true,"case":"P17 isolated read bytes"}'
    (root / "rights.json").write_bytes(payload)
    entry = {
        "kind": "rights_custody", "path": "rights.json",
        "sha256": hashlib.sha256(payload).hexdigest(), "subject": "candidate01",
        "issuer_id": "independent01", "scope": "EVALUATION_ONLY",
        "revision": "rev01", "source_id": "source01", "grant_id": "grant01",
        "license_id": "license01", "run_id": "run01", "host_id": "host01",
        "candidate_commit": "a" * 40, "candidate_image_sha256": "b" * 64,
        "issued_ms": 1, "consent_until_ms": 9999999999999,
        "acl_until_ms": 9999999999999, "retention_until_ms": 9999999999999,
        "revoked": False,
    }
    manifest = {
        "schema": p17.SCHEMA, "subject": "candidate01", "run_id": "run01",
        "grant_id": "grant01", "host_id": "host01",
        "candidate_commit": "a" * 40, "candidate_image_sha256": "b" * 64,
        "artifacts": [entry],
    }
    _save(root, manifest)
    return root, manifest


def _save(root, manifest):
    (root / "manifest.json").write_bytes(_json_bytes(manifest))


def _invoke(root, scratch, capsys, manifest="manifest.json"):
    code = p17.main([
        "inspect", "--ingress-root", str(root), "--manifest", manifest,
        "--scratch", str(scratch),
    ])
    response = json.loads(capsys.readouterr().out)
    assert code != 0, "P17 CLI must NEVER treat P16 ingress-only as admission"
    assert response["decision"] == p17.CLI_DENIED
    assert response["schema"] == p17.CLI_SCHEMA
    assert response["official_cited_gate_pass"] is False
    assert response["may_execute_official_evaluation"] is False
    assert response["original523"] == e15.REJECT_523
    assert response["ar09_phase_b"] == e15.REJECT_B
    return code, response


def _read_denial(scratch, response):
    assert response["receipt_written"] is True
    assert response["transport_ok"] is True
    path = Path(response["receipt_path"])
    assert path == scratch / "P16_REQUEST_RECEIPT.json"
    assert path.is_file()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert hashlib.sha256(path.read_bytes()).hexdigest() == response["receipt_sha256"]
    assert p17.validate_denial_receipt(path, response["receipt_sha256"])
    receipt = json.loads(path.read_text())
    assert receipt["classification"] == response["classification"]
    assert receipt["cli_schema"] == p17.CLI_SCHEMA
    assert receipt["decision"] == p17.CLI_DENIED
    assert receipt["receipt_written"] is True
    assert receipt["transport_ok"] is True
    assert receipt["official_cited_gate_pass"] is False
    assert receipt["may_execute_official_evaluation"] is False
    return receipt


@pytest.mark.parametrize("missing_kind", p17.REQUIRED, ids=list(p17.REQUIRED))
def test_p17_missing_each_independent_evidence_class_never_exit_zero(
    tmp_path, capsys, missing_kind,
):
    root, m = _fixture(tmp_path)
    # The rights kind uses a different valid local file. Never infer that the
    # inspected SHA proves external custodian rights.
    if missing_kind == "rights_custody":
        m["artifacts"][0]["kind"] = "native_sources"
    _save(root, m)
    scratch = tmp_path / "receipt"
    code, response = _invoke(root, scratch, capsys)
    assert code == p17.EXIT_AUTHORITY_DENIED
    receipt = _read_denial(scratch, response)
    assert "MISSING_REQUIRED_" + missing_kind.upper() in receipt["denial_reasons"]
    assert receipt["verified_content_sha256"]
    assert "EXTERNAL_ROOT_AUTHORITY_NOT_INDEPENDENTLY_PROVEN" in receipt[
        "denial_reasons"
    ]


MANIFEST_PATHS = [
    ("traversal", "../manifest.json"),
    ("embedded_traversal", "root/../manifest.json"),
    ("absolute", "/tmp/p17_manifest.json"),
    ("tilde", "~/manifest.json"),
    ("encoded_slash", "manifest%2f.json"),
    ("encoded_dot", "%2e%2e/manifest.json"),
    ("escaped_backslash", "dir\\manifest.json"),
    ("double_slash", "dir//manifest.json"),
    ("dot_component", "./manifest.json"),
    ("hidden", ".secret"),
    ("nested_hidden", "dir/.secret"),
    ("nul", "a\x00b"),
    ("newline", "a\nb"),
    ("tab", "a\tb"),
    ("trailing_space", "manifest.json "),
    ("leading_space", " manifest.json"),
    ("semicolon", "manifest;json"),
    ("oversized", "x" * 280),
    ("missing", "absent.json"),
]


@pytest.mark.parametrize("name,path", MANIFEST_PATHS, ids=[r[0] for r in MANIFEST_PATHS])
def test_p17_manifest_path_or_missing_file_denies_cli(
    tmp_path, capsys, name, path,
):
    root, _ = _fixture(tmp_path)
    scratch = tmp_path / "receipt"
    code, response = _invoke(root, scratch, capsys, path)
    assert code == p17.EXIT_AUTHORITY_DENIED
    receipt = _read_denial(scratch, response)
    assert receipt["classification"] == p17.CODE_ABSENT
    assert "EXTERNAL_ARTIFACTS_ABSENT" in receipt["denial_reasons"]


TOP_FAULTS = [
    ("wrong_schema", "schema", "forged"),
    ("schema_null", "schema", None),
    ("schema_bool", "schema", True),
    ("empty_subject", "subject", ""),
    ("subject_none", "subject", None),
    ("subject_unicode", "subject", "欺"),
    ("run_missing", "run_id", ""),
    ("run_number", "run_id", 123),
    ("grant_null", "grant_id", None),
    ("host_empty", "host_id", ""),
    ("commit_bad", "candidate_commit", "x" * 40),
    ("commit_short", "candidate_commit", "a" * 39),
    ("image_bad", "candidate_image_sha256", "z" * 64),
    ("image_short", "candidate_image_sha256", "b" * 63),
    ("artifact_map", "artifacts", {}),
    ("artifact_string", "artifacts", "fixture"),
    ("artifact_oversized", "artifacts", [{}] * 65),
    ("new_key", "non_contract_secret", "ignored"),
]


@pytest.mark.parametrize("name,key,value", TOP_FAULTS, ids=[r[0] for r in TOP_FAULTS])
def test_p17_malformed_manifest_exits_nonzero_without_receipt(
    tmp_path, capsys, name, key, value,
):
    root, m = _fixture(tmp_path)
    m[key] = value
    _save(root, m)
    scratch = tmp_path / "receipt"
    code, response = _invoke(root, scratch, capsys)
    assert code == p17.EXIT_INPUT_DENIED
    assert response["transport_ok"] is False
    assert response["receipt_written"] is False
    assert response["receipt_path"] is None
    assert response["receipt_sha256"] is None
    assert not (scratch / "P16_REQUEST_RECEIPT.json").exists()


ARTIFACT_FAULTS = [
    ("bad_kind", "kind", "notlisted"),
    ("path_traversal", "path", "../source.json"),
    ("path_absolute", "path", "/tmp/source.json"),
    ("path_encoded", "path", "%2e%2e/source.json"),
    ("path_hidden", "path", ".hidden"),
    ("path_missing", "path", "absent.json"),
    ("sha_forged", "sha256", "0" * 64),
    ("sha_bad", "sha256", "Z" * 64),
    ("subject_wrong", "subject", "forged01"),
    ("issuer_not_id", "issuer_id", "forged signer"),
    ("scope_release", "scope", "RELEASE"),
    ("scope_production", "scope", "PRODUCTION"),
    ("grant_wrong", "grant_id", "grant02"),
    ("run_wrong", "run_id", "run02"),
    ("host_wrong", "host_id", "host02"),
    ("image_wrong", "candidate_image_sha256", "f" * 64),
    ("commit_wrong", "candidate_commit", "f" * 40),
    ("consent_expired", "consent_until_ms", 1),
    ("acl_expired", "acl_until_ms", 1),
    ("retention_expired", "retention_until_ms", 1),
    ("revoked", "revoked", True),
    ("revoked_number", "revoked", 1),
    ("license_wrong_type", "license_id", None),
    ("issued_future", "issued_ms", 9999999999999),
]


@pytest.mark.parametrize(
    "name,key,value", ARTIFACT_FAULTS, ids=[r[0] for r in ARTIFACT_FAULTS],
)
def test_p17_bad_artifact_never_grants_cli_success(
    tmp_path, capsys, name, key, value,
):
    root, m = _fixture(tmp_path)
    m["artifacts"][0][key] = value
    _save(root, m)
    scratch = tmp_path / "receipt"
    code, response = _invoke(root, scratch, capsys)
    assert code == p17.EXIT_AUTHORITY_DENIED
    receipt = _read_denial(scratch, response)
    assert receipt["classification"] == p17.CODE_ABSENT
    assert receipt["denial_reasons"]
    assert receipt["original523"] == e15.REJECT_523
    assert receipt["ar09_phase_b"] == e15.REJECT_B


@pytest.mark.parametrize("mode", [
    "duplicate_json", "truncated", "invalid_utf8", "json_array",
    "nonfinite", "null", "empty_file",
])
def test_p17_parser_denied_no_stale_success(tmp_path, capsys, mode):
    root, m = _fixture(tmp_path)
    data = {
        "duplicate_json": _json_bytes(m).replace(
            b'"schema":', b'"schema":"invalid","schema":', 1
        ),
        "truncated": b'{"schema":',
        "invalid_utf8": b"\xff",
        "json_array": b"[]",
        "nonfinite": b'{"schema":NaN}',
        "null": b"null",
        "empty_file": b"",
    }[mode]
    (root / "manifest.json").write_bytes(data)
    code, response = _invoke(root, tmp_path / "receipt", capsys)
    assert code == p17.EXIT_INPUT_DENIED
    assert response["receipt_written"] is False


FAKE_RESULT_FAULTS = [
    ("admitted_classification", "classification", "ADMITTED"),
    ("wrong_original_cohort", "original523", "ORIGINAL523_ACCEPTED"),
    ("wrong_phase_b_cohort", "ar09_phase_b", "PHASE_B_ACCEPTED"),
    ("official_gate_true", "official_cited_gate_pass", True),
    ("evaluation_flag_true", "may_execute_official_evaluation", True),
    ("e15_missing", "e15", None),
    ("e15_list", "e15", []),
    ("sha_forged", "verified_content_sha256", {"rights_custody": "x"}),
    ("reason_missing", "denial_reasons", None),
    ("nested_accepted", "e15", {
        "original523": {"status": "OFFICIAL_PASS",
                        "official_cited_gate_pass": False,
                        "may_execute_official_evaluation": False}
    }),
    ("missing_client_ack", "e15", {
        "original523": {"status": e15.REJECT_523,
                        "official_cited_gate_pass": True,
                        "may_execute_official_evaluation": False}
    }),
]


@pytest.mark.parametrize(
    "name,key,value", FAKE_RESULT_FAULTS, ids=[r[0] for r in FAKE_RESULT_FAULTS],
)
def test_p17_injected_producer_inconsistent_or_forged_cannot_exit_zero(
    tmp_path, capsys, monkeypatch, name, key, value,
):
    root, _ = _fixture(tmp_path)
    receipt = {
        "classification": p17.CODE_AUTH,
        "original523": e15.REJECT_523,
        "ar09_phase_b": e15.REJECT_B,
        "official_cited_gate_pass": False,
        "may_execute_official_evaluation": False,
        "verified_content_sha256": {},
        "denial_reasons": ["EXTERNAL_ROOT_AUTHORITY_NOT_INDEPENDENTLY_PROVEN"],
        "e15": {},
    }
    receipt[key] = value
    monkeypatch.setattr(p17, "inspect", lambda *args, **kwargs: receipt)
    code, response = _invoke(root, tmp_path / "receipt", capsys)
    assert code == p17.EXIT_INPUT_DENIED
    assert response["receipt_written"] is False
    assert response["transport_ok"] is True


@pytest.mark.parametrize("mode", [
    "decision", "schema", "transport", "receipt_written", "classification",
    "official", "original", "phaseb", "sha", "e15",
])
def test_p17_tampered_denial_receipt_cannot_be_revalidated(
    tmp_path, capsys, mode,
):
    root, _ = _fixture(tmp_path)
    scratch = tmp_path / "receipt"
    code, response = _invoke(root, scratch, capsys)
    assert code == p17.EXIT_AUTHORITY_DENIED
    path = Path(response["receipt_path"])
    receipt = _read_denial(scratch, response)
    changes = {
        "decision": ("decision", "ADMITTED"),
        "schema": ("cli_schema", "unknown"),
        "transport": ("transport_ok", False),
        "receipt_written": ("receipt_written", False),
        "classification": ("classification", "FULL_PASS"),
        "official": ("official_cited_gate_pass", True),
        "original": ("original523", "ORIGINAL523_ADMITTED"),
        "phaseb": ("ar09_phase_b", "PHASE_B_ADMITTED"),
        "sha": ("verified_content_sha256", {"rights_custody": "z" * 64}),
        "e15": ("e15", {"phase_b": {"status": "PASS"}}),
    }
    key, value = changes[mode]
    receipt[key] = value
    path.write_bytes(_json_bytes(receipt))
    assert not p17.validate_denial_receipt(path, response["receipt_sha256"])
    assert not p17.validate_denial_receipt(path, hashlib.sha256(
        path.read_bytes()
    ).hexdigest())


@pytest.mark.parametrize("mode", [
    "denied_exception", "permission_exception", "io_exception",
    "relative_scratch", "scratch_is_file", "scratch_is_symlink",
    "receipt_integrity_failure",
])
def test_p17_receipt_write_failure_never_carries_stale_ok(
    tmp_path, capsys, monkeypatch, mode,
):
    root, _ = _fixture(tmp_path)
    scratch = tmp_path / "receipt"
    if mode == "denied_exception":
        def raising(*args, **kwargs):
            raise p17.Denied("SCRATCH_NOT_PRIVATE_DIRECTORY")
        monkeypatch.setattr(p17, "write_receipt", raising)
    elif mode in ("permission_exception", "io_exception"):
        def raising(*args, **kwargs):
            raise OSError("private /secret should never echo")
        monkeypatch.setattr(p17, "write_receipt", raising)
    elif mode == "relative_scratch":
        scratch = Path("relative_untrusted_p17")
    elif mode == "scratch_is_file":
        scratch.write_text("protected")
    elif mode == "scratch_is_symlink":
        safe = tmp_path / "directory"
        safe.mkdir()
        scratch.symlink_to(safe, target_is_directory=True)
    else:
        monkeypatch.setattr(p17, "validate_denial_receipt", lambda *args: False)
    code, response = _invoke(root, scratch, capsys)
    assert code == p17.EXIT_RECEIPT_DENIED
    assert response["transport_ok"] is True
    assert response["receipt_written"] is False
    assert response["receipt_path"] is None
    assert response["receipt_sha256"] is None


@pytest.mark.parametrize("mode", [
    "bad_zip", "zip_traversal", "zip_symlink", "zip_members",
    "zip_expansion", "zip_undeclared", "zip_file_traversal",
])
def test_p17_zip_admission_failures_nonzero_even_when_hash_valid(
    tmp_path, capsys, mode,
):
    root, m = _fixture(tmp_path)
    stream = io.BytesIO()
    if mode == "bad_zip":
        data = b"PK\x03\x04not-a-zip"
    else:
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as z:
            if mode in ("zip_traversal", "zip_file_traversal"):
                z.writestr("../escape.json", b"private")
            elif mode == "zip_symlink":
                link = zipfile.ZipInfo("link")
                link.create_system = 3
                link.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(link, b"target")
            elif mode == "zip_members":
                for n in range(130):
                    z.writestr(f"member{n}.json", b"e")
            elif mode == "zip_expansion":
                z.writestr("big.txt", b"x" * 200_000)
            else:
                z.writestr("normal.txt", b"some fixture")
        data = stream.getvalue()
    name = "bundle.json" if mode == "zip_undeclared" else "bundle.zip"
    (root / name).write_bytes(data)
    m["artifacts"][0]["path"] = name
    m["artifacts"][0]["sha256"] = hashlib.sha256(data).hexdigest()
    _save(root, m)
    code, response = _invoke(root, tmp_path / "receipt", capsys)
    assert code == p17.EXIT_AUTHORITY_DENIED
    receipt = _read_denial(tmp_path / "receipt", response)
    assert receipt["classification"] == p17.CODE_ABSENT
    assert receipt["denial_reasons"]


@pytest.mark.parametrize("mode", ["symlink_artifact", "hardlink_artifact", "symlink_root"])
def test_p17_independent_file_root_denial(tmp_path, capsys, mode):
    root, m = _fixture(tmp_path)
    if mode == "symlink_root":
        alias = tmp_path / "alias"
        alias.symlink_to(root, target_is_directory=True)
        code, response = _invoke(alias, tmp_path / "receipt", capsys)
        assert code == p17.EXIT_INPUT_DENIED
        assert response["receipt_written"] is False
        return
    source = root / "rights.json"
    alias = root / "artifact.json"
    if mode == "symlink_artifact":
        alias.symlink_to(source)
    else:
        os.link(source, alias)
    m["artifacts"][0]["path"] = "artifact.json"
    _save(root, m)
    code, response = _invoke(root, tmp_path / "receipt", capsys)
    assert code == p17.EXIT_AUTHORITY_DENIED
    receipt = _read_denial(tmp_path / "receipt", response)
    assert receipt["classification"] == p17.CODE_ABSENT


def test_p17_actual_fixture_file_digest_valid_but_authority_denied(
    tmp_path, capsys,
):
    root, _ = _fixture(tmp_path)
    code, response = _invoke(root, tmp_path / "receipt", capsys)
    assert code == p17.EXIT_AUTHORITY_DENIED
    receipt = _read_denial(tmp_path / "receipt", response)
    assert receipt["verified_content_sha256"]["rights_custody"]
    assert receipt["original523"] == e15.REJECT_523
    assert receipt["ar09_phase_b"] == e15.REJECT_B
    assert receipt["may_execute_official_evaluation"] is False
    assert receipt["official_cited_gate_pass"] is False


def test_p17_old_denial_receipt_without_p17_contract_not_admission(tmp_path):
    path = tmp_path / "old_receipt.json"
    path.write_bytes(_json_bytes({
        "schema": p17.SCHEMA, "classification": p17.CODE_ABSENT,
        "transport_ok": True, "receipt_written": True,
        "original523": e15.REJECT_523, "ar09_phase_b": e15.REJECT_B,
    }))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    assert not p17.validate_denial_receipt(path, sha)


def test_p17_denial_receipt_absent_mismatched_digest_does_not_verify(tmp_path):
    path = tmp_path / "missing.json"
    assert not p17.validate_denial_receipt(path, "0" * 64)
    path.write_text('{"decision":"DENIED"}')
    assert not p17.validate_denial_receipt(path, "0" * 64)


def test_p17_stale_denial_receipt_must_not_match_current_no_write(
    tmp_path, capsys,
):
    root, _ = _fixture(tmp_path)
    scratch = tmp_path / "receipt"
    code, result = _invoke(root, scratch, capsys)
    assert code == p17.EXIT_AUTHORITY_DENIED
    old_sha = result["receipt_sha256"]
    (root / "manifest.json").write_bytes(b"invalid")
    code, result = _invoke(root, scratch, capsys)
    assert code == p17.EXIT_INPUT_DENIED
    assert result["receipt_written"] is False
    assert result["receipt_sha256"] is None
    # The old receipt can still be valid as an old *denial*, never acceptance.
    assert p17.validate_denial_receipt(
        scratch / "P16_REQUEST_RECEIPT.json", old_sha
    )


def test_p17_sha_tamper_even_if_recomputed_forged_allow_rejected(tmp_path, capsys):
    root, _ = _fixture(tmp_path)
    _, response = _invoke(root, tmp_path / "receipt", capsys)
    path = Path(response["receipt_path"])
    forged = json.loads(path.read_text())
    forged["decision"] = "ADMIT"
    path.write_bytes(_json_bytes(forged))
    new_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    assert not p17.validate_denial_receipt(path, new_sha)


@pytest.mark.parametrize("mode", [
    "forged_verified_out_of_band", "forged_sha_registry",
    "forged_issuer_registry", "forged_subject_registry",
    "unverified_registry",
])
def test_p17_forged_registry_cannot_promote_bytes_to_authority(
    tmp_path, capsys, monkeypatch, mode,
):
    root, m = _fixture(tmp_path)
    valid_sha = m["artifacts"][0]["sha256"]
    registry = p17.TrustedAuthorityRegistry(
        authorized_artifacts={
            "rights_custody": "0" * 64 if mode == "forged_sha_registry"
            else valid_sha
        },
        nominated_issuers={
            "rights_custody": "untrusted01" if mode == "forged_issuer_registry"
            else "independent01"
        },
        e15_context=e15.IndependentContext(),  # NO signed external roots
        verified_out_of_band=mode != "unverified_registry",
        subject="fake_other01" if mode == "forged_subject_registry"
        else "candidate01",
        grant_id="grant01",
    )
    # The forged registry flag is a caller claim, never an external credential.
    result = p17.inspect(root, "manifest.json", registry=registry)
    assert result["classification"] == p17.CODE_AUTH
    assert result["official_cited_gate_pass"] is False
    assert result["may_execute_official_evaluation"] is False
    assert result["original523"] == e15.REJECT_523
    assert result["ar09_phase_b"] == e15.REJECT_B
    monkeypatch.setattr(p17, "inspect", lambda *a, **kw: result)
    code, output = _invoke(root, tmp_path / "receipt", capsys)
    assert code == p17.EXIT_AUTHORITY_DENIED
    receipt = _read_denial(tmp_path / "receipt", output)
    assert receipt["decision"] == "DENIED"
    assert receipt["denial_reasons"]
