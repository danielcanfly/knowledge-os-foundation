"""P16 bounded read-only external evidence intake. Never authenticates its own roots."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import time
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from knowledge_engine import m27_w5_e15_original523_evaluator_admission_v1_experimental as e15

SCHEMA = "m27-p16-external-evidence-v1"
MAX_MANIFEST = 1_048_576
MAX_ARTIFACT = 8_388_608
MAX_ZIP_UNCOMPRESSED = 16_777_216
MAX_ZIP_MEMBERS = 128
REQUIRED = (
    "rights_custody", "original_index", "phase_b_index", "native_sources",
    "citation_spans", "grading_rubric", "graded_original", "graded_phase_b",
    "image_attestation", "build_attestation", "runner_attestation",
    "instrumentation_attestation", "client_delivery", "provider_usage",
    "provider_prices", "provider_invoice", "issuer_roots",
)
OPTIONAL = ("rollback_rehearsal", "release_authorization")
ROLES = e15.ROLES
HEX = re.compile(r"^[0-9a-f]{64}$")
IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,95}$")
MAX_FILES = 64
CODE_ABSENT = "EXTERNAL_ARTIFACTS_ABSENT"
CODE_AUTH = "P16_EXTERNAL_AUTHORITY_NOT_ADMITTED"
CLI_SCHEMA = "m27-p17-ingress-cli-denial-v1"
CLI_DENIED = "DENIED"
EXIT_AUTHORITY_DENIED = 20
EXIT_INPUT_DENIED = 21
EXIT_RECEIPT_DENIED = 22


class Denied(ValueError):
    """Stable denial code. No untrusted bytes included in diagnostics."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class Artifact:
    kind: str
    path: str
    sha256: str
    subject: str
    issuer_id: str
    scope: str
    revision: str
    source_id: str
    grant_id: str
    license_id: str
    run_id: str
    host_id: str
    candidate_commit: str
    candidate_image_sha256: str
    issued_ms: int
    consent_until_ms: int
    acl_until_ms: int
    retention_until_ms: int
    revoked: bool = False


@dataclass(frozen=True, slots=True)
class TrustedAuthorityRegistry:
    """Injected by a *separately authenticated* auditor process, never the input.

    Independent file hashes/issuer grants must be provisioned outside ingress.
    Claiming 'external' in the manifest or storing local self-signed keys is
    insufficient. The CLI deliberately offers no root-import switch.
    """

    authorized_artifacts: Mapping[str, str]
    nominated_issuers: Mapping[str, str]
    e15_context: e15.IndependentContext
    verified_out_of_band: bool = False
    subject: str = ""
    grant_id: str = ""


def _id(value: object) -> bool:
    return isinstance(value, str) and IDENT.fullmatch(value) is not None


def _sha(value: object) -> bool:
    return isinstance(value, str) and HEX.fullmatch(value) is not None


def _int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for k, value in pairs:
        if k in data:
            raise Denied("DUPLICATE_JSON_KEY")
        data[k] = value
    return data


def _json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              Denied("NONFINITE_JSON_VALUE")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, Denied):
            raise
        raise Denied("MALFORMED_JSON") from None


def _relative(value: object) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or len(value) > 255:
        raise Denied("UNSAFE_ARTIFACT_PATH")
    if (
        value.startswith(("/", "~")) or os.path.isabs(value)
        or "\\" in value or "%" in value or "\x00" in value
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
        or "//" in value or value.strip() != value
    ):
        raise Denied("UNSAFE_ARTIFACT_PATH")
    parts = tuple(value.split("/"))
    if any(p in ("", ".", "..") or p.startswith(".") for p in parts):
        raise Denied("PATH_TRAVERSAL_REJECTED")
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,95}", p)
           for p in parts):
        raise Denied("UNSAFE_ARTIFACT_PATH")
    return parts


