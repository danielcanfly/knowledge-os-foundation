"""W5 B12 isolated 19-source byte package and strict transitive dependency gate.

This is offline fixture evidence only, never a signed image, provider or release proof.
"""
from __future__ import annotations

import ast
import json
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from knowledge_engine.m27_w5_b11_local_package_attestor_v1_experimental import (
    PINNED as PREVIOUS_17,
)
from knowledge_engine.m27_w5_b11_local_package_attestor_v1_experimental import (
    archive_name,
    canonical,
    digest,
    inspect_archive,
    safe_member,
    validate_relpath,
    zip_entry,
)

SCHEMA = "m27.w5.b12.dependency.complete.package/v1"
F12_SCHEMA = "m27.w5.source_freeze_manifest/v2"
SOURCE_HEAD = "f81e1ef4642624e9f28f6a314f18d1bcc2e1a3a9"
SOURCE_TREE = "16ef7e807a28c3a6d884351bf66dca042b72fa33"
MANIFEST_SHA = "051dafba045515350d0908886fcc9d46da30262df5839cb383c685574a47f751"
PREVIOUS_F11_SHA = "6612fa1b6782f524b274025bad471cc3b66d70b6961aeda84d380cb1c7ae8721"
PROJECT = Path("/Users/huaihsuanhuang/Desktop/Chatgpt/M27/M27_VNEXT_MASTER_20261009")
FROZEN_ROOT = PROJECT / "06_WORKSITES/W5_B11R_POSTCOMMIT_REGRESSION_REPAIR"
F12_MANIFEST = (PROJECT / "07_MASTER_REBASE_20261010/05_EVIDENCE_INDEX"
                / "W5_F12_19_SOURCE_FREEZE_MANIFEST_20261010.json")
INTERPRETER = "/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python"
EXTRA_PINS = {
    "m27_ar06_governed_memory_experimental.py":
        "056095bedb35f927b7f11bc56e63fb172b18d0366eed977f789c015483b67f12",
    "m27_ar07_compute_policy_experimental.py":
        "37c80701ec86905bcee5770cba9a5bbd69ef0cec12d7fa238ad44c6e15ed2039",
}
PINS = {**PREVIOUS_17, **EXTRA_PINS}
MODULE_NAMES = tuple(sorted(name[:-3] for name in PINS))
I02 = "m27_w4_i02_local_runtime_v1_experimental"
BUILDER = "zip-stored-1980-100644-f12-v1"
PUBLIC_ABI = {
    I02: "I02LocalRuntimeV1",
    "m27_w3_ar06_durable_governance_v1_experimental": "DurableMemoryExclusion",
    "m27_w3_ar07_compute_budget_v1_experimental": "LocalComputeBudget",
}
OUTPUTS = ("B12_19_SOURCE_DIAGNOSTIC.zip", "B12_PACKAGE_RECEIPT.json", "B12_IMPORT_ORIGIN.json")


