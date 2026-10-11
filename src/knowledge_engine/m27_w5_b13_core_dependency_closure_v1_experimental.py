"""F13 frozen 20-source core dependency closure, offline FEATURE-OFF only.

This is not a signed OCI layer, Ed25519 feature approval, or production authorization.
The separate frozen B12 worktree is never written to or used as a build destination.
"""
from __future__ import annotations

import ast
import json
import stat
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path

from knowledge_engine.m27_w5_b11_local_package_attestor_v1_experimental import (
    digest,
    inspect_archive,
    validate_relpath,
    zip_entry,
)
from knowledge_engine.m27_w5_b12_dependency_complete_package_v1_experimental import (
    PINS as F12_PINS,
)

PROJECT = Path("/Users/huaihsuanhuang/Desktop/Chatgpt/M27/M27_VNEXT_MASTER_20261009")
FROZEN_ROOT = PROJECT / "06_WORKSITES/W5_B12_DEPENDENCY_COMPLETE_PACKAGE"
F13_MANIFEST = (PROJECT / "07_MASTER_REBASE_20261010/05_EVIDENCE_INDEX"
                / "W5_F13_20_SOURCE_FREEZE_MANIFEST_20261011.json")
F12_MANIFEST = (PROJECT / "07_MASTER_REBASE_20261010/05_EVIDENCE_INDEX"
                / "W5_F12_19_SOURCE_FREEZE_MANIFEST_20261010.json")
INTERPRETER = "/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python"
SOURCE_HEAD = "e7cbfdbc4da2027fcd42e7e4586362018a2323ef"
SOURCE_TREE = "891d7487d8b9c6b085d1dbbdd651b3817fc7c35d"
MANIFEST_SHA = "0781bb17f1dd405e5140accc1071d019742643902849bb75cd512af9be2f0cde"
F12_SHA = "051dafba045515350d0908886fcc9d46da30262df5839cb383c685574a47f751"
BROKER = "m27_ar03_context_broker_experimental.py"
BROKER_SHA = "b3263c8ae00d99296d449965b94fb6b40a4f70ae8d260e86133ea3b824da9d6e"
PINS = {**F12_PINS, BROKER: BROKER_SHA}
NAMES = tuple(sorted(n[:-3] for n in PINS))
I02 = "m27_w4_i02_local_runtime_v1_experimental"
AR06 = "m27_ar06_governed_memory_experimental"
P09 = "m27_w4_p09_external_evidence_v1_experimental"
SCHEMA = "m27.w5.b13.offline.core.closure/v1"
BUILDER = "F13-zip-stored-1980-100644-v1"
OUTPUTS = ("B13_F13_20_SOURCE_CORE.zip", "B13_CORE_RECEIPT.json",
           "B13_ISOLATED_IMPORT_AND_FEATURE_OFF.json")
OPTIONAL = {
    "profile": "CORE_OFFLINE_FEATURE_OFF",
    "dependency": "cryptography",
    "owner_module": P09 + ".py",
    "function": "EvidenceIntake._verify_signature",
    "feature": "AUTHORIZED_EXTERNAL_ED25519_SIGNATURE_VERIFICATION",
    "decision": "EXCLUDED_FROM_CORE_PACKAGE_FAIL_CLOSED_ON_UNAVAILABLE",
    "no_real_external_signed_evidence_admitted": True,
    "require_independent_optional_layer_attestation_for_full_feature": True,
    "no_install_or_vendor_in_core": True,
}


class ClosureBlocked(ValueError):
    """Explicit fail-closed status. No evidence promotion on failure."""


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ClosureBlocked(reason)


def canonical(obj: object) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            + "\n").encode("ascii")


