"""W5 B11 deterministic, *local-only* source package witness (not an OCI attestation)."""

# ruff: noqa: E501  # Frozen SHA256 pin rows must preserve exact immutable values.
from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import stat
import subprocess
import tempfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

SCHEMA = "m27.w5.b11.local.source.package/v1"
FREEZE_SCHEMA = "m27.w5.source_freeze_manifest/v1"
HEAD = "e0ceb7e564b81597bfd54eba72fd38edae92311e"
TREE = "eff5db48057a03442f4270e2f4f10bbf7d93831b"
FROZEN_SOURCE_ROOT = "/Users/huaihsuanhuang/Desktop/Chatgpt/M27/M27_VNEXT_MASTER_20261009/06_WORKSITES/W5_L10_AR10_GOVERNED_LEARNING_OFFLINE"
FREEZE_MANIFEST_SHA256 = "6612fa1b6782f524b274025bad471cc3b66d70b6961aeda84d380cb1c7ae8721"
PINNED = dict(
    line.split(" ", 1)
    for line in """
m27_i01_core_local_vertical_v1_experimental.py a8636627d2df692d94794e3dea4149fd18e7812dd655ecf81a3b5ae98d819a3c
m27_ar02_durable_writer_v1_experimental.py ddcd94f3a5ab3c67b4de2bc57cbf6c80a1c07493f1a583351b84b900f220bea6
m27_ar03_verified_rights_v1_experimental.py ab4e6866b758b3a00c0325bec4c482af2e4c150358b24caec12fd33f4acd5c12
m27_ar04_permit_sandbox_v1_experimental.py 6cbf4d739b5baf4419b99e4f744841a7c81e63e2a31eb6a37e894d0d67c8bcb4
m27_ar05_independent_verifier_v1_experimental.py 9bf79427f76cf2ac1f90b59c0186d634388e38991aaa812a5519621a4799f926
m27_w3_ar06_durable_governance_v1_experimental.py 3bf9734b34fa48edae85efbcc1e5abd17d7c19dc11ab2be51355bc5b86df9dcb
m27_w3_ar07_compute_budget_v1_experimental.py 4ef3ccf495e6263998ac0e8b4a3dbbe0aeb626f7503a2de8fe3ee8bbe29147d3
m27_w3_ar08_qa_stream_v1_experimental.py 7da575596ad23e93f284b9a439ac3b8f30782e3e79b7e3f0ba563f5b4866cbc0
m27_w3_ar08_research_recovery_v1_experimental.py 006fc54387af51629f8f6986da381024ce442f371ca1f68bf23164b68ec0cf72
m27_w3_ar08_coding_action_v1_experimental.py 40a0f8154192abfed04fd63ea76605b8b635da09b80d2ddd38adbc8aaed04bb9
m27_w4_i02_local_runtime_v1_experimental.py 34146e0903d55b52b504ca6410c927b7b403a741d37f6cbb4ff1ec263e5b61d8
m27_w4_ar09_independent_harness_v1_experimental.py d9abbc7d303b84d2e5405721877aacaab5664cb1c085e97ccdd6f41d8f07e9c6
m27_w4_d09_corpus_admission_v1_experimental.py b99634b27eb0a5825ff90de82632d014c307d04eaaf681e06622c603fc17a85c
m27_w4_t09_transport_evidence_v1_experimental.py fe632b5a78a507efc8f4dbf7cf2e6bf37ab6a1afb77b1be9a9b69133710a6b0f
m27_w4_p09_external_evidence_v1_experimental.py 455082daeedc84ab671baec7b99109004571788212e8ec4a71bd195b8689a640
m27_w4_e09b_blind_gate_v1_experimental.py a6cecc5ce43b09accca406ce6f423c741a532b3e2383b7d652b91a0d3ca040f4
m27_w5_l10_ar10_candidate_governance_v1_experimental.py 1b909885c54872522a21c66931d585a58b41329f332f773f37abc17d1ff3c6dd
""".strip().splitlines()
)
PUBLIC_ABI = {
    "m27_ar02_durable_writer_v1_experimental.py": "DurableWriterV1",
    "m27_w4_i02_local_runtime_v1_experimental.py": "I02LocalRuntimeV1",
    "m27_w4_ar09_independent_harness_v1_experimental.py": "IndependentOutcomeHarnessV1",
    "m27_w5_l10_ar10_candidate_governance_v1_experimental.py": "AR10CandidateGovernanceV1",
}
PROBES = (
    "m27_ar02_durable_writer_v1_experimental",
    "m27_w4_ar09_independent_harness_v1_experimental",
    "m27_w5_l10_ar10_candidate_governance_v1_experimental",
)
OWNED = frozenset(
    {
        "src/knowledge_engine/m27_w5_b11_local_package_attestor_v1_experimental.py",
        "tests/test_m27_w5_b11_local_package_attestor_v1_experimental.py",
        "docs/m27/m27_w5_b11_local_package_attestor_v1_receipts.md",
    }
)