class PackageBlocked(ValueError):
    """A package/claim must never be promoted after this violation."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def enforce(condition: bool, reason: str) -> None:
    if not condition:
        raise PackageBlocked(reason)


def validate_manifest(doc: object) -> tuple[tuple[str, str], ...]:
    enforce(isinstance(doc, dict), "F12_MANIFEST_INVALID")
    enforce(set(doc) == {
        "schema", "date", "qualification", "source_worktree", "git_head",
        "git_tree", "original_f11_sha256", "previous_f11_head", "original_count",
        "additional_dependency_paths", "entry_count", "external_phase_b_qualified",
        "production_authorized", "real_executed_image_attested", "files",
    }, "F12_MANIFEST_METADATA_FORGED")
    enforce(doc["schema"] == F12_SCHEMA, "F12_MANIFEST_SCHEMA_INVALID")
    enforce(doc["date"] == "2026-10-10", "F12_DATE_INVALID")
    enforce(
        doc["qualification"] == (
            "F12_LOCAL_19_SOURCE_BYTE_AND_STATIC_IMPORT_CANDIDATE_ONLY_NOT_SIGNED_RUNTIME_IMAGE"
        ),
        "F12_QUALIFICATION_FORGED",
    )
    enforce(doc["source_worktree"] == str(FROZEN_ROOT), "F12_FROZEN_ROOT_SUBSTITUTED")
    enforce(
        doc["git_head"] == SOURCE_HEAD and doc["git_tree"] == SOURCE_TREE
        and doc["previous_f11_head"] == "e0ceb7e564b81597bfd54eba72fd38edae92311e",
        "F12_SOURCE_REVISION_FORGED",
    )
    enforce(doc["original_f11_sha256"] == PREVIOUS_F11_SHA
            and doc["original_count"] == 17 and doc["entry_count"] == 19,
            "F12_F11_RELABELED_OR_WRONG_COUNT")
    enforce(doc["additional_dependency_paths"] == [
        "src/knowledge_engine/m27_ar06_governed_memory_experimental.py",
        "src/knowledge_engine/m27_ar07_compute_policy_experimental.py",
    ], "F12_ADDITIONAL_DEPENDENCIES_MUTATED")
    enforce(
        doc["external_phase_b_qualified"] is False
        and doc["production_authorized"] is False
        and doc["real_executed_image_attested"] is False,
        "F12_RELEASE_PRIVILEGE_INJECTION",
    )
    entries = doc["files"]
    enforce(isinstance(entries, list) and len(entries) == 19, "F12_SOURCE_ENTRY_COUNT")
    found: dict[str, str] = {}
    components: set[str] = set()
    folded: set[str] = set()
    for row in entries:
        enforce(isinstance(row, dict) and set(row) == {"component", "path", "sha256"},
                "F12_MALFORMED_ROW")
        c = row["component"]
        enforce(isinstance(c, str) and c.isascii() and c and c not in components,
                "F12_COMPONENT_COLLISION")
        components.add(c)
        try:
            path = validate_relpath(row["path"])
        except (ValueError, TypeError) as exc:
            raise PackageBlocked("F12_UNSAFE_PATH") from exc
        enforce(path.casefold() not in folded, "F12_PATH_COLLISION")
        folded.add(path.casefold())
        file_name = path.rsplit("/", 1)[-1]
        enforce(file_name in PINS, "F12_UNAPPROVED_SOURCE_EXPORT")
        enforce(row["sha256"] == PINS[file_name], "F12_SOURCE_PIN_MISMATCH")
        found[path] = row["sha256"]
    enforce(set(found) == {"src/knowledge_engine/" + f for f in PINS},
            "F12_SOURCE_UNIVERSE_MISMATCH")
    return tuple(sorted(found.items()))


def scan_imports(raw: bytes, name: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Walk *all* lexical scopes, including lazy imports in functions."""
    try:
        tree = ast.parse(raw, filename=name)
    except (SyntaxError, UnicodeError) as exc:
        raise PackageBlocked("F12_INVALID_SYNTAX") from exc
    local: set[str] = set()
    external: set[str] = set()
    for node in ast.walk(tree):
        specs: list[str] = []
        if isinstance(node, ast.Import):
            specs.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            enforce(node.level == 0, "F12_RELATIVE_IMPORT_AMBIGUITY")
            enforce(node.module is not None, "F12_INTERNAL_IMPORT_AMBIGUITY")
            specs.append(node.module)
        elif isinstance(node, ast.Call):
            fn = node.func
            if (isinstance(fn, ast.Name) and fn.id == "__import__") or (
                isinstance(fn, ast.Attribute) and fn.attr == "import_module"
            ):
                raise PackageBlocked("F12_DYNAMIC_IMPORT_AMBIGUITY")
        for spec in specs:
            root, _, sub = spec.partition(".")
            if root == "knowledge_engine":
                enforce(bool(sub) and sub.count(".") == 0,
                        "F12_INTERNAL_IMPORT_AMBIGUITY")
                local.add("knowledge_engine/" + sub + ".py")
            elif root not in sys.stdlib_module_names:
                external.add(root)
    return tuple(sorted(local)), tuple(sorted(external))


def verify_closure(dependencies: dict[str, dict], inventory: set[str]) -> dict[str, list[str]]:
    enforce("knowledge_engine/" + I02 + ".py" in inventory, "F12_I02_MISSING")
    graph: dict[str, list[str]] = {}
    for name in sorted(inventory - {"knowledge_engine/__init__.py"}):
        enforce(name in dependencies, "F12_DEPENDENCY_SCAN_MISSING")
        children = list(dependencies[name]["internal"])
        graph[name] = children
        for child in children:
            enforce(child in inventory, "F12_DEPENDENCY_CLOSURE_BLOCKED: " + child)
        third_party = dependencies[name]["third_party"]
        enforce(not third_party, "F12_FORBIDDEN_THIRD_PARTY: " + ",".join(third_party))
    # A graph cycle does not automatically violate import semantics, but a real
    # interpreter must prove its ability to import it before claiming success.
    return graph


