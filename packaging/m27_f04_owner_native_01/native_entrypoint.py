"""One-owner M27 NONPROD native App entrypoint.

Runs the exact frozen 7aa C1 provider -> source verifier -> two real OS client
ACK implementation. This entrypoint does not provide an external issuer,
redefine formal F04 admission, or authorize a provider call on its own.
Runtime source, rights fence, G01 vendor, and capability are mounted, not baked.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ABI = "m27.f04.owner-native-app/v1"
C1_HEAD = "7aa58392bcf5f4be493912c8a2817d0e4d08df52"
C1_TREE = "63ff1c5f0c41c7e70701ee688d1f6d70b855dbcd"
SAFE_MODE = "OWNER_CONTROLLED_NONPROD_ONLY"
C1_ENTRY = "m27_c1_dev_minimax_a05_e2e.py"

class Denied(ValueError):
    pass

def require(condition: bool, reason: str) -> None:
    if not condition:
        raise Denied(reason)

def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def git(repo: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, timeout=15, check=False)
    require(p.returncode == 0, "FROZEN_GIT_COMMAND_DENIED")
    return p.stdout.decode("utf-8").strip()

def check_source_lock(source_root: Path, lock_path: Path) -> dict:
    require(source_root.is_dir() and not source_root.is_symlink(),
            "IMAGE_SOURCE_DIRECTORY_INVALID")
    lock = json.loads(lock_path.read_bytes())
    require(type(lock) is dict and set(lock) == {"schema", "head", "tree", "modules"} and
            lock["schema"] == ABI + ".source-lock/v1" and
            lock["head"] == C1_HEAD and lock["tree"] == C1_TREE and
            type(lock["modules"]) is dict and len(lock["modules"]) == 15,
            "IMAGE_SOURCE_LOCK_INCORRECT")
    seen = set()
    for name, expected in lock["modules"].items():
        require(type(name) is str and
                re.fullmatch(r"m27_[a-z0-9_]+[.]py", name) is not None and
                type(expected) is str and re.fullmatch(r"[0-9a-f]{64}", expected) is not None,
                "IMAGE_LOCK_MEMBER_INVALID")
        p = source_root / name
        require(p.is_file() and not p.is_symlink() and
                sha(p.read_bytes()) == expected,
                "IMAGE_SOURCE_SHA256_MISMATCH")
        seen.add(name)
    require(C1_ENTRY in seen, "MODEL_CLIENT_ENTRY_NOT_IN_IMAGE")
    physical = {p.name for p in source_root.iterdir() if p.suffix == ".py"}
    require(physical == seen, "UNLISTED_IMAGE_SOURCE_MODULE")
    return {"source_module_count": len(seen), "source_lock_sha256": sha(lock_path.read_bytes())}

def owner_only_file(path: Path) -> None:
    st = path.lstat()
    require(stat.S_ISREG(st.st_mode) and st.st_uid == os.geteuid() and
            (st.st_mode & 0o077) == 0 and st.st_size > 0 and st.st_size < 2048,
            "CAPABILITY_FILE_OWNER_MODE_DENIED")

def preflight(args) -> dict:
    require(os.geteuid() != 0, "ROOT_NATIVE_PRODUCT_DENIED")
    require(args.provider_mode == "m26-parity-direct", "UNAUTHORIZED_PROVIDER_ROUTE")
    root = Path(args.source_root)
    pinned = check_source_lock(root, Path(args.source_lock))
    repo = Path(args.repo)
    require(repo.is_dir() and not repo.is_symlink() and (repo / ".git").exists(),
            "PINNED_RUNTIME_REPO_UNAVAILABLE")
    require(git(repo, "rev-parse", "HEAD") == C1_HEAD and
            git(repo, "rev-parse", "HEAD^{tree}") == C1_TREE,
            "MOUNTED_REPO_HEAD_TREE_DRIFT")
    require(not git(repo, "status", "--porcelain", "--untracked-files=all"),
            "MOUNTED_REPO_NOT_CLEAN")
    token = Path(args.token)
    owner_only_file(token)
    require(token.parent.stat().st_uid == os.geteuid() and
            stat.S_IMODE(token.parent.stat().st_mode) == 0o700 and
            not token.parent.is_symlink() and
            not (token.parent / "c1.sock").exists(),
            "REPLAY_OR_SOCKET_PRIVATE_DIR_DENIED")
    evidence = Path(args.evidence)
    require(evidence.is_dir() and not evidence.is_symlink() and
            evidence.stat().st_uid == os.geteuid() and
            stat.S_IMODE(evidence.stat().st_mode) == 0o700 and
            not any(evidence.iterdir()),
            "EVIDENCE_MUST_BE_EMPTY_OWNER_PRIVATE")
    for path, why in ((Path(args.fence), "A05_RIGHTS_FENCE_NOT_MOUNTED"),
                      (Path(args.vendor), "PINNED_VENDOR_NOT_MOUNTED")):
        require(path.exists() and not path.is_symlink(), why)
    # A real provisioned owner-only secret is required before ANY model effect.
    # The actual credential bytes remain inside the Linux runtime only.
    for secret in (args.provider_secret, args.cloudflare_account_file,
                   args.cloudflare_token_file):
        owner_only_file(Path(secret))
    # Provider vendor hashes/Git HEAD and all A05 release/ACL/TTL/revoke
    # checks are done by frozen C1 7aa; never weaken these at the wrapper.
    return {"abi": ABI, "route": "Cloudflare Workers AI primary; MiniMax fallback",
            "source_head": C1_HEAD, "source_tree": C1_TREE, **pinned}

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "fence", "vendor", "token", "evidence"):
        ap.add_argument("--" + name, required=True)
    ap.add_argument("--source-root", default="/opt/m27/knowledge_engine")
    ap.add_argument("--source-lock", default="/opt/m27/app/source_lock.json")
    ap.add_argument("--provider-mode", default="m26-parity-direct")
    ap.add_argument("--provider-secret", default="/run/secrets/minimax_api_key")
    ap.add_argument("--cloudflare-account-file", default="/run/secrets/cloudflare_account_id")
    ap.add_argument("--cloudflare-token-file", default="/run/secrets/cloudflare_ai_token")
    a = ap.parse_args()
    try:
        preflight(a)
    except (Denied, OSError, ValueError, subprocess.TimeoutExpired,
            json.JSONDecodeError) as exc:
        reason = str(exc) if isinstance(exc, Denied) else type(exc).__name__
        print(json.dumps({"status": "NATIVE_APP_FAIL_CLOSED",
                          "reason": reason[:90], "provider_calls": 0,
                          "formal_f04_pass": False}, sort_keys=True))
        raise SystemExit(2)
    # Native transport runs HTTPS in THIS image/process group, not SSH to the
    # legacy canary. Frozen C1 server/OS Client/semantic verifier remain 7aa.
    try:
        import native_runner
        result = native_runner.run({"repo": a.repo, "fence": a.fence,
                                    "vendor": a.vendor, "token": a.token,
                                    "evidence": a.evidence,
                                    "provider_secret": a.provider_secret,
                                    "cloudflare_account_file": a.cloudflare_account_file,
                                    "cloudflare_token_file": a.cloudflare_token_file})
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError):
        # No raw credential, exception message, or provider header may appear
        # in the output. A missing runtime secret is NOT an authentication
        # substitute and is never allowed to trigger a provider request.
        print(json.dumps({"status": "NATIVE_APP_FAIL_CLOSED",
                          "reason": "OWNER_RUNTIME_DEPENDENCY_OR_PROVIDER_SECRET_DENIED",
                          "provider_calls": None, "formal_f04_pass": False},
                         sort_keys=True))
        raise SystemExit(2)
    print(json.dumps({"status": "NATIVE_APP_E2E_COMPLETE",
                      **result, "formal_f04_pass": False}, sort_keys=True))

if __name__ == "__main__":
    main()
