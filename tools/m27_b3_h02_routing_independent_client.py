"""Independent OS process HTTP streaming+ACK client for B3-05 local fixture only."""
from __future__ import annotations

import hashlib
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request


def run(origin: str, request_id: str, mode: str = "BYPASS") -> dict:
    if not origin.startswith("http://127.0.0.1:"):
        raise ValueError("LOOPBACK_ONLY")
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    with opener.open(origin + "/nonprod/h02/session", timeout=3) as r:
        r.read()
    body = {"schema_version": "m27.cache04-choice-demo/v1", "request_id": request_id,
            "cache_mode": mode, "question": "What does this fixture source say?"}
    headers = {"Content-Type": "application/json", "Origin": origin,
               "X-Cache-Demo-Request": "1"}
    start_ns = time.monotonic_ns()
    req = urllib.request.Request(
        origin + "/nonprod/h02/route", data=json.dumps(body).encode(),
        headers=headers, method="POST")
    events = []
    statuses = []
    try:
        with opener.open(req, timeout=6) as response:
            code = response.status
            if code == 200:
                for line in response:
                    if line.strip():
                        frame = json.loads(line)
                        events.append({"kind": frame["event"],
                                       "t_ns": time.monotonic_ns(),
                                       "claim_id": frame.get("obligation_id"),
                                       "text_sha256": frame.get("text_sha256")})
                        statuses.append(frame)
            else:
                statuses.append(json.loads(response.read()))
    except urllib.error.HTTPError as exc:
        code = exc.code
        statuses.append(json.loads(exc.read()))
    claims = [
        {"obligation_id": frame["obligation_id"],
         "text_sha256": frame["text_sha256"]}
        for frame in statuses if frame.get("event") == "answer_text"
    ]
    terminal = next((x["receipt"] for x in statuses if x.get("event") == "terminal"), None)
    ack = None
    if code == 200 and terminal and terminal["status"] == "answered" and claims:
        ackreq = urllib.request.Request(
            origin + "/nonprod/h02/route/ack",
            data=json.dumps({"request_id": request_id, "claims": claims}).encode(),
            headers=headers, method="POST")
        with opener.open(ackreq, timeout=3) as response:
            ack = {"http_status": response.status, **json.loads(response.read())}
    return {
        "client_process_pid": os.getpid(), "origin_scheme": "http-local-loopback",
        "started_ns": start_ns, "completed_ns": time.monotonic_ns(),
        "http_status": code, "events": events,
        "terminal": terminal, "ack": ack,
        "client_first_text_before_terminal": (
            bool(events) and events[0]["kind"] == "answer_text"
            and events[-1]["kind"] == "terminal"
            and events[0]["t_ns"] < events[-1]["t_ns"]
        ),
        "body_not_logged": True,
        "fixture_only_not_gateway_live": True,
    }


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3
                         else "BYPASS"), indent=2, sort_keys=True))