def manifest_entries(doc: object, f12: object) -> tuple[tuple[str, str], ...]:
    require(isinstance(doc, dict), "F13_MANIFEST_INVALID")
    require(set(doc) == {
        "schema", "date", "qualification", "source_worktree", "git_head",
        "git_tree", "previous_f12_manifest_sha256", "previous_source_count",
        "entry_count", "additional_dependency_path", "optional_dependency_policy",
        "internal_ast_closure_checked", "core_optional_dependency_not_fully_implemented",
        "external_phase_b_qualified", "production_authorized",
        "real_executed_image_attested", "files",
    }, "F13_MANIFEST_METADATA_FORGED")
    fields = {
        "schema": "m27.w5.source_freeze_manifest/v3",
        "date": "2026-10-11",
        "qualification": (
            "F13_LOCAL_20_SOURCE_CORE_CLOSURE_CANDIDATE_OPTIONAL_ED25519_EXCLUDED_NOT_RELEASE"
        ),
        "source_worktree": str(FROZEN_ROOT),
        "git_head": SOURCE_HEAD,
        "git_tree": SOURCE_TREE,
        "previous_f12_manifest_sha256": F12_SHA,
        "previous_source_count": 19,
        "entry_count": 20,
        "additional_dependency_path": "src/knowledge_engine/" + BROKER,
        "optional_dependency_policy": OPTIONAL,
        "internal_ast_closure_checked": True,
        "core_optional_dependency_not_fully_implemented": True,
        "external_phase_b_qualified": False,
        "production_authorized": False,
        "real_executed_image_attested": False,
    }
    for key, value in fields.items():
        require(type(doc[key]) is type(value) and doc[key] == value,
                "F13_METADATA_OR_POLICY_FORGED: " + key)
    require(isinstance(f12, dict) and isinstance(f12.get("files"), list),
            "F13_F12_HISTORY_INVALID")
    f12_map = {r["path"]: r["sha256"] for r in f12["files"]}
    require(len(f12_map) == 19 and
            f12_map == {"src/knowledge_engine/" + n: sha for n, sha in F12_PINS.items()},
            "F13_F12_HISTORY_PIN_DRIFT")
    rows = doc["files"]
    require(isinstance(rows, list) and len(rows) == 20, "F13_SOURCE_COUNT")
    expected = {"src/knowledge_engine/" + n: sha for n, sha in PINS.items()}
    result: dict[str, str] = {}
    components: set[str] = set()
    folded: set[str] = set()
    for r in rows:
        require(isinstance(r, dict) and set(r) == {"component", "path", "sha256"},
                "F13_SOURCE_ROW_FORGED")
        c, path, sha = r["component"], r["path"], r["sha256"]
        require(isinstance(c, str) and c.isascii() and c and c not in components,
                "F13_COMPONENT_DUPLICATE")
        components.add(c)
        try:
            safe = validate_relpath(path)
        except (ValueError, TypeError) as exc:
            raise ClosureBlocked("F13_UNSAFE_PATH") from exc
        require(isinstance(path, str) and
                unicodedata.normalize("NFKC", path) == path and
                safe == path and path.startswith("src/knowledge_engine/") and
                path.count("/") == 2 and path.endswith(".py"),
                "F13_UNSAFE_PATH")
        folded_path = unicodedata.normalize("NFKC", path).casefold()
        require(folded_path not in folded, "F13_PATH_COLLISION")
        folded.add(folded_path)
        require(path in expected, "F13_UNAPPROVED_EXPORT")
        require(sha == expected[path], "F13_SHA_PIN_MISMATCH")
        result[path] = sha
    require(result == expected, "F13_SOURCE_UNIVERSE_OR_BROKER_MISSING")
    require({k: v for k, v in result.items() if not k.endswith("/" + BROKER)}
            == f12_map, "F13_HISTORICAL_F12_PIN_MUTATED")
    return tuple(sorted(result.items()))


def _lexical_class_function(node: ast.AST,
                            parents: dict[ast.AST, ast.AST]) -> tuple[str, str]:
    funcs, classes = [], []
    parent = parents.get(node)
    while parent is not None:
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append(parent.name)
        elif isinstance(parent, ast.ClassDef):
            classes.append(parent.name)
        parent = parents.get(parent)
    return (".".join(reversed(classes)), ".".join(reversed(funcs)))


