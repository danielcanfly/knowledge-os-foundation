"""Owner Native App: pinned vendor+in-container provider to unchanged C1 server."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import m27_c1_dev_minimax_a05_e2e as c1dev
import native_https_provider as direct

def require(ok,reason):
    if not ok:raise ValueError(reason)

def pinned_vendor(vendor:Path)->None:
    vendor=vendor.resolve(strict=True)
    require(vendor.name=="g01_vendor" and vendor.is_dir(),
            "UNQUALIFIED_G01_VENDOR")
    for name,expected in c1dev.PINNED.items():
        require(hashlib.sha256((vendor/name).read_bytes()).hexdigest()==expected,
                "PINNED_VENDOR_SHA_DRIFT")
    repo=vendor.parent.parent
    head=subprocess.run(["git","-C",str(repo),"rev-parse","HEAD"],
                        capture_output=True,text=True,timeout=10,check=True).stdout.strip()
    dirty=subprocess.run(["git","-C",str(repo),"status","--porcelain","--untracked-files=all"],
                         capture_output=True,text=True,timeout=10,check=True).stdout.strip()
    require(head==c1dev.VENDOR_GIT and not dirty,"G01_VENDOR_GIT_OR_WORKTREE_DRIFT")

def run(args):
    # This runner is physically inside the locked Owner Nonprod OCI image.
    # It does not substitute a source fake, third-party verifier, or old VM SSH.
    require(type(args) is dict and set(args)==
            {"repo","fence","vendor","token","evidence","provider_secret"},
            "INVALID_NATIVE_APP_RUN_ARGUMENTS")
    vendor=Path(args["vendor"])
    pinned_vendor(vendor)
    secret=Path(args["provider_secret"])
    # Verify owner/OS secret without emitting or copying secret bytes.
    key=direct.secret(secret)
    del key
    c1dev.vendor_generator=lambda v: (lambda: direct.stream(
        provider_secret=secret,prompt=c1dev.PROMPT))
    sys.argv=[str(Path(c1dev.__file__)),"run",
              "--repo",args["repo"],"--fence",args["fence"],
              "--vendor",args["vendor"],"--token",args["token"],
              "--evidence",args["evidence"],"--provider-mode","minimax-dev"]
    c1dev.main()

if __name__=="__main__":
    raise SystemExit("OWNER_NATIVE_RUNNER_NOT_STANDALONE")