IMPORT_SCRIPT = r"""
import hashlib, importlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve(strict=True)
names = json.loads(sys.argv[2])
assert sys.flags.isolated == 1 and sys.flags.no_site == 1 and sys.dont_write_bytecode
assert "knowledge_engine" not in sys.modules
assert not any(k.startswith("knowledge_engine.") for k in sys.modules)
assert "sitecustomize" not in sys.modules
sys.path.insert(0, str(root))
assert sys.path[0] == str(root)
modules = []
for name in [ "m27_w4_i02_local_runtime_v1_experimental", *names ]:
    m = importlib.import_module("knowledge_engine." + name)
    target = root / "knowledge_engine" / (name + ".py")
    assert pathlib.Path(m.__file__).resolve(strict=True) == target
    assert pathlib.Path(m.__spec__.origin).resolve(strict=True) == target
    assert m.__dict__ is sys.modules[m.__name__].__dict__
    assert str(root) == str(pathlib.Path(m.__file__).parents[1])
    modules.append({"name": name, "file": str(target), "origin": str(target),
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    "dict_identity": True})
for mod, cls in {
  "m27_w4_i02_local_runtime_v1_experimental": "I02LocalRuntimeV1",
  "m27_w3_ar06_durable_governance_v1_experimental": "DurableMemoryExclusion",
  "m27_w3_ar07_compute_budget_v1_experimental": "LocalComputeBudget",
}.items():
    assert isinstance(getattr(sys.modules["knowledge_engine." + mod], cls), type)
assert len(set(row["name"] for row in modules)) == len(names)
loaded = sorted(k for k in sys.modules if k.startswith("knowledge_engine."))
assert loaded == sorted("knowledge_engine." + n for n in names)
print(json.dumps({"isolated":True, "no_site":True, "sitecustomize":False,
                  "python":list(sys.version_info[:2]), "sys_path":sys.path,
                  "modules":modules,"unexpected_modules":[], "i02_class":True,
                  "ar06_ar07_classes":True},sort_keys=True))
"""


def validate_import_proof(proof: object, extract_root: Path,
                          expected: dict[str, str]) -> None:
    enforce(isinstance(proof, dict) and set(proof) == {
        "isolated", "no_site", "sitecustomize", "python", "sys_path",
        "modules", "unexpected_modules", "i02_class", "ar06_ar07_classes",
    }, "F12_IMPORT_RECEIPT_FORGED")
    enforce(proof["isolated"] is True and proof["no_site"] is True
            and proof["sitecustomize"] is False and proof["python"] == [3, 11],
            "F12_ISOLATION_INVALID")
    enforce(proof["i02_class"] is True and proof["ar06_ar07_classes"] is True,
            "F12_ABI_ORIGIN_UNVERIFIED")
    paths = proof["sys_path"]
    enforce(isinstance(paths, list) and paths and paths[0] == str(extract_root.resolve()),
            "F12_IMPORT_PATH_SHADOWED")
    enforce(all("06_WORKSITES" not in x and "/src" not in x
                for x in paths if isinstance(x, str)),
            "F12_IMPORT_HOST_SOURCE_LEAK")
    enforce(proof["unexpected_modules"] == [], "F12_UNEXPECTED_PACKAGE_MODULE")
    records = proof["modules"]
    enforce(isinstance(records, list) and len(records) == 20,
            "F12_IMPORT_MODULE_COUNT")
    enforce(records[0].get("name") == I02, "F12_I02_NOT_IMPORTED_FIRST")
    enforce({r.get("name") for r in records if isinstance(r, dict)}
            == set(MODULE_NAMES), "F12_IMPORT_MODULE_UNIVERSE")
    for row in records:
        enforce(isinstance(row, dict) and set(row) == {
            "name", "file", "origin", "sha256", "dict_identity",
        }, "F12_IMPORT_ENTRY_FORGED")
        want = (extract_root / "knowledge_engine" / (row["name"] + ".py")).resolve()
        enforce(row["file"] == str(want) and row["origin"] == str(want)
                and row["dict_identity"] is True, "F12_IMPORT_ORIGIN_UNVERIFIED")
        enforce(row["sha256"] == expected["knowledge_engine/" + row["name"] + ".py"],
                "F12_IMPORT_SOURCE_HASH_MISMATCH")


