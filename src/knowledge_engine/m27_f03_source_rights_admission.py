"""F03: read-only first-party repository-source candidate admission.

No Product issuer, IdP, third-party license, cache HIT, provider or deployment.
An OS-local lease is evidence of bounded Nonprod access ONLY. Never accept it
as an independent rights grant. F03 does not modify H02/shared ABI.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
from typing import Any, Callable

BASE_H02 = "7966e9c766a38a22cd91432edb5dbf2115eff305"
ALLOWED_SOURCES = frozenset({
    "docs/m27/b3_h02_gateway_routing_successor_nonprod.md",
    "docs/m27/b1_cache03_rights_integration.md",
})
SCOPE = "OWNER_CHECKOUT_OS_LOCAL_NONPROD_ONLY"
CACHE_ENABLED = False
PRODUCT_ADMITTED = False
MAX_TTL_SECONDS = 3600
_HEX = re.compile(r"[0-9a-f]{64}\Z")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def denial(code: str) -> dict:
    return {
        "decision": "DENY_" + code, "scope": SCOPE,
        "product_authenticated": False, "product_admitted": False,
        "verified_final": False, "answer_cache_enabled": False,
        "answer_cache_hit": False, "answer_cache_write": False,
        "independent_issuer": False, "candidate_only": False,
    }


class Rejected(ValueError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise Rejected(message)


# Gitless F03 authority is a distinct externally signed SOURCE Controller lane.
# No locally generated key can serve as a trusted Product Source/IdP principal.
F03_GITLESS_ABI = "m27.f03.a05-gitless-external-immutable-source/v1"
F03_EXTERNAL_SOURCE_ROOT_SHA256 = None  # Actual independent custodian has not signed.
F03_GITLESS_ALLOWED_A05 = frozenset({
    "wave_b01/components/a05/adapter/a05_retrieval.py",
    "wave_b01/components/a05/source/corpus.json",
    "wave_b01/components/a05/source/release.json",
    *("wave_b01/components/a05/source/" + str(i).zfill(2) + "_" + name
      for i, name in enumerate((
          "m27_architecture_overview.md", "contracts.md", "request_flow.md",
          "context_planner.md", "context_compiler.md", "compute_policy.md",
          "tool_and_capability_registry.md", "skill_runtime.md",
          "workspace_and_memory.md", "governance_eval_release.md",
          "migration_plan.md")))
})
F03_GITLESS_ALLOWED_LOCAL = ALLOWED_SOURCES
F03_GITLESS_MAX_TOTAL_BYTES = 500_000


def _f03_git_blob_oid(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") +
                        b"\0" + raw).hexdigest()


def _f03_nofollow_bytes(root: Path, relative: str) -> bytes:
    check(type(relative) is str and relative and
          not relative.startswith("/") and
          all(part and part not in (".", "..") and
              not part.startswith(".") for part in relative.split("/")) and
          "\\" not in relative, "GITLESS_FORBIDDEN_RELATIVE_SOURCE")
    current = root
    for part in relative.split("/")[:-1]:
        current = current / part
        check(not current.is_symlink() and current.is_dir(),
              "GITLESS_SYMLINKED_SOURCE_PARENT")
    path = root / relative
    check(not path.is_symlink(), "GITLESS_SOURCE_SYMLINK")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            st = os.fstat(fd)
            import stat
            check(stat.S_ISREG(st.st_mode) and st.st_uid == os.geteuid() and
                  st.st_nlink == 1 and st.st_size <= 262144 and
                  not (st.st_mode & 0o022),
                  "GITLESS_BLOB_OS_OWNER_MODE_OR_SIZE")
            data = os.read(fd, 262145)
            after = os.fstat(fd)
            check(len(data) == st.st_size and
                  st.st_ino == after.st_ino and
                  st.st_mtime_ns == after.st_mtime_ns and
                  st.st_size == after.st_size,
                  "GITLESS_SOURCE_READ_RACE")
            return data
        finally:
            os.close(fd)
    except OSError as exc:
        raise Rejected("GITLESS_SOURCE_OS_UNAVAILABLE") from exc


def inspect_a05_gitless_bytes_unsigned(root: Path, payload: dict,
                                      *, expected_head: str,
                                      expected_tree: str,
                                      kind: str = "a05",
                                      expected_epoch: int | None = None) -> dict:
    """Real on-disk hash/OID inspection, NOT Controller/source-rights admission.

    Only immutable documents/release/adapter may be in the pinned manifest.
    Mutable revocations.json is deliberately excluded and must still pass the
    independent owner fence + epoch + two-time checks at read/delivery.
    """
    root = Path(root)
    check(not root.is_symlink(), "GITLESS_ROOT_SYMLINK")
    root = root.resolve(strict=True)
    check(not any((root / name).exists() or (root / name).is_symlink()
                  for name in (".git", ".env", "Gold", "gold", "pilot",
                               "benchmarks")),
          "GITLESS_PROTECTED_OR_GIT_BYTES_PRESENT")
    allow = F03_GITLESS_ALLOWED_A05 if kind == "a05" else F03_GITLESS_ALLOWED_LOCAL
    check(kind in ("a05", "local") and type(payload) is dict and
          set(payload) == {"schema", "kind", "head", "tree", "base_h02",
                           "a05_release_id", "a05_manifest_sha256", "a05_revision",
                           "source_controller", "tenant", "principal", "epoch",
                           "issued_at", "expires_at", "rights_scope", "files"},
          "GITLESS_SIGNED_SCOPE_SCHEMA")
    check(payload["schema"] == F03_GITLESS_ABI and
          payload["kind"] == kind and
          payload["head"] == expected_head and
          payload["tree"] == expected_tree and
          payload["base_h02"] == BASE_H02 and
          payload["a05_release_id"] == A05_RELEASE_ID and
          payload["a05_manifest_sha256"] == A05_SOURCE_PIN and
          payload["a05_revision"] == A05_REVISION and
          payload["tenant"] == "owner-internal" and
          payload["principal"] == "os-uid:" + str(os.geteuid()) and
          payload["rights_scope"] == (
              A05_LOCAL_SCOPE if kind == "a05" else SCOPE) and
          type(payload["source_controller"]) is str and
          len(payload["source_controller"]) >= 3 and
          type(payload["epoch"]) is int and payload["epoch"] >= 1 and
          (expected_epoch is None or payload["epoch"] == expected_epoch),
          "GITLESS_C1_A05_OR_RIGHTS_BINDING_DENIED")
    now = int(dt.datetime.now(dt.timezone.utc).timestamp())
    check(type(payload["issued_at"]) is int and
          type(payload["expires_at"]) is int and
          now - 300 <= payload["issued_at"] <= now and
          now < payload["expires_at"] <= payload["issued_at"] + 3600,
          "GITLESS_CONTROLLER_TTL_EXPIRED")
    entries = payload["files"]
    check(type(entries) is list and len(entries) == len(allow),
          "GITLESS_A05_INCOMPLETE_IMMUTABLE_SET")
    mapping = {}
    total = 0
    for entry in entries:
        check(type(entry) is dict and
              set(entry) == {"path", "sha256", "git_blob_oid", "git_mode"} and
              type(entry["path"]) is str and
              entry["path"] in allow and entry["path"] not in mapping and
              entry["git_mode"] == "100644" and
              type(entry["sha256"]) is str and
              _HEX.fullmatch(entry["sha256"]) is not None and
              type(entry["git_blob_oid"]) is str and
              re.fullmatch("[0-9a-f]{40}", entry["git_blob_oid"]) is not None,
              "GITLESS_A05_BLOB_ENTRY_DENIED")
        raw = _f03_nofollow_bytes(root, entry["path"])
        total += len(raw)
        check(total <= F03_GITLESS_MAX_TOTAL_BYTES,
              "GITLESS_A05_BYTES_BUDGET")
        check(sha(raw) == entry["sha256"] and
              _f03_git_blob_oid(raw) == entry["git_blob_oid"],
              "GITLESS_A05_REAL_SOURCE_SHA_OR_GIT_OID_DRIFT")
        mapping[entry["path"]] = entry
    check(set(mapping) == allow, "GITLESS_A05_UNLISTED_SOURCE")
    # The A05 published source directory may contain exactly the pinned
    # immutable material and the separate mutable revocations.json. Nothing
    # else (especially hidden metadata, symlink or protected fixtures).
    if kind == "a05":
        source_dir = root / A05_SOURCE
        check(source_dir.is_dir() and not source_dir.is_symlink(),
              "GITLESS_MISSING_A05_SOURCE_DIR")
        physical = set()
        for child in source_dir.iterdir():
            check(child.is_file() and not child.is_symlink() and
                  not child.name.startswith("."),
                  "GITLESS_UNDECLARED_OR_UNSAFE_A05_FILE")
            physical.add(A05_SOURCE + "/" + child.name)
        check(physical == {x for x in allow if x.startswith(A05_SOURCE + "/")} |
              {A05_SOURCE + "/revocations.json"},
              "GITLESS_EXTRA_OR_MISSING_A05_FILES")
        adapter_dir = root / "wave_b01/components/a05/adapter"
        check(adapter_dir.is_dir() and not adapter_dir.is_symlink() and
              {p.name for p in adapter_dir.iterdir()} == {"a05_retrieval.py"},
              "GITLESS_EXTRA_OR_MISSING_A05_ADAPTER")
    return {"decision": "UNSIGNED_REAL_GITLESS_BYTES_STRUCTURALLY_VERIFIED_ONLY",
            "verified_immutable_files": len(mapping),
            "inventory_sha256": sha(canonical(entries)),
            "source_authorized": False, "product_admitted": False}


class F03ExternalGitlessByteReader:
    """Independent Controller-verified restrictive A05 byte-reader (public verify ONLY).

    Source Controller must independently sign immutable blob inventory and
    current release, bound to exact C1 HEAD/TREE, OS principal and A05 epoch.
    The operator-supplied manifest/key is not an authority until a DISTINCT
    immutable public-root SHA is admitted in reviewed F03 release code.
    """
    def __init__(self, root: Path, *, signed_manifest: Path,
                 public_root: Path, expected_head: str, expected_tree: str,
                 expected_epoch: int, kind: str = "a05"):
        check(type(F03_EXTERNAL_SOURCE_ROOT_SHA256) is str and
              _HEX.fullmatch(F03_EXTERNAL_SOURCE_ROOT_SHA256) is not None,
              "SOURCE_CONTROLLER_READER_NOT_ADMITTED")
        import stat
        keypath = Path(public_root)
        key_stat = keypath.lstat()
        check(stat.S_ISREG(key_stat.st_mode) and not keypath.is_symlink() and
              key_stat.st_uid == os.geteuid() and key_stat.st_size <= 4096 and
              (key_stat.st_mode & 0o022) == 0,
              "GITLESS_EXTERNAL_PUBLIC_ROOT_UNTRUSTED")
        key = _f03_nofollow_bytes(keypath.parent.resolve(), keypath.name)
        check(sha(key) == F03_EXTERNAL_SOURCE_ROOT_SHA256,
              "GITLESS_EXTERNAL_CONTROLLER_ROOT_PIN_DRIFT")
        record = json.loads(_f03_nofollow_bytes(
            Path(signed_manifest).parent.resolve(), Path(signed_manifest).name))
        check(type(record) is dict and
              set(record) == {"payload", "signature_b64"},
              "GITLESS_EXTERNAL_SIGNATURE_ENVELOPE")
        import base64
        try:
            signature = base64.b64decode(record["signature_b64"], validate=True)
        except (ValueError, TypeError) as exc:
            raise Rejected("GITLESS_CONTROLLER_SIGNATURE_ENCODING") from exc
        check(len(signature) == 64, "GITLESS_CONTROLLER_SIGNATURE_LENGTH")
        with __import__("tempfile").TemporaryDirectory(prefix="f03-gitless-public-only-") as td:
            temp = Path(td)
            (temp / "root.pem").write_bytes(key)
            (temp / "payload").write_bytes(canonical(record["payload"]))
            (temp / "sig").write_bytes(signature)
            result = subprocess.run(
                ["openssl", "pkeyutl", "-verify", "-pubin", "-rawin",
                 "-inkey", str(temp / "root.pem"),
                 "-in", str(temp / "payload"), "-sigfile", str(temp / "sig")],
                capture_output=True, check=False, timeout=5)
        check(result.returncode == 0, "GITLESS_CONTROLLER_SIGNATURE_INVALID")
        check(not Path(root).is_symlink(), "GITLESS_SOURCE_ROOT_SYMLINK")
        self.root = Path(root).resolve(strict=True)
        self.kind = kind
        self.payload = record["payload"]
        self.identity = (expected_head, expected_tree)
        self.epoch = expected_epoch
        check(self.payload.get("epoch") == expected_epoch,
              "GITLESS_CONTROLLER_EPOCH_MISMATCH")
        inspect_a05_gitless_bytes_unsigned(
            self.root, self.payload,
            expected_head=expected_head, expected_tree=expected_tree,
            kind=kind, expected_epoch=expected_epoch)
        self.allowed = {e["path"]: e for e in self.payload["files"]}

    def read_pinned(self, relative: str, *, current_epoch: int) -> bytes:
        check(current_epoch == self.epoch and
              type(relative) is str and relative in self.allowed,
              "SOURCE_CONTROLLER_EPOCH_OR_SCOPE_REVOKED")
        now = int(dt.datetime.now(dt.timezone.utc).timestamp())
        check(now < self.payload["expires_at"],
              "SOURCE_CONTROLLER_READER_LEASE_EXPIRED")
        raw = _f03_nofollow_bytes(self.root, relative)
        pinned = self.allowed[relative]
        check(sha(raw) == pinned["sha256"] and
              _f03_git_blob_oid(raw) == pinned["git_blob_oid"],
              "GITLESS_AUTHENTICATED_BLOB_CHANGED")
        return raw


class LocalFirstPartySourceReader:
    """Standalone candidate; caller's identity is not an IdP credential.

    Registry and fence MUST be supplied from outside this module, not
    constructed based on client input. Missing paths always deny. Local proof
    is incapable of upgrading to product admission.
    """

    def __init__(self, repo: Path, registry: Path | None = None,
                 revocation_fence: Path | None = None,
                 gitless_reader: F03ExternalGitlessByteReader | None = None):
        self.repo = Path(repo).resolve(strict=True)
        self.registry = Path(registry) if registry else None
        self.fence = Path(revocation_fence) if revocation_fence else None
        self.uid = os.geteuid()
        check(gitless_reader is None or (
              isinstance(gitless_reader, F03ExternalGitlessByteReader)
              and gitless_reader.kind == "local" and
              gitless_reader.root == self.repo),
              "SOURCE_CONTROLLER_READER_NOT_ADMITTED")
        self.gitless_reader = gitless_reader

    def _read_private_json(self, path: Path | None) -> tuple[dict, str]:
        check(path is not None, "MISSING_LOCAL_RIGHTS_REGISTRY")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            st = os.fstat(fd)
            check(st.st_uid == self.uid and st.st_mode & 0o077 == 0,
                  "UNTRUSTED_REGISTRY_PERMISSIONS")
            check(st.st_size < 65536, "OVERSIZED_REGISTRY")
            raw = os.read(fd, 65537)
            value = json.loads(raw)
            check(type(value) is dict, "INVALID_REGISTRY")
            return value, sha(raw)
        finally:
            os.close(fd)

    def _snapshot(self, *, tenant: str, principal: str,
                  source_id: str, now: int) -> tuple[dict, str, int]:
        check(type(tenant) is str and type(principal) is str,
              "IDENTITY_REQUIRED")
        lease, lease_digest = self._read_private_json(self.registry)
        fence, _ = self._read_private_json(self.fence)
        check(set(lease) == {
            "scope", "tenant", "principal", "source_id", "source_sha256",
            "revision", "epoch", "expires_at", "retention_seconds",
            "status", "rights_class"
        }, "INVALID_LEASE_SHAPE")
        check(set(fence) == {"source_id", "minimum_epoch"},
              "INVALID_FENCE_SHAPE")
        check(lease["scope"] == SCOPE and lease["rights_class"] == "owner-local-repo-read",
              "UNLICENSED_OR_PRODUCT_SCOPE")
        check(tenant == lease["tenant"] and principal == lease["principal"],
              "TENANT_PRINCIPAL")
        check(principal == "os-uid:" + str(self.uid),
              "UNBOUND_OS_PRINCIPAL")
        check(source_id == lease["source_id"] == fence["source_id"],
              "SOURCE_SCOPE")
        check(type(lease["epoch"]) is int and type(fence["minimum_epoch"]) is int
              and lease["epoch"] >= 0 and fence["minimum_epoch"] >= 0
              and lease["epoch"] == fence["minimum_epoch"], "STALE_RIGHTS_OR_RESTORE")
        check(lease["status"] == "ACTIVE", "REVOKED")
        check(type(lease["expires_at"]) is int and now < lease["expires_at"],
              "EXPIRED")
        check(type(lease["retention_seconds"]) is int and
              0 < lease["retention_seconds"] <= MAX_TTL_SECONDS and
              now + lease["retention_seconds"] <= lease["expires_at"],
              "RETENTION_OR_TTL")
        check(type(lease["source_sha256"]) is str and
              _HEX.fullmatch(lease["source_sha256"]) is not None, "SOURCE_SHA")
        check(lease["revision"] == BASE_H02, "STALE_SOURCE_REVISION")
        return lease, lease_digest, fence["minimum_epoch"]

    def _git_base_bytes(self, source_id: str, *, epoch: int) -> bytes:
        check(source_id in ALLOWED_SOURCES, "SOURCE_NOT_ALLOWLISTED")
        if self.gitless_reader is not None:
            return self.gitless_reader.read_pinned(source_id, current_epoch=epoch)
        check((self.repo / ".git").exists(),
              "SOURCE_CONTROLLER_READER_NOT_ADMITTED")
        r = subprocess.run(
            ["git", "-C", str(self.repo), "cat-file", "blob",
             BASE_H02 + ":" + source_id],
            capture_output=True, check=False, timeout=5,
        )
        check(r.returncode == 0, "UNTRACKED_OR_MISSING_BASE_SOURCE")
        return r.stdout

    def _disk_source_bytes(self, source_id: str) -> bytes:
        check(source_id in ALLOWED_SOURCES, "SOURCE_NOT_ALLOWLISTED")
        path = self.repo / source_id
        check(path.is_file() and not path.is_symlink(), "UNSAFE_SOURCE_PATH")
        check(path.resolve(strict=True).is_relative_to(self.repo),
              "SOURCE_ESCAPES_REPO")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            st = os.fstat(fd)
            check(st.st_uid == self.uid and st.st_size <= 131072,
                  "SOURCE_OWNER_OR_SIZE")
            data = os.read(fd, 131073)
            check(len(data) <= 131072, "SOURCE_TOO_LARGE")
            return data
        finally:
            os.close(fd)

    def read_source(self, source_id: str, *, tenant: str, principal: str,
                    now: int | None = None,
                    mid_read: Callable[[], None] | None = None) -> dict:
        """Reads actual Git-tracked OS file, fences rights before and after."""
        try:
            check(type(source_id) is str and source_id in ALLOWED_SOURCES,
                  "UNLICENSED_SOURCE")
            now = int(dt.datetime.now(dt.timezone.utc).timestamp()) if now is None else now
            check(type(now) is int, "INVALID_TIME")
            lease, before, epoch = self._snapshot(
                tenant=tenant, principal=principal, source_id=source_id, now=now)
            tracked = self._git_base_bytes(source_id, epoch=epoch)
            check(sha(tracked) == lease["source_sha256"], "STALE_METADATA")
            disk = self._disk_source_bytes(source_id)
            check(disk == tracked, "DISK_SOURCE_VERSION_DRIFT")
            if mid_read:
                mid_read()
            again, after, epoch_after = self._snapshot(
                tenant=tenant, principal=principal, source_id=source_id, now=now)
            check(before == after and epoch == epoch_after and again == lease,
                  "RIGHTS_CHANGED_DURING_READ")
            check(self._disk_source_bytes(source_id) == disk,
                  "SOURCE_CHANGED_DURING_READ")
            # Never persist corpus text to cache or report; cite exact row digests.
            rows = [
                {"line": i, "line_sha256": sha(line.encode("utf-8")),
                 "excerpt": line}
                for i, line in enumerate(disk.decode("utf-8").splitlines(), 1)
                if line.strip()
            ]
            return {
                "decision": "LOCAL_SOURCE_READ_ONLY_CANDIDATE",
                "scope": SCOPE, "source_id": source_id,
                "source_version": BASE_H02, "source_sha256": sha(disk),
                "line_count": len(disk.decode("utf-8").splitlines()),
                "rows": rows, "rights_epoch": epoch, "rights_sha256": before,
                "source_manifest_sha256": sha(canonical({
                    "source_id": source_id, "version": BASE_H02, "sha256": sha(disk)})),
                "product_authenticated": False, "product_admitted": False,
                "verified_final": False, "answer_cache_enabled": False,
                "answer_cache_hit": False, "answer_cache_write": False,
                "independent_issuer": False, "candidate_only": True,
            }
        except (Rejected, OSError, ValueError, TypeError, UnicodeError,
                subprocess.TimeoutExpired) as exc:
            code = str(exc) if isinstance(exc, Rejected) else "SOURCE_OR_REGISTRY_UNAVAILABLE"
            return denial(code)

    def admit_excerpts(self, source_id: str, *, tenant: str, principal: str,
                       excerpts: list[dict], obligations: list[str],
                       numbers: list[str] | None = None,
                       require_negation: bool = False,
                       now: int | None = None,
                       before_publish: Callable[[], None] | None = None) -> dict:
        """Exact-source extractive binding; never semantic model qualification."""
        receipt = self.read_source(
            source_id, tenant=tenant, principal=principal, now=now)
        if not receipt["candidate_only"]:
            return receipt
        try:
            check(type(excerpts) is list and 1 <= len(excerpts) <= 8,
                  "BAD_EXCERPTS")
            check(type(obligations) is list and 0 < len(obligations) <= 12 and
                  all(type(x) is str and x for x in obligations), "BAD_OBLIGATIONS")
            check(type(require_negation) is bool, "BAD_NEGATION_FLAG")
            check(type(numbers or []) is list and
                  all(type(x) is str and x for x in (numbers or [])),
                  "BAD_NUMERIC_CONSTRAINT")
            citations = []
            for claim in excerpts:
                check(type(claim) is dict and set(claim) == {
                    "source_id", "line", "quote", "line_sha256"}, "BAD_CLAIM")
                line = claim["line"]
                check(type(line) is int and 1 <= line <= receipt["line_count"],
                      "BAD_LINE")
                check(claim["source_id"] == source_id, "CROSS_SOURCE_INJECTION")
                actual = next((v for v in receipt["rows"] if v["line"] == line), None)
                check(actual is not None and
                      claim["line_sha256"] == actual["line_sha256"] and
                      claim["quote"] == actual["excerpt"], "QUOTE_NOT_SOURCE_EXACT")
                citations.append({
                    "source_id": source_id, "revision": BASE_H02,
                    "source_sha256": receipt["source_sha256"],
                    "citation_sha256": actual["line_sha256"], "line": line,
                })
            combined = "\n".join(x["quote"] for x in excerpts)
            check(all(x.casefold() in combined.casefold() for x in obligations),
                  "ANSWER_OBLIGATION_MISMATCH")
            for n in numbers or []:
                check(re.search(r"(?<![0-9])" + re.escape(n) + r"(?![0-9])",
                                combined) is not None, "NUMBER_MISMATCH")
            if require_negation:
                check(re.search(r"\b(no|not|never|without|cannot|doesn't)\b",
                                combined, re.I) is not None, "NEGATION_UNSUPPORTED")
            if before_publish:
                before_publish()
            fence = self.read_source(
                source_id, tenant=tenant, principal=principal, now=now)
            check(fence["candidate_only"] and
                  fence["rights_sha256"] == receipt["rights_sha256"] and
                  fence["source_sha256"] == receipt["source_sha256"],
                  "PREPUBLICATION_REVOKED_OR_CHANGED")
            return {
                "decision": "EXTRACTIVE_SOURCE_BOUND_CANDIDATE_ONLY",
                "scope": SCOPE, "citations": citations,
                "source": {
                    "corpus_id": "owner-m27-repo-nonprod",
                    "corpus_revision": BASE_H02,
                    "corpus_sha256": receipt["source_sha256"],
                    "source_manifest_sha256": receipt["source_manifest_sha256"],
                    "acl_sha256": sha(canonical({
                        "tenant": tenant, "principal": principal})),
                    "rights_sha256": receipt["rights_sha256"],
                    "source_ids": [source_id],
                },
                "policy": {"revocation_epoch": receipt["rights_epoch"]},
                "h02_join_required": True, "cache_mode": "BYPASS",
                "product_authenticated": False, "product_admitted": False,
                "verified_final": False, "answer_cache_enabled": False,
                "answer_cache_hit": False, "answer_cache_write": False,
                "independent_issuer": False, "candidate_only": True,
            }
        except (Rejected, TypeError, ValueError) as exc:
            return denial(str(exc) if isinstance(exc, Rejected)
                          else "BAD_UNTRUSTED_CLAIM")


def product_source_admission(*_args: Any, **_kwargs: Any) -> dict:
    """No product authority can be manufactured from an OS-local read."""
    return denial("MISSING_INDEPENDENT_PRODUCT_IDP_RIGHTS_ISSUER")


# F03 follow-up: consume the already-existing owner A05 first-party SOURCE
# release and original read-only BM25/affinity adapter without altering them.
A05_SOURCE = "wave_b01/components/a05/source"
A05_ADAPTER = "wave_b01/components/a05/adapter/a05_retrieval.py"
A05_SOURCE_PIN = "7835ec95cee639722f89a0520336283f7e226358ad7be003a2a906635d1200e3"
A05_RELEASE_ID = "a05context-7835ec95cee63972"
A05_REVISION = "89f1d7be1623cd6926a69e38871544eefe39e584"
A05_LOCAL_SCOPE = "OWNER_DECLARED_FIRST_PARTY_A05_NONPROD_ONLY"


def _a05_deny(reason: str) -> dict:
    result = denial(reason)
    result["source_corpus"] = "A05_OWNER_FIRST_PARTY_11_DOCS"
    result["source_read_only"] = True
    result["cache_mode"] = "BYPASS"
    return result


class A05OwnerCorpusAdmission:
    """Real, separately tracked 11-document source; no Product authentication.

    Static trusted release bytes and source files are pinned to the B3-05 Git
    commit. Mutable local revocations require a separate independent OS-owned
    epoch fence. A copied corpus is accepted *only* as an isolated negative
    test copy. No public/remote caller can obtain a Product identity here.
    """

    def __init__(self, repo: Path, *, fence: Path | None = None,
                 source_root: Path | None = None,
                 isolated_test_copy: bool = False,
                 gitless_reader: F03ExternalGitlessByteReader | None = None):
        self.repo = Path(repo).resolve(strict=True)
        check(gitless_reader is None or (
              isinstance(gitless_reader, F03ExternalGitlessByteReader)
              and gitless_reader.kind == "a05" and
              gitless_reader.root == self.repo),
              "SOURCE_CONTROLLER_READER_NOT_ADMITTED")
        self.gitless_reader = gitless_reader
        self.source_root = (Path(source_root) if source_root is not None
                            else self.repo / A05_SOURCE).resolve(strict=True)
        self.fence = Path(fence) if fence else None
        self.uid = os.geteuid()
        self.isolated_test_copy = isolated_test_copy
        # Immutable commit-bound Git object baseline only. Live Source/ACL,
        # revocation, release and citation bytes are re-read every request.
        # This is NOT a response, retrieval-result or Product answer cache.
        self._pinned_blob_cache: dict[str, bytes] = {}
        self._pinned_blob_lock = threading.RLock()
        self.original_root = (self.repo / A05_SOURCE).resolve(strict=True)
        if self.source_root != self.original_root:
            check(isolated_test_copy and
                  self.source_root.is_relative_to(Path(__import__("tempfile").gettempdir()).resolve()),
                  "ONLY_ISOLATED_NONPROD_TEST_COPY")

    def _pinned(self, relative: str) -> bytes:
        check(not relative.startswith("/") and ".." not in Path(relative).parts,
              "INVALID_GIT_RELATIVE_PATH")
        # Git's exact BASE_H02:path blob is immutable content-addressed
        # provenance. Avoid spawning ~27 identical git processes per query.
        # Never memoize live file bytes or mutable revocation authority here.
        with self._pinned_blob_lock:
            if self.gitless_reader is not None:
                return self.gitless_reader.read_pinned(
                    relative, current_epoch=self.gitless_reader.epoch)
            check((self.repo / ".git").exists(),
                  "SOURCE_CONTROLLER_READER_NOT_ADMITTED")
            if relative not in self._pinned_blob_cache:
                result = subprocess.run(
                    ["git", "-C", str(self.repo), "cat-file", "blob",
                     BASE_H02 + ":" + relative],
                    capture_output=True, check=False, timeout=5)
                check(result.returncode == 0, "MISSING_PINNED_SOURCE")
                self._pinned_blob_cache[relative] = result.stdout
            return self._pinned_blob_cache[relative]

    def _read(self, filename: str) -> bytes:
        check(filename == Path(filename).name and
              filename not in ("", ".", ".."), "INVALID_SOURCE_FILE")
        path = self.source_root / filename
        check(not path.is_symlink() and path.is_file() and
              path.resolve(strict=True).is_relative_to(self.source_root),
              "SOURCE_SYMLINK_OR_MISSING")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            st = os.fstat(fd)
            check(st.st_uid == self.uid and st.st_size <= 262144,
                  "SOURCE_OWNERSHIP_OR_SIZE")
            raw = os.read(fd, 262145)
            check(len(raw) <= 262144, "SOURCE_OVERSIZE")
            return raw
        finally:
            os.close(fd)

    def _pinned_release(self) -> tuple[dict, dict, str]:
        corpus_raw = self._read("corpus.json")
        release_raw = self._read("release.json")
        check(sha(corpus_raw) == A05_SOURCE_PIN, "CORPUS_MANIFEST_DRIFT")
        check(corpus_raw == self._pinned(A05_SOURCE + "/corpus.json") and
              release_raw == self._pinned(A05_SOURCE + "/release.json"),
              "RELEASE_NOT_PINNED_TO_H02_PARENT")
        corpus, release = json.loads(corpus_raw), json.loads(release_raw)
        check(type(corpus) is dict and type(release) is dict,
              "INVALID_SOURCE_RELEASE")
        check(corpus.get("owner_source_controller_confirmed") is True and
              corpus.get("source_rights_scope") ==
              "FIRST_PARTY_OWNER_WRITTEN_ARCHITECTURE_DOCS_ONLY" and
              corpus.get("real_first_party_docs") == 11 and
              corpus.get("grounded_quote_count") == 21 and
              corpus.get("production_qualified") is False,
              "INVALID_CORPUS_RIGHTS_SCOPE")
        check(release.get("source_manifest_sha256") == A05_SOURCE_PIN and
              release.get("release_id") == A05_RELEASE_ID and
              release.get("source_revision_q34") == A05_REVISION and
              release.get("rights") ==
              "OWNER_DECLARED_FIRST_PARTY_ARCHITECTURE_DOCS_ONLY" and
              release.get("owner_first_party_only") is True and
              release.get("real_idp_authorized") is False and
              release.get("production_qualified") is False and
              release.get("source_release_ci_signed") is False and
              release.get("tenant_acl") == {"owner-internal": ["internal"]} and
              release.get("docs") == 11 and
              release.get("verified_spans") == 21,
              "INVALID_FIRST_PARTY_RELEASE")
        docs = corpus.get("docs")
        spans = corpus.get("chunks")
        check(type(docs) is list and len(docs) == 11 and
              type(spans) is list and len(spans) == 21 and
              len({s["passage_id"] for s in spans}) == 21,
              "INVALID_DOCUMENTS_OR_PASSAGES")
        lookup = {}
        for doc in docs:
            name = doc.get("filename")
            check(type(name) is str and name.endswith(".md") and
                  name == Path(name).name and name not in lookup and
                  doc.get("owner_source_rights") == "OWNER_DECLARED_FIRST_PARTY" and
                  doc.get("protected_evaluation") is False,
                  "UNLICENSED_DOCUMENT_OR_DUPLICATE")
            raw = self._read(name)
            check(raw == self._pinned(A05_SOURCE + "/" + name) and
                  sha(raw) == doc.get("sha256") and
                  len(raw) == doc.get("bytes"),
                  "SOURCE_REVISION_OR_SHA_MISMATCH")
            lookup[name] = raw
        for s in spans:
            name = s.get("source_filename")
            check(name in lookup and
                  s.get("source_sha256") == sha(lookup[name]) and
                  s.get("transport_allowed_only_after_live_revalidation") is True,
                  "BAD_SPAN_SOURCE")
            start, end = s.get("byte_start"), s.get("byte_end")
            check(type(start) is int and type(end) is int and
                  0 <= start < end <= len(lookup[name]),
                  "BAD_SPAN_BOUNDS")
            piece = lookup[name][start:end]
            check(sha(piece) == s.get("quote_sha256") and
                  piece.decode("utf-8") == s.get("quote"),
                  "SPAN_SHA_OR_QUOTE_TAMPER")
        return corpus, release, sha(release_raw)

    def _epoch(self, release: dict) -> tuple[int, str, set[str]]:
        check(self.fence is not None, "REMOTE_EPOCH_NOT_AVAILABLE_LOCAL_HOLD")
        fd = os.open(self.fence, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            st = os.fstat(fd)
            check(st.st_uid == self.uid and st.st_mode & 0o077 == 0 and
                  st.st_size <= 4096, "UNTRUSTED_LOCAL_FENCE")
            fence_data = json.loads(os.read(fd, 4097))
        finally:
            os.close(fd)
        check(type(fence_data) is dict and
              set(fence_data) == {"release_id", "minimum_epoch"} and
              fence_data["release_id"] == A05_RELEASE_ID and
              type(fence_data["minimum_epoch"]) is int and
              fence_data["minimum_epoch"] >= 1,
              "INVALID_LOCAL_FENCE")
        raw = self._read("revocations.json")
        rec = json.loads(raw)
        check(type(rec) is dict and set(rec) == {
            "schema", "epoch", "release_id", "revoked_document_sha256"} and
            rec["schema"] == "m27.a05.revocation_state.v1" and
            rec["release_id"] == release["release_id"] and
            type(rec["epoch"]) is int and
            rec["epoch"] == fence_data["minimum_epoch"] and
            type(rec["revoked_document_sha256"]) is list and
            all(type(x) is str and _HEX.fullmatch(x) for x in rec["revoked_document_sha256"]),
            "STALE_RESTORED_OR_INVALID_REVOCATION")
        if self.gitless_reader is not None:
            check(self.gitless_reader.epoch == rec["epoch"],
                  "SOURCE_CONTROLLER_EPOCH_OR_SCOPE_REVOKED")
        return rec["epoch"], sha(raw), set(rec["revoked_document_sha256"])

    def source_retrieval(self, question: str, *, tenant: str, principal: str,
                         source_revision: str = A05_REVISION,
                         release_id: str = A05_RELEASE_ID,
                         obligations: list[str] | None = None,
                         ttl_seconds: int = 300, now: dt.datetime | None = None,
                         before_return: Callable[[], None] | None = None) -> dict:
        """Actually call existing owner A05 BM25/affinity read path.

        The only result is eligible *source candidate*, never native Product
        answer, cacheable HIT, or independent semantic/ACL authority.
        """
        try:
            check(type(tenant) is str and tenant == "owner-internal" and
                  type(principal) is str and principal == "os-uid:" + str(self.uid),
                  "TENANT_OR_OS_PRINCIPAL_DENIED")
            check(type(question) is str and 0 < len(question) <= 2048,
                  "INVALID_QUERY")
            check(type(source_revision) is str and source_revision == A05_REVISION and
                  type(release_id) is str and release_id == A05_RELEASE_ID,
                  "WRONG_RELEASE_OR_REVISION")
            check(type(ttl_seconds) is int and 0 < ttl_seconds <= MAX_TTL_SECONDS,
                  "TTL_TOO_LONG")
            check(type(obligations) is list and len(obligations) > 0 and
                  len(obligations) <= 8 and all(type(s) is str and s.strip() for s in obligations),
                  "OBLIGATIONS_REQUIRED")
            check(not re.search(r"\b(no|not|never|without|cannot|doesn't)\b",
                                question, flags=re.I) and
                  not re.search(r"(?<!\w)\d+(?!\w)", question),
                  "NEGATED_OR_NUMBER_QUERY_NEEDS_SEMANTIC_VERIFIER")
            instant = now or dt.datetime.now(dt.timezone.utc)
            check(isinstance(instant, dt.datetime) and
                  instant.tzinfo is not None and
                  instant.utcoffset() == dt.timedelta(0),
                  "UTC_TIME_REQUIRED")
            corpus, release, release_sha = self._pinned_release()
            expires = dt.datetime.fromisoformat(release["expires_at"])
            begins = dt.datetime.fromisoformat(release["snapshot_at"])
            check(begins <= instant and
                  instant + dt.timedelta(seconds=ttl_seconds) <= expires,
                  "RELEASE_FRESHNESS_TTL")
            epoch, rev_digest, revoked = self._epoch(release)
            adapter_raw = (self.repo / A05_ADAPTER).read_bytes()
            check(adapter_raw == self._pinned(A05_ADAPTER),
                  "ADAPTER_VERSION_DRIFT")
            # Load the previously implemented native local retrieval method,
            # not new fixture text or fake model calls.
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "m27_a05_f03_owned_reader", self.repo / A05_ADAPTER)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            engine = module.ContextIndex(root=self.source_root)
            result = engine.search(
                question=question, tenant=tenant, roles=["internal"],
                release_id=release_id, source_revision=source_revision,
                limit=5, now=instant)
            check(result["answer_generated"] is False and
                  result["retrieval"] ==
                  "BM25_plus_local_distributional_rerank_NOT_product_vector",
                  "INVALID_NONPROD_RETRIEVAL_ENGINE")
            if result["status"] != "source_passages":
                return _a05_deny("UNSUPPORTED_SOURCE_QUERY")
            rows = result["results"]
            check(rows and len(rows) <= 5, "BAD_RETRIEVAL_RESULT")
            citations = []
            all_excerpts = []
            for row in rows:
                cite = row["citation"]
                source_file = cite["document"]
                meta = next((x for x in corpus["docs"] if
                             x["filename"] == source_file), None)
                check(meta is not None and
                      cite["document_sha256"] == meta["sha256"] and
                      cite["source_revision"] == A05_REVISION and
                      cite["release_id"] == A05_RELEASE_ID and
                      cite["revocation_epoch"] == epoch and
                      cite["document_sha256"] not in revoked,
                      "CITATION_SOURCE_RIGHTS_MISMATCH")
                check(cite["source_uri"] == "urn:sha256:" + meta["sha256"],
                      "CITATION_SOURCE_INJECTION")
                actual = self._read(source_file)
                piece = actual[cite["byte_start"]:cite["byte_end"]]
                check(piece.decode() == row["excerpt"] and
                      sha(piece) == cite["excerpt_sha256"], "CITATION_BYTES_MISMATCH")
                citations.append(cite)
                all_excerpts.append(row["excerpt"])
            joined = "\n".join(all_excerpts).casefold()
            check(all(s.casefold() in joined for s in obligations),
                  "SOURCE_ANSWER_OBLIGATION_UNSUPPORTED")
            if before_return:
                before_return()
            next_corpus, next_release, next_release_sha = self._pinned_release()
            next_epoch, next_rev, _ = self._epoch(next_release)
            check(next_release_sha == release_sha and
                  next_corpus == corpus and
                  next_epoch == epoch and next_rev == rev_digest,
                  "REVOKED_OR_SOURCE_CHANGED_BEFORE_DELIVERY")
            # Re-read all citation bytes; even an overwritten source must deny.
            for cite in citations:
                actual = self._read(cite["document"])
                check(sha(actual) == cite["document_sha256"] and
                      sha(actual[cite["byte_start"]:cite["byte_end"]]) ==
                      cite["excerpt_sha256"], "REVALIDATE_CITATION_FAILED")
            return {
                "decision": "A05_REAL_LOCAL_RETRIEVAL_SOURCE_CANDIDATE",
                "scope": A05_LOCAL_SCOPE, "release_id": A05_RELEASE_ID,
                "release_sha256": release_sha,
                "source_manifest_sha256": A05_SOURCE_PIN,
                "source_revision": A05_REVISION, "rights_epoch": epoch,
                "revocation_sha256": rev_digest,
                "sources": citations, "candidate_excerpts": all_excerpts,
                "retrieval": result["retrieval"],
                "retrieved_documents": len({c["document"] for c in citations}),
                "source": {
                    "corpus_id": A05_RELEASE_ID,
                    "corpus_revision": A05_REVISION,
                    "corpus_sha256": A05_SOURCE_PIN,
                    "source_manifest_sha256": A05_SOURCE_PIN,
                    "acl_sha256": sha(canonical({
                        "tenant": tenant, "roles": ["internal"],
                        "os_uid": self.uid})),
                    "rights_sha256": sha(canonical({
                        "owner_scope": release["rights"],
                        "release_sha256": release_sha,
                        "revocation_sha256": rev_digest})),
                    "source_ids": [c["document"] for c in citations],
                },
                "policy": {"revocation_epoch": epoch},
                "cache_mode": "BYPASS",
                "nonprod_file_mode": "TEST_COPY" if self.isolated_test_copy else "REAL_GIT_SOURCE",
                "answer_cache_enabled": False,
                "answer_cache_hit": False, "answer_cache_write": False,
                "product_authenticated": False, "product_admitted": False,
                "verified_final": False, "independent_issuer": False,
                "candidate_only": True, "native_consumer_joined": False,
            }
        except (Rejected, OSError, ValueError, KeyError, TypeError,
                UnicodeError, subprocess.TimeoutExpired) as exc:
            reason = str(exc) if isinstance(exc, Rejected) else "SOURCE_READ_OR_ADAPTER_FAILURE"
            return _a05_deny(reason)
        except Exception:
            # Unknown adapter/revocation failure never opens Product cache.
            return _a05_deny("UNKNOWN_RETRIEVAL_OR_RIGHTS_FAILURE")