def scan_source(raw: bytes, module: str) -> dict[str, object]:
    """Strict all-scope AST: lazy functions, nested closures, and imports."""
    try:
        tree = ast.parse(raw, filename=module)
    except (SyntaxError, UnicodeError, ValueError) as exc:
        raise ClosureBlocked("F13_INVALID_SOURCE_SYNTAX") from exc
    parents = {child: parent for parent in ast.walk(tree)
               for child in ast.iter_child_nodes(parent)}
    internal: set[str] = set()
    optional: list[dict] = []
    for node in ast.walk(tree):
        specs: list[str] = []
        if isinstance(node, ast.Import):
            specs = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            require(node.level == 0 and node.module is not None,
                    "F13_RELATIVE_IMPORT_UNSUPPORTED")
            specs = [node.module]
        elif isinstance(node, ast.Call):
            fn = node.func
            if ((isinstance(fn, ast.Name) and fn.id in
                 {"__import__", "eval", "exec", "compile"}) or
                (isinstance(fn, ast.Attribute) and fn.attr in
                 {"import_module", "__import__"})):
                raise ClosureBlocked("F13_DYNAMIC_IMPORT_UNSUPPORTED")
        for spec in specs:
            root, _, sub = spec.partition(".")
            if root == "knowledge_engine":
                require(sub and "." not in sub, "F13_INTERNAL_IMPORT_AMBIGUOUS")
                internal.add("knowledge_engine/" + sub + ".py")
            elif root == "cryptography":
                cls, fn = _lexical_class_function(node, parents)
                allowed = (
                    module == "knowledge_engine/" + P09 + ".py" and
                    cls == "EvidenceIntake" and fn == "_verify_signature" and
                    isinstance(node, ast.ImportFrom) and
                    node.module == "cryptography.hazmat.primitives.asymmetric.ed25519" and
                    len(node.names) == 1 and node.names[0].name == "Ed25519PublicKey" and
                    node.names[0].asname is None
                )
                require(allowed, "F13_UNAUTHORIZED_EXTERNAL_CRYPTO_IMPORT")
                optional.append({"owner": module, "line": node.lineno,
                                 "function": cls + "." + fn,
                                 "dependency": "cryptography", "feature": "EXCLUDED"})
            else:
                require(root in sys.stdlib_module_names,
                        "F13_UNPINNED_THIRD_PARTY: " + root)
    return {"internal": sorted(internal), "optional": optional}


def strict_graph(deps: dict[str, dict], inventory: set[str]) -> dict[str, list[str]]:
    require(inventory == {"knowledge_engine/" + n for n in PINS},
            "F13_SOURCE_UNIVERSE_MISMATCH")
    graph = {}
    for name in sorted(inventory):
        require(name in deps and isinstance(deps[name], dict),
                "F13_SCAN_MISSING")
        require(set(deps[name]) == {"internal", "optional"} and
                isinstance(deps[name]["optional"], list),
                "F13_SCAN_INVALID")
        children = deps[name].get("internal")
        require(isinstance(children, list), "F13_SCAN_INVALID")
        for child in children:
            require(child in inventory, "F13_CORE_CLOSURE_BLOCKED: " + child)
        graph[name] = sorted(set(children))
    require("knowledge_engine/" + BROKER in
            graph["knowledge_engine/" + AR06 + ".py"],
            "F13_AR06_DEFERRED_AR03_EDGE_MISSING")
    opt = [o for d in deps.values() for o in d.get("optional", [])]
    require(len(opt) == 1 and isinstance(opt[0], dict) and
            set(opt[0]) == {"owner", "line", "function", "dependency", "feature"} and
            opt[0]["owner"] == "knowledge_engine/" + P09 + ".py" and
            opt[0]["function"] == "EvidenceIntake._verify_signature" and
            opt[0]["dependency"] == "cryptography" and
            opt[0]["feature"] == "EXCLUDED" and
            type(opt[0]["line"]) is int and opt[0]["line"] > 0,
            "F13_OPTIONAL_CRYPTO_SCOPE_UNVERIFIED")
    return graph


