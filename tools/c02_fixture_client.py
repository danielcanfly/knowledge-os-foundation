#!/usr/bin/env python3
"""Separate-process C02 fixture Client.  Never a qualification issuer."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization


def canonical_sha(value) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--mode", choices=("valid", "forged"), default="valid")
    args = parser.parse_args()
    event = json.loads(input())
    event_sha = canonical_sha(event)
    message = f"{event['request_id']}|{event['run_id']}|{event_sha}".encode()
    key = serialization.load_pem_private_key(args.private_key.read_bytes(), password=None)
    signature = key.sign(message)
    if args.mode == "forged":
        signature = b"forged-ack"
    receipt = {
        "schema_version": "m27.c02.client-ack/v1",
        "request_id": event["request_id"],
        "run_id": event["run_id"],
        "event_sha256": event_sha,
        "client_id": "c02-independent-os-fixture-client",
        "received_at_epoch_ns": time.time_ns(),
        "signature": base64.b64encode(signature).decode(),
        "client_process_pid": __import__("os").getpid(),
        "qualification_class": "DETERMINISTIC_FIXTURE",
    }
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
