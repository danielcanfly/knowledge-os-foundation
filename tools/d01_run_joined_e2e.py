#!/usr/bin/env python3
"""Run fixed genuine-model D01 trials through source, verifier, and OS Client."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import signal
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from knowledge_engine.m27_c02_native_composer import GeneratedClaim
from knowledge_engine.m27_c02_semantic_provider import (
    C02_RESPONSE_ABI,
    EvidenceClass,
    ProviderAuthority,
    SourceBoundSemanticProvider,
    TrustStatus,
)
from knowledge_engine.m27_d01_nonprod_integration import (
    D01Policy,
    D01SourceSpec,
    run_d01_nonprod_e2e,
)

MODEL_NAME = "qwen2.5-0.5b-instruct-q4_k_m.gguf"
MODEL_SHA = "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db"
CLI_REL = "llama-b11425/llama-cli"
CLI_SHA = "cf4f088f32507af619a1d65516d235ef7644db8c81ff1d3e175ff640dab75ab7"

CASES = (
    (
        "valid-ack",
        "valid",
        "How does Kubernetes recover a failed service?",
        "Kubernetes restarts failed services to restore the desired state.",
    ),
    (
        "forged-ack",
        "forged",
        "What happens after an unknown external effect?",
        "After an unknown external effect, automatic retry is denied until reconciliation.",
    ),
)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(path: Path) -> str:
    return sha(path.read_bytes())


def canonical_sha(value) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return sha(raw)


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
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    model = runtime / MODEL_NAME
    cli = runtime / CLI_REL
    stage_receipt = runtime / "STAGE_RECEIPT.json"
    if (
        not model.is_file()
        or model.is_symlink()
        or digest(model) != MODEL_SHA
        or not cli.is_file()
        or cli.is_symlink()
        or digest(cli) != CLI_SHA
        or not os.access(cli, os.X_OK)
        or not stage_receipt.is_file()
    ):
        raise SystemExit("D01_MODEL_RUNTIME_NOT_PINNED")

    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    public_bytes = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    fixture_client = Path(__file__).with_name("c02_fixture_client.py")
    rows = []
    generation_durations: list[float] = []
    started_wall = time.time_ns()
    started_mono = time.monotonic_ns()
    with tempfile.TemporaryDirectory(prefix="m27-d01-client-") as temp:
        key_path = Path(temp) / "ephemeral-client-private.pem"
        key_path.write_bytes(private_pem)
        key_path.chmod(0o600)
        for index, (case_id, client_mode, question, source_text) in enumerate(CASES, 1):
            case_dir = output / case_id
            case_dir.mkdir(parents=True, exist_ok=True)
            source_path = case_dir / "source.txt"
            source_path.write_text(source_text + "\n", encoding="utf-8")
            raw = source_path.read_bytes()
            prompt = (
                "<|im_start|>system\nAnswer in one short sentence using only the supplied "
                "evidence. Add no facts and no preface.<|im_end|>\n"
                f"<|im_start|>user\nQuestion: {question}\nEvidence: {source_text}"
                "<|im_end|>\n<|im_start|>assistant\n"
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
                str(7100 + index),
                "--no-display-prompt",
                "--simple-io",
                "--no-perf",
                "--single-turn",
            ]
            model_start = time.monotonic_ns()
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
            generation_ms = round((time.monotonic_ns() - model_start) / 1_000_000, 3)
            generation_durations.append(generation_ms)
            generated = "" if timed_out or proc.returncode != 0 else extract(stdout)
            (case_dir / "model.stdout.log").write_text(stdout, encoding="utf-8")
            (case_dir / "model.stderr.log").write_text(stderr, encoding="utf-8")

            auth = ProviderAuthority(
                provider_id="d01-deterministic-fixture-provider",
                model_identity="d01-fixture-nli",
                model_version="1",
                runtime_sha256="a" * 64,
                license_id="TEST_ONLY",
                license_sha256="b" * 64,
                signer_id="d01-fixture-signer",
                qualification_receipt_sha256="c" * 64,
                trust_status=TrustStatus.VERIFIED,
                evidence_class=EvidenceClass.DETERMINISTIC_FIXTURE,
                task_bounds=("semantic_entailment",),
                languages=("en",),
                authorized_principals=("d01-integrator",),
                valid_until_epoch_s=time.time() + 3_600,
                max_attempts=1,
                timeout_ms=100,
                max_cost_units=1.0,
                model_architecture="fixture-nli",
                allowed_model_architectures=("fixture-nli",),
                license_scope="NONPROD_SEMANTIC_VERIFICATION",
                approved_license_ids=("TEST_ONLY",),
            )
            attestation_id = f"d01-fixture-attestation-{index}"

            def transport(
                payload,
                source_id=f"d01-source-{case_id}",
                authority=auth,
                attestation=attestation_id,
            ):
                return {
                    "schema_version": C02_RESPONSE_ABI,
                    "request_id": payload["request_id"],
                    "run_id": payload["run_id"],
                    "nonce": payload["nonce"],
                    "provider_id": authority.provider_id,
                    "model_identity": authority.model_identity,
                    "model_version": authority.model_version,
                    "decision": "ENTAILED",
                    "confidence": 0.99,
                    "reason": "deterministic fixture verdict for ABI transport only",
                    "supporting_source_ids": [source_id],
                    "cost_units": 0,
                    "issued_at_epoch_s": time.time() - 1,
                    "expires_at_epoch_s": time.time() + 60,
                    "signer_id": authority.signer_id,
                    "attestation_id": attestation,
                    "attestation": "fixture:" + attestation,
                }

            semantic = SourceBoundSemanticProvider(
                auth,
                transport,
                lambda result, _payload: result["attestation"]
                == "fixture:" + result["attestation_id"],
            )
            source_id = f"d01-source-{case_id}"

            def generator(
                _question,
                _sources,
                text=generated,
                sid=source_id,
                elapsed=generation_ms,
            ):
                return GeneratedClaim(
                    text=text,
                    cited_source_ids=(sid,),
                    model_identity="Qwen2.5-0.5B-Instruct-Q4_K_M",
                    model_version=MODEL_SHA,
                    actual_model_output=True,
                    generation_duration_ms=elapsed,
                )

            client_records = []

            def publish(event, mode=client_mode, records=client_records):
                client_proc = subprocess.Popen(
                    [
                        sys.executable,
                        "-B",
                        str(fixture_client),
                        "--private-key",
                        str(key_path),
                        "--mode",
                        mode,
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=True,
                )
                client_stdout, client_stderr = client_proc.communicate(
                    json.dumps(event) + "\n", timeout=10
                )
                records.append(
                    {
                        "pid": client_proc.pid,
                        "exit_code": client_proc.returncode,
                        "stdout_sha256": sha(client_stdout.encode()),
                        "stderr_sha256": sha(client_stderr.encode()),
                    }
                )
                return json.loads(client_stdout)

            def verify_ack(ack, event):
                try:
                    message = (
                        f"{event['request_id']}|{event['run_id']}|{canonical_sha(event)}".encode()
                    )
                    public.verify(base64.b64decode(ack["signature"]), message)
                    return True
                except Exception:
                    return False

            source_spec = D01SourceSpec(
                path=source_path,
                source_id=source_id,
                title=f"D01 public Nonprod source {case_id}",
                observed_revision="2026-10-17",
                expected_revision="2026-10-17",
                expected_source_sha256=sha(raw),
                byte_start=0,
                byte_end=len(raw),
                expected_excerpt_sha256=sha(raw),
                language="en",
                tenant_id="d01-nonprod",
                allowed_principals=("d01-integrator",),
                expires_at_epoch_s=time.time() + 3_600,
                license_id="D01_PUBLIC_NONSECRET_TEST_SOURCE",
                rights_grant_id="OWNER_D01_NONPROD_DISPATCH",
                rights_valid_until_epoch_s=time.time() + 3_600,
            )
            outcome = run_d01_nonprod_e2e(
                request_id=f"d01-{case_id}",
                run_id=f"d01-joined-{index}",
                question=question,
                tenant_id="d01-nonprod",
                principal="d01-integrator",
                source_specs=(source_spec,),
                generator=generator,
                semantic_provider=semantic,
                client_publisher=publish,
                verify_client_ack=verify_ack,
                budget_units=1.0,
                policy=D01Policy(
                    opt_in_enabled=True,
                    allow_ephemeral_fixture_client=True,
                ),
            )
            rows.append(
                {
                    "case_id": case_id,
                    "client_mode": client_mode,
                    "model_pid": proc.pid,
                    "model_exit_code": proc.returncode,
                    "model_timed_out": timed_out,
                    "generation_duration_ms": generation_ms,
                    "generated_text": generated,
                    "generated_text_sha256": sha(generated.encode()),
                    "model_stdout_sha256": sha(stdout.encode()),
                    "model_stderr_sha256": sha(stderr.encode()),
                    "client_processes": client_records,
                    "outcome": outcome.as_dict(),
                }
            )
    ended_wall = time.time_ns()
    result = {
        "schema": "m27.d01.joined-real-model-e2e/v1",
        "status": "PASS_LOCAL_CANDIDATE_ONLY",
        "fixed_denominator": len(CASES),
        "actual_local_model_generations": sum(
            bool(row["generated_text"]) and row["model_exit_code"] == 0 for row in rows
        ),
        "fixture_transport_deliveries": sum(
            bool(row["outcome"]["fixture_transport_delivery"]) for row in rows
        ),
        "forged_ack_denials": sum(
            row["outcome"]["terminal_reason"] == "CLIENT_ACK_INVALID" for row in rows
        ),
        "official_client_publications": 0,
        "provider_qualification_proven": False,
        "native_composer_admission": False,
        "formal_product_go": False,
        "c28": False,
        "f35": False,
        "rel01": False,
        "production": "NO_GO",
        "external_provider_calls": 0,
        "billable_provider_calls": 0,
        "local_compute_cost_claimed_zero": False,
        "model_sha256": MODEL_SHA,
        "llama_cli_sha256": CLI_SHA,
        "runtime_stage_receipt_sha256": digest(stage_receipt),
        "ephemeral_client_public_key_sha256": sha(public_bytes),
        "ephemeral_client_private_key_persisted": False,
        "started_wall_epoch_ns": started_wall,
        "ended_wall_epoch_ns": ended_wall,
        "duration_ms": round((time.monotonic_ns() - started_mono) / 1_000_000, 3),
        "generation_latency_denominator": len(generation_durations),
        "generation_latency_p95_ms": percentile95(generation_durations),
        "generation_latency_mean_ms": round(statistics.mean(generation_durations), 3),
        "cases": rows,
    }
    valid = rows[0]["outcome"]
    forged = rows[1]["outcome"]
    assert result["actual_local_model_generations"] == len(CASES)
    assert valid["status"] == "FIXTURE_ONLY" and valid["fixture_transport_delivery"] is True
    assert forged["terminal_reason"] == "CLIENT_ACK_INVALID"
    assert all(not row["outcome"]["official_client_publication"] for row in rows)
    receipt = output / "D01_JOINED_REAL_MODEL_E2E.json"
    receipt.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": result["status"], "receipt": str(receipt)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