class AttestationError(ValueError):
    """Fail-closed local provenance violation."""


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise AttestationError(reason)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def validate_relpath(value: object, *, archive: bool = False) -> str:
    require(isinstance(value, str), "path not string")
    require(
        value.isascii() and unicodedata.normalize("NFKC", value) == value, "ambiguous unicode path"
    )
    require(bool(value) and len(value) < 200, "invalid path length")
    require(not any(c in value for c in "\\:\x00\r\n"), "separator or control byte")
    p = PurePosixPath(value)
    require(not p.is_absolute() and str(p) == value, "noncanonical path or traversal")
    require(not any(x in ("", ".", "..") for x in value.split("/")), "dot segment")
    bits = value.split("/")
    if archive:
        require(len(bits) == 2 and bits[0] == "knowledge_engine", "archive package root")
    else:
        require(len(bits) == 3 and bits[:2] == ["src", "knowledge_engine"], "source boundary")
    require(re.fullmatch(r"[a-z0-9_]+\.py", bits[-1]) is not None, "untrusted extension/filename")
    return value


def validate_freeze(doc: object) -> tuple[tuple[str, str], ...]:
    require(isinstance(doc, dict) and doc.get("schema") == FREEZE_SCHEMA, "freeze schema")
    require(doc.get("git_head") == HEAD and doc.get("git_tree") == TREE, "wrong frozen commit/tree")
    require(doc.get("production_authorized") is False, "production assertion")
    require(doc.get("external_phase_b_qualified") is False, "external release assertion")
    require(doc.get("source_worktree") == FROZEN_SOURCE_ROOT, "untrusted frozen source root")
    require(
        set(doc)
        == {
            "schema",
            "date",
            "qualification",
            "source_worktree",
            "git_head",
            "git_tree",
            "master_gate",
            "ar10_gate",
            "external_phase_b_qualified",
            "production_authorized",
            "files",
        },
        "untrusted freeze metadata",
    )
    entries = doc.get("files")
    require(isinstance(entries, list) and len(entries) == 17, "missing or extra source entries")
    found = {}
    folded = set()
    components = set()
    for row in entries:
        require(isinstance(row, dict) and isinstance(row.get("component"), str), "malformed row")
        require(
            row["component"] not in components and row["component"].isascii(), "duplicate component"
        )
        components.add(row["component"])
        p = validate_relpath(row.get("path"))
        require(p not in found and p.casefold() not in folded, "duplicate or casefold source")
        folded.add(p.casefold())
        name = p.split("/")[-1]
        require(name in PINNED, "file not in pinned freeze")
        require(row.get("sha256") == PINNED[name], "source SHA mismatch")
        found[p] = row["sha256"]
    require(
        set(found) == {"src/knowledge_engine/" + n for n in PINNED}, "unexpected freeze universe"
    )
    # The externally frozen F11 source manifest is trusted byte-for-byte, then canonicalized.
    return tuple(sorted(found.items()))


def safe_member(filename: str, content: bytes) -> None:
    validate_relpath(filename)
    require(len(content) <= 2_000_000 and len(content) > 0, "source size")
    require(not content.startswith(b"\xef\xbb\xbf"), "byte order mark")
    require(b"\x00" not in content, "binary injected")
    try:
        tree = ast.parse(content, filename=filename)
    except (SyntaxError, UnicodeError) as exc:
        raise AttestationError("invalid source syntax") from exc
    if filename.split("/")[-1] in PUBLIC_ABI:
        names = {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
        require(PUBLIC_ABI[filename.split("/")[-1]] in names, "public ABI missing")


def archive_name(src: str) -> str:
    return src.removeprefix("src/")


def inspect_dependencies(content: bytes) -> tuple[str, ...]:
    tree = ast.parse(content)
    deps = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("knowledge_engine.")
        ):
            deps.add(node.module.split(".")[1] + ".py")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("knowledge_engine."):
                    deps.add(alias.name.split(".")[1] + ".py")
    return tuple(sorted(deps))


