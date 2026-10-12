"""Synthetic-only P24 witness-verifier tests; NEVER execute original P16/B13 paths."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from knowledge_engine.m27_w5_p24_p16_b13_witness_gate_v1_experimental import (
    PURPOSE,
    SCHEMA,
    STATUS_CHAIN,
    STATUS_UNVERIFIED,
    _canonical,
    parse_json_bytes,
    read_existing_regular,
    verify_existing_witness,
)

NOW = datetime(2026, 10, 12, 5, 0, tzinfo=UTC)
SOURCE_COMMIT = "a" * 40
RUNNER_SHA = "b" * 64


def SHA(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


STDOUT = b"synthetic native stdout: checked test progress\n"
STDERR = b""
TEST_LOG = b"synthetic runner observed real child exit code 0; test stdout and exit separately\n"


def _detail(scope: str) -> dict:
    if scope == "P16_SEVEN_SUITE":
        return {
            "suite_ids": [f"synthetic-scope-{i}" for i in range(7)],
            "negative_case_count": 60,
            "pytest_summary": "67 passed in 1.0s",
        }
    if scope == "P16_STANDALONE_AST":
        return {"parser": "python-ast", "parsed_paths": ["synthetic.py"], "diagnostics": []}
    if scope == "B13_BLOB20_PARITY":
        return {
            "entries": [
                {
                    "path": f"synthetic/path_{i}.py",
                    "file_sha256": "1" * 64,
                    "git_blob_bytes_sha256": "1" * 64,
                    "git_object_id": "2" * 40,
                }
                for i in range(20)
            ]
        }
    if scope == "B13_ORIGINAL_POSITIVE":
        return {
            "zip_digest_first": "f" * 64,
            "zip_digest_second": "f" * 64,
            "steps": [
                {
                    "step": label,
                    "child_exit": 20 if label == "missing_crypto_denied" else 0,
                    "child_exit_observed": True,
                    "stdout_sha256": SHA(f"synthetic-{label}".encode()),
                }
                for label in (
                    "zip_build_1",
                    "zip_build_2",
                    "isolated_import",
                    "lazy_functional",
                    "missing_crypto_denied",
                )
            ],
        }
    raise AssertionError(scope)


def synthetic(scope: str = "P16_SEVEN_SUITE") -> tuple[dict, dict, Ed25519PrivateKey]:
    """Generate temporary in-process signer solely for cryptographic unit fixtures."""
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    kinds = {
        "P16_SEVEN_SUITE": ("pytest-seven-scopes", 60),
        "P16_STANDALONE_AST": ("standalone-ast", 1),
        "B13_BLOB20_PARITY": ("twenty-git-blob-parity", 20),
        "B13_ORIGINAL_POSITIVE": ("zip-import-functional-positive", 4),
    }
    doc = {
        "schema": SCHEMA,
        "witness_id": "synthetic-unique-1",
        "scope": scope,
        "origin": {
            "source_commit": SOURCE_COMMIT,
            "source_tree": "c" * 40,
            "runner_sha256": RUNNER_SHA,
            "test_revision": "d" * 40,
        },
        "authorization": {
            "grant_id": "synthetic-grant",
            "issuer_id": "synthetic-issuer",
            "subject": "synthetic-reviewer",
            "scope": scope,
            "purpose": PURPOSE,
            "issued_at": "2026-10-11T00:00:00Z",
            "expires_at": "2026-10-30T00:00:00Z",
            "revoked_at": None,
        },
        "native": {
            "runner_sha256": RUNNER_SHA,
            "source_commit": SOURCE_COMMIT,
            "kind": kinds[scope][0],
            "started_at": "2026-10-11T01:00:00Z",
            "ended_at": "2026-10-11T02:00:00Z",
            "child_exit": 0,
            "child_exit_observed": True,
            "wrapper_exit": 0,
            "stdout_sha256": SHA(STDOUT),
            "stderr_sha256": SHA(STDERR),
            "test_log_sha256": SHA(TEST_LOG),
            "case_count": kinds[scope][1],
        },
        "detail": _detail(scope),
    }
    registry = {
        "synthetic-issuer": {
            "public_key_b64": base64.b64encode(public).decode(),
            "allowed_scopes": [scope],
            "approved_grants": {
                "synthetic-grant": {
                    "subject": "synthetic-reviewer",
                    "scope": scope,
                    "purpose": PURPOSE,
                    "source_commit": SOURCE_COMMIT,
                    "runner_sha256": RUNNER_SHA,
                    "expires_at": "2026-10-30T00:00:00Z",
                }
            },
            "revoked_grants": [],
        }
    }
    sign(doc, key)
    return doc, registry, key


def sign(doc: dict, key: Ed25519PrivateKey) -> None:
    body = {k: v for k, v in doc.items() if k != "signature"}
    doc["signature"] = {
        "algorithm": "Ed25519",
        "issuer_id": "synthetic-issuer",
        "value_b64": base64.b64encode(key.sign(_canonical(body))).decode(),
    }


def _run(doc: dict, registry: dict, **kwargs) -> dict:
    kwargs.setdefault("stdout", STDOUT)
    kwargs.setdefault("stderr", STDERR)
    kwargs.setdefault("test_log", TEST_LOG)
    kwargs.setdefault("now", NOW)
    return verify_existing_witness(doc, registry, **kwargs)


@pytest.mark.parametrize(
    "scope",
    ["P16_SEVEN_SUITE", "P16_STANDALONE_AST", "B13_BLOB20_PARITY", "B13_ORIGINAL_POSITIVE"],
)
def test_synthetic_schema_crypto_chain_never_original_admission(scope):
    doc, registry, _ = synthetic(scope)
    result = _run(doc, registry)
    assert result["decision"] == STATUS_CHAIN
    assert result["receipt_chain_verified"] is True
    assert result["original_p16_pass"] is False
    assert result["original_b13_pass"] is False
    assert result["external_authority_admitted"] is False
    assert result["release_authorized"] is False


# Each case mutates ONE independent synthetic evidence assumption and re-signs
# when the point is the semantic checker rather than signature verification.
NEGATIVE_MUTATIONS = [
    "missing_candidate",
    "missing_registry",
    "extra_field",
    "missing_schema",
    "wrong_schema",
    "unknown_scope",
    "invalid_id",
    "replayed_id",
    "bad_source_commit",
    "bad_source_tree",
    "bad_test_revision",
    "bad_runner_digest",
    "runner_mismatch",
    "native_commit_mismatch",
    "native_kind_mismatch",
    "native_missing",
    "native_extra",
    "native_exit20",
    "native_exit21",
    "native_exit22",
    "native_exit_boolean",
    "native_exit_unobserved",
    "wrapper_exit20",
    "wrapper_exit21",
    "wrapper_exit22",
    "native_cases_zero",
    "native_cases_bool",
    "native_cases_fiftynine",
    "native_digest_missing",
    "native_digest_invalid",
    "native_output_stdout_missing",
    "native_output_stderr_missing",
    "native_output_log_missing",
    "native_output_stdout_corrupt",
    "native_output_stderr_corrupt",
    "native_output_log_corrupt",
    "native_log_empty",
    "native_log_observed_stdout_no_exit",
    "native_p17_os_exit20_disguised",
    "native_p17_os_exit21_disguised",
    "native_p17_os_exit22_disguised",
    "auth_missing",
    "auth_extra",
    "auth_unknown_grant",
    "auth_bad_issuer",
    "auth_bad_subject",
    "auth_bad_purpose",
    "auth_wrong_scope",
    "auth_expired",
    "auth_future_grant",
    "auth_future_run",
    "auth_time_reverse",
    "auth_revoked_claim",
    "auth_revoked_registry",
    "registry_no_scope",
    "registry_missing_grant",
    "registry_subject_mismatch",
    "registry_commit_mismatch",
    "registry_runner_mismatch",
    "registry_grant_expiry_mismatch",
    "registry_missing_pubkey",
    "registry_bad_pubkey",
    "sig_missing",
    "sig_algorithm",
    "sig_wrong_issuer",
    "sig_short",
    "sig_bad_base64",
    "sig_tampered",
    "scope_bad_suite_count",
    "scope_duplicate_suite",
    "scope_cases_count_bad",
    "scope_summary_bad",
    "detail_missing",
    "detail_unsiged_tamper",
]


@pytest.mark.parametrize("mutation", NEGATIVE_MUTATIONS, ids=NEGATIVE_MUTATIONS)
def test_synthetic_negative_refuses_untrusted_or_incomplete_receipt(mutation):
    doc, registry, key = synthetic()
    doc = copy.deepcopy(doc)
    registry = copy.deepcopy(registry)
    kwargs = {}
    dont_resign = False
    if mutation == "missing_candidate":
        doc = None
    elif mutation == "missing_registry":
        registry = None
    elif mutation == "extra_field":
        doc["extra"] = True
    elif mutation == "missing_schema":
        del doc["schema"]
    elif mutation == "wrong_schema":
        doc["schema"] = "unrecognized"
    elif mutation == "unknown_scope":
        doc["scope"] = "P17_AS_IF_P16"
    elif mutation == "invalid_id":
        doc["witness_id"] = "../out-of-scope"
    elif mutation == "replayed_id":
        kwargs["seen_witness_ids"] = frozenset({doc["witness_id"]})
    elif mutation in {"bad_source_commit", "bad_source_tree", "bad_test_revision"}:
        attr = {
            "bad_source_commit": "source_commit",
            "bad_source_tree": "source_tree",
            "bad_test_revision": "test_revision",
        }[mutation]
        doc["origin"][attr] = "incorrect"
    elif mutation == "bad_runner_digest":
        doc["origin"]["runner_sha256"] = "incorrect"
    elif mutation == "runner_mismatch":
        doc["native"]["runner_sha256"] = "e" * 64
    elif mutation == "native_commit_mismatch":
        doc["native"]["source_commit"] = "e" * 40
    elif mutation == "native_kind_mismatch":
        doc["native"]["kind"] = "synthetic-cli-metadata"
    elif mutation == "native_missing":
        del doc["native"]["child_exit"]
    elif mutation == "native_extra":
        doc["native"]["success_flag"] = True
    elif mutation.startswith("native_exit") and mutation != "native_exit_unobserved":
        doc["native"]["child_exit"] = (
            mutation == "native_exit_boolean" or int(mutation[-2:])
            if mutation.endswith(("20", "21", "22"))
            else True
        )
    elif mutation == "native_exit_unobserved":
        doc["native"]["child_exit_observed"] = False
    elif mutation.startswith("wrapper_exit"):
        doc["native"]["wrapper_exit"] = int(mutation[-2:])
    elif mutation in {"native_cases_zero", "native_cases_bool", "native_cases_fiftynine"}:
        doc["native"]["case_count"] = {
            "native_cases_zero": 0,
            "native_cases_bool": True,
            "native_cases_fiftynine": 59,
        }[mutation]
    elif mutation == "native_digest_missing":
        del doc["native"]["test_log_sha256"]
    elif mutation == "native_digest_invalid":
        doc["native"]["test_log_sha256"] = "invalid"
    elif mutation.startswith("native_output_"):
        field = mutation.split("_")[2]
        kwargs[{"stdout": "stdout", "stderr": "stderr", "log": "test_log"}[field]] = (
            None if mutation.endswith("_missing") else b"tampered"
        )
    elif mutation == "native_log_empty":
        kwargs["test_log"] = b""
        doc["native"]["test_log_sha256"] = SHA(b"")
    elif mutation == "native_log_observed_stdout_no_exit":
        log = b"stdout is present, wrapper returned success, child still running"
        kwargs["test_log"] = log
        doc["native"]["test_log_sha256"] = SHA(log)
    elif mutation.startswith("native_p17_os_exit"):
        code = mutation.split("_")[3].removeprefix("exit")
        log = f"original runner exit code 0; P17 CLI denied exit {code}".encode()
        kwargs["test_log"] = log
        doc["native"]["test_log_sha256"] = SHA(log)
    elif mutation == "auth_missing":
        del doc["authorization"]["expires_at"]
    elif mutation == "auth_extra":
        doc["authorization"]["untrusted_owner_chat"] = True
    elif mutation == "auth_unknown_grant":
        doc["authorization"]["grant_id"] = "invented"
    elif mutation == "auth_bad_issuer":
        doc["authorization"]["issuer_id"] = "unknown-issuer"
    elif mutation == "auth_bad_subject":
        doc["authorization"]["subject"] = "unapproved-identity"
    elif mutation == "auth_bad_purpose":
        doc["authorization"]["purpose"] = "execute-original-tests"
    elif mutation == "auth_wrong_scope":
        doc["authorization"]["scope"] = "B13_ORIGINAL_POSITIVE"
    elif mutation == "auth_expired":
        doc["authorization"]["expires_at"] = "2026-10-12T00:00:00Z"
        registry["synthetic-issuer"]["approved_grants"]["synthetic-grant"]["expires_at"] = (
            "2026-10-12T00:00:00Z"
        )
    elif mutation == "auth_future_grant":
        doc["authorization"]["issued_at"] = "2026-10-13T00:00:00Z"
    elif mutation == "auth_future_run":
        doc["native"]["ended_at"] = "2026-10-13T00:00:00Z"
    elif mutation == "auth_time_reverse":
        doc["native"]["started_at"] = "2026-10-11T03:00:00Z"
    elif mutation == "auth_revoked_claim":
        doc["authorization"]["revoked_at"] = "2026-10-11T01:30:00Z"
    elif mutation == "auth_revoked_registry":
        registry["synthetic-issuer"]["revoked_grants"].append("synthetic-grant")
    elif mutation == "registry_no_scope":
        registry["synthetic-issuer"]["allowed_scopes"] = []
    elif mutation == "registry_missing_grant":
        registry["synthetic-issuer"]["approved_grants"] = {}
    elif mutation.startswith("registry_") and mutation.endswith("_mismatch"):
        attr = mutation.removeprefix("registry_").removesuffix("_mismatch")
        key_name = {
            "subject": "subject",
            "commit": "source_commit",
            "runner": "runner_sha256",
            "grant_expiry": "expires_at",
        }[attr]
        registry["synthetic-issuer"]["approved_grants"]["synthetic-grant"][key_name] = "other"
    elif mutation == "registry_missing_pubkey":
        del registry["synthetic-issuer"]["public_key_b64"]
    elif mutation == "registry_bad_pubkey":
        registry["synthetic-issuer"]["public_key_b64"] = "!"
    elif mutation == "sig_missing":
        del doc["signature"]
        dont_resign = True
    elif mutation == "sig_algorithm":
        doc["signature"]["algorithm"] = "HMAC"
        dont_resign = True
    elif mutation == "sig_wrong_issuer":
        doc["signature"]["issuer_id"] = "claimed-independent"
        dont_resign = True
    elif mutation == "sig_short":
        doc["signature"]["value_b64"] = base64.b64encode(b"bad").decode()
        dont_resign = True
    elif mutation == "sig_bad_base64":
        doc["signature"]["value_b64"] = "invalid@@"
        dont_resign = True
    elif mutation == "sig_tampered":
        doc["witness_id"] = "synthetic-unique-2"
        dont_resign = True
    elif mutation == "scope_bad_suite_count":
        doc["detail"]["suite_ids"].pop()
    elif mutation == "scope_duplicate_suite":
        doc["detail"]["suite_ids"][6] = doc["detail"]["suite_ids"][0]
    elif mutation == "scope_cases_count_bad":
        doc["detail"]["negative_case_count"] = 59
    elif mutation == "scope_summary_bad":
        doc["detail"]["pytest_summary"] = "ran successfully"
    elif mutation == "detail_missing":
        del doc["detail"]
    elif mutation == "detail_unsiged_tamper":
        doc["detail"]["negative_case_count"] = 61
        dont_resign = True
    else:
        raise AssertionError(mutation)
    if isinstance(doc, dict) and not dont_resign:
        sign(doc, key)
    result = _run(doc, registry, **kwargs)
    assert result["decision"] == STATUS_UNVERIFIED, (mutation, result)
    assert result["original_p16_pass"] is False
    assert result["original_b13_pass"] is False


SCOPE_NEGATIVE = [
    ("P16_STANDALONE_AST", "parser"),
    ("P16_STANDALONE_AST", "paths"),
    ("P16_STANDALONE_AST", "duplicates"),
    ("P16_STANDALONE_AST", "diagnostics"),
    ("B13_BLOB20_PARITY", "nineteen"),
    ("B13_BLOB20_PARITY", "duplicate"),
    ("B13_BLOB20_PARITY", "sha"),
    ("B13_BLOB20_PARITY", "path"),
    ("B13_BLOB20_PARITY", "object_id"),
    ("B13_ORIGINAL_POSITIVE", "zip_mismatch"),
    ("B13_ORIGINAL_POSITIVE", "missing_step"),
    ("B13_ORIGINAL_POSITIVE", "step_exit"),
    ("B13_ORIGINAL_POSITIVE", "step_unobserved"),
    ("B13_ORIGINAL_POSITIVE", "step_missing_sha"),
]


@pytest.mark.parametrize(("scope", "mutation"), SCOPE_NEGATIVE)
def test_synthetic_original_scope_specific_negative(scope, mutation):
    doc, registry, key = synthetic(scope)
    detail = doc["detail"]
    if mutation == "parser":
        detail["parser"] = "fake"
    elif mutation == "paths":
        detail["parsed_paths"] = []
    elif mutation == "duplicates":
        detail["parsed_paths"] = ["same.py", "same.py"]
    elif mutation == "diagnostics":
        detail["diagnostics"] = ["SyntaxError"]
    elif mutation == "nineteen":
        detail["entries"].pop()
    elif mutation == "duplicate":
        detail["entries"][1]["path"] = detail["entries"][0]["path"]
    elif mutation == "sha":
        detail["entries"][0]["file_sha256"] = "0" * 64
    elif mutation == "path":
        detail["entries"][0]["path"] = "../outside.py"
    elif mutation == "object_id":
        detail["entries"][0]["git_object_id"] = "x"
    elif mutation == "zip_mismatch":
        detail["zip_digest_second"] = "e" * 64
    elif mutation == "missing_step":
        detail["steps"].pop()
    elif mutation == "step_exit":
        detail["steps"][0]["child_exit"] = 1
    elif mutation == "step_unobserved":
        detail["steps"][2]["child_exit_observed"] = False
    elif mutation == "step_missing_sha":
        del detail["steps"][3]["stdout_sha256"]
    sign(doc, key)
    assert _run(doc, registry)["decision"] == STATUS_UNVERIFIED


@pytest.mark.parametrize(
    ("raw", "description"),
    [
        (b'{"x":1,"x":2}', "duplicate"),
        (b'{"x":NaN}', "NaN"),
        (b"[]", "array"),
        (b"", "empty"),
        (b"{invalid", "syntax"),
        (b"\xff", "utf8"),
        (b"x" * 131073, "oversized"),
    ],
    ids=["duplicate", "nonfinite", "array", "empty", "syntax", "utf8", "oversized"],
)
def test_strict_receipt_parser_rejects_invalid(raw, description):
    with pytest.raises((ValueError, UnicodeError, json.JSONDecodeError)):
        parse_json_bytes(raw)


def test_read_existing_receipt_is_readonly_and_bounded(tmp_path):
    path = tmp_path / "witness.json"
    path.write_bytes(b'{"safe":"synthetic"}')
    assert parse_json_bytes(read_existing_regular(tmp_path, "witness.json")) == {
        "safe": "synthetic"
    }
    assert path.read_bytes() == b'{"safe":"synthetic"}'


@pytest.mark.parametrize(
    "name", ["../outside", "/etc/passwd", "sub/other", "..", "", "back\\slash"]
)
def test_read_existing_denies_path_escape(tmp_path, name):
    with pytest.raises(ValueError):
        read_existing_regular(tmp_path, name)


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "oversize"])
def test_read_existing_denies_unsafe_type(tmp_path, kind):
    original = tmp_path / "source.json"
    original.write_text("{}")
    target = tmp_path / "receipt.json"
    if kind == "symlink":
        target.symlink_to(original)
    elif kind == "hardlink":
        os.link(original, target)
    else:
        target.write_bytes(b"x" * 100)
    with pytest.raises((ValueError, OSError)):
        read_existing_regular(tmp_path, target.name, limit=10)


def test_status_does_not_promote_p17_exit20_21_22():
    for code in (20, 21, 22):
        doc, registry, key = synthetic()
        doc["native"]["child_exit"] = code
        sign(doc, key)
        result = _run(doc, registry)
        assert result["reason"] == "NATIVE_EXIT_RUNNER_OR_CASES_INVALID"
        assert result["original_p16_pass"] is False


def test_unhashable_scope_fails_closed_instead_of_raising():
    doc, registry, key = synthetic()
    doc["scope"] = ["P16_SEVEN_SUITE"]
    sign(doc, key)
    result = _run(doc, registry)
    assert result["decision"] == STATUS_UNVERIFIED
    assert result["reason"] == "UNKNOWN_ORIGINAL_SCOPE"