def _open_root(root: Path) -> int:
    if not root.is_absolute():
        raise Denied("INGRESS_ROOT_MUST_BE_ABSOLUTE")
    try:
        if stat.S_ISLNK(os.lstat(root).st_mode):
            raise Denied("SYMLINK_ROOT_REJECTED")
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        if not stat.S_ISDIR(os.fstat(fd).st_mode):
            os.close(fd)
            raise Denied("INGRESS_ROOT_NOT_DIRECTORY")
        return fd
    except (OSError, ValueError) as exc:
        if isinstance(exc, Denied):
            raise
        raise Denied("INGRESS_ROOT_UNAVAILABLE") from None


def _read_at(root_fd: int, rel: str, *, limit: int) -> bytes:
    parts = _relative(rel)
    handles: list[int] = []
    try:
        parent = root_fd
        for component in parts[:-1]:
            fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY |
                         os.O_NOFOLLOW, dir_fd=parent)
            handles.append(fd)
            parent = fd
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK |
                     os.O_NOFOLLOW, dir_fd=parent)
        handles.append(fd)
        first = os.fstat(fd)
        if not stat.S_ISREG(first.st_mode) or first.st_nlink != 1:
            raise Denied("NOT_SINGLE_REGULAR_FILE")
        if first.st_size > limit:
            raise Denied("ARTIFACT_SIZE_LIMIT")
        digest_parts: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(fd, min(65_536, limit + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise Denied("ARTIFACT_SIZE_LIMIT")
            digest_parts.append(chunk)
        after = os.fstat(fd)
        path_after = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        if (
            (first.st_dev, first.st_ino, first.st_size, first.st_mtime_ns,
             first.st_ctime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
                after.st_ctime_ns)
            or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            != (path_after.st_dev, path_after.st_ino, path_after.st_size,
                path_after.st_mtime_ns)
            or size != first.st_size
        ):
            raise Denied("ARTIFACT_TOCTOU_CHANGED")
        return b"".join(digest_parts)
    except OSError as exc:
        if exc.errno in (40, 62):
            raise Denied("SYMLINK_TRAVERSAL_REJECTED") from None
        raise Denied("ARTIFACT_OPEN_OR_RACE_DENIED") from None
    finally:
        for fd in reversed(handles):
            os.close(fd)


def _zip_safe(raw: bytes, name: str) -> None:
    if not (name.endswith(".zip") or raw.startswith(b"PK\x03\x04")):
        return
    if not name.endswith(".zip"):
        raise Denied("UNDECLARED_ARCHIVE_PAYLOAD")
    import io
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            items = archive.infolist()
            if len(items) > MAX_ZIP_MEMBERS:
                raise Denied("ZIP_MEMBER_LIMIT")
            total = 0
            for item in items:
                _relative(item.filename.rstrip("/"))
                if item.flag_bits & 1:
                    raise Denied("ENCRYPTED_ZIP_NOT_ADMITTED")
                if stat.S_ISLNK(item.external_attr >> 16):
                    raise Denied("ZIP_SYMLINK_REJECTED")
                total += item.file_size
                if total > MAX_ZIP_UNCOMPRESSED:
                    raise Denied("ZIP_UNCOMPRESSED_LIMIT")
                if item.file_size > max(1, item.compress_size) * 50:
                    raise Denied("ZIP_EXPANSION_RATIO_LIMIT")
                with archive.open(item) as stream:
                    seen = 0
                    while True:
                        block = stream.read(65_536)
                        if not block:
                            break
                        seen += len(block)
                        if seen > item.file_size or seen > MAX_ZIP_UNCOMPRESSED:
                            raise Denied("ZIP_CONTENT_LENGTH_CONFLICT")
                    if seen != item.file_size:
                        raise Denied("ZIP_CONTENT_LENGTH_CONFLICT")
    except (zipfile.BadZipFile, EOFError, RuntimeError, OSError, ValueError) as exc:
        if isinstance(exc, Denied):
            raise
        raise Denied("CORRUPTED_ARCHIVE") from None


def _artifact(obj: object, now_ms: int, subject: str) -> Artifact:
    if not isinstance(obj, dict):
        raise Denied("UNTYPED_ARTIFACT_RECORD")
    names = {f.name for f in fields(Artifact)}
    if set(obj) != names:
        raise Denied("ARTIFACT_SCHEMA_MISMATCH")
    try:
        a = Artifact(**obj)
    except TypeError:
        raise Denied("ARTIFACT_SCHEMA_MISMATCH") from None
    if a.kind not in REQUIRED + OPTIONAL:
        raise Denied("UNKNOWN_ARTIFACT_CLASS")
    _relative(a.path)
    if not _sha(a.sha256):
        raise Denied("INVALID_EXPECTED_SHA256")
    if not all(_id(v) for v in (a.subject, a.issuer_id, a.revision,
                                a.source_id, a.grant_id, a.license_id,
                                a.run_id, a.host_id)):
        raise Denied("INVALID_ARTIFACT_IDENTITY")
    if a.subject != subject:
        raise Denied("CANDIDATE_SUBJECT_MISMATCH")
    if not re.fullmatch(r"[0-9a-f]{40}", a.candidate_commit or "") or not _sha(
        a.candidate_image_sha256
    ):
        raise Denied("EXECUTED_IMAGE_LINEAGE_INVALID")
    if a.scope != "EVALUATION_ONLY":
        raise Denied("SCOPE_NOT_AUTHORIZED")
    if not all(_int(v) for v in (
        a.issued_ms, a.acl_until_ms, a.consent_until_ms,
        a.retention_until_ms
    )):
        raise Denied("ARTIFACT_CLOCK_INVALID")
    if a.issued_ms > now_ms:
        raise Denied("ISSUANCE_IN_FUTURE")
    if min(a.acl_until_ms, a.consent_until_ms,
           a.retention_until_ms) <= now_ms:
        raise Denied("CONSENT_ACL_OR_RETENTION_EXPIRED")
    if a.revoked is not False:
        raise Denied("RIGHTS_OR_GRANT_REVOKED")
    return a


def _typed(cls: Any, value: Any, nested: dict[str, tuple[Any, bool]]
           | None = None) -> Any:
    if not isinstance(value, dict) or set(value) != {f.name for f in fields(cls)}:
        raise Denied("E15_TYPED_METADATA_SCHEMA_INVALID")
    data = dict(value)
    for field_name, (nested_cls, many) in (nested or {}).items():
        data[field_name] = (
            tuple(_typed(nested_cls, x) for x in data[field_name])
            if many and isinstance(data[field_name], list)
            else _typed(nested_cls, data[field_name]) if not many else
            (_ for _ in ()).throw(Denied("E15_TYPED_METADATA_SCHEMA_INVALID"))
        )
    for f in fields(cls):
        if f.name in ("implementer_ids", "reviewer_ids") and isinstance(
            data[f.name], list
        ):
            data[f.name] = tuple(data[f.name])
    try:
        return cls(**data)
    except (TypeError, ValueError):
        raise Denied("E15_TYPED_METADATA_SCHEMA_INVALID") from None


def _e15_metadata(
    binary: Mapping[str, bytes],
    context: e15.IndependentContext | None,
    now_ms: int,
    lineage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    outcomes: dict[str, Any] = {}
    for name, sealed, scored in (
        ("original523", "original_index", "graded_original"),
        ("phase_b", "phase_b_index", "graded_phase_b"),
    ):
        try:
            m = _typed(e15.SealedManifest, _json(binary[sealed]), {
                "candidate": (e15.FrozenImage, False),
                "sources": (e15.SourcePin, True),
                "cases": (e15.OpaqueCase, True),
            })
            p = _typed(e15.RunPacket, _json(binary[scored]), {
                "results": (e15.ScoredCase, True),
                "claims": (e15.SignedClaim, True),
            })
            if lineage is not None and (
                m.candidate.commit != lineage["candidate_commit"]
                or m.candidate.image_sha256 != lineage["candidate_image_sha256"]
                or p.run_id != lineage["run_id"]
                or m.cohort != (e15.ORIGINAL if name == "original523"
                                else e15.PHASE_B)
            ):
                raise Denied("CANDIDATE_OR_COHORT_LINEAGE_CONFLICT")
            decision = e15.inspect(m, p, context, now_ms=now_ms)
            outcomes[name] = {
                "status": decision.status,
                "reasons": list(decision.reasons),
                "assigned": decision.total_assigned,
                "results": decision.result_count,
                "official_cited_gate_pass": False,
                "may_execute_official_evaluation": False,
            }
        except (Denied, KeyError, AttributeError, TypeError, ValueError,
                RecursionError):
            outcomes[name] = {
                "status": (e15.REJECT_523 if name == "original523"
                           else e15.REJECT_B),
                "reasons": ["E15_TYPED_METADATA_NOT_ADMITTED"],
                "official_cited_gate_pass": False,
                "may_execute_official_evaluation": False,
            }
    return outcomes


def _request_receipt(
    subject: str, found: Mapping[str, str], errors: set[str],
    classifications: Mapping[str, Any],
) -> dict[str, Any]:
    duties = {
        "rights_custody": "Independent rights issuer and nominated lawful custodian",
        "original_index": "Independent original-523 sealed corpus custodian",
        "phase_b_index": "Separate blinded 200-case Phase B custodian",
        "native_sources": "Licensed native source owner/source verifier",
        "citation_spans": "Independent source revision/span verifier",
        "grading_rubric": "Independent rubric approver and grader",
        "graded_original": "Independent original-523 grader including all outcomes",
        "graded_phase_b": "Independent Phase B grader including all outcomes",
        "image_attestation": "Independent executed immutable image builder",
        "build_attestation": "Independent build/signing authority",
        "runner_attestation": "Independent executed runner authority",
        "instrumentation_attestation": "Independent instrumentation observer",
        "client_delivery": "Authenticated native-app client/observer",
        "provider_usage": "Provider usage receipt custodian",
        "provider_prices": "Provider price/currency version authority",
        "provider_invoice": "Provider invoice/reconciliation custodian",
        "issuer_roots": "Separate authority trust-root registrar (eight roles)",
    }
    return {
        "schema": SCHEMA,
        "classification": (CODE_AUTH if found else CODE_ABSENT),
        "original523": e15.REJECT_523,
        "ar09_phase_b": e15.REJECT_B,
        "official_cited_gate_pass": False,
        "may_execute_official_evaluation": False,
        "subject": subject if _id(subject) else "UNVERIFIED_SUBJECT",
        "verified_content_sha256": dict(sorted(found.items())),
        "denial_reasons": sorted(errors),
        "e15": classifications,
        "requests": [
            {"kind": k, "responsible_independent_party": duties[k],
             "required": True, "file_sha256": found.get(k),
             "scope": "EVALUATION_ONLY",
             "independent_signature_required": True}
            for k in REQUIRED
        ],
        "optional_release_requests": list(OPTIONAL),
        "independent_issuer_roles": list(ROLES),
        "hard_gates_unchanged": ["B13_BLOCKED", "W5_FULL_COMPLETE_FALSE",
                                 "REL01_NOT_CERTIFIED", "PRODUCTION_UNCHANGED"],
    }


def inspect(
    ingress_root: str | Path, manifest_path: str,
    *, registry: TrustedAuthorityRegistry | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Read, hash and reconcile real local bytes. Never fetch or execute them.

    Registry is an injected independent trust boundary, NOT manifest-supplied.
    All artifacts are inspected even when external authority is absent, but no
    sensitive artifact body is included in the receipt.
    """
    now = int(time.time() * 1000) if now_ms is None else now_ms
    if not _int(now):
        raise Denied("CLOCK_INVALID")
    found: dict[str, str] = {}
    raw_meta: dict[str, bytes] = {}
    errors: set[str] = set()
    classifications: dict[str, Any] = {}
    subject = "UNVERIFIED_SUBJECT"
    fd = _open_root(Path(ingress_root))
    try:
        try:
            raw = _read_at(fd, manifest_path, limit=MAX_MANIFEST)
        except Denied as exc:
            errors.add(exc.code)
            errors.add(CODE_ABSENT)
            return _request_receipt(subject, found, errors, classifications)
        meta = _json(raw)
        if not isinstance(meta, dict) or set(meta) != {
            "schema", "subject", "run_id", "grant_id", "artifacts",
            "host_id", "candidate_commit", "candidate_image_sha256"
        } or meta["schema"] != SCHEMA:
            raise Denied("INGRESS_MANIFEST_SCHEMA_INVALID")
        subject = meta["subject"]
        if not all(_id(meta[x]) for x in (
            "subject", "run_id", "grant_id", "host_id"
        )):
            raise Denied("MANIFEST_IDENTITY_INVALID")
        if not re.fullmatch(r"[0-9a-f]{40}", meta["candidate_commit"] or "") \
                or not _sha(meta["candidate_image_sha256"]):
            raise Denied("MANIFEST_CANDIDATE_LINEAGE_INVALID")
        artifacts = meta["artifacts"]
        if not isinstance(artifacts, list) or len(artifacts) > MAX_FILES:
            raise Denied("MANIFEST_ARTIFACT_COUNT_INVALID")
        if not artifacts:
            errors.add(CODE_ABSENT)
        used_paths: set[str] = set()
        used_kinds: set[str] = set()
        used_sha: set[str] = set()
        for entry in artifacts:
            try:
                a = _artifact(entry, now, subject)
                if a.grant_id != meta["grant_id"]:
                    raise Denied("GRANT_BINDING_MISMATCH")
                if (a.run_id != meta["run_id"] or a.host_id != meta["host_id"]
                    or a.candidate_commit != meta["candidate_commit"]
                    or a.candidate_image_sha256 != meta["candidate_image_sha256"]):
                    raise Denied("RUN_HOST_OR_EXECUTED_IMAGE_LINEAGE_MISMATCH")
                if a.path in used_paths or a.kind in used_kinds:
                    raise Denied("DUPLICATE_MANIFEST_ARTIFACT")
                used_paths.add(a.path)
                used_kinds.add(a.kind)
                if a.sha256 in used_sha:
                    raise Denied("DUPLICATE_CONTENT_DIGEST")
                used_sha.add(a.sha256)
                data = _read_at(fd, a.path, limit=MAX_ARTIFACT)
                actual = hashlib.sha256(data).hexdigest()
                if actual != a.sha256:
                    raise Denied("FILE_CONTENT_SHA256_MISMATCH")
                _zip_safe(data, a.path)
                found[a.kind] = actual
                if a.kind in ("original_index", "graded_original",
                              "phase_b_index", "graded_phase_b"):
                    raw_meta[a.kind] = data
                if registry is None or not registry.verified_out_of_band:
                    errors.add("INDEPENDENT_TRUST_REGISTRY_NOT_PROVISIONED")
                else:
                    if registry.subject != subject or registry.grant_id != a.grant_id:
                        errors.add("EXTERNAL_REGISTRY_SUBJECT_OR_GRANT_MISMATCH")
                    if registry.authorized_artifacts.get(a.kind) != actual:
                        errors.add("EXTERNAL_AUTHORITY_SHA256_NOT_MATCHED")
                    if registry.nominated_issuers.get(a.kind) != a.issuer_id:
                        errors.add("INDEPENDENT_ISSUER_NOT_NOMINATED")
            except Denied as exc:
                errors.add(exc.code)
        for kind in REQUIRED:
            if kind not in found:
                errors.add("MISSING_REQUIRED_" + kind.upper())
        context = (registry.e15_context if registry and
                   registry.verified_out_of_band else None)
        classifications = _e15_metadata(raw_meta, context, now, meta)
        for name, value in classifications.items():
            if name == "original523" and value["status"] != (
                "ORIGINAL523_METADATA_ACCEPTED_FOR_INDEPENDENT_REVIEW"
            ):
                errors.add("ORIGINAL523_TYPED_PROVENANCE_NOT_ADMITTED")
            if name == "phase_b" and value["status"] == e15.REJECT_B:
                errors.add("AR09_PHASE_B_TYPED_PROVENANCE_NOT_ADMITTED")
        if registry is None or not registry.verified_out_of_band:
            errors.add("EXTERNAL_ROOT_AUTHORITY_NOT_INDEPENDENTLY_PROVEN")
        # Both cohorts still need external evaluator-only execution and an
        # independently reviewable receipt; this service is NEVER a grader.
        return _request_receipt(subject, found, errors, classifications)
    finally:
        os.close(fd)


def write_receipt(scratch: str | Path, receipt: Mapping[str, Any]) -> Path:
    """Atomic private redacted receipt; no evidence bodies or raw signatures."""
    target = Path(scratch)
    if not target.is_absolute():
        raise Denied("SCRATCH_PATH_NOT_ABSOLUTE")
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    if target.is_symlink() or not target.is_dir():
        raise Denied("SCRATCH_NOT_PRIVATE_DIRECTORY")
    os.chmod(target, 0o700)
    final = target / "P16_REQUEST_RECEIPT.json"
    temp = target / ("P16_REQUEST_RECEIPT." + str(os.getpid()) + ".tmp")
    raw = (json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False,
                      allow_nan=False) + "\n").encode()
    try:
        fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                     os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, final)
        os.chmod(final, 0o600)
    finally:
        if temp.exists():
            temp.unlink()
    return final


def _safe_denial_code(value: object) -> str:
    """Never echo untrusted exception messages or protected source paths."""
    if isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{2,95}", value):
        return value
    return "UNCLASSIFIED_INPUT_DENIAL"


def _cli_denial_payload(
    *, classification: str = CODE_AUTH, reasons: list[str] | None = None,
    transport_ok: bool = False, receipt_written: bool = False,
    receipt_path: str | None = None, receipt_sha256: str | None = None,
) -> dict[str, Any]:
    """Versioned output; transport/receipt success NEVER means admission."""
    return {
        "schema": CLI_SCHEMA, "decision": CLI_DENIED,
        "transport_ok": transport_ok, "receipt_written": receipt_written,
        "receipt_path": receipt_path, "receipt_sha256": receipt_sha256,
        "classification": classification,
        "original523": e15.REJECT_523, "ar09_phase_b": e15.REJECT_B,
        "official_cited_gate_pass": False,
        "may_execute_official_evaluation": False,
        "denial_reasons": sorted(set(reasons or [CODE_AUTH])),
    }


def _denial_receipt_shape(value: object) -> bool:
    """Check the whole ingress-only envelope, including nested E15 denials.

    This is a DENIAL validation helper, explicitly not an admission verifier.
    Future independently authorized product acceptance requires another trust
    domain; no shape, boolean or self-attested registry here grants it.
    """
    if not isinstance(value, dict):
        return False
    if not (
        value.get("cli_schema") == CLI_SCHEMA
        and value.get("decision") == CLI_DENIED
        and value.get("transport_ok") is True
        and value.get("receipt_written") is True
        and value.get("classification") in (CODE_ABSENT, CODE_AUTH)
        and value.get("original523") == e15.REJECT_523
        and value.get("ar09_phase_b") == e15.REJECT_B
        and value.get("official_cited_gate_pass") is False
        and value.get("may_execute_official_evaluation") is False
    ):
        return False
    reasons = value.get("denial_reasons")
    if not isinstance(reasons, list) or not reasons or not all(
        isinstance(v, str) and _safe_denial_code(v) == v for v in reasons
    ):
        return False
    content = value.get("verified_content_sha256")
    if not isinstance(content, dict) or not all(
        isinstance(k, str) and k in REQUIRED + OPTIONAL and _sha(v)
        for k, v in content.items()
    ):
        return False
    nested = value.get("e15")
    if not isinstance(nested, dict) or not set(nested).issubset(
        {"original523", "phase_b"}
    ):
        return False
    for name, entry in nested.items():
        if not isinstance(entry, dict) or (
            entry.get("may_execute_official_evaluation") is not False
            or entry.get("official_cited_gate_pass") is not False
            or not isinstance(entry.get("status"), str)
        ):
            return False
        if name == "phase_b" and entry["status"] not in (
            e15.REJECT_B, "AR09_PHASE_B_METADATA_ACCEPTED_FOR_INDEPENDENT_REVIEW"
        ):
            return False
        if name == "original523" and entry["status"] not in (
            e15.REJECT_523, "ORIGINAL523_METADATA_ACCEPTED_FOR_INDEPENDENT_REVIEW"
        ):
            return False
    return True


def validate_denial_receipt(
    path: str | Path, expected_sha256: str
) -> bool:
    """Bind a P17 *denied* receipt to exact bytes. True is NEVER an allow."""
    if not _sha(expected_sha256):
        return False
    try:
        target = Path(path)
        if not target.is_absolute() or target.is_symlink():
            return False
        raw = target.read_bytes()
        return (
            len(raw) <= 131072
            and hashlib.sha256(raw).hexdigest() == expected_sha256
            and _denial_receipt_shape(_json(raw))
        )
    except (OSError, Denied, ValueError, TypeError):
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only external evidence intake")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("inspect")
    cmd.add_argument("--ingress-root", required=True)
    cmd.add_argument("--manifest", required=True, help="relative to ingress root")
    cmd.add_argument("--scratch", required=True, help="outside tracked worktree")
    args = parser.parse_args(argv)
    try:
        receipt = inspect(args.ingress_root, args.manifest)
    except Denied as exc:
        print(json.dumps(_cli_denial_payload(reasons=[
            _safe_denial_code(exc.code)
        ]), sort_keys=True))
        return EXIT_INPUT_DENIED
    except (OSError, ValueError, TypeError):
        print(json.dumps(_cli_denial_payload(reasons=[
            "INGRESS_IO_OR_TYPE_DENIED"
        ]), sort_keys=True))
        return EXIT_INPUT_DENIED

    # The P16 producer always returns an ingress-only classification. Neither
    # readable bytes nor nested E15 metadata can grant official authority.
    # Preserve old P16 receipt keys for compatibility; add explicit P17 denial.
    receipt = dict(receipt)
    # A forged producer that asserts approval must be rejected, not silently
    # repaired into a superficially valid denial receipt.
    if (
        receipt.get("official_cited_gate_pass") is not False
        or receipt.get("may_execute_official_evaluation") is not False
        or not isinstance(receipt.get("denial_reasons"), list)
    ):
        print(json.dumps(_cli_denial_payload(
            reasons=["FORGED_PRODUCER_ADMISSION_DENIED"], transport_ok=True,
        ), sort_keys=True))
        return EXIT_INPUT_DENIED
    receipt["cli_schema"] = CLI_SCHEMA
    receipt["decision"] = CLI_DENIED
    receipt["transport_ok"] = True
    receipt["receipt_written"] = True
    receipt["official_cited_gate_pass"] = False
    receipt["may_execute_official_evaluation"] = False
    if not receipt.get("denial_reasons"):
        receipt["denial_reasons"] = ["INDEPENDENT_EXTERNAL_ADMISSION_REQUIRED"]
    if not _denial_receipt_shape(receipt):
        print(json.dumps(_cli_denial_payload(
            reasons=["UNSAFE_INGRESS_RESULT_DENIED"], transport_ok=True,
        ), sort_keys=True))
        return EXIT_INPUT_DENIED
    try:
        output = write_receipt(args.scratch, receipt)
        raw_sha = hashlib.sha256(output.read_bytes()).hexdigest()
        if not validate_denial_receipt(output, raw_sha):
            print(json.dumps(_cli_denial_payload(
                reasons=["RECEIPT_INTEGRITY_DENIED"], transport_ok=True,
            ), sort_keys=True))
            return EXIT_RECEIPT_DENIED
    except (Denied, OSError, ValueError, TypeError) as exc:
        code = exc.code if isinstance(exc, Denied) else "RECEIPT_IO_DENIED"
        print(json.dumps(_cli_denial_payload(
            reasons=[_safe_denial_code(code)], transport_ok=True,
        ), sort_keys=True))
        return EXIT_RECEIPT_DENIED
    out = _cli_denial_payload(
        classification=receipt["classification"],
        reasons=receipt["denial_reasons"], transport_ok=True,
        receipt_written=True, receipt_path=str(output),
        receipt_sha256=raw_sha,
    )
    print(json.dumps(out, sort_keys=True))
    return EXIT_AUTHORITY_DENIED


if __name__ == "__main__":
    raise SystemExit(main())
