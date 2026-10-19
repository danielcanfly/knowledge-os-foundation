"""C1 exact Gitless source proof verifier. NOT an independent release signer.

An external independently controlled source root MUST be pinned by an approved
current Product release BEFORE this module can qualify a Gitless bundle.
No self-generated keys, unsigned manifests, caller-provided digest overrides,
copying .git, source privilege bypass or Product PASS.
"""
from __future__ import annotations
import base64
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
import time
import json

ABI = "m27.c1.gitless-external-source-proof/v1"
C1_GITLESS_TRUST_ROOT_SHA256 = None  # Separate authentic Source Controller/Signer required.
MAX_FILES = 80
MAX_BYTES = 4_000_000


class GitlessDenied(ValueError):
    pass


def require(x, msg):
    if not x:
        raise GitlessDenied(msg)


def canonical(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def is_hex(value, length):
    return type(value) is str and re.fullmatch("[a-f0-9]{"+str(length)+"}",value) is not None


def inspect_exact_bundle(root: Path, payload: dict, *, expected_head: str,
                         expected_tree: str) -> dict:
    """Pre-signature structural inspection only. Positive != source admission."""
    root = Path(root).resolve(strict=True)
    require(type(payload) is dict and
            set(payload)=={"schema","head","tree","source_controller","expires_at",
                           "files","tenant","source_release_id"}, "GITLESS_MANIFEST_SCHEMA_DENIED")
    require(payload["schema"] == ABI and is_hex(payload["head"],40)
            and is_hex(payload["tree"],40) and
            payload["head"]==expected_head and payload["tree"]==expected_tree,
            "GITLESS_GIT_IDENTITY_MISMATCH")
    require(type(payload["tenant"]) is str and payload["tenant"]=="owner-internal"
            and type(payload["source_release_id"]) is str
            and payload["source_release_id"].startswith("a05context-")
            and type(payload["source_controller"]) is str
            and 3 <= len(payload["source_controller"]) <= 128,
            "GITLESS_SOURCE_SCOPE_DENIED")
    require(type(payload["expires_at"]) is int and
            time.time() < payload["expires_at"] <= time.time() + 86400,
            "GITLESS_SOURCE_PROOF_EXPIRED_OR_UNBOUNDED")
    files=payload["files"]
    require(type(files) is list and 1<=len(files)<=MAX_FILES,
            "GITLESS_FILES_COUNT_DENIED")
    declared=set()
    observations=[]
    total=0
    for entry in files:
        require(type(entry) is dict and
                set(entry)=={"path","sha256","git_blob_oid","git_mode"},
                "GITLESS_ENTRY_SHAPE_DENIED")
        name=entry["path"]
        require(type(name) is str and name and len(name)<=255
                and "\\" not in name and not name.startswith("/")
                and not name.startswith(".") and
                name == PurePosixPath(name).as_posix()
                and all(p not in (".","..","") for p in name.split("/"))
                and not any(segment in (".git",".env","__pycache__",
                   ".pytest_cache","gold","Gold","pilot","benchmarks") for segment in name.split("/")),
                "GITLESS_FORBIDDEN_SOURCE_PATH")
        require(name not in declared and entry["git_mode"] in ("100644","100755")
                and is_hex(entry["sha256"],64)
                and is_hex(entry["git_blob_oid"],40),
                "GITLESS_DUPLICATE_OR_INVALID_BLOB_PIN")
        declared.add(name)
        path=root/name
        try:
            st=path.lstat()
        except OSError as exc:
            raise GitlessDenied("GITLESS_MISSING_SOURCE_FILE") from exc
        require(stat.S_ISREG(st.st_mode) and not path.is_symlink()
                and st.st_nlink == 1 and st.st_size <= MAX_BYTES
                and bool(st.st_mode & stat.S_IXUSR)==(entry["git_mode"]=="100755"),
                "GITLESS_SOURCE_MODE_OR_SYMLINK_DENIED")
        total+=st.st_size
        require(total<=MAX_BYTES,"GITLESS_SOURCE_SIZE_BUDGET")
        raw=path.read_bytes()
        require(len(raw)==st.st_size and digest(raw)==entry["sha256"],
                "GITLESS_SOURCE_SHA256_MISMATCH")
        oid=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
        require(oid==entry["git_blob_oid"],"GITLESS_GIT_BLOB_OID_MISMATCH")
        observations.append({"path":name,"sha256":digest(raw),
                             "git_blob_oid":oid,"git_mode":entry["git_mode"]})
    # Reject all files not declared, hidden files, symlinks and git metadata.
    actual=set()
    for base, dirs, paths in os.walk(root, followlinks=False):
        for d in dirs:
            current=Path(base)/d
            require(not current.is_symlink() and
                    current.name not in (".git",".env","__pycache__", ".pytest_cache",
                                          "gold","Gold","pilot","benchmarks"),
                    "GITLESS_UNAUTHORIZED_SOURCE_DIR")
        for file in paths:
            fp=Path(base)/file
            require(not fp.is_symlink(), "GITLESS_UNAUTHORIZED_SYMLINK")
            actual.add(fp.relative_to(root).as_posix())
    require(actual==declared,"GITLESS_EXTRA_OR_MISSING_SOURCE_BYTES")
    return {"status":"EXACT_GIT_BLOB_SET_INSPECTED_UNSIGNED_ONLY",
            "files_verified":len(observations),"sha256":digest(canonical(observations)),
            "signed_source_admitted":False,"git_metadata_absent":True}


def verify_signed_gitless_bundle(root: Path, signed: dict, *, expected_head: str,
                                 expected_tree: str, public_key_path: Path) -> dict:
    """Never accept caller-supplied root pin. A separately released pinned trust
    root is required. The current accepted branch intentionally has NONE."""
    require(is_hex(C1_GITLESS_TRUST_ROOT_SHA256,64),
            "EXTERNAL_SOURCE_CONTROLLER_TRUST_ROOT_NOT_ADMITTED")
    require(type(signed) is dict and set(signed)=={"payload","signature_b64"},
            "EXTERNAL_GITLESS_SIGNATURE_SHAPE_DENIED")
    key_path=Path(public_key_path)
    st=key_path.lstat()
    require(stat.S_ISREG(st.st_mode) and not key_path.is_symlink() and
            st.st_size<=4096 and st.st_uid==os.geteuid(),
            "EXTERNAL_PUBLIC_ROOT_FILE_DENIED")
    pem=key_path.read_bytes()
    require(digest(pem)==C1_GITLESS_TRUST_ROOT_SHA256,
            "GITLESS_PUBLIC_TRUST_ROOT_PIN_MISMATCH")
    # Verify independent signed bytes before inspecting source content.
    try:
        signature=base64.b64decode(signed["signature_b64"],validate=True)
    except (ValueError,TypeError) as exc:
        raise GitlessDenied("EXTERNAL_SOURCE_SIGNATURE_INVALID") from exc
    require(len(signature)==64,"EXTERNAL_SOURCE_SIGNATURE_INVALID")
    with tempfile.TemporaryDirectory(prefix="c1-gitless-external-verify-") as td:
        temp=Path(td)
        (temp/"public.pem").write_bytes(pem)
        (temp/"payload").write_bytes(canonical(signed["payload"]))
        (temp/"signature").write_bytes(signature)
        p=subprocess.run(["openssl","pkeyutl","-verify","-pubin","-rawin",
                    "-inkey",str(temp/"public.pem"),"-in",str(temp/"payload"),
                    "-sigfile",str(temp/"signature")],capture_output=True,
                    timeout=5,check=False)
        require(p.returncode==0,"EXTERNAL_SOURCE_SIGNATURE_CRYPTO_DENIED")
    attested=inspect_exact_bundle(root,signed["payload"],
                           expected_head=expected_head,expected_tree=expected_tree)
    return {**attested,"status":"SIGNED_GITLESS_SOURCE_VERIFIED",
            "signed_source_admitted":True,
            "source_controller":signed["payload"]["source_controller"]}