def zip_entry(name: str) -> zipfile.ZipInfo:
    item = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    item.compress_type = zipfile.ZIP_STORED
    item.create_system = 3
    item.external_attr = 0o100644 << 16
    return item


def inspect_archive(
    archive: Path, expected: dict[str, str], expected_digest: str
) -> tuple[dict, ...]:
    require(archive.is_file() and not archive.is_symlink(), "archive missing/symlink")
    before = digest(archive.read_bytes())
    require(
        before == expected_digest and archive.stat().st_size <= 40_000_000, "archive digest/size"
    )
    rows = []
    try:
        with zipfile.ZipFile(archive) as z:
            infos = z.infolist()
            names = [info.filename for info in infos]
            require(names == sorted(expected), "duplicate/missing/unsorted archive entry")
            require(len(set(x.casefold() for x in names)) == len(names), "archive collision")
            require(z.comment == b"", "archive comments not canonical")
            for item in infos:
                name = validate_relpath(item.filename, archive=True)
                require(item.compress_type == zipfile.ZIP_STORED, "compression changed")
                require(item.date_time == (1980, 1, 1, 0, 0, 0), "nondeterministic date")
                require(item.extra == b"" and item.comment == b"", "archive metadata injection")
                require(
                    item.create_system == 3 and item.external_attr >> 16 == 0o100644,
                    "archive mode/symlink",
                )
                require(item.file_size <= 2_000_000, "oversized archive entry")
                raw = z.read(item)
                require(
                    digest(raw) == expected[name] and len(raw) == item.file_size, "payload changed"
                )
                rows.append(
                    {
                        "entry": name,
                        "sha256": digest(raw),
                        "length": len(raw),
                        "header_offset": item.header_offset,
                        "data_offset": item.header_offset
                        + 30
                        + len(name.encode())
                        + len(item.extra),
                    }
                )
    except (OSError, zipfile.BadZipFile, EOFError, RuntimeError, ValueError) as exc:
        if isinstance(exc, AttestationError):
            raise
        raise AttestationError("invalid/truncated ZIP") from exc
    require(digest(archive.read_bytes()) == before, "archive changed during verification")
    return tuple(rows)


def validate_receipt(receipt: dict, *, expected_sha: str, rows: tuple[dict, ...]) -> None:
    require(receipt.get("schema") == SCHEMA, "builder version")
    require(receipt.get("git_head") == HEAD and receipt.get("git_tree") == TREE, "I02 lineage")
    require(receipt.get("archive_sha256") == expected_sha, "rollback or replay digest")
    require(receipt.get("entries") == list(rows), "manifest entry or offset mismatch")
    require(
        receipt.get("immutable") is True and receipt.get("release_attested") is False,
        "release claim",
    )
    require(receipt.get("builder") == "zip-stored-1980-100644-v1", "builder metadata changed")
    require(receipt.get("entry_count") == len(rows), "archive count changed")
    require(
        set(receipt)
        == {
            "schema",
            "git_head",
            "git_tree",
            "freeze_manifest_sha256",
            "archive_sha256",
            "immutable",
            "release_attested",
            "entry_count",
            "entries",
            "dependencies_unfrozen",
            "package_root",
            "builder",
            "import_probe_modules",
        },
        "untrusted package metadata",
    )
    require("tag" not in receipt and "signature" not in receipt, "mutable tag/signature injection")


def validate_import_receipt(receipt: object, root: Path, expected: dict[str, str]) -> None:
    require(isinstance(receipt, dict) and receipt.get("isolated") is True, "not isolated")
    require(
        receipt.get("no_site") is True and receipt.get("sitecustomize") is False, "site injection"
    )
    require(receipt.get("python") == [3, 11], "unpinned interpreter")
    paths = receipt.get("sys_path")
    require(
        isinstance(paths, list) and bool(paths) and paths[0] == str(root.resolve()),
        "root precedence drift",
    )
    imports = receipt.get("modules")
    require(isinstance(imports, list) and len(imports) == len(PROBES), "missing import origin")
    require(
        {x.get("name") for x in imports if isinstance(x, dict)} == set(PROBES), "wrong module keys"
    )
    for m in imports:
        require(isinstance(m, dict), "invalid import record")
        wanted = (root / "knowledge_engine" / (m["name"] + ".py")).resolve()
        require(
            m.get("origin") == str(wanted) and m.get("file") == str(wanted), "side-loaded import"
        )
        require(
            m.get("sha256") == expected["knowledge_engine/" + m["name"] + ".py"],
            "import bytes drift",
        )
    require(receipt.get("other_package_modules") == [], "unexpected preloaded code")