ISOLATED_SCRIPT = r"""
import builtins, hashlib, importlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve(strict=True)
names = json.loads(sys.argv[2])
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert "knowledge_engine" not in sys.modules
assert not any(k.startswith("knowledge_engine.") for k in sys.modules)
assert "sitecustomize" not in sys.modules
assert not any("site-packages" in p or "/06_WORKSITES/" in p
               for p in sys.path if isinstance(p, str))
sys.path.insert(0, str(root))
mods = []
for name in ["m27_w4_i02_local_runtime_v1_experimental", *[n for n in names
             if n != "m27_w4_i02_local_runtime_v1_experimental"]]:
    m = importlib.import_module("knowledge_engine." + name)
    target = (root / "knowledge_engine" / (name + ".py")).resolve(strict=True)
    assert pathlib.Path(m.__file__).resolve(strict=True) == target
    assert pathlib.Path(m.__spec__.origin).resolve(strict=True) == target
    assert sys.modules[m.__name__] is m
    mods.append({"name":name,"origin":str(target),
                 "sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
                 "identity":True})
loaded = sorted(k for k in sys.modules if k.startswith("knowledge_engine."))
assert loaded == sorted("knowledge_engine." + n for n in names)
assert len(mods) == len(names) == 20 and len(set(m["name"] for m in mods)) == 20
assert isinstance(getattr(sys.modules["knowledge_engine.m27_w4_i02_local_runtime_v1_experimental"],
                         "I02LocalRuntimeV1"), type)

# Real function-local import and real broker selector: no external user material.
a = importlib.import_module("knowledge_engine.m27_ar06_governed_memory_experimental")
broker = importlib.import_module("knowledge_engine.m27_ar03_context_broker_experimental")
seen = []
real_select = broker.select
def counted(req, candidates, grant=None):
    assert isinstance(req, broker.Request)
    assert all(isinstance(c, broker.Candidate) for c in candidates)
    result = real_select(req, candidates, grant)
    seen.append({"tenant":req.tenant,"purpose":req.purpose,
                 "candidates":len(candidates),"omissions":len(result.omissions)})
    return result
broker.select = counted
accepted = a.AcceptedMemory(
    memory_id="synthetic-memory", candidate_id="synthetic-candidate",
    tenant="tenant-a", subject="alice", purpose="research",
    source_revision="r1", source_digest="a"*64,
    value_ref="synthetic://empty", value_digest="b"*64,
    policy_version="v1", consent_version="v1", lawful_basis_ref="fixture",
    residency="local", reviewer_ref="fixture", review_expires_at=2000,
    expires_at=2000, version=1, exclusion_generation=0, taint_labels=(),
    mock_only=True, native_citation_eligible=False)
outcome = a.ar03a_metadata_probe(accepted,now=1000,principal="alice")
broker.select = real_select
# Independently exercise original Broker deny-first tenant, purpose and source conditions.
req = broker.Request("tenant-a","alice","research",frozenset({"memory"}),1000,100,10,100)
grant = broker.GrantFixture("tenant-a","alice","research",
                            frozenset({"memory"}),2000,True)
def candidate(**kwargs):
    data = dict(scope="memory",source_id="synthetic-source",revision="r1",
                digest="c"*64,tenant="tenant-a",principals=frozenset({"alice"}),
                purpose="research",expires=2000,retrieved=999,tokens=1,cost=1)
    data.update(kwargs)
    return broker.Candidate(**data)
cases = {
 "no_grant": real_select(req,(candidate(),)).selected == (),
 "other_tenant": real_select(req,(candidate(tenant="tenant-b"),),grant).selected == (),
 "wrong_purpose": real_select(req,(candidate(purpose="other"),),grant).selected == (),
 "missing_revision": real_select(req,(candidate(revision=""),),grant).selected == (),
 "revoked": real_select(req,(candidate(revoked=True),),grant).selected == (),
 "expired_consent": real_select(req,(candidate(consent_expires=1000),),grant).selected == (),
}
assert all(cases.values())
functional = bool(seen) and isinstance(outcome, (dict, tuple, list, broker.Result))
# Even if the function returns a scalar, a real select call is the mandatory witness.
functional = bool(seen)
# Check explicit no-third-party signature verification semantics in this environment.
p09 = importlib.import_module("knowledge_engine.m27_w4_p09_external_evidence_v1_experimental")
orig_import = builtins.__import__
attempted = []
def no_crypto(name, *args, **kwargs):
    if name == "cryptography" or name.startswith("cryptography."):
        attempted.append(name)
        raise ModuleNotFoundError("cryptography excluded from core")
    return orig_import(name,*args,**kwargs)
frozen = p09.FrozenCandidate("f"*40,"e"*40,None,None)
anchor = p09.Anchor("authority","synthetic-custodian","kid",b"\x00"*32,
                    "ed25519","external","synthetic-root")
record = p09.SignedRecord(
    role="authority",signer="synthetic-custodian",key_id="kid",
    algorithm="ed25519",tenant="tenant-a",run="offline-run",
    request="offline-request",attempt="one",revision="r1",
    issued_ms=900,expires_ms=2000,previous_digest=None,
    body={"fixture":True},digest="0"*64,signature="00"*64)
intake = p09.EvidenceIntake(frozen,(anchor,),authorized_external_custodian=True,
                            now_ms=1000,invoice_close_ms=1000)
builtins.__import__ = no_crypto
try:
    verify = intake._verify_signature(record)
finally:
    builtins.__import__ = orig_import
assert isinstance(verify,tuple) and verify != (True,True)
result = {
 "isolated":True,"no_site":True,"python":[3,11],
 "sys_path":sys.path,"modules":mods,"unexpected_modules":[],
 "deferred":{"called":functional,"count":len(seen),"events":seen,
             "broker_path":broker.__file__,"deny_first":cases},
 "ed25519":{"unavailable":True,"crypto_import_attempts":attempted,
            "verified":bool(verify[0]),"admitted":bool(verify[1])}
}
print(json.dumps(result,sort_keys=True))
"""


