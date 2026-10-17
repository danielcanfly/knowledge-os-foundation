#!/usr/bin/env python3
"""Run authorized local Qwen candidate generation through the C02 composer.

The run intentionally has no semantic provider.  Genuine model output is
captured, then the composer must return a safe terminal rather than publish it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import statistics
import subprocess
import time
from pathlib import Path

from knowledge_engine.m27_c02_native_composer import GeneratedClaim, compose_native_candidate
from knowledge_engine.m27_c02_semantic_provider import SourceBinding

MODEL_NAME = "qwen2.5-0.5b-instruct-q4_k_m.gguf"
MODEL_SHA = "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db"
CLI_REL = "llama-b11425/llama-cli"
CLI_SHA = "cf4f088f32507af619a1d65516d235ef7644db8c81ff1d3e175ff640dab75ab7"


CASES = (
    (
        "en-support",
        "en",
        "How does Kubernetes improve service reliability?",
        "Kubernetes coordinates scheduling, controlled rollouts, and recovery of failed services.",
    ),
    (
        "en-numeric",
        "en",
        "How many retries are allowed after an unknown external effect?",
        "After an unknown external effect, the action policy allows zero automatic retries "
        "until reconciliation.",
    ),
    (
        "ja-support",
        "ja",
        "Kubernetes は障害時に何をしますか？",
        "Kubernetes は障害が発生したサービスを再起動し、望ましい状態へ復旧します。",
    ),
    (
        "zh-support",
        "zh",
        "語意驗證失敗時系統應如何處理？",
        "語意驗證結果不明時，系統必須停止發布並回傳安全終止狀態。",
    ),
)


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def extract(stdout: str) -> str:
    marker = "<|im_start|>assistant\n"
    if marker not in stdout:
        return ""
    value = stdout.rsplit(marker, 1)[-1].strip()
    for trailer in ("\n[ Prompt:", "\n\n[ Prompt:", "\nExiting...", "\n>"):
        if trailer in value:
            value = value.split(trailer, 1)[0].strip()
    return re.sub(r"^\s*['\"]|['\"]\s*$", "", value).strip()


def percentile95(values: list[float]) -> float:
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, int(0.95 * len(ordered) + 0.999999) - 1))
    return ordered[rank]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    model = runtime / MODEL_NAME
    cli = runtime / CLI_REL
    stage = runtime / "STAGE_RECEIPT.json"
    if (
        not model.is_file()
        or model.is_symlink()
        or digest(model) != MODEL_SHA
        or not cli.is_file()
        or cli.is_symlink()
        or digest(cli) != CLI_SHA
        or not os.access(cli, os.X_OK)
        or not stage.is_file()
    ):
        raise SystemExit("C02_MODEL_RUNTIME_NOT_QUALIFIED")

    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    durations = []
    for index, (case_id, language, question, source_text) in enumerate(CASES, 1):
        source_bytes = source_text.encode("utf-8")
        binding = SourceBinding(
            source_id=f"c02-public-{case_id}",
            title=f"C02 public {case_id}",
            revision="2026-10-17",
            raw_bytes=source_bytes,
            source_sha256=digest_bytes(source_bytes),
            byte_start=0,
            byte_end=len(source_bytes),
            excerpt_sha256=digest_bytes(source_bytes),
            language=language,
            tenant_id="c02-nonprod",
            allowed_principals=("c02-worker",),
            expires_at_epoch_s=time.time() + 3_600,
            license_id="C02_PUBLIC_NONSECRET_TEST_SOURCE",
        )
        system = (
            "Answer the question in one concise sentence using only the supplied evidence. "
            "Do not add facts, do not quote the evidence verbatim, and provide no preface."
        )
        user = f"Question: {question}\nEvidence: {source_text}"
        prompt = (
            f"<|im_start|>system\n{system}\n<|im_end|>\n"
            f"<|im_start|>user\n{user}\n<|im_end|>\n<|im_start|>assistant\n"
        )
        command = [
            str(cli),
            "-m",
            str(model),
            "-p",
            prompt,
            "-n",
            "64",
            "-c",
            "1024",
            "--temp",
            "0",
            "-s",
            str(6100 + index),
            "--no-display-prompt",
            "--simple-io",
            "--no-perf",
            "--single-turn",
        ]
        started = time.monotonic_ns()
        proc = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=45)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate(timeout=3)
        duration_ms = round((time.monotonic_ns() - started) / 1_000_000, 3)
        durations.append(duration_ms)
        generated = "" if timed_out or proc.returncode != 0 else extract(stdout)
        (args.output / f"{case_id}.stdout.log").write_text(stdout, encoding="utf-8")
        (args.output / f"{case_id}.stderr.log").write_text(stderr, encoding="utf-8")

        def actual_generator(
            _question,
            _sources,
            value=generated,
            elapsed=duration_ms,
            source_id=binding.source_id,
        ):
            return GeneratedClaim(
                value,
                (source_id,),
                "Qwen2.5-0.5B-Instruct-Q4_K_M",
                MODEL_SHA,
                True,
                elapsed,
            )

        composed = compose_native_candidate(
            request_id=f"c02-{case_id}",
            run_id=f"c02-real-model-{index}",
            question=question,
            tenant_id="c02-nonprod",
            principal="c02-worker",
            sources=(binding,),
            generator=actual_generator,
            semantic_provider=None,
            client_publisher=None,
            verify_client_ack=None,
            budget_units=1.0,
        )
        rows.append(
            {
                "case_id": case_id,
                "language": language,
                "question": question,
                "question_sha256": digest_bytes(question.encode()),
                "source_binding": {
                    "source_id": binding.source_id,
                    "title": binding.title,
                    "revision": binding.revision,
                    "source_sha256": binding.source_sha256,
                    "byte_start": 0,
                    "byte_end": len(source_bytes),
                    "excerpt_sha256": binding.excerpt_sha256,
                },
                "pid": proc.pid,
                "exit_code": proc.returncode,
                "timed_out": timed_out,
                "duration_ms": duration_ms,
                "max_new_tokens": 64,
                "seed": 6100 + index,
                "model_sha256": MODEL_SHA,
                "llama_cli_sha256": CLI_SHA,
                "actual_local_model": True,
                "external_provider_calls": 0,
                "billable_provider_calls": 0,
                "generated_text": generated,
                "generated_text_sha256": digest_bytes(generated.encode()),
                "stdout_sha256": digest_bytes(stdout.encode()),
                "stderr_sha256": digest_bytes(stderr.encode()),
                "composer_status": composed.status,
                "composer_terminal_reason": composed.terminal_reason,
                "published": composed.publishable,
                "native_composer_admitted": composed.native_composer_admitted,
            }
        )
    successful = sum(bool(row["generated_text"]) and row["exit_code"] == 0 for row in rows)
    result = {
        "schema": "m27.c02.real-model-candidate-run/v1",
        "status": "CANDIDATE_GENERATION_COMPLETE_PROVIDER_QUALIFICATION_NOT_PROVEN",
        "runtime_stage_receipt_sha256": digest(stage),
        "model_sha256": MODEL_SHA,
        "llama_cli_sha256": CLI_SHA,
        "model_license": "Apache-2.0",
        "runtime_license": "MIT",
        "case_count": len(rows),
        "successful_generation_count": successful,
        "published_count": sum(bool(row["published"]) for row in rows),
        "native_composer_admitted_count": sum(
            bool(row["native_composer_admitted"]) for row in rows
        ),
        "latency_denominator": len(durations),
        "latency_p95_ms": percentile95(durations),
        "latency_mean_ms": round(statistics.mean(durations), 3),
        "cases": rows,
    }
    output = args.output / "C02_REAL_MODEL_CANDIDATE_RUN.json"
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "cases": len(rows),
                "generated": successful,
                "published": result["published_count"],
                "p95_ms": result["latency_p95_ms"],
                "receipt": str(output),
            },
            sort_keys=True,
        )
    )
    return 0 if successful == len(rows) and result["published_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
