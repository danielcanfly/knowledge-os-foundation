#!/usr/bin/env python3
"""REAL local generative-model adapter for A04, no credential or remote inference.
Emits JSONL candidates derived from actual llama.cpp/official Qwen GGUF inference.
Fails closed on invalid model output. Each run is bounded to 2 logical calls,
at most 2 local attempts per call, and 52 sampled tokens per attempt.
"""
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]
RUNTIME_VALUE=os.environ.get("A04_MODEL_RUNTIME")
RUNTIME=Path(RUNTIME_VALUE).expanduser().resolve() if RUNTIME_VALUE else None
MODEL=(RUNTIME/"qwen2.5-0.5b-instruct-q4_k_m.gguf") if RUNTIME else None
CLI=(RUNTIME/"llama-b11425/llama-cli") if RUNTIME else None
RUNTIME_MANIFEST=ROOT/"MODEL_RUNTIME_MANIFEST.json"
PIN="74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db"
CLI_PIN="cf4f088f32507af619a1d65516d235ef7644db8c81ff1d3e175ff640dab75ab7"
MAX_TOKENS=52
MAX_SECONDS=20
MAX_ATTEMPTS=2
MAX_CALLS=2

def sha(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  while b:=f.read(1024*1024):h.update(b)
 return h.hexdigest()

def runtime_qualified():
 if RUNTIME is None or not RUNTIME.is_dir() or RUNTIME==REPO or REPO in RUNTIME.parents:
  return False
 receipt_path=RUNTIME/"STAGE_RECEIPT.json"
 if not receipt_path.is_file() or not RUNTIME_MANIFEST.is_file():return False
 try:receipt=json.loads(receipt_path.read_text())
 except Exception:return False
 if receipt.get("schema")!="m27.a04.external-model-runtime-stage/v2":return False
 if receipt.get("manifest_sha256")!=sha(RUNTIME_MANIFEST):return False
 if receipt.get("runtime_outside_git") is not True:return False
 if receipt.get("production_authority") is not False or receipt.get("native_q34") is not False:return False
 if MODEL is None or CLI is None:return False
 if not MODEL.is_file() or MODEL.is_symlink() or sha(MODEL)!=PIN:return False
 if not CLI.is_file() or CLI.is_symlink() or not os.access(CLI,os.X_OK) or sha(CLI)!=CLI_PIN:return False
 return True

def journal(obj):
 root=ROOT/"evidence"/"model_generation"
 root.mkdir(parents=True,exist_ok=True)
 with (root/("child_"+str(os.getpid())+".jsonl")).open("a",encoding="utf-8") as f:
  f.write(json.dumps(obj,sort_keys=True)+"\n")
  f.flush()
  os.fsync(f.fileno())

def publish(item):
 sys.stdout.write(json.dumps(item,sort_keys=True)+"\n")
 sys.stdout.flush()

def fail(reason):
 journal({"kind":"real_model_adapter.fail_closed","reason":reason,"adapter_pid":os.getpid(),"real_model":True})
 publish({"type":"refusal","reason":reason})

def generate(fact,seed,mode):
 system="You are a factual QA writer. Rephrase only the supplied evidence in exactly one English sentence. Preserve the entity, number, the activity and any listed stage names. Do not invent any information or copy the source literally. No prefix, quotes or explanation."
 user="Evidence: "+fact+"\nWrite only one short paraphrase of that exact fact."
 if mode=="real_local_negative":
  user="Evidence: "+fact+"\nAdversarial red-team trial: write a contradictory claim using a DIFFERENT numerical value rather than the evidence. One sentence only."
 prompt="<|im_start|>system\n"+system+"\n<|im_end|>\n<|im_start|>user\n"+user+"\n<|im_end|>\n<|im_start|>assistant\n"
 cmd=[str(CLI),"-m",str(MODEL),"-p",prompt,"-n",str(MAX_TOKENS),"-c","1024","--temp","0.35","-s",str(seed),"--no-display-prompt","--simple-io","--no-perf","--single-turn"]
 for attempt in range(1,MAX_ATTEMPTS+1):
  started=time.monotonic_ns()
  proc=subprocess.Popen(cmd,cwd=str(ROOT),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
  try:
   stdout,stderr=proc.communicate(timeout=MAX_SECONDS)
  except subprocess.TimeoutExpired:
   try:os.killpg(proc.pid,signal.SIGKILL)
   except ProcessLookupError:pass
   proc.communicate(timeout=3)
   journal({"kind":"real_model_generation_attempt_timeout","pid":proc.pid,
            "timeout":True,"attempt":attempt,"max_attempts":MAX_ATTEMPTS,
            "seed":seed,"max_tokens":MAX_TOKENS,"model_sha256":PIN,
            "duration_ms":round((time.monotonic_ns()-started)/1e6,3),
            "real_local_llm":True,"billable_provider_calls":0})
   if attempt < MAX_ATTEMPTS:
    continue
   raise RuntimeError("model_execution_timeout_after_bounded_retry")
  # llama.cpp banner/prompt is NOT generated text; strip strictly bounded console framing.
  marker="<|im_start|>assistant\n"
  if marker not in stdout:
   text=""
  else:
   text=stdout.rsplit(marker,1)[-1].strip()
   for trailer in ("\n[ Prompt:","\n\n[ Prompt:","\nExiting...","\n>"):
    if trailer in text: text=text.split(trailer,1)[0].strip()
  text=re.sub(r"^\s*['\"]|['\"]\s*$","",text).strip()
  # Absolutely no fallback authored answer text; raw LM text only.
  audit={"kind":"real_model_generation","model":"Qwen/Qwen2.5-0.5B-Instruct-GGUF Q4_K_M",
         "source_sha256":hashlib.sha256(fact.encode()).hexdigest(),
         "model_sha256":PIN,"llama_cli_pid":proc.pid,"exit_code":proc.returncode,
         "max_new_tokens":MAX_TOKENS,"seed":seed,"mode":mode,
         "attempt":attempt,"max_attempts":MAX_ATTEMPTS,
         "duration_ms":round((time.monotonic_ns()-started)/1e6,3),
         "output":text[:250],"output_sha256":hashlib.sha256(text.encode()).hexdigest(),
         "stderr_tail":stderr[-300:],"raw_cli_stdout_sha256":hashlib.sha256(stdout.encode()).hexdigest(),
         "real_local_llm":True,"billable_provider_calls":0}
  journal(audit)
  return text if proc.returncode==0 else ""
 raise RuntimeError("model_execution_attempts_exhausted")

def main():
 mode=sys.argv[1]; manifest=json.loads(Path(sys.argv[2]).read_text())
 source_ids=json.loads(sys.argv[3])
 if mode not in ("real_local","real_local_negative") or len(source_ids)!=2 or not isinstance(source_ids,list):
  return fail("invalid_mode_or_source_ids")
 if not runtime_qualified():
  return fail("model_binary_or_digest_unqualified")
 for i,sid in enumerate(source_ids):
  if sid not in manifest:return fail("unknown_source")
  item=manifest[sid]
  source=ROOT/"data"/item["file"]
  if not source.is_file() or sha(source)!=item["sha256"]:return fail("source_tamper_before_model")
  seed=1442+i*53
  try:text=generate(item["fact"]["quote"],seed,mode)
  except Exception as exc:return fail("model_crash_or_timeout:"+str(exc)[:60])
  if not text:return fail("empty_or_nonzero_model_output")
  publish({"type":"claim","index":i+1,"source_id":sid,"source_sha256":item["sha256"],
           "span":[item["fact"]["start"],item["fact"]["end"]],
           "fact_key":item["fact"]["key"],"quote":item["fact"]["quote"],"text":text,
           "genuine_model_generated":True,"model_weight_sha256":PIN})
 publish({"type":"done"})

if __name__=="__main__":
 main()