def validate_probe(proof: object, root: Path, expected: dict[str, str]) -> None:
    require(isinstance(proof, dict) and set(proof) == {
        "isolated", "no_site", "python", "sys_path", "modules",
        "unexpected_modules", "deferred", "ed25519",
    }, "F13_IMPORT_RECEIPT_FORGED")
    require(proof["isolated"] is True and proof["no_site"] is True
            and proof["python"] == [3, 11], "F13_IMPORT_ISOLATION_FORGED")
    paths = proof["sys_path"]
    require(isinstance(paths, list) and paths and paths[0] == str(root.resolve())
            and not any("site-packages" in s or "/06_WORKSITES/" in s or "/src" in s
                        for s in paths if isinstance(s, str)),
            "F13_IMPORT_HOST_OR_SITE_SHADOW")
    rows = proof["modules"]
    require(isinstance(rows, list) and len(rows) == 20 and
            rows[0]["name"] == I02 and proof["unexpected_modules"] == [],
            "F13_IMPORT_MODULE_UNIVERSE")
    require({r["name"] for r in rows} == set(NAMES), "F13_IMPORT_MODULE_UNIVERSE")
    for row in rows:
        require(set(row) == {"name", "origin", "sha256", "identity"},
                "F13_IMPORT_ORIGIN_FORGED")
        want = str((root / "knowledge_engine" / (row["name"] + ".py")).resolve())
        require(row["origin"] == want and
                row["sha256"] == expected["knowledge_engine/" + row["name"] + ".py"]
                and row["identity"] is True, "F13_IMPORT_ORIGIN_OR_SHA_FORGED")
    lazy = proof["deferred"]
    require(lazy["called"] is True and lazy["count"] >= 1
            and lazy["broker_path"] == str(root / "knowledge_engine" / BROKER)
            and set(lazy["deny_first"]) == {
                "no_grant", "other_tenant", "wrong_purpose",
                "missing_revision", "revoked", "expired_consent"}
            and all(value is True for value in lazy["deny_first"].values()),
            "F13_DEFERRED_FUNCTIONAL_UNVERIFIED")
    crypto = proof["ed25519"]
    require(crypto["unavailable"] is True and
            crypto["verified"] is False and crypto["admitted"] is False and
            isinstance(crypto["crypto_import_attempts"], list) and
            bool(crypto["crypto_import_attempts"]) and
            all(isinstance(n, str) and n.startswith("cryptography.")
                for n in crypto["crypto_import_attempts"]),
            "F13_OPTIONAL_ED25519_POLICY_UNVERIFIED")


