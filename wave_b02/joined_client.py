#!/usr/bin/env python3
"""Independent OS Client for the B02 joined loopback stream."""
from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import time


def post(port: int, path: str, body: dict) -> tuple[int, dict]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    payload = json.dumps(body, sort_keys=True).encode("utf-8")
    connection.request("POST", path, body=payload, headers={
        "Content-Type": "application/json", "Content-Length": str(len(payload)),
    })
    response = connection.getresponse()
    data = response.read()
    status = response.status
    connection.close()
    return status, json.loads(data) if data else {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--fault", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deadline-ms", type=int, default=60000)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    payload = json.dumps({"contract": contract, "fault": args.fault,
                          "deadline_ms": args.deadline_ms}, sort_keys=True).encode("utf-8")
    connection = http.client.HTTPConnection("127.0.0.1", args.port, timeout=180)
    started = time.monotonic_ns()
    connection.request("POST", "/v1/joined", body=payload, headers={
        "Content-Type": "application/json", "Content-Length": str(len(payload)),
    })
    response = connection.getresponse()
    events = []
    controls = []
    if response.status == 200:
        while True:
            line = response.readline()
            if not line:
                break
            received = time.monotonic_ns()
            event = json.loads(line)
            event["client_received_ns"] = received
            events.append(event)
            if event.get("event") == "run.started" and args.fault == "cancel":
                status, body = post(args.port, "/v1/cancel", {"run_id": contract["run_id"]})
                controls.append({"kind": "cancel", "status": status, "body": body})
            if event.get("event") == "claim.verified":
                base = {"run_id": contract["run_id"], "seq": event["seq"],
                        "client_received_ns": received}
                if args.fault == "none":
                    status, body = post(args.port, "/v1/ack", {**base, "proof": "0" * 64})
                    controls.append({"kind": "forged_ack", "status": status, "body": body})
                status, body = post(args.port, "/v1/ack",
                                    {**base, "proof": event["proof_sha256"]})
                controls.append({"kind": "valid_ack", "status": status, "body": body})
                if args.fault == "none":
                    status, body = post(args.port, "/v1/ack",
                                        {**base, "proof": event["proof_sha256"]})
                    controls.append({"kind": "replay_ack", "status": status, "body": body})
    else:
        raw = response.read()
        controls.append({"kind": "request_error", "status": response.status,
                         "body": json.loads(raw) if raw else {}})
    connection.close()
    receipt = {
        "schema": "m27.wave-b02.joined-independent-client/v1",
        "client_pid": os.getpid(), "run_id": contract["run_id"],
        "fault": args.fault, "http_status": response.status,
        "started_ns": started, "completed_ns": time.monotonic_ns(),
        "events": events, "controls": controls,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, ensure_ascii=False,
                                      sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"run_id": contract["run_id"], "fault": args.fault,
                      "events": len(events), "controls": len(controls)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