def validate_package_receipt(receipt: object, rows: tuple[dict, ...],
                             archive_sha: str, graph: dict, closure_reason: str) -> None:
    enforce(isinstance(receipt, dict) and set(receipt) == {
        "schema", "builder", "source_head", "source_tree", "manifest_sha256",
        "archive_sha256", "entries", "source_count", "archive_entry_count",
        "dependency_graph", "closure_reason", "run_id", "release_attested",
        "production_authorized", "complete_workload_verified",
        "ci_oci_image_verified", "isolated_import_verdict",
    }, "F12_PACKAGE_RECEIPT_FORGED")
    enforce(receipt["schema"] == SCHEMA and receipt["builder"] == BUILDER,
            "F12_BUILDER_VERSION_FORGED")
    enforce(receipt["source_head"] == SOURCE_HEAD and receipt["source_tree"] == SOURCE_TREE
            and receipt["manifest_sha256"] == MANIFEST_SHA, "F12_RECEIPT_PROVENANCE_FORGED")
    enforce(receipt["archive_sha256"] == archive_sha and receipt["entries"] == list(rows)
            and receipt["source_count"] == 19 and receipt["archive_entry_count"] == 20,
            "F12_ARCHIVE_OR_OFFSETS_FORGED")
    enforce(receipt["dependency_graph"] == graph
            and receipt["closure_reason"] == closure_reason, "F12_DEPENDENCY_RECEIPT_FORGED")
    enforce(isinstance(receipt["run_id"], str) and receipt["run_id"].isascii()
            and len(receipt["run_id"]) >= 8, "F12_RUN_ID_INVALID")
    enforce(receipt["release_attested"] is False
            and receipt["production_authorized"] is False
            and receipt["complete_workload_verified"] is False
            and receipt["ci_oci_image_verified"] is False,
            "F12_FAKE_RELEASE_OR_CI_CERTIFICATION")
    enforce(receipt["isolated_import_verdict"] in {
        "B12_FULL_I02_ISOLATED_MODULE_IMPORT_PASS", "IMPORT_ORIGIN_UNVERIFIED",
    }, "F12_SELF_CLAIMED_IMPORT_PASS")


