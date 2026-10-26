"""Fail-closed Owner Nonprod launcher for a pre-provisioned, authorized secret.

No credentials are obtained from .env, Docker environment, prior canaries,
shell history, or any remote source. An independently approved secret file
must already exist. This launcher neither signs nor releases OCI images.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

ROOT = Path("/home/ubuntu/m27-owner-native-01-runtime")
IMAGE = "m27-owner-native-app:f04-owner-native-01-cloudflare-v8-7aa"
IMAGE_ID = "sha256:d9fa36b3d0f81fbf3d6c009a6ababcf64cddf6dc9b0ae976c614e03de7310863"
C1_HEAD = "7aa58392bcf5f4be493912c8a2817d0e4d08df52"
G01_HEAD = "81eae18f819ab90850bce3b89a3ee9237be68a8d"
RUN_UID = 65532
RUN_NAME = "m27-f04-owner-native-01-cloudflare-single"
SECRET_IN_CONTAINER = "/run/secrets/minimax_api_key"
CLOUDFLARE_ACCOUNT_IN_CONTAINER = "/run/secrets/cloudflare_account_id"
CLOUDFLARE_TOKEN_IN_CONTAINER = "/run/secrets/cloudflare_ai_token"


class Denied(ValueError):
    pass


def require(ok: bool, why: str) -> None:
    if not ok:
        raise Denied(why)


def executable(*args: str) -> str:
    proc = subprocess.run(args, check=False, capture_output=True, timeout=20, text=True)
    require(proc.returncode == 0, "SOURCE_IDENTITY_OR_DOCKER_COMMAND_DENIED")
    return proc.stdout.strip()


def private_file(path: Path) -> None:
    require(path.is_absolute() and not path.is_symlink() and
            not any(ord(ch) < 32 or ch == "," for ch in str(path)),
            "SECRET_PATH_NOT_APPROVED")
    st = path.lstat()
    require(stat.S_ISREG(st.st_mode) and st.st_uid == RUN_UID and
            stat.S_IMODE(st.st_mode) == 0o600 and 20 <= st.st_size <= 512,
            "SECRET_UID_MODE_OR_LENGTH_DENIED")


def build_command(*, approved_secret: Path, cloudflare_account_file: Path,
                  cloudflare_token_file: Path, root: Path = ROOT,
                  image: str = IMAGE, dry_run: bool = False) -> list[str]:
    """Preserve source/root boundaries and use a single scoped Docker mount."""
    require(root == ROOT and image == IMAGE,
            "UNEXPECTED_NONPROD_RUNTIME_ROOT_OR_IMAGE")
    for item in (approved_secret, cloudflare_account_file,
                 cloudflare_token_file):
        private_file(item)
    c1, g01 = root / "c1-git", root / "g01-git"
    private = root / "private"
    for repo, sha in ((c1, C1_HEAD), (g01, G01_HEAD)):
        require(repo.is_dir() and (repo / ".git").is_dir(), "AUTHORIZED_GIT_CHECKOUT_ABSENT")
        require(executable("git", "-c", "safe.directory=" + str(repo), "-C",
                           str(repo), "rev-parse", "HEAD") == sha,
                "PINNED_GIT_HEAD_DRIFT")
        require(not executable("git", "-c", "safe.directory=" + str(repo), "-C",
                               str(repo), "status", "--porcelain", "--untracked-files=all"),
                "PINNED_GIT_DIRTY")
    require(private.is_dir() and not private.is_symlink() and
            private.stat().st_uid == RUN_UID and
            stat.S_IMODE(private.stat().st_mode) == 0o700,
            "OWNER_PRIVATE_DIR_UNAVAILABLE")
    require(executable("docker", "image", "inspect", image,
                       "--format", "{{.Id}}") == IMAGE_ID,
            "EXACT_NONPROD_IMAGE_CONFIG_ID_MISMATCH")
    require(not executable("docker", "ps", "-a", "--filter", "name=^/" + RUN_NAME + "$",
                           "--format", "{{.Names}}"), "SINGLE_TASK_ALREADY_RUNNING")
    # Actual source/controller rights are rechecked by pinned app and C1, not
    # constructed or inferred by this host launcher.
    cmd = ["docker", "run", "--rm", "--pull", "never", "--name", RUN_NAME,
           "--network", "bridge", "--read-only",
           "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m",
           "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
           "--pids-limit", "64", "--memory", "384m", "--cpus", "2",
           "--user", f"{RUN_UID}:{RUN_UID}",
           "--mount", f"type=bind,source={c1},target=/runtime/c1,readonly",
           "--mount", f"type=bind,source={g01},target=/runtime/g01,readonly",
           "--mount", f"type=bind,source={private},target=/runtime/private",
           "--mount", f"type=bind,source={approved_secret},target={SECRET_IN_CONTAINER},readonly",
           "--mount", f"type=bind,source={cloudflare_account_file},target={CLOUDFLARE_ACCOUNT_IN_CONTAINER},readonly",
           "--mount", f"type=bind,source={cloudflare_token_file},target={CLOUDFLARE_TOKEN_IN_CONTAINER},readonly",
           image, "--repo", "/runtime/c1",
           "--fence", "/runtime/private/fence.json",
           "--vendor", "/runtime/g01/tools/g01_vendor",
           "--token", "/runtime/private/client_capability",
           "--evidence", "/runtime/private/evidence_cf_primary_04",
           "--provider-secret", SECRET_IN_CONTAINER,
           "--cloudflare-account-file", CLOUDFLARE_ACCOUNT_IN_CONTAINER,
           "--cloudflare-token-file", CLOUDFLARE_TOKEN_IN_CONTAINER]
    return cmd


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approved-secret-file", type=Path, required=True)
    parser.add_argument("--cloudflare-account-file", type=Path, required=True)
    parser.add_argument("--cloudflare-token-file", type=Path, required=True)
    parser.add_argument("--execute-once", action="store_true")
    args = parser.parse_args()
    try:
        cmd = build_command(approved_secret=args.approved_secret_file,
                            cloudflare_account_file=args.cloudflare_account_file,
                            cloudflare_token_file=args.cloudflare_token_file)
    except (Denied, OSError, subprocess.TimeoutExpired) as exc:
        why = str(exc) if isinstance(exc, Denied) else type(exc).__name__
        print(json.dumps({"status": "OWNER_NONPROD_LAUNCH_FAIL_CLOSED",
                          "reason": why, "model_calls": 0,
                          "signed_or_released": False}, sort_keys=True))
        return 2
    if not args.execute_once:
        print(json.dumps({"status": "LAUNCH_READY_WITH_APPROVED_SECRET",
                          "actual_model_calls": 0,
                          "live_e2e_proven": False, "signed_or_released": False},
                         sort_keys=True))
        return 0
    # No automatic retry on ambiguous provider/network error.
    # Do not print the command: it contains host path to a private file.
    proc = subprocess.run(cmd, check=False, timeout=55)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