class OfflineCoreDependencyClosureV1:
    """Pinned B12 frozen input; F13 versioned feature-off offline evidence."""

    def __init__(self, source_root: Path = FROZEN_ROOT,
                 manifest: Path = F13_MANIFEST, scratch: Path | None = None,
                 interpreter: str = INTERPRETER):
        self.source_root = Path(source_root)
        self.manifest = Path(manifest)
        self.scratch = Path(scratch) if scratch is not None else (
            PROJECT / "05_EVIDENCE_INDEX/W5_B13_DEPENDENCY_CLOSURE_FIX_SCRATCH")
        self.interpreter = interpreter

    def git(self, *args: str) -> str:
        try:
            return subprocess.run(["git", "-C", str(self.source_root), *args],
                                  capture_output=True, text=True, check=True,
                                  timeout=20).stdout.strip()
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise ClosureBlocked("F13_GIT_READ_UNVERIFIED") from exc

    def verify_source(self) -> tuple[dict[str, bytes], dict[str, dict]]:
        require(self.source_root.absolute() == FROZEN_ROOT
                and not self.source_root.is_symlink() and
                self.source_root.resolve(strict=True) == FROZEN_ROOT.resolve(strict=True),
                "F13_FROZEN_ROOT_SUBSTITUTED")
        require(self.manifest.absolute() == F13_MANIFEST and
                not self.manifest.is_symlink(), "F13_MANIFEST_SUBSTITUTED")
        require(digest(self.manifest.read_bytes()) == MANIFEST_SHA,
                "F13_MANIFEST_DIGEST_INVALID")
        require(digest(F12_MANIFEST.read_bytes()) == F12_SHA,
                "F13_HISTORICAL_F12_MANIFEST_DIGEST_INVALID")
        try:
            pairs = manifest_entries(json.loads(self.manifest.read_bytes()),
                                     json.loads(F12_MANIFEST.read_bytes()))
        except (ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, ClosureBlocked):
                raise
            raise ClosureBlocked("F13_MANIFEST_PARSE_INVALID") from exc
        require(self.git("rev-parse", "HEAD") == SOURCE_HEAD and
                self.git("rev-parse", "HEAD^{tree}") == SOURCE_TREE,
                "F13_FROZEN_HEAD_OR_TREE_CHANGED")
        require(self.git("status", "--porcelain=v1", "-uall") == "",
                "F13_FROZEN_SOURCE_DIRTY")
        source, deps = {}, {}
        for relative, sha in pairs:
            path = self.source_root / relative
            require(not path.is_symlink() and not path.parent.is_symlink() and
                    path.parent.resolve(strict=True) ==
                    (self.source_root / "src/knowledge_engine").resolve(strict=True),
                    "F13_SOURCE_SYMLINK_OR_ESCAPE")
            st = path.lstat()
            require(stat.S_ISREG(st.st_mode) and not st.st_mode & 0o111
                    and st.st_size <= 2_000_000, "F13_SOURCE_MODE_OR_SIZE")
            require(self.git("ls-files", "--stage", "--", relative).startswith("100644 "),
                    "F13_SOURCE_NOT_TRACKED_100644")
            raw = path.read_bytes()
            require(len(raw) == st.st_size and digest(raw) == sha,
                    "F13_ORIGINAL_SOURCE_SHA_INVALID")
            try:
                blob = subprocess.run(
                    ["git", "-C", str(self.source_root), "show", SOURCE_HEAD + ":" + relative],
                    capture_output=True, check=True, timeout=20).stdout
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                raise ClosureBlocked("F13_ORIGINAL_GIT_BLOB_UNAVAILABLE") from exc
            require(raw == blob and digest(blob) == sha,
                    "F13_ORIGINAL_GIT_BLOB_MISMATCH")
            name = "knowledge_engine/" + path.name
            source[name] = raw
            deps[name] = scan_source(raw, name)
        require(self.git("rev-parse", "HEAD") == SOURCE_HEAD and
                self.git("status", "--porcelain=v1", "-uall") == "",
                "F13_SOURCE_RACE_DETECTED")
        return source, deps

    @staticmethod
    def build(dest: Path, sources: dict[str, bytes]) -> tuple[str, tuple[dict, ...]]:
        expected = {name: digest(raw) for name, raw in sources.items()}
        expected["knowledge_engine/__init__.py"] = digest(b"")
        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_STORED,
                             allowZip64=False) as archive:
            for name in sorted(expected):
                archive.writestr(zip_entry(name), b"" if name.endswith("/__init__.py")
                                 else sources[name])
        checksum = digest(dest.read_bytes())
        return checksum, inspect_archive(dest, expected, checksum)

    def probe(self, archive: Path, expected: dict[str, str], parent: Path) -> dict:
        require(self.interpreter == INTERPRETER and Path(self.interpreter).is_file(),
                "F13_UNPINNED_PYTHON")
        root = parent / "extracted"
        root.mkdir(mode=0o700)
        with zipfile.ZipFile(archive) as z:
            require(len(z.infolist()) == len(expected), "F13_ZIP_MEMBER_COUNT")
            for member in sorted(expected):
                validate_relpath(member, archive=True)
                file = root / member
                file.parent.mkdir(exist_ok=True)
                with file.open("xb") as stream:
                    stream.write(z.read(member))
                require(digest(file.read_bytes()) == expected[member],
                        "F13_EXTRACTED_SOURCE_DRIFT")
        try:
            result = subprocess.run(
                [self.interpreter, "-I", "-S", "-B", "-c", ISOLATED_SCRIPT,
                 str(root), json.dumps(NAMES)],
                capture_output=True, text=True, check=True, timeout=35,
                cwd=parent, env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            detail = (exc.stderr if isinstance(exc, subprocess.CalledProcessError)
                      else str(exc))
            raise ClosureBlocked("F13_ISOLATED_PROBE_FAILED: " + detail[-400:]) from exc
        try:
            proof = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ClosureBlocked("F13_PROBE_RECEIPT_PARSE") from exc
        validate_probe(proof, root, expected)
        return proof

    def run(self, *, run_id: str) -> dict:
        require(isinstance(run_id, str) and len(run_id) >= 8 and
                run_id.isascii() and run_id.replace("-", "").replace("_", "").isalnum(),
                "F13_RUN_ID_INVALID")
        sources, deps = self.verify_source()
        graph = strict_graph(deps, set(sources))
        require(len(sources) == 20 and len(PINS) == 20, "F13_SOURCE_COUNT")
        require(str(self.scratch).startswith(str(PROJECT / "05_EVIDENCE_INDEX/"
                "W5_B13_DEPENDENCY_CLOSURE_FIX_SCRATCH")) or
                self.scratch.resolve().is_relative_to(Path("/tmp").resolve()),
                "F13_SCRATCH_OUTSIDE_ALLOWED")
        self.scratch.mkdir(parents=True, exist_ok=True)
        receipt_root = self.scratch / ("run-" + run_id)
        try:
            receipt_root.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise ClosureBlocked("F13_DUPLICATE_RUN_ID") from exc
        with tempfile.TemporaryDirectory(dir=self.scratch, prefix="first_") as d1:  # noqa: SIM117
            with tempfile.TemporaryDirectory(dir=self.scratch, prefix="second_") as d2:
                a, b = Path(d1) / "package.zip", Path(d2) / "package.zip"
                sha1, rows1 = self.build(a, sources)
                sha2, rows2 = self.build(b, sources)
                require(sha1 == sha2 and a.read_bytes() == b.read_bytes()
                        and rows1 == rows2, "F13_REPRODUCIBLE_ZIP_FAILURE")
                expected = {name: digest(raw) for name, raw in sources.items()}
                expected["knowledge_engine/__init__.py"] = digest(b"")
                assert len(rows1) == 21
                probe = self.probe(a, expected, Path(d1))
                receipt = {
                    "schema": SCHEMA, "builder": BUILDER,
                    "manifest_sha256": MANIFEST_SHA, "source_head": SOURCE_HEAD,
                    "source_tree": SOURCE_TREE, "source_count": 20,
                    "zip_members": 21, "archive_sha256": sha1,
                    "entries": list(rows1), "dependency_graph": graph,
                    "optional_policy": OPTIONAL, "run_id": run_id,
                    "statuses": {
                        "byte": "B13_LOCAL_20_SOURCE_BYTES_REPRODUCIBLE_PASS",
                        "closure": "B13_CORE_INTERNAL_TRANSITIVE_IMPORT_CLOSURE_PASS",
                        "import": "B13_FULL_I02_ISOLATED_MODULE_IMPORT_PASS",
                        "deferred": "B13_AR03_DEFERRED_IMPORT_FUNCTIONAL_PROOF_PASS",
                        "optional": "B13_OPTIONAL_ED25519_EXCLUDED_FAIL_CLOSED",
                        "all_features_dependency_closed": False,
                        "real_signed_executed_oci_image_attested": False,
                        "REL01": "NOT_CERTIFIED", "REL02": "NOT_AUTHORIZED",
                    },
                }
                for name, data in zip(OUTPUTS, (a.read_bytes(), canonical(receipt),
                                                  canonical(probe)), strict=True):
                    with (receipt_root / name).open("xb") as f:
                        f.write(data)
                return {
                    "archive_sha256": sha1, "receipt_sha256": digest(canonical(receipt)),
                    "import_sha256": digest(canonical(probe)),
                    "paths": [str(receipt_root / n) for n in OUTPUTS],
                    "graph": graph, "probe": probe, "statuses": receipt["statuses"],
                    "row_count": len(rows1), "source_count": len(sources),
                }
