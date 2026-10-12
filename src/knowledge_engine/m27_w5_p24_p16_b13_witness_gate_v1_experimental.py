"""P24 read-only gate for existing P16/B13 native witness receipts.

This module NEVER executes the historical P16 or B13 actions. Cryptographic
receipt consistency is not external source authority or release admission.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "m27.w5.p24.original-evidence-witness/v1"
STATUS_UNVERIFIED = "ORIGINAL_EVIDENCE_UNVERIFIED"
STATUS_CHAIN = "WITNESS_CHAIN_VERIFIED_ADMISSION_PENDING"
PURPOSE = "readonly-existing-original-evidence-verification"
MAX_WITNESS_BYTES = 131_072
MAX_OUTPUT_BYTES = 2_097_152

SCOPES: dict[str, tuple[str, int]] = {
    "P16_SEVEN_SUITE": ("pytest-seven-scopes", 60),
    "P16_STANDALONE_AST": ("standalone-ast", 1),
    "B13_BLOB20_PARITY": ("twenty-git-blob-parity", 20),
    "B13_ORIGINAL_POSITIVE": ("zip-import-functional-positive", 4),
}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
B13_STEPS = (
    "zip_build_1",
    "zip_build_2",
    "isolated_import",
    "lazy_functional",
    "missing_crypto_denied",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False
    ).encode("ascii")


def _fail(reason: str) -> dict[str, Any]:
    return {
        "schema": "m27.w5.p24.witness-gate-result/v1",
        "decision": STATUS_UNVERIFIED,
        "reason": reason,
        "receipt_chain_verified": False,
        "original_p16_pass": False,
        "original_b13_pass": False,
        "external_authority_admitted": False,
        "release_authorized": False,
    }


def _object(value: Any, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _sha(value: Any) -> bool:
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def _id(value: Any) -> bool:
    return isinstance(value, str) and SAFE_ID.fullmatch(value) is not None


def _time(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("timestamp must use explicit UTC Z")
    result = datetime.fromisoformat(value[:-1] + "+00:00")
    if result.tzinfo is None:
        raise ValueError("timezone required")
    return result.astimezone(UTC)


def _decode64(value: Any, expected: int) -> bytes:
    if not isinstance(value, str):
        raise ValueError("base64 must be string")
    raw = base64.b64decode(value, validate=True)
    if len(raw) != expected or base64.b64encode(raw).decode("ascii") != value:
        raise ValueError("invalid canonical base64 length")
    return raw


def _pairs_unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("duplicate JSON key")
        output[key] = value
    return output


def parse_json_bytes(raw: bytes) -> dict[str, Any]:
    """Bounded duplicate-rejecting JSON document parser; no JSON5/nonfinite values."""
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_WITNESS_BYTES:
        raise ValueError("missing or oversized witness")
    parsed = json.loads(
        raw.decode("utf-8", errors="strict"),
        object_pairs_hook=_pairs_unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")),
    )
    if not isinstance(parsed, dict):
        raise ValueError("witness must be object")
    return parsed


def read_existing_regular(
    root: str | Path, filename: str, *, limit: int = MAX_WITNESS_BYTES
) -> bytes:
    """Read pre-existing receipt/log bytes; reject traversal, symlink, hardlink, FIFO."""
    if not isinstance(filename, str) or not _id(filename) or "/" in filename or "\\" in filename:
        raise ValueError("unsafe witness filename")
    if not isinstance(limit, int) or not 0 < limit <= MAX_OUTPUT_BYTES:
        raise ValueError("invalid read limit")
    root_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW)
    try:
        fd = os.open(
            filename, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=root_fd
        )
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
                raise ValueError("unsafe file type/size")
            with os.fdopen(os.dup(fd), "rb") as stream:
                raw = stream.read(limit + 1)
            after = os.fstat(fd)
            if (
                len(raw) > limit
                or len(raw) != before.st_size
                or (before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns)
                != (after.st_ino, after.st_dev, after.st_size, after.st_mtime_ns)
            ):
                raise ValueError("changed or oversized file")
            return raw
        finally:
            os.close(fd)
    finally:
        os.close(root_fd)


def _validate_detail(scope: str, detail: Any) -> str | None:
    if not isinstance(detail, dict):
        return "MISSING_OR_INVALID_SCOPE_DETAIL"
    if scope == "P16_SEVEN_SUITE":
        if (
            set(detail) != {"suite_ids", "negative_case_count", "pytest_summary"}
            or not isinstance(detail["suite_ids"], list)
            or len(detail["suite_ids"]) != 7
            or len(set(map(str, detail["suite_ids"]))) != 7
            or not all(_id(x) for x in detail["suite_ids"])
            or type(detail["negative_case_count"]) is not int
            or detail["negative_case_count"] < 60
            or not isinstance(detail["pytest_summary"], str)
            or not re.fullmatch(r"[1-9][0-9]* passed(?: in [0-9.]+s)?", detail["pytest_summary"])
        ):
            return "P16_SEVEN_SUITE_REPORT_INVALID"
    elif scope == "P16_STANDALONE_AST":
        if (
            set(detail) != {"parser", "parsed_paths", "diagnostics"}
            or detail["parser"] != "python-ast"
            or not isinstance(detail["parsed_paths"], list)
            or not detail["parsed_paths"]
            or len(detail["parsed_paths"]) != len(set(map(str, detail["parsed_paths"])))
            or not all(
                isinstance(x, str) and x.endswith(".py") and ".." not in x
                for x in detail["parsed_paths"]
            )
            or detail["diagnostics"] != []
        ):
            return "P16_AST_REPORT_INVALID"
    elif scope == "B13_BLOB20_PARITY":
        entries = detail.get("entries")
        if (
            set(detail) != {"entries"}
            or not isinstance(entries, list)
            or len(entries) != 20
            or not all(
                isinstance(x, dict)
                and set(x) == {"path", "file_sha256", "git_blob_bytes_sha256", "git_object_id"}
                for x in entries
            )
        ):
            return "B13_TWENTY_BLOB_REPORT_INVALID"
        paths: list[str] = []
        for item in entries:
            path = item["path"]
            if (
                not isinstance(path, str)
                or not path.endswith(".py")
                or path.startswith("/")
                or ".." in Path(path).parts
                or not _sha(item["file_sha256"])
                or item["file_sha256"] != item["git_blob_bytes_sha256"]
                or not isinstance(item["git_object_id"], str)
                or GIT_SHA.fullmatch(item["git_object_id"]) is None
            ):
                return "B13_BLOB_PARITY_FAILED"
            paths.append(path)
        if len(set(paths)) != 20:
            return "B13_DUPLICATE_BLOB_PATH"
    elif scope == "B13_ORIGINAL_POSITIVE":
        steps = detail.get("steps")
        if (
            set(detail) != {"steps", "zip_digest_first", "zip_digest_second"}
            or not _sha(detail.get("zip_digest_first"))
            or detail["zip_digest_first"] != detail.get("zip_digest_second")
        ):
            return "B13_ZIP_PARITY_INVALID"
        if (
            not isinstance(steps, list)
            or len(steps) != 5
            or [x.get("step") if isinstance(x, dict) else None for x in steps] != list(B13_STEPS)
        ):
            return "B13_POSITIVE_STEP_SET_INVALID"
        for entry in steps:
            if (
                set(entry) != {"step", "child_exit", "child_exit_observed", "stdout_sha256"}
                or entry["child_exit_observed"] is not True
                or not _sha(entry["stdout_sha256"])
            ):
                return "B13_NATIVE_STEP_MISSING"
            code = entry["child_exit"]
            if type(code) is not int or (
                code != 0 if entry["step"] != "missing_crypto_denied" else code == 0
            ):
                return "B13_NATIVE_STEP_EXIT_INVALID"
    else:
        return "UNKNOWN_ORIGINAL_SCOPE"
    return None


def verify_existing_witness(
    candidate: Mapping[str, Any] | None,
    independent_registry: Mapping[str, Any] | None,
    *,
    stdout: bytes | None = None,
    stderr: bytes | None = None,
    test_log: bytes | None = None,
    now: datetime | None = None,
    seen_witness_ids: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Verify separately held signed receipts, never grant original P16/B13 PASS.

    independent_registry must be provided by an independent custodian, NOT read
    from the candidate receipt; synthetic/local registry verification only proves
    schema/crypto consistency, not authentic external issuance.
    """
    if not isinstance(candidate, Mapping) or not isinstance(independent_registry, Mapping):
        return _fail("MISSING_WITNESS_OR_INDEPENDENT_REGISTRY")
    candidate = dict(candidate)
    expected = {
        "schema",
        "witness_id",
        "scope",
        "origin",
        "authorization",
        "native",
        "detail",
        "signature",
    }
    if set(candidate) != expected or candidate["schema"] != SCHEMA:
        return _fail("WITNESS_SCHEMA_INVALID")
    witness_id, scope = candidate["witness_id"], candidate["scope"]
    if not _id(witness_id) or witness_id in seen_witness_ids:
        return _fail("REPLAY_OR_INVALID_WITNESS_ID")
    if not isinstance(scope, str) or scope not in SCOPES:
        return _fail("UNKNOWN_ORIGINAL_SCOPE")
    origin, auth, native, sig = (
        candidate[x] for x in ("origin", "authorization", "native", "signature")
    )
    if not _object(origin, {"source_commit", "source_tree", "runner_sha256", "test_revision"}):
        return _fail("SOURCE_ORIGIN_INVALID")
    if not all(
        isinstance(origin[key], str) and GIT_SHA.fullmatch(origin[key])
        for key in ("source_commit", "source_tree", "test_revision")
    ) or not _sha(origin["runner_sha256"]):
        return _fail("SOURCE_ORIGIN_HASH_INVALID")
    if not _object(
        auth,
        {
            "grant_id",
            "issuer_id",
            "subject",
            "scope",
            "purpose",
            "issued_at",
            "expires_at",
            "revoked_at",
        },
    ):
        return _fail("AUTHORIZATION_SHAPE_INVALID")
    if (
        not all(_id(auth[x]) for x in ("grant_id", "issuer_id", "subject"))
        or auth["scope"] != scope
        or auth["purpose"] != PURPOSE
    ):
        return _fail("UNAUTHORIZED_PURPOSE_OR_IDENTITY")
    if not _object(
        native,
        {
            "runner_sha256",
            "source_commit",
            "kind",
            "started_at",
            "ended_at",
            "child_exit",
            "child_exit_observed",
            "wrapper_exit",
            "stdout_sha256",
            "stderr_sha256",
            "test_log_sha256",
            "case_count",
        },
    ):
        return _fail("NATIVE_RECEIPT_SHAPE_INVALID")
    if (
        native["runner_sha256"] != origin["runner_sha256"]
        or native["source_commit"] != origin["source_commit"]
        or native["kind"] != SCOPES[scope][0]
        or native["child_exit_observed"] is not True
        or type(native["child_exit"]) is not int
        or native["child_exit"] != 0
        or type(native["wrapper_exit"]) is not int
        or native["wrapper_exit"] != 0
        or type(native["case_count"]) is not int
        or native["case_count"] < SCOPES[scope][1]
    ):
        return _fail("NATIVE_EXIT_RUNNER_OR_CASES_INVALID")
    if not all(_sha(native[key]) for key in ("stdout_sha256", "stderr_sha256", "test_log_sha256")):
        return _fail("NATIVE_OUTPUT_DIGEST_INVALID")
    if not all(isinstance(x, bytes) for x in (stdout, stderr, test_log)):
        return _fail("MISSING_NATIVE_TEST_OUTPUT_BYTES")
    if any(len(x) > MAX_OUTPUT_BYTES for x in (stdout, stderr, test_log)):
        return _fail("NATIVE_TEST_OUTPUT_OVERSIZED")
    for field, output in (
        ("stdout_sha256", stdout),
        ("stderr_sha256", stderr),
        ("test_log_sha256", test_log),
    ):
        if hashlib.sha256(output).hexdigest() != native[field]:
            return _fail("NATIVE_OUTPUT_BYTES_HASH_MISMATCH")
    if not test_log or not stdout or b"exit code" not in test_log.lower():
        return _fail("NATIVE_LOG_OR_EXIT_PROVENANCE_MISSING")
    if (
        b"exit 20" in test_log.lower()
        or b"exit 21" in test_log.lower()
        or b"exit 22" in test_log.lower()
    ):
        return _fail("P17_CLI_DENIAL_NOT_SUCCESSFUL_ORIGINAL_TEST")
    detail_error = _validate_detail(scope, candidate["detail"])
    if detail_error:
        return _fail(detail_error)
    if (
        not _object(sig, {"algorithm", "issuer_id", "value_b64"})
        or sig["algorithm"] != "Ed25519"
        or sig["issuer_id"] != auth["issuer_id"]
    ):
        return _fail("MISSING_OR_INVALID_CRYPTO_SIGNATURE")
    if not _id(sig["issuer_id"]) or sig["issuer_id"] not in independent_registry:
        return _fail("UNKNOWN_INDEPENDENT_ISSUER")
    record = independent_registry[sig["issuer_id"]]
    if not _object(
        record, {"public_key_b64", "allowed_scopes", "approved_grants", "revoked_grants"}
    ):
        return _fail("INDEPENDENT_REGISTRY_INVALID")
    grants = record["approved_grants"]
    if (
        not isinstance(grants, dict)
        or not isinstance(record["allowed_scopes"], (list, tuple, frozenset))
        or scope not in record["allowed_scopes"]
        or not isinstance(record["revoked_grants"], (list, tuple, frozenset))
        or auth["grant_id"] in record["revoked_grants"]
        or auth["grant_id"] not in grants
    ):
        return _fail("GRANT_NOT_INDEPENDENTLY_APPROVED_OR_REVOKED")
    grant = grants[auth["grant_id"]]
    if not _object(
        grant, {"subject", "scope", "purpose", "source_commit", "runner_sha256", "expires_at"}
    ):
        return _fail("INDEPENDENT_GRANT_INVALID")
    if (
        any(grant[key] != auth[key] for key in ("subject", "scope", "purpose", "expires_at"))
        or grant["source_commit"] != origin["source_commit"]
        or grant["runner_sha256"] != origin["runner_sha256"]
        or auth["revoked_at"] is not None
    ):
        return _fail("GRANT_IDENTITY_OR_SOURCE_MISMATCH")
    try:
        current = (now or datetime.now(UTC)).astimezone(UTC)
        issued, expires = _time(auth["issued_at"]), _time(auth["expires_at"])
        started, ended = _time(native["started_at"]), _time(native["ended_at"])
        if not issued <= started <= ended <= current < expires:
            return _fail("CONSENT_TIME_EXPIRED_OR_INVALID")
        public_key = _decode64(record["public_key_b64"], 32)
        signature = _decode64(sig["value_b64"], 64)
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        body = {k: v for k, v in candidate.items() if k != "signature"}
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, _canonical(body))
    except (ValueError, TypeError, binascii.Error, ImportError, OverflowError):
        return _fail("CRYPTO_OR_TIMESTAMP_INVALID")
    except Exception as exc:
        # Includes cryptography InvalidSignature; exception contents are never exposed.
        return _fail(
            "SIGNATURE_INVALID"
            if type(exc).__name__ == "InvalidSignature"
            else "CRYPTO_VERIFICATION_FAILED"
        )
    return {
        "schema": "m27.w5.p24.witness-gate-result/v1",
        "decision": STATUS_CHAIN,
        "reason": "CRYPTOGRAPHIC_RECEIPT_CHAIN_ONLY_NOT_INDEPENDENT_EXTERNAL_ADMISSION",
        "receipt_chain_verified": True,
        "witness_id": witness_id,
        "scope": scope,
        "source_commit": origin["source_commit"],
        "original_p16_pass": False,
        "original_b13_pass": False,
        "external_authority_admitted": False,
        "release_authorized": False,
    }
