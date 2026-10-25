"""F04-C1-02 public-only external authority consumer for a NEW nonprod C1.

An Ed25519 signature proves possession of a key, NOT a real-world appointment.
The Release Controller's authentic independently approved public-root SHA must
be baked into a separately reviewed source release. It is intentionally None.
Test-fixture verification is unadmitted, never a model-call or Product permit.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time

import m27_c1_gitless_source_proof as gitless
import m27_f03_source_rights_admission as f03

ABI = "m27.c1.f04-external-public-consumer/v1"
RELEASE_CONTROLLER_ROOT_SHA256 = None  # NOT approved. Never runtime supplied.
ROLES = ("provider_controller", "source_controller", "semantic_issuer", "client_idp")
CLAIMS = ("execution_governance_verification", "policy_engine_enforcement")
A05_DOCS = {
    "00_m27_architecture_overview.md":
        "044c03b3d8ad38ac0a22a734a2469629c132499cce5c43d49138d703a5ffca1d",
    "01_contracts.md":
        "6f98ef617f1c1957ccec627aeae0381f9db48dbd763503a818732bbeb1476a02",
}
CORPUS = "7835ec95cee639722f89a0520336283f7e226358ad7be003a2a906635d1200e3"


class Denied(ValueError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise Denied(reason)


def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def hex_digest(v, n=64) -> bool:
    return type(v) is str and re.fullmatch(r"[0-9a-f]{%d}" % n, v) is not None


def _mapping(v, keys, reason):
    require(type(v) is dict and set(v) == set(keys), reason)
    return v


def _window(p, now: int, *, ttl: int = 300):
    issued, expiry = p.get("issued_at"), p.get("expires_at")
    require(type(issued) is int and type(expiry) is int and
            type(now) is int and 0 < issued <= now < expiry <= issued + ttl and
            now - issued <= ttl, "F04_TIME_WINDOW_EXPIRED_OR_UNBOUNDED")


def _verify_signed(key: bytes, signed: dict) -> dict:
    _mapping(signed, ("payload", "signature_b64"), "F04_ENVELOPE_INVALID")
    payload, b64 = signed["payload"], signed["signature_b64"]
    require(type(payload) is dict and type(b64) is str and
            80 <= len(b64) <= 100 and
            key.startswith(b"-----BEGIN PUBLIC KEY-----") and len(key) <= 4096,
            "F04_PUBLIC_SIGNATURE_INVALID")
    try:
        raw = base64.b64decode(b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise Denied("F04_PUBLIC_SIGNATURE_ENCODING") from exc
    require(len(raw) == 64, "F04_SIGNATURE_LENGTH_INVALID")
    with tempfile.TemporaryDirectory(prefix="f04-c1-public-only-") as temp:
        base = Path(temp)
        (base / "key.pem").write_bytes(key)
        (base / "payload").write_bytes(canonical(payload))
        (base / "signature").write_bytes(raw)
        try:
            run = subprocess.run(
                ["openssl", "pkeyutl", "-verify", "-pubin",
                 "-inkey", str(base / "key.pem"), "-rawin",
                 "-in", str(base / "payload"),
                 "-sigfile", str(base / "signature")],
                capture_output=True, check=False, timeout=5)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise Denied("F04_CRYPTO_VERIFIER_UNAVAILABLE") from exc
        require(run.returncode == 0, "F04_PUBLIC_SIGNATURE_MISMATCH")
    return payload


def verify_release_structure(evidence: dict, *, pinned_root_sha256: str,
                             expected_head: str, expected_tree: str,
                             now: int) -> dict:
    """Pure public cryptographic verification, NEVER a Product authorization.

    Only the runtime entrypoint may supply the compiled approved root pin.
    Test fixtures calling this with an ephemeral pin remain UNADMITTED.
    """
    require(hex_digest(pinned_root_sha256), "F04_NO_APPROVED_RELEASE_ROOT")
    _mapping(evidence, ("release_root_pem", "release_signed",
                       "revocations_signed", "rights_signed",
                       "gitless_signed", "gitless_source_directory"),
             "F04_EVIDENCE_FIELDS_INVALID")
    pem_string = evidence["release_root_pem"]
    require(type(pem_string) is str, "F04_RELEASE_ROOT_INVALID")
    pem = pem_string.encode("ascii")
    require(digest(pem) == pinned_root_sha256, "F04_RELEASE_ROOT_PIN_MISMATCH")
    release = _verify_signed(pem, evidence["release_signed"])
    _mapping(release, ("schema", "head", "tree", "source_manifest_sha256",
                      "source_release_id", "tenant", "roles",
                      "release_principal", "release_custodian",
                      "revocation_epoch", "issued_at", "expires_at"),
             "F04_RELEASE_SCHEMA_INVALID")
    _window(release, now)
    require(release["schema"] == "m27.external-independent-trust/v1" and
            release["head"] == expected_head and release["tree"] == expected_tree and
            hex_digest(expected_head, 40) and hex_digest(expected_tree, 40) and
            release["source_manifest_sha256"] == CORPUS and
            release["source_release_id"] == f03.A05_RELEASE_ID and
            release["tenant"] == "owner-internal" and
            type(release["revocation_epoch"]) is int and
            release["revocation_epoch"] >= 1 and
            type(release["release_principal"]) is str and
            type(release["release_custodian"]) is str,
            "F04_RELEASE_SOURCE_OR_ROOT_SCOPE_INVALID")
    roles = release["roles"]
    _mapping(roles, ROLES, "F04_RELEASE_ROLE_SET_INVALID")
    principals, custodians, public_roots = [], [], []
    for role in ROLES:
        item = _mapping(roles[role],
            ("principal", "custodian", "public_key_pem", "scope"),
            "F04_ROLE_DESCRIPTOR_INVALID")
        require(type(item["principal"]) is str and
                type(item["custodian"]) is str and
                3 <= len(item["principal"]) <= 128 and
                3 <= len(item["custodian"]) <= 128 and
                type(item["public_key_pem"]) is str and
                len(item["public_key_pem"]) < 4096 and
                item["scope"] == "NONPROD_EXACT_C1_TASK_ONLY",
                "F04_ROLE_SCOPE_INVALID")
        principals.append(item["principal"])
        custodians.append(item["custodian"])
        public_roots.append(digest(item["public_key_pem"].encode("ascii")))
    require(len(set(principals)) == 4 and len(set(custodians)) == 4 and
            len(set(public_roots)) == 4 and
            release["release_principal"] not in principals and
            release["release_custodian"] not in custodians and
            digest(pem) not in public_roots,
            "F04_FIVE_ROLE_SEPARATION_NOT_MET")
    revocation = _verify_signed(pem, evidence["revocations_signed"])
    _mapping(revocation, ("schema", "release_sha256", "epoch",
                          "revoked_principals", "issued_at", "expires_at"),
             "F04_REVOCATION_SCHEMA_INVALID")
    _window(revocation, now)
    require(revocation["schema"] == "m27.external-trust-revocations/v1" and
            revocation["release_sha256"] == digest(canonical(release)) and
            revocation["epoch"] == release["revocation_epoch"] and
            type(revocation["revoked_principals"]) is list and
            not any(x in revocation["revoked_principals"]
                    for x in principals + [release["release_principal"]]),
            "F04_REVOKED_OR_DRIFTED_RELEASE")
    return {"release": release, "revocation": revocation, "roles": roles,
            "public_signature_valid": True,
            "formal_product_pass": False,
            "qualification": "PUBLIC_CRYPTOGRAPHIC_STRUCTURE_ONLY_NOT_REAL_AUTHORITY"}


def _role_payload(evidence, inspected, role: str, signed: dict,
                  fields: dict, *, now: int) -> dict:
    descriptor = inspected["roles"][role]
    p = _verify_signed(descriptor["public_key_pem"].encode("ascii"), signed)
    _mapping(p, (*fields, "role", "issuer", "nonce", "issued_at", "expires_at"),
             "F04_ROLE_GRANT_SHAPE_INVALID")
    _window(p, now)
    require(p["role"] == role and p["issuer"] == descriptor["principal"] and
            all(p[k] == v for k, v in fields.items()) and
            hex_digest(p["nonce"], 48),
            "F04_GRANT_ROLE_NONCE_OR_CONTEXT_MISMATCH")
    return p


def verify_source_rights(evidence: dict, inspected: dict, *,
                         task: dict, now: int) -> dict:
    rights_fields = {
        "task_sha256": task["task_sha256"],
        "request_id": task["request_id"],
        "source_sha256": CORPUS,
        "source_proof_sha256": task["source_proof_sha256"],
        "tenant": "owner-internal",
        "source_release_id": f03.A05_RELEASE_ID,
        "head": inspected["release"]["head"],
        "tree": inspected["release"]["tree"],
        "documents": A05_DOCS,
    }
    payload = _verify_signed(
        inspected["roles"]["source_controller"]["public_key_pem"].encode("ascii"),
        evidence["rights_signed"])
    _mapping(payload, (*rights_fields, "role", "issuer", "nonce",
                       "issued_at", "expires_at", "region", "retention_seconds",
                       "serving_ttl_seconds", "revocation_uri", "acl",
                       "gitless_manifest_sha256", "source_rights_epoch"),
             "F04_A05_RIGHTS_SCHEMA_INVALID")
    _window(payload, now)
    require(payload["role"] == "source_controller" and
            payload["issuer"] == inspected["roles"]["source_controller"]["principal"] and
            all(payload[k] == v for k, v in rights_fields.items()) and
            payload["nonce"] == task["nonce"] and
            payload["source_rights_epoch"] == task["rights_epoch"] and
            type(payload["region"]) is str and 2 <= len(payload["region"]) <= 64 and
            type(payload["retention_seconds"]) is int and
            0 <= payload["retention_seconds"] <= 86400 and
            type(payload["serving_ttl_seconds"]) is int and
            0 < payload["serving_ttl_seconds"] <= 300 and
            type(payload["revocation_uri"]) is str and
            payload["revocation_uri"].startswith("https://") and
            payload["acl"] == {"tenant": "owner-internal", "read": ["internal"]},
            "F04_A05_ONLINE_SERVING_RIGHTS_NOT_GRANTED")
    signed_gitless = evidence["gitless_signed"]
    gitless_payload = _verify_signed(
        inspected["roles"]["source_controller"]["public_key_pem"].encode("ascii"),
        signed_gitless)
    require(digest(canonical(gitless_payload)) == payload["gitless_manifest_sha256"],
            "F04_GITLESS_RIGHTS_MANIFEST_MISMATCH")
    require(type(gitless_payload) is dict and
            type(gitless_payload.get("files")) is list and
            len(gitless_payload["files"]) == 14 and
            {x.get("path") for x in gitless_payload["files"]
             if type(x) is dict} == set(f03.F03_GITLESS_ALLOWED_A05) and
            gitless_payload.get("source_controller") == payload["issuer"],
            "F04_GITLESS_NOT_EXACT_A05_FOURTEEN")
    by_path = {row["path"]: row["sha256"]
               for row in gitless_payload["files"] if type(row) is dict
               and "path" in row and "sha256" in row}
    require(all(by_path.get(f03.A05_SOURCE + "/" + name) == sha
                for name, sha in A05_DOCS.items()) and
            by_path.get(f03.A05_SOURCE + "/corpus.json") == CORPUS,
            "F04_GITLESS_TWO_DOC_CORPUS_PIN_MISMATCH")
    # Signed SOURCE claim is only meaningful if all 14 physical SHA/OID/mode
    # checks run. Historical unsigned request or a file inventory is not enough.
    result = gitless.inspect_exact_bundle(
        Path(evidence["gitless_source_directory"]),
        gitless_payload, expected_head=inspected["release"]["head"],
        expected_tree=inspected["release"]["tree"])
    require(result["files_verified"] == 14 and
            result["signed_source_admitted"] is False,
            "F04_GITLESS_PHYSICAL_EVIDENCE_INVALID")
    return {"rights_payload_sha256": digest(canonical(payload)),
            "gitless_payload_sha256": digest(canonical(gitless_payload)),
            "verified_physical_files": 14, "signed_signature_verified": True,
            "scope": "NONPROD_RIGHTS_CRYPTOGRAPHIC_CONSUMER_ONLY",
            "product_pass": False}


def verify_task_receipts(inspected: dict, receipts: list, *, task: dict,
                         now: int) -> dict:
    """Seven same-task public receipts. Journal is independently checked later."""
    require(type(receipts) is list and len(receipts) == 7,
            "F04_SEVEN_RECEIPTS_REQUIRED")
    expected = (
        ("provider_controller", "start", ""),
        ("source_controller", "rights", ""),
        ("semantic_issuer", "claim", CLAIMS[0]),
        ("client_idp", "ack", CLAIMS[0]),
        ("semantic_issuer", "claim", CLAIMS[1]),
        ("client_idp", "ack", CLAIMS[1]),
        ("client_idp", "terminal", ""),
    )
    witnessed = []
    for envelope, (role, event, claim) in zip(receipts, expected):
        key = inspected["roles"][role]["public_key_pem"].encode("ascii")
        p = _verify_signed(key, envelope)
        _mapping(p, ("role", "issuer", "event", "claim_id", "task_sha256",
                     "request_id", "nonce", "source_sha256", "source_proof_sha256",
                     "issued_at", "expires_at", "text_sha256", "citation_document",
                     "challenge_sha256", "server_pid", "client_pid",
                     "delivered_ns", "ack_ns", "provider_done_ns"),
                 "F04_RECEIPT_ABI_INVALID")
        _window(p, now)
        require(p["role"] == role and
                p["issuer"] == inspected["roles"][role]["principal"] and
                p["event"] == event and p["claim_id"] == claim and
                p["task_sha256"] == task["task_sha256"] and
                p["request_id"] == task["request_id"] and
                p["nonce"] == task["nonce"] and
                p["source_sha256"] == CORPUS and
                p["source_proof_sha256"] == task["source_proof_sha256"],
                "F04_RECEIPT_TASK_ROLE_REPLAY_OR_SWAP")
        if event in ("claim", "ack"):
            require(hex_digest(p["text_sha256"]) and
                    p["citation_document"] in A05_DOCS and
                    p["citation_document"] == (
                        "00_m27_architecture_overview.md" if claim == CLAIMS[0]
                        else "01_contracts.md"),
                    "F04_CLAIM_CITATION_OR_TEXT_UNBOUND")
        if event == "ack":
            require(hex_digest(p["challenge_sha256"]) and
                    type(p["server_pid"]) is int and type(p["client_pid"]) is int and
                    p["server_pid"] > 0 and p["client_pid"] > 0 and
                    p["server_pid"] != p["client_pid"] and
                    type(p["delivered_ns"]) is int and
                    type(p["ack_ns"]) is int and
                    type(p["provider_done_ns"]) is int and
                    0 < p["delivered_ns"] < p["ack_ns"] <
                    p["provider_done_ns"],
                    "F04_CROSS_PROCESS_ACK_NOT_PRETERMINAL")
        witnessed.append(p)
    for semantic, ack in ((witnessed[2], witnessed[3]),
                          (witnessed[4], witnessed[5])):
        require(all(semantic[k] == ack[k] for k in (
            "claim_id", "text_sha256", "citation_document")),
                "F04_SEMANTIC_AND_CLIENT_TEXT_NOT_IDENTICAL")
    require(witnessed[3]["ack_ns"] < witnessed[5]["ack_ns"] and
            witnessed[3]["provider_done_ns"] == witnessed[5]["provider_done_ns"],
            "F04_TWO_ACK_SEQUENCE_OR_PROVIDER_DONE_DRIFT")
    return {"cryptographically_verified_receipts": 7,
            "two_preterminal_ack_fields_checked": True,
            "actual_os_delivery_independently_observed": False,
            "product_pass": False,
            "qualification": "RECEIPT_AND_LEDGER_CONSISTENCY_NOT_LIVE_E2E"}


def _read_private_json(path: Path) -> dict:
    path = Path(path)
    st = path.lstat()
    require(stat.S_ISREG(st.st_mode) and not path.is_symlink() and
            st.st_nlink == 1 and st.st_uid == os.geteuid() and
            stat.S_IMODE(st.st_mode) == 0o600 and
            0 < st.st_size <= 180000, "F04_EVIDENCE_PRIVATE_FILE_REQUIRED")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(fd)
        raw = os.read(fd, 180001)
        after = os.fstat(fd)
        require(before.st_ino == st.st_ino and
                (before.st_ino, before.st_size, before.st_mtime_ns) ==
                (after.st_ino, after.st_size, after.st_mtime_ns) and
                len(raw) == st.st_size, "F04_EVIDENCE_MUTATED_DURING_READ")
    finally:
        os.close(fd)
    try:
        return json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise Denied("F04_EVIDENCE_JSON_INVALID") from exc


def require_live_launch(evidence_path: Path | None, *, task: dict,
                        expected_head: str, expected_tree: str) -> dict:
    """Only launch entry: hard fail without genuine source-pinned approval."""
    require(hex_digest(RELEASE_CONTROLLER_ROOT_SHA256),
            "F04_RELEASE_CONTROLLER_ROOT_NOT_APPROVED")
    require(hex_digest(gitless.C1_GITLESS_TRUST_ROOT_SHA256) and
            hex_digest(f03.F03_EXTERNAL_SOURCE_ROOT_SHA256),
            "F04_INDEPENDENT_SOURCE_ROOT_PINS_REQUIRED")
    require(evidence_path is not None, "F04_MISSING_SIGNED_EXTERNAL_EVIDENCE")
    evidence = _read_private_json(evidence_path)
    inspected = verify_release_structure(
        evidence, pinned_root_sha256=RELEASE_CONTROLLER_ROOT_SHA256,
        expected_head=expected_head, expected_tree=expected_tree,
        now=int(time.time()))
    source_pem = inspected["roles"]["source_controller"]["public_key_pem"].encode("ascii")
    require(digest(source_pem) == gitless.C1_GITLESS_TRUST_ROOT_SHA256 and
            digest(source_pem) == f03.F03_EXTERNAL_SOURCE_ROOT_SHA256,
            "F04_GITLESS_F03_SOURCE_AUTHORITY_ROOT_DIVERGENCE")
    verify_source_rights(evidence, inspected, task=task, now=int(time.time()))
    # NativeLiveProduct separately checks the genuinely signed provider,
    # Source, IdP grants and two Semantic/Client ACKs during live execution.
    return {"status": "F04_PUBLIC_ROOT_RIGHTS_PRELAUNCH_VERIFIED_ONLY",
            "actual_provider_call": False, "formal_product_pass": False,
            "source_sha256": CORPUS,
            "release_signature_verified": True}
