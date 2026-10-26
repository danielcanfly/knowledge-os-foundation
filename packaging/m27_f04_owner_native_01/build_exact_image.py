"""Reproducible exact-source native app builder for authorized Oracle AMD64 Docker.

Only frozen 15 C1 Git blobs plus committed wrapper, lock and Dockerfile enter
the build. No .git, source-rights fence, vendor keys, credentials, or .env.
A local Docker CONFIG ID is explicitly NOT a signed OCI MANIFEST digest.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile

C1_HEAD = "7aa58392bcf5f4be493912c8a2817d0e4d08df52"
C1_TREE = "63ff1c5f0c41c7e70701ee688d1f6d70b855dbcd"
TAG = "m27-owner-native-app:f04-owner-native-01-cloudflare-v7-7aa"
PACKAGE = "packaging/m27_f04_owner_native_01"
MAX_BUILD_CONTEXT = 900_000
REMOTE = r"""
import hashlib,io,json,os,pathlib,re,subprocess,sys,tarfile,tempfile
def sha(b):return hashlib.sha256(b).hexdigest()
def check(ok,c):
 if not ok:raise SystemExit(c)
m=json.loads(sys.argv[1])
data=sys.stdin.buffer.read(900001)
check(len(data)<=900000 and sha(data)==m["context_sha256"],"CONTEXT_SHA_OR_SIZE_DENIED")
with tempfile.TemporaryDirectory(prefix="m27-f04-owner-native-",dir="/tmp") as t:
 root=pathlib.Path(t); physical={}
 with tarfile.open(fileobj=io.BytesIO(data),mode="r:") as tf:
  parts=tf.getmembers()
  check(len(parts)==21,"EXACT_21_BUILD_FILES_REQUIRED")
  for p in parts:
   check(p.isfile() and not p.issym() and not p.islnk() and
         p.name in m["files"] and p.name not in physical and
         p.uid==0 and p.gid==0 and p.mtime==0 and p.mode==0o444,
         "UNSAFE_CONTEXT_MEMBER")
   b=tf.extractfile(p).read()
   check(sha(b)==m["files"][p.name],"BUILD_CONTEXT_FILE_SHA_MISMATCH")
   path=root/p.name;path.parent.mkdir(parents=True,exist_ok=True)
   path.write_bytes(b)
   physical[p.name]=sha(b)
  check(physical==m["files"],"CONTEXT_SOURCE_SET_DRIFT")
 cmd=["docker","build","--pull=false","--platform","linux/amd64",
      "--progress=plain","-t",m["tag"],str(root)]
 try:p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=240)
 except subprocess.TimeoutExpired:raise SystemExit("NATIVE_DOCKER_BUILD_TIMEOUT")
 (root/"build.log").write_bytes(p.stdout+p.stderr)
 check(p.returncode==0,"NATIVE_DOCKER_BUILD_FAILED_EXIT_"+str(p.returncode)+"_LOG_SHA256_"+sha(p.stdout+p.stderr))
 inspect=subprocess.run(["docker","image","inspect",m["tag"]],capture_output=True,timeout=15)
 check(inspect.returncode==0,"NEW_IMAGE_INSPECT_FAILED")
 item=json.loads(inspect.stdout)[0]
 check(item["Os"]=="linux" and item["Architecture"]=="amd64","NOT_REAL_LINUX_AMD64")
 # This is a real container App invocation, not a CLI-import or --help.
 # Missing mounts must be rejected before any provider effect.
 cmd=["docker","run","--rm","--pull","never","--network","none",
      "--read-only","--tmpfs","/tmp:rw,noexec,nosuid,size=32m",
      "--cap-drop","ALL","--security-opt","no-new-privileges",
      "--pids-limit","64","--memory","256m","--cpus","1",
      "--user","65532:65532",m["tag"],
      "--repo","/nonexistent","--fence","/nonexistent",
      "--vendor","/nonexistent","--token","/nonexistent",
      "--evidence","/nonexistent"]
 try:negative=subprocess.run(cmd,capture_output=True,timeout=50)
 except subprocess.TimeoutExpired:raise SystemExit("FAIL_CLOSED_CONTAINER_TIMEOUT")
 check(negative.returncode==2 and
       b"NATIVE_APP_FAIL_CLOSED" in negative.stdout and
       b"PINNED_RUNTIME_REPO_UNAVAILABLE" in negative.stdout,
       "REAL_APP_FAIL_CLOSED_NEGATIVE_NOT_PROVEN")
 print(json.dumps({
  "schema":"m27.f04.owner-native-lnx-amd64-build/v1",
  "status":"NATIVE_APP_IMAGE_BUILD_AND_FAIL_CLOSED_BOOT_PASS",
  "tag":m["tag"],"os":item["Os"],"arch":item["Architecture"],
  "image_config_id":item["Id"],"image_repo_digests":item.get("RepoDigests") or [],
  "app_run_exit":negative.returncode,
  "actual_app_denial":"PINNED_RUNTIME_REPO_UNAVAILABLE",
  "source_modules":15,"source_head":m["source_head"],
  "source_tree":m["source_tree"],"app_head":m["app_head"],
  "context_sha256":sha(data),"build_log_sha256":sha(p.stdout+p.stderr),
  "model_called_inside_container":False,
  "dual_os_client_acks_inside_container":0,
  "signature":None,"sbom_full_spdx":None,"rollback_executed":False,
  "original_formal_f04_pass":False},sort_keys=True))
