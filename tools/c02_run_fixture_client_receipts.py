#!/usr/bin/env python3
"""Create positive/negative separate-OS Client receipts for C02 ABI plumbing."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from knowledge_engine.m27_c02_native_composer import GeneratedClaim, compose_native_candidate
from knowledge_engine.m27_c02_semantic_provider import (
    C02_RESPONSE_ABI,
    EvidenceClass,
    ProviderAuthority,
    SourceBinding,
    SourceBoundSemanticProvider,
    TrustStatus,
)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha(value) -> str:
    return sha(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    public_bytes = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    private_pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    client = Path(__file__).with_name("c02_fixture_client.py")
    source_text = "Kubernetes restarts failed services to restore the desired state."
    raw = source_text.encode()
    binding = SourceBinding(
        "client-source",
        "C02 Client Public Source",
        "2026-10-17",
        raw,
        sha(raw),
        0,
        len(raw),
        sha(raw),
        "en",
        "c02-nonprod",
        ("c02-worker",),
        time.time() + 3_600,
        license_id="C02_PUBLIC_NONSECRET_TEST_SOURCE",
    )
    auth = ProviderAuthority(
        "c02-fixture-provider",
        "c02-fixture-nli",
        "1",
        "a" * 64,
        "TEST_ONLY",
        "b" * 64,
        "c02-fixture-signer",
        "c" * 64,
        TrustStatus.VERIFIED,
        EvidenceClass.DETERMINISTIC_FIXTURE,
        ("semantic_entailment",),
        ("en",),
        ("c02-worker",),
        time.time() + 3_600,
        1,
        100,
        1.0,
        model_architecture="fixture-nli-architecture",
        allowed_model_architectures=("fixture-nli-architecture",),
        license_scope="NONPROD_SEMANTIC_VERIFICATION",
        approved_license_ids=("TEST_ONLY",),
    )
    attestation_counter = 0

    def transport(payload):
        nonlocal attestation_counter
        attestation_counter += 1
        attestation_id = f"fixture-attestation-{attestation_counter}"
        return {
            "schema_version": C02_RESPONSE_ABI,
            "request_id": payload["request_id"],
            "run_id": payload["run_id"],
            "nonce": payload["nonce"],
            "provider_id": auth.provider_id,
            "model_identity": auth.model_identity,
            "model_version": auth.model_version,
            "decision": "ENTAILED",
            "confidence": 0.99,
            "reason": "deterministic fixture for client transport only",
            "supporting_source_ids": ["client-source"],
            "cost_units": 0,
            "issued_at_epoch_s": time.time() - 1,
            "expires_at_epoch_s": time.time() + 60,
            "signer_id": auth.signer_id,
            "attestation_id": attestation_id,
            "attestation": "fixture:" + attestation_id,
        }

    semantic = SourceBoundSemanticProvider(
        auth,
        transport,
        lambda result, _payload: result["attestation"] == "fixture:" + result["attestation_id"],
    )

    def generator(_question, _sources):
        return GeneratedClaim(
            "Kubernetes restores the desired state by restarting failed services.",
            ("client-source",),
            "separate-generator-fixture",
            "1",
            True,
            0.1,
        )

    rows = []
    with tempfile.TemporaryDirectory(prefix="m27-c02-client-") as temp:
        key_path = Path(temp) / "client-private.pem"
        key_path.write_bytes(private_pem)
        key_path.chmod(0o600)
        for mode in ("valid", "forged"):
            process_records = []

            def publish(event, client_mode=mode, records=process_records):
                proc = subprocess.Popen(
                    [
                        sys.executable,
                        "-B",
                        str(client),
                        "--private-key",
                        str(key_path),
                        "--mode",
                        client_mode,
                    ],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=True,
                )
                stdout, stderr = proc.communicate(json.dumps(event) + "\n", timeout=10)
                records.append(
                    {
                        "pid": proc.pid,
                        "exit_code": proc.returncode,
                        "stdout_sha256": sha(stdout.encode()),
                        "stderr_sha256": sha(stderr.encode()),
                    }
                )
                return json.loads(stdout)

            def verify_ack(ack, event):
                try:
                    message = (
                        f"{event['request_id']}|{event['run_id']}|{canonical_sha(event)}".encode()
                    )
                    public.verify(base64.b64decode(ack["signature"]), message)
                    return True
                except Exception:
                    return False

            result = compose_native_candidate(
                request_id=f"client-{mode}",
                run_id=f"client-{mode}-run",
                question="How does Kubernetes recover?",
                tenant_id="c02-nonprod",
                principal="c02-worker",
                sources=(binding,),
                generator=generator,
                semantic_provider=semantic,
                client_publisher=publish,
                verify_client_ack=verify_ack,
                budget_units=1.0,
                allow_nonqualifying_fixture_delivery=True,
            )
            rows.append(
                {
                    "mode": mode,
                    "status": result.status,
                    "publishable": result.publishable,
                    "native_composer_admitted": result.native_composer_admitted,
                    "terminal_reason": result.terminal_reason,
                    "client_receipt": result.client_receipt,
                    "event_types": [event["type"] for event in result.events],
                    "process": process_records,
                }
            )
    result = {
        "schema": "m27.c02.independent-client-fixture-receipts/v1",
        "status": "PASS_FIXTURE_TRANSPORT_ONLY",
        "qualification_class": "DETERMINISTIC_FIXTURE",
        "provider_qualification_proven": False,
        "native_composer_admitted": False,
        "public_key_sha256": sha(public_bytes),
        "private_key_persisted": False,
        "cases": rows,
    }
    assert rows[0]["status"] == "FIXTURE_ONLY" and rows[0]["publishable"] is True
    assert rows[1]["status"] == "SAFE_TERMINAL" and rows[1]["publishable"] is False
    output = args.output / "C02_CLIENT_RECEIPTS.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"status": result["status"], "cases": len(rows), "receipt": str(output)}, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
