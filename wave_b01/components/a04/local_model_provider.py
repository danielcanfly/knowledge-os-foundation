#!/usr/bin/env python3
"""REAL local generative-model adapter for A04, no credential or remote inference.
Emits JSONL candidates derived from actual llama.cpp/official Qwen GGUF inference.
Fails closed on invalid model output. Each run max 2 calls x 52 sampled tokens.
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
# Resolve the integration worktree's ignored runtime link before launching.
# llama.cpp loads adjacent runtime assets relative to its executable path; an
# unresolved directory symlink can leave the child waiting instead of reaching
# inference even though the pinned binary and model bytes are valid.
MODEL=(ROOT/"model_runtime/qwen2.5-0.5b-instruct-q4_k_m.gguf").resolve()
CLI=(ROOT/"model_runtime/llama-b11425/llama-cli").resolve()
PIN="74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db"
MAX_TOKENS=52
MAX_SECONDS=20
MAX_CALLS=2

def sha(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  while b:=f.read(1024*1024):h.update(b)
 return h.hexdigest()

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
 started=time.monotonic_ns()
 proc=subprocess.Popen(cmd,cwd=str(ROOT),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
 try:
  stdout,stderr=proc.communicate(timeout=MAX_SECONDS)
 except subprocess.TimeoutExpired:
  try:os.killpg(proc.pid,signal.SIGKILL)
  except ProcessLookupError:pass
  proc.communicate(timeout=3)
  journal({"kind":"real_model_generation","pid":proc.pid,"timeout":True,"seed":seed,"max_tokens":MAX_TOKENS,"model_sha256":PIN,"duration_ms":round((time.monotonic_ns()-started)/1e6,3)})
  raise RuntimeError("model_execution_timeout")
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
        "duration_ms":round((time.monotonic_ns()-started)/1e6,3),
        "output":text[:250],"output_sha256":hashlib.sha256(text.encode()).hexdigest(),
        "stderr_tail":stderr[-300:],"raw_cli_stdout_sha256":hashlib.sha256(stdout.encode()).hexdigest(),
        "real_local_llm":True,"billable_provider_calls":0}
 journal(audit)
 return text if proc.returncode==0 else ""

def main():
 mode=sys.argv[1]; manifest=json.loads(Path(sys.argv[2]).read_text())
 source_ids=json.loads(sys.argv[3])
 if mode not in ("real_local","real_local_negative") or len(source_ids)!=2 or not isinstance(source_ids,list):
  return fail("invalid_mode_or_source_ids")
 if not CLI.is_file() or not os.access(CLI,os.X_OK) or not MODEL.is_file() or sha(MODEL)!=PIN:
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