"""
def run_git(repo: Path, *args: str) -> bytes:
    p = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, timeout=25)
    if p.returncode:
        raise RuntimeError("GIT_SOURCE_LOOKUP_FAILED")
    return p.stdout

def build_context(repo: Path) -> tuple[bytes,dict]:
    head=run_git(repo,"rev-parse","HEAD").decode().strip()
    if run_git(repo,"status","--porcelain","--untracked-files=all").strip():
        raise RuntimeError("BUILDER_REQUIRES_COMMITTED_CLEAN_TREE")
    lock=json.loads(run_git(repo,"show",head+":"+PACKAGE+"/source_lock.json"))
    if lock["head"]!=C1_HEAD or lock["tree"]!=C1_TREE or len(lock["modules"])!=15:
        raise RuntimeError("INVALID_C1_7AA_LOCK")
    data={}
    for name,expected in lock["modules"].items():
        raw=run_git(repo,"show",C1_HEAD+":src/knowledge_engine/"+name)
        if hashlib.sha256(raw).hexdigest()!=expected:
            raise RuntimeError("C1_GIT_BLOB_LOCK_MISMATCH")
        data["knowledge_engine/"+name]=raw
    for name in ("Dockerfile","native_entrypoint.py","native_runner.py","native_https_provider.py","native_cloudflare_provider.py","source_lock.json"):
        data[name]=run_git(repo,"show",head+":"+PACKAGE+"/"+name)
    blob=io.BytesIO()
    with tarfile.open(fileobj=blob,mode="w") as t:
        for name,raw in sorted(data.items()):
            ti=tarfile.TarInfo(name);ti.size=len(raw);ti.mode=0o444
            ti.uid=0;ti.gid=0;ti.mtime=0;t.addfile(ti,io.BytesIO(raw))
    tar=blob.getvalue()
    if len(tar)>MAX_BUILD_CONTEXT:raise RuntimeError("SOURCE_CONTEXT_BUDGET_EXCEEDED")
    meta={"tag":TAG,"app_head":head,"source_head":C1_HEAD,"source_tree":C1_TREE,
          "context_sha256":hashlib.sha256(tar).hexdigest(),
          "files":{k:hashlib.sha256(v).hexdigest() for k,v in data.items()}}
    return tar,meta

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    if a.out.exists():raise RuntimeError("OUTPUT_EXISTS_REFUSE_REWRITE")
    tar,meta=build_context(a.repo.resolve(strict=True))
    cmd="python3 -c "+shlex.quote(REMOTE)+" "+shlex.quote(json.dumps(meta,sort_keys=True))
    result=subprocess.run(["ssh","-T","-o","BatchMode=yes",
       "-o","ConnectTimeout=8","oracle-vm",cmd],input=tar,
       capture_output=True,timeout=295)
    if result.returncode:
        error=result.stderr.decode(errors="replace")
        raise RuntimeError("REMOTE_NATIVE_BUILD_ERROR_EXIT_"+str(result.returncode)+
                           "_OUTPUT_SHA256_"+hashlib.sha256(result.stdout+result.stderr).hexdigest()+
                           "_SAFE_REASON_"+error[-170:])
    output=json.loads(result.stdout)
    a.out.write_text(json.dumps(output,sort_keys=True,indent=2)+"\n")
    print(json.dumps(output,sort_keys=True))

if __name__=="__main__":main()
