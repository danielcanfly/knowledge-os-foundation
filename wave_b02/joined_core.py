"""B02-owned joined Nonprod adapter primitives.

This module binds one immutable task envelope to the existing A06 TaskContract
projection and the accepted A05 source grant.  It has no Production, Q34,
remote Provider, IdP, signing, or protected-evaluation capability.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from typing import Any, Mapping

from wave_b01.integration import admit_task_contract
from wave_b01.components.a05.adapter.a05_retrieval import ContextIndex, SourceError


REPO = Path(__file__).resolve().parents[1]
A05_SOURCE = REPO / "wave_b01/components/a05/source"
MODEL_SHA256 = "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db"
CLI_SHA256 = "cf4f088f32507af619a1d65516d235ef7644db8c81ff1d3e175ff640dab75ab7"
QUESTION = "PolicyEngine deterministic enforcement Agent request decides"
TARGET_PASSAGE = "D01P004"
ALLOWED_FAULTS = {
    "none", "stale_source", "revoked_source", "source_byte_tamper",
    "citation_span_tamper", "missing_verified_text", "invalid_verified_text",
    "timeout", "cancel", "unknown_unresolved",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def contract_hash(contract: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical(contract))


def a06_projection(contract: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "version", "run_id", "tenant", "context_grant", "actor", "goal",
        "deadline", "budget", "rights", "a06_sources", "outcome",
    }
    if set(contract) != expected or contract.get("version") != "m27.b02.joined-task/v1":
        raise ValueError("JOINED_CONTRACT_FIELDS")
    budget = contract.get("budget")
    if not isinstance(budget, dict):
        raise ValueError("JOINED_BUDGET")
    return {
        "run_id": contract["run_id"],
        "tenant": contract["tenant"],
        "actor": contract["actor"],
        "goal": contract["goal"],
        "deadline": contract["deadline"],
        "budget": {
            "max_source_reads": budget.get("max_source_reads"),
            "max_action_attempts": budget.get("max_action_attempts"),
        },
        "sources": contract["a06_sources"],
        "rights": contract["rights"],
        "outcome": contract["outcome"],
        "version": "a06-v1",
    }


def admit_joined_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    if contract.get("budget", {}).get("max_model_calls") != 1:
        raise ValueError("MODEL_BUDGET_DENIED")
    if contract.get("budget", {}).get("max_context_reads") != 1:
        raise ValueError("CONTEXT_BUDGET_DENIED")
    projection = a06_projection(contract)
    admitted = admit_task_contract(projection)
    grant = contract.get("context_grant")
    if not isinstance(grant, dict) or set(grant) != {
        "tenant", "roles", "release_id", "source_revision", "expires_at"
    }:
        raise PermissionError("A05_CONTEXT_GRANT_INVALID")
    if grant["release_id"] != "a05context-7835ec95cee63972" or \
            grant["source_revision"] != "89f1d7be1623cd6926a69e38871544eefe39e584" or \
            grant["expires_at"] != "2027-01-11T21:36:23.210892+00:00":
        raise PermissionError("A05_CONTEXT_GRANT_MISMATCH")
    return {
        "schema": "m27.wave-b02.joined-admission/v1",
        "run_id": contract["run_id"],
        "joined_contract_sha256": contract_hash(contract),
        "a06_projection_sha256": contract_hash(projection),
        "a06_admission": admitted,
        "a05_context_grant": grant,
        "production_authority": False,
    }


def retrieve_a05(contract: Mapping[str, Any], *, root: Path = A05_SOURCE,
                 now=None) -> dict[str, Any]:
    grant = contract["context_grant"]
    index = ContextIndex(root)
    result = index.search(
        question=QUESTION,
        tenant=grant["tenant"],
        roles=grant["roles"],
        release_id=grant["release_id"],
        source_revision=grant["source_revision"],
        limit=1,
        now=now,
    )
    if result["status"] != "source_passages" or len(result["results"]) != 1:
        raise SourceError(412, "joined_context_unavailable")
    passage = result["results"][0]
    if passage["passage_id"] != TARGET_PASSAGE:
        raise SourceError(409, "joined_target_passage_mismatch")
    result["memory_candidates_included"] = 0
    result["citation_authority"] = "A05_PINNED_FIRSTPARTY_SOURCE_ONLY"
    return result


def verify_generated_claim(context: Mapping[str, Any], text: str, *,
                           source_root: Path = A05_SOURCE) -> dict[str, Any]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("VERIFIED_TEXT_MISSING")
    passage = context["results"][0]
    citation = passage["citation"]
    path = source_root / citation["document"]
    raw = path.read_bytes()
    if sha256_bytes(raw) != citation["document_sha256"]:
        raise ValueError("SOURCE_BYTES_TAMPERED")
    start, end = citation["byte_start"], citation["byte_end"]
    if not (0 <= start < end <= len(raw)):
        raise ValueError("CITATION_SPAN_INVALID")
    excerpt = raw[start:end]
    if sha256_bytes(excerpt) != citation["excerpt_sha256"] or \
            excerpt.decode("utf-8") != passage["excerpt"]:
        raise ValueError("CITATION_OR_EXCERPT_TAMPERED")
    sentence = text.strip()
    if sentence == passage["excerpt"] or len(sentence) > 220 or not sentence.endswith("."):
        raise ValueError("GENERATED_TEXT_FORMAT_OR_EXTRACTIVE")
    if sentence.count(".") != 1 or not re.fullmatch(r"[A-Za-z0-9 ,.';:\-]+", sentence):
        raise ValueError("GENERATED_TEXT_FORMAT_OR_EXTRACTIVE")
    low = sentence.lower().replace("policy engine", "policyengine")
    required = ("agent", "request", "policyengine", "decid", "deterministic", "enforc")
    if not all(term in low for term in required):
        raise ValueError("BOUNDED_SEMANTIC_UNSUPPORTED")
    if re.search(r"\b(?:not|never|without|false|instead|unless|except|maybe|probably)\b", low):
        raise ValueError("BOUNDED_SEMANTIC_NEGATION_OR_HEDGE")
    if any(term in low for term in ("production", "dollars", "profit", "month", "year")):
        raise ValueError("BOUNDED_SEMANTIC_ADDITIONAL_FACT")
    return {
        "text": sentence,
        "text_sha256": sha256_bytes(sentence.encode("utf-8")),
        "passage_id": passage["passage_id"],
        "source_id": citation["document"],
        "source_sha256": citation["document_sha256"],
        "span": [start, end],
        "excerpt_sha256": citation["excerpt_sha256"],
        "release_id": citation["release_id"],
        "source_revision": citation["source_revision"],
        "revocation_epoch": citation["revocation_epoch"],
        "verifier": "b02_a05_policyengine_bounded_entailment_v1",
        "memory_citation_authority": False,
    }


def _extract_generated(stdout: str) -> str:
    marker = "<|im_start|>assistant\n"
    if marker not in stdout:
        return ""
    text = stdout.rsplit(marker, 1)[-1].strip()
    for trailer in ("\n[ Prompt:", "\n\n[ Prompt:", "\nExiting...", "\n>"):
        if trailer in text:
            text = text.split(trailer, 1)[0].strip()
    return re.sub(r"^\s*['\"]|['\"]\s*$", "", text).strip()


def generate_local_model(runtime: Path, excerpt: str, audit_path: Path, *,
                         timeout_seconds: int = 25) -> tuple[str, dict[str, Any]]:
    model = runtime / "qwen2.5-0.5b-instruct-q4_k_m.gguf"
    cli = runtime / "llama-b11425/llama-cli"
    if sha256_file(model) != MODEL_SHA256 or sha256_file(cli) != CLI_SHA256:
        raise RuntimeError("JOINED_MODEL_RUNTIME_DIGEST_MISMATCH")
    system = (
        "Paraphrase exactly one supplied evidence statement. Output exactly one English "
        "sentence. The sentence must include Agent, request, PolicyEngine, decides, "
        "deterministic, and enforcement. Do not copy the source literally and do not add facts."
    )
    user = "Evidence: " + excerpt + "\nWrite only the one grounded sentence."
    prompt = ("<|im_start|>system\n" + system + "\n<|im_end|>\n<|im_start|>user\n" +
              user + "\n<|im_end|>\n<|im_start|>assistant\n")
    command = [str(cli), "-m", str(model), "-p", prompt, "-n", "48", "-c", "1024",
               "--temp", "0", "-s", "2761", "--no-display-prompt", "--simple-io",
               "--no-perf", "--single-turn"]
    attempts = []
    for attempt in (1, 2):
        started = time.monotonic_ns()
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, start_new_session=True)
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate(timeout=3)
        duration = round((time.monotonic_ns() - started) / 1e6, 3)
        output = "" if timed_out else _extract_generated(stdout)
        record = {
            "attempt": attempt, "max_attempts": 2, "pid": proc.pid,
            "exit_code": proc.returncode, "timed_out": timed_out,
            "duration_ms": duration, "max_new_tokens": 48, "seed": 2761,
            "model_sha256": MODEL_SHA256, "llama_cli_sha256": CLI_SHA256,
            "input_excerpt_sha256": sha256_bytes(excerpt.encode("utf-8")),
            "raw_stdout_sha256": sha256_bytes(stdout.encode("utf-8")),
            "stderr_sha256": sha256_bytes(stderr.encode("utf-8")),
            "output": output, "output_sha256": sha256_bytes(output.encode("utf-8")),
            "actual_local_model": True, "billable_provider_calls": 0,
            "external_provider_calls": 0,
        }
        attempts.append(record)
        if not timed_out and proc.returncode == 0 and output:
            audit = {"schema": "m27.wave-b02.joined-model-audit/v1",
                     "attempts": attempts, "selected_attempt": attempt}
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n",
                                  encoding="utf-8")
            return output, audit
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps({"schema": "m27.wave-b02.joined-model-audit/v1",
                                      "attempts": attempts, "selected_attempt": None},
                                     indent=2, sort_keys=True) + "\n", encoding="utf-8")
    raise RuntimeError("JOINED_MODEL_TIMEOUT_OR_EMPTY")