class OfflineDependencyCompletePackageV1:
    """Byte-accurate diagnostic build; qualified run rejects incomplete closure."""

    def __init__(self, source_root: Path = FROZEN_ROOT,
                 manifest: Path = F12_MANIFEST, scratch: Path | None = None,
                 interpreter: str = INTERPRETER):
        self.source_root = Path(source_root)
        self.manifest = Path(manifest)
        self.scratch = Path(scratch) if scratch else Path(tempfile.gettempdir()) / "b12-scratch"
        self.interpreter = interpreter

    def _git(self, *args: str) -> str:
        try:
            r = subprocess.run(["git", "-C", str(self.source_root), *args],
                               text=True, capture_output=True, check=True, timeout=20)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise PackageBlocked("F12_SOURCE_GIT_UNVERIFIED") from exc
        return r.stdout.strip()

    def verify_source(self) -> tuple[dict[str, bytes], dict[str, dict]]:
        enforce(self.source_root.absolute() == FROZEN_ROOT
                and not self.source_root.is_symlink()
                and self.source_root.resolve(strict=True) == FROZEN_ROOT.resolve(strict=True),
                "F12_FROZEN_ROOT_SUBSTITUTED")
        enforce(self.manifest.absolute() == F12_MANIFEST and not self.manifest.is_symlink(),
                "F12_MANIFEST_SUBSTITUTED")
        raw = self.manifest.read_bytes()
        enforce(digest(raw) == MANIFEST_SHA, "F12_MANIFEST_SHA_MISMATCH")
        try:
            entries = validate_manifest(json.loads(raw))
        except (ValueError, KeyError, TypeError) as exc:
            if isinstance(exc, PackageBlocked):
                raise
            raise PackageBlocked("F12_MANIFEST_JSON_INVALID") from exc
        enforce(self._git("rev-parse", "HEAD") == SOURCE_HEAD, "F12_SOURCE_HEAD_MISMATCH")
        enforce(self._git("rev-parse", "HEAD^{tree}") == SOURCE_TREE, "F12_SOURCE_TREE_MISMATCH")
        enforce(self._git("status", "--porcelain=v1", "-uall") == "",
                "F12_SOURCE_DIRTY")
        sources: dict[str, bytes] = {}
        deps: dict[str, dict] = {}
        for rel, sha in entries:
            path = self.source_root / rel
            enforce(not path.is_symlink() and path.parent.resolve() ==
                    (self.source_root / "src/knowledge_engine").resolve(),
                    "F12_SOURCE_SYMLINK_OR_ALIAS")
            st = path.lstat()
            enforce(stat.S_ISREG(st.st_mode) and not st.st_mode & 0o111
                    and st.st_size <= 2_000_000, "F12_SOURCE_MODE_OR_SIZE")
            enforce(self._git("ls-files", "--stage", "--", rel).startswith("100644 "),
                    "F12_SOURCE_UNTRACKED_OR_MODE")
            data = path.read_bytes()
            enforce(len(data) == st.st_size and digest(data) == sha,
                    "F12_SOURCE_SHA_MISMATCH")
            try:
                snapshot = subprocess.run(["git", "-C", str(self.source_root),
                                           "show", SOURCE_HEAD + ":" + rel],
                                          capture_output=True, check=True, timeout=20).stdout
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                raise PackageBlocked("F12_SOURCE_GIT_BLOB_UNAVAILABLE") from exc
            enforce(snapshot == data, "F12_SOURCE_BLOB_DRIFT")
            try:
                safe_member(rel, data)
            except ValueError as exc:
                raise PackageBlocked("F12_SOURCE_INVALID_SYNTAX_OR_ABI") from exc
            name = archive_name(rel)
            internal, third = scan_imports(data, name)
            sources[name] = data
            deps[name] = {"internal": list(internal), "third_party": list(third)}
        enforce(self._git("rev-parse", "HEAD") == SOURCE_HEAD
                and self._git("status", "--porcelain=v1", "-uall") == "",
                "F12_SOURCE_RACE_OR_DIRTY")
        return sources, deps

    def _build(self, path: Path, source: dict[str, bytes]) -> tuple[str, tuple[dict, ...]]:
        expected = {name: digest(raw) for name, raw in source.items()}
        expected["knowledge_engine/__init__.py"] = digest(b"")
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED,
                             allowZip64=False) as archive:
            for name in sorted(expected):
                archive.writestr(zip_entry(name),
                                 b"" if name.endswith("/__init__.py") else source[name])
        sha = digest(path.read_bytes())
        rows = inspect_archive(path, expected, sha)
        return sha, rows

    def _probe(self, archive: Path, expected: dict[str, str], location: Path) -> dict:
        root = location / "extracted"
        root.mkdir(mode=0o700)
        with zipfile.ZipFile(archive) as z:
            for name in sorted(expected):
                validate_relpath(name, archive=True)
                dest = root / name
                dest.parent.mkdir(exist_ok=True)
                with dest.open("xb") as out:
                    out.write(z.read(name))
                enforce(digest(dest.read_bytes()) == expected[name],
                        "F12_EXTRACTION_HASH_MISMATCH")
        enforce(self.interpreter == INTERPRETER and Path(self.interpreter).is_file(),
                "F12_INTERPRETER_UNPINNED")
        try:
            completed = subprocess.run(
                [self.interpreter, "-I", "-S", "-B", "-c", IMPORT_SCRIPT,
                 str(root), json.dumps(MODULE_NAMES)],
                capture_output=True, text=True, check=True, timeout=30,
                cwd=location, env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
            )
            rec = json.loads(completed.stdout)
            validate_import_proof(rec, root, expected)
            return rec
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
                ValueError, json.JSONDecodeError) as exc:
            raise PackageBlocked("IMPORT_ORIGIN_UNVERIFIED") from exc

    def diagnose(self, *, run_id: str) -> dict:
        """Preserve evidence while keeping a blocker as a blocker, not a release PASS."""
        enforce(isinstance(run_id, str) and run_id.isascii() and len(run_id) >= 8,
                "F12_RUN_ID_INVALID")
        enforce(not self.scratch.is_symlink()
                and self.scratch.absolute() != self.source_root.absolute(),
                "F12_SCRATCH_UNSAFE")
        self.scratch.mkdir(parents=True, exist_ok=True, mode=0o700)
        enforce(not any((self.scratch / n).exists() or (self.scratch / n).is_symlink()
                        for n in OUTPUTS), "F12_DUPLICATE_RUN_OR_REPLAY")
        sources, deps = self.verify_source()
        expected = {k: digest(v) for k, v in sources.items()}
        expected["knowledge_engine/__init__.py"] = digest(b"")
        inventory = set(expected)
        graph = {k: deps[k]["internal"] for k in sorted(deps)}
        closure_reason = ""
        try:
            verify_closure(deps, inventory)
        except PackageBlocked as exc:
            closure_reason = exc.reason
        with (tempfile.TemporaryDirectory(dir=self.scratch, prefix="b12_a_") as a,
              tempfile.TemporaryDirectory(dir=self.scratch, prefix="b12_b_") as b):
            left = Path(a) / "bundle.zip"
            right = Path(b) / "bundle.zip"
            sha_a, rows_a = self._build(left, sources)
            sha_b, rows_b = self._build(right, sources)
            enforce(sha_a == sha_b and rows_a == rows_b
                    and left.read_bytes() == right.read_bytes(),
                    "F12_NONDETERMINISTIC_ZIP")
            try:
                imported = self._probe(left, expected, Path(a))
                import_verdict = "B12_FULL_I02_ISOLATED_MODULE_IMPORT_PASS"
            except PackageBlocked as exc:
                imported = {"error": exc.reason}
                import_verdict = "IMPORT_ORIGIN_UNVERIFIED"
            receipt = {
                "schema": SCHEMA, "builder": BUILDER,
                "source_head": SOURCE_HEAD, "source_tree": SOURCE_TREE,
                "manifest_sha256": MANIFEST_SHA, "archive_sha256": sha_a,
                "entries": list(rows_a), "source_count": 19, "archive_entry_count": 20,
                "dependency_graph": graph, "closure_reason": closure_reason,
                "run_id": run_id, "release_attested": False,
                "production_authorized": False, "complete_workload_verified": False,
                "ci_oci_image_verified": False,
                "isolated_import_verdict": import_verdict,
            }
            validate_package_receipt(receipt, rows_a, sha_a, graph, closure_reason)
            # No release claim; three own scratch outputs only.
            archive_path, receipt_path, import_path = (self.scratch / name for name in OUTPUTS)
            shutil.copyfile(left, archive_path)
            receipt_path.write_bytes(canonical(receipt))
            import_path.write_bytes(canonical(imported))
            enforce(digest(archive_path.read_bytes()) == sha_a
                    and json.loads(receipt_path.read_bytes()) == receipt
                    and json.loads(import_path.read_bytes()) == imported,
                    "F12_TORN_OUTPUT")
            # Independent read-back with original expected SHA and canonical metadata.
            rows_readback = inspect_archive(archive_path, expected, sha_a)
            validate_package_receipt(json.loads(receipt_path.read_bytes()),
                                     rows_readback, sha_a, graph, closure_reason)
            return {
                "status": closure_reason or import_verdict,
                "dependency_closure": closure_reason or "PASS",
                "byte_verdict": "B12_LOCAL_19_SOURCE_BYTES_REPRODUCIBLE_PASS",
                "import_verdict": import_verdict,
                "workload_verdict": "B12_COMPLETE_I02_WORKLOAD_RUN_UNVERIFIED",
                "ci_verdict": "B12_REAL_EXECUTED_OCI_CI_IMAGE_UNVERIFIED",
                "archive_sha256": sha_a, "receipt_sha256": digest(receipt_path.read_bytes()),
                "import_receipt_sha256": digest(import_path.read_bytes()),
                "archives_equal": True, "source_count": len(sources),
                "entry_count": len(rows_a), "paths": list(map(str, (
                    archive_path, receipt_path, import_path))),
            }

    def run(self, *, run_id: str) -> dict:
        result = self.diagnose(run_id=run_id)
        enforce(result["dependency_closure"] == "PASS", result["dependency_closure"])
        enforce(result["import_verdict"] == "B12_FULL_I02_ISOLATED_MODULE_IMPORT_PASS",
                "IMPORT_ORIGIN_UNVERIFIED")
        return result