IMPORT_PROBE_SCRIPT = r"""
import hashlib, importlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
names = json.loads(sys.argv[2])
assert sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode
assert 'knowledge_engine' not in sys.modules and str(root) not in sys.path
sys.path.insert(0, str(root))
mods = []
for name in names:
    m = importlib.import_module("knowledge_engine." + name)
    p = (root / "knowledge_engine" / (name + ".py")).resolve()
    assert pathlib.Path(m.__file__).resolve() == p
    assert pathlib.Path(m.__spec__.origin).resolve() == p
    mods.append({"name": name, "file": str(p), "origin": str(p),
                 "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
extra = [k for k in sys.modules if k.startswith("knowledge_engine.")
         and k not in {"knowledge_engine." + n for n in names}]
print(json.dumps({"isolated": True, "no_site": True,
                  "sitecustomize": "sitecustomize" in sys.modules,
                  "python": list(sys.version_info[:2]), "sys_path": sys.path,
                  "modules": mods, "other_package_modules": sorted(extra)},
                 sort_keys=True))
"""


class OfflinePackageAttestorV1:
    """Witnesses pinned source bytes, two canonical packages, and isolated fixture imports."""

    def __init__(
        self,
        source_root: Path,
        freeze_manifest: Path,
        scratch_root: Path,
        interpreter: str = "/Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python",
    ):
        self.source_root = Path(source_root).resolve(strict=True)
        self.freeze_manifest = Path(freeze_manifest)
        self.scratch_root = Path(scratch_root)
        self.interpreter = interpreter

    def _git(self, *args: str) -> str:
        out = subprocess.run(
            ["git", "-C", str(self.source_root), *args],
            check=True,
            text=True,
            capture_output=True,
            timeout=15,
        )
        return out.stdout.strip()

    def verify_source(self) -> tuple[dict[str, bytes], dict[str, list[str]]]:
        raw = self.freeze_manifest.read_bytes()
        require(digest(raw) == FREEZE_MANIFEST_SHA256, "freeze manifest changed")
        try:
            entries = validate_freeze(json.loads(raw))
        except (ValueError, KeyError) as exc:
            raise AttestationError("invalid freeze JSON") from exc
        require(self._git("rev-parse", "HEAD") == HEAD, "dirty/replaced HEAD")
        require(self._git("rev-parse", "HEAD^{tree}") == TREE, "wrong source tree")
        status = self._git("status", "--porcelain=v1", "-uall")
        for line in status.splitlines():
            require(line[:2] in ("??", "A ", " A") and line[3:] in OWNED, "source tree dirty")
        result, deps = {}, {}
        for relative, expected_sha in entries:
            p = self.source_root / relative
            require(
                p.parent.resolve() == (self.source_root / "src/knowledge_engine").resolve(),
                "source outside boundary",
            )
            st = p.lstat()
            require(
                stat.S_ISREG(st.st_mode) and not (st.st_mode & 0o111), "source executable/symlink"
            )
            require(st.st_size <= 2_000_000, "oversized source")
            require(
                self._git("ls-files", "--stage", "--", relative).startswith("100644 "),
                "git mode mismatch",
            )
            data = p.read_bytes()
            require(
                len(data) == st.st_size and digest(data) == expected_sha, "source bytes mismatch"
            )
            safe_member(relative, data)
            result[archive_name(relative)] = data
            deps[archive_name(relative)] = list(inspect_dependencies(data))
        require(self._git("rev-parse", "HEAD") == HEAD, "source commit raced")
        require(
            self._git("status", "--porcelain=v1", "-uall") == status, "source dirty during snapshot"
        )
        return result, deps

    def _build(self, output: Path, source: dict[str, bytes]) -> tuple[str, tuple[dict, ...]]:
        expected = {k: digest(v) for k, v in source.items()}
        expected["knowledge_engine/__init__.py"] = digest(b"")
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as z:
            for name in sorted(expected):
                z.writestr(zip_entry(name), b"" if name.endswith("/__init__.py") else source[name])
        archive_sha = digest(output.read_bytes())
        rows = inspect_archive(output, expected, archive_sha)
        return archive_sha, rows

    def _probe(self, archive: Path, expected: dict[str, str], location: Path) -> dict:
        target = location / "runtime"
        target.mkdir(mode=0o700)
        with zipfile.ZipFile(archive) as z:
            for name in sorted(expected):
                data = z.read(name)
                dest = target / name
                dest.parent.mkdir(exist_ok=True)
                with dest.open("xb") as f:
                    f.write(data)
                require(digest(dest.read_bytes()) == expected[name], "extraction differs")
        require(Path(self.interpreter).is_file(), "pinned interpreter unavailable")
        cmd = [
            self.interpreter,
            "-I",
            "-S",
            "-B",
            "-c",
            IMPORT_PROBE_SCRIPT,
            str(target.resolve()),
            json.dumps(PROBES),
        ]
        try:
            out = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                cwd=location,
                timeout=20,
                env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
            )
            record = json.loads(out.stdout)
            validate_import_receipt(record, target, expected)
            return record
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            ValueError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            raise AttestationError(
                "IMPORT_ORIGIN_UNVERIFIED: fresh isolated interpreter failed"
            ) from exc

    def run(self) -> dict:
        require(not self.scratch_root.is_symlink(), "scratch symlink")
        self.scratch_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        require(
            self.scratch_root.resolve() != self.source_root
            and self.source_root not in self.scratch_root.resolve().parents,
            "scratch overlaps Git",
        )
        source, deps = self.verify_source()
        expected = {k: digest(v) for k, v in source.items()}
        expected["knowledge_engine/__init__.py"] = digest(b"")
        with (
            tempfile.TemporaryDirectory(dir=self.scratch_root, prefix="b11_a_") as a,
            tempfile.TemporaryDirectory(dir=self.scratch_root, prefix="b11_b_") as b,
        ):
            left = Path(a) / "bundle.zip"
            right = Path(b) / "bundle.zip"
            sha_a, rows_a = self._build(left, source)
            sha_b, rows_b = self._build(right, source)
            require(
                sha_a == sha_b and left.read_bytes() == right.read_bytes() and rows_a == rows_b,
                "nonreproducible build",
            )
            dep_missing = {
                k: [x for x in v if "knowledge_engine/" + x not in expected]
                for k, v in deps.items()
                if any("knowledge_engine/" + x not in expected for x in v)
            }
            receipt = {
                "schema": SCHEMA,
                "git_head": HEAD,
                "git_tree": TREE,
                "freeze_manifest_sha256": FREEZE_MANIFEST_SHA256,
                "archive_sha256": sha_a,
                "immutable": True,
                "release_attested": False,
                "entry_count": len(rows_a),
                "entries": list(rows_a),
                "dependencies_unfrozen": dep_missing,
                "package_root": "knowledge_engine",
                "builder": "zip-stored-1980-100644-v1",
                "import_probe_modules": list(PROBES),
            }
            validate_receipt(receipt, expected_sha=sha_a, rows=rows_a)
            probe = self._probe(left, expected, Path(a))
            # Committing a result only after both byte-level checks and actual import.
            durable = self.scratch_root / "B11_LOCAL_SOURCE_PACKAGE.zip"
            sidecar = self.scratch_root / "B11_LOCAL_SOURCE_PACKAGE_MANIFEST.json"
            import_sidecar = self.scratch_root / "B11_IMPORT_ORIGIN_FIXTURE.json"
            require(
                not any(p.is_symlink() for p in (durable, sidecar, import_sidecar)),
                "scratch output symlink",
            )
            for file_path in (durable, sidecar, import_sidecar):
                require(not file_path.exists(), "replayed output or concurrent writer")
            shutil.copyfile(left, durable)
            sidecar.write_bytes(canonical(receipt))
            import_sidecar.write_bytes(canonical(probe))
            require(digest(durable.read_bytes()) == sha_a, "torn final write")
            require(
                digest(sidecar.read_bytes()) == digest(canonical(receipt)), "manifest torn write"
            )
            return {
                "package_sha256": sha_a,
                "manifest_sha256": digest(sidecar.read_bytes()),
                "import_receipt_sha256": digest(import_sidecar.read_bytes()),
                "archive_path": str(durable),
                "manifest_path": str(sidecar),
                "import_receipt_path": str(import_sidecar),
                "source_files": len(source),
                "package_entries": len(rows_a),
                "missing_unfrozen_dependencies": dep_missing,
                "verdict_local": "B11_LOCAL_REPRODUCIBLE_BYTES_PASS",
                "verdict_fixture": "B11_IMPORT_ORIGIN_FIXTURE_VERIFIED",
                "verdict_full_i02_runtime": "IMPORT_ORIGIN_UNVERIFIED",
                "verdict_release": "B11_REAL_RUNTIME_IMAGE_ATTESTATION_UNVERIFIED",
            }
