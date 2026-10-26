"""Owner Native App: Cloudflare-primary provider wired to unchanged C1 server."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import m27_c1_dev_minimax_a05_e2e as c1dev
import m27_c1_m26_provider_parity_nonprod as parity
import native_cloudflare_provider as cloudflare
import native_https_provider as direct

def require(ok,reason):
    if not ok:raise ValueError(reason)

def terminal_result(evidence:Path)->dict:
    record=evidence/"C1_REAL_MINIMAX_DEV_RUN_RESULT.json"
    require(record.is_file() and not record.is_symlink(),
            "NATIVE_E2E_RESULT_MISSING")
    result=json.loads(record.read_bytes())
    require(type(result) is dict,"NATIVE_E2E_RESULT_INVALID")
    journal=evidence/"C1_DEV_REAL_PROVIDER_AND_CLIENT.jsonl"
    require(journal.is_file() and not journal.is_symlink(),
            "NATIVE_E2E_JOURNAL_MISSING")
    identities=[]
    for raw in journal.read_text().splitlines():
        item=json.loads(raw)
        if item.get("event")=="real_provider_identity":
            identities.append(item.get("model"))
    return {
        "provider_calls":result.get("actual_real_provider_call_count"),
        "provider_done":result.get("real_provider_done_observed"),
        "native_acks":result.get("local_native_ack_count"),
        "client_exit":result.get("client_process_exit"),
        "primary_model":identities[-1] if identities else None,
    }

def require_complete(result:dict)->None:
    require(result=={"provider_calls":1,"provider_done":True,
                     "native_acks":2,"client_exit":0,
                     "primary_model":"@cf/openai/gpt-oss-120b"},
            "NATIVE_E2E_TERMINAL_OR_ACK_INCOMPLETE")

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
            {"repo","fence","vendor","token","evidence","provider_secret",
             "cloudflare_account_file","cloudflare_token_file"},
            "INVALID_NATIVE_APP_RUN_ARGUMENTS")
    secret=Path(args["provider_secret"])
    def fallback():
        # The backup is initialized only after the frozen parity router has
        # accepted an eligible pre-text Cloudflare infrastructure failure.
        pinned_vendor(Path(args["vendor"]))
        yield from direct.stream(provider_secret=secret,prompt=c1dev.PROMPT)
    original=parity.cloudflare_first_with_minimax_backup
    parity.cloudflare_first_with_minimax_backup=lambda *,prompt,vendor: original(
        prompt=prompt,vendor=vendor,
        primary_fn=lambda value: cloudflare.stream(
            account_file=Path(args["cloudflare_account_file"]),
            token_file=Path(args["cloudflare_token_file"]),prompt=value),
        fallback_fn=fallback)
    sys.argv=[str(Path(c1dev.__file__)),"run",
              "--repo",args["repo"],"--fence",args["fence"],
              "--vendor",args["vendor"],"--token",args["token"],
              "--evidence",args["evidence"],"--provider-mode","m26-parity-direct"]
    c1dev.main()
    result=terminal_result(Path(args["evidence"]))
    require_complete(result)
    return result

if __name__=="__main__":
    raise SystemExit("OWNER_NATIVE_RUNNER_NOT_STANDALONE")
