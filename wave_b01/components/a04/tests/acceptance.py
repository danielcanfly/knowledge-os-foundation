#!/usr/bin/env python3
"""Independent loopback TCP client acceptance suite, separate OS subprocess.
Writes raw per-case event/timestamp receipts, preserves failures.
"""
import concurrent.futures
import hashlib
import http.client
import json
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
EV = ROOT / "evidence"
CASES = EV / "client_cases"
CASES.mkdir(parents=True, exist_ok=True)
TOKENS = json.loads((DATA / "tokens.json").read_text())
PORT = int((EV / "port.txt").read_text())
manifest = json.loads((DATA / "manifest.json").read_text())
results = []

def new_id(tag):
    return tag + "_" + uuid.uuid4().hex[:12]

def post(path, payload, tenant="tenant-alpha"):
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=6)
    body = json.dumps(payload)
    conn.request("POST", path, body=body, headers={
        "Authorization": "Bearer " + TOKENS[tenant],
        "Content-Type": "application/json", "Content-Length": str(len(body)),
    })
    response = conn.getresponse()
    status = response.status
    data = response.read().decode()
    conn.close()
    try: obj = json.loads(data)
    except json.JSONDecodeError: obj = {"raw": data[:160]}
    return status, obj

def reset_revocations(items=None):
    tmp = DATA / "revocations.json.tmp"
    tmp.write_text(json.dumps({"revoked": items or []}), encoding="utf-8")
    tmp.replace(DATA / "revocations.json")

def stream(mode="good", *, tenant="tenant-alpha", source_ids=None, deadline_ms=2500,
           on_event=None, ack=True, disconnect=False, run_id=None):
    run_id = run_id or new_id(mode)
    payload = {"run_id": run_id, "tenant": tenant,
               "source_ids": source_ids or ["atlas-A", "delta-B"],
               "mode": mode, "deadline_ms": deadline_ms}
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=(65 if mode.startswith("real_local") else 7))
    conn.request("POST", "/v1/stream", body=json.dumps(payload),
                 headers={"Authorization": "Bearer " + TOKENS[tenant],
                          "Content-Type": "application/json"})
    response = conn.getresponse()
    if response.status != 200:
        body = response.read().decode()
        conn.close()
        return {"status": response.status, "body": body, "events": [], "run_id": run_id}
    events = []
    frame = {}
    try:
        while True:
            line = response.fp.readline()
            if not line:
                break
            received_ns = time.monotonic_ns()
            decoded = line.decode("utf-8", errors="replace").strip()
            if not decoded:
                if "data" in frame:
                    event = json.loads(frame["data"])
                    event["client_received_ns"] = received_ns
                    events.append(event)
                    if on_event:
                        on_event(event, run_id)
                    if ack and event["event"] == "claim.verified":
                        st, info = post("/v1/ack", {"run_id":run_id, "seq":event["seq"],
                                                  "proof":event["proof_sha256"],
                                                  "client_received_ns":received_ns}, tenant)
                        event["client_ack_status"] = st
                        event["client_ack_response"] = info
                    if disconnect and event["event"] == "claim.verified":
                        try:
                            sock = conn.sock or getattr(getattr(response.fp, "raw", None), "_sock", None)
                            if sock is not None:
                                sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                                                __import__("struct").pack("ii", 1, 0))
                                sock.shutdown(socket.SHUT_RDWR)
                        except OSError: pass
                        break
                    if event["event"] == "run.terminal":
                        break
                frame = {}
            elif decoded.startswith("data: "):
                frame["data"] = decoded[6:]
    finally:
        conn.close()
    return {"status": 200, "events": events, "run_id": run_id}

def check(cond, msg):
    if not cond:
        raise AssertionError(msg)

def kinds(data):
    return [e["event"] for e in data["events"]]

def statuses(data):
    return [e.get("status") for e in data["events"] if e["event"] == "run.terminal"]

def verified(data):
    return [e for e in data["events"] if e["event"] == "claim.verified"]

def expect_order(data, min_claims=2):
    es = data["events"]
    check(data["status"] == 200, "SSE status non-200")
    check(len(verified(data)) >= min_claims, "too few verified claims")
    check(statuses(data) == ["succeeded"], "expected successful terminal")
    seqs = [x["seq"] for x in es]
    check(seqs == list(range(1, len(seqs)+1)), "non-monotonic SSE event IDs")
    done = next(e for e in es if e["event"] == "worker.finished")
    terminal = next(e for e in es if e["event"] == "run.terminal")
    first = verified(data)[0]
    check(first["client_received_ns"] < done["worker_finished_ns"], "client received no pre-worker generated claim")
    check(first["client_received_ns"] < terminal["client_received_ns"], "not pre-terminal")
    check(done["worker_finished_ns"] < terminal["client_received_ns"], "terminal before worker completed")
    check(first["text"] != manifest[first["source_id"]]["fact"]["quote"], "extractive claim masquerading")
    for c in verified(data):
        entry = manifest[c["source_id"]]
        check(c["source_sha256"] == entry["sha256"], "source hash mismatch")
        check(c["span"] == [entry["fact"]["start"],entry["fact"]["end"]], "bad evidence span")
        check(c["client_ack_status"] == 200, "client ACK was not accepted")
        b = (c["source_id"] + "|" + c["source_sha256"] + "|" +
             str(c["span"]) + "|" + c["fact_key"] + "|" + c["text"]).encode()
        check(c["proof_sha256"] == hashlib.sha256(b).hexdigest(), "proof incorrect")

def run_case(name, fn):
    started = time.monotonic_ns()
    raw = {}
    try:
        raw = fn() or {}
        success = True
        error = None
    except Exception:
        success = False
        error = traceback.format_exc()
    report = {"case": name, "pass": success, "error": error,
              "elapsed_ms": round((time.monotonic_ns()-started)/1e6, 3),
              "evidence": raw}
    dest = CASES / (name + ".json")
    dest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    results.append({"case": name, "pass": success, "error": error, "receipt": str(dest)})
    print(json.dumps({"case": name, "PASS": success,
                      "error": error[-180:] if error else ""}), flush=True)

def good():
    d = stream()
    expect_order(d)
    check(len(verified(d))==2, "expected two attested non-identical facts")
    check(len({e["source_id"] for e in verified(d)})==2, "must be independent sources")
    return d

def refusal():
    d = stream("refuse")
    check(statuses(d)==["refused"], "no safe refused terminal")
    check(not verified(d), "refusal emitted claim")
    return d

def negative(mode, expected_reason):
    d = stream(mode)
    check("claim.rejected" in kinds(d), "negative claim was not rejected")
    check(len(verified(d))==0, "unsafe or out-of-sequence claim was published")
    check(statuses(d)==["rejected"], "partial verified result counted as success")
    check(any(expected_reason in e.get("reason","") for e in d["events"]), "wrong rejection reason")
    return d

def one():
    d = stream("one")
    check(statuses(d)==["rejected"] and len(verified(d))==1, "one-claim terminal false pass")
    return d

def duplicate_sequence():
    d = stream("duplicate")
    expect_order(d)
    check(kinds(d).count("claim.rejected")==1, "duplicate not rejected")
    check(any(e.get("reason")=="claim_sequence" for e in d["events"]), "wrong reason")
    return d

def out_of_order():
    d = stream("out_of_order")
    expect_order(d)
    check(kinds(d).count("claim.rejected")==1, "out-of-order not rejected")
    return d

def repair():
    d = stream("repair")
    expect_order(d)
    check(kinds(d).index("claim.rejected") < kinds(d).index("claim.verified"), "unsafe claim leaked")
    return d

def timeout():
    d = stream("slow",deadline_ms=140)
    check(statuses(d)==["timeout"], "timeout not terminal")
    check(len(verified(d)) <= 1, "late claim exposed after deadline")
    return d

def cancelled():
    seen = []
    def callback(e, run_id):
        if e["event"]=="claim.verified" and not seen:
            seen.append(1)
            st, _ = post("/v1/cancel",{"run_id":run_id})
            check(st==202, "cancel failed")
    d = stream("slow",on_event=callback)
    check(statuses(d)==["cancelled"], "cancel did not win race")
    check(len(verified(d))==1, "late claim sent after cancellation")
    return d

def cancel_race():
    seen = []
    statuses_list = []
    def callback(e, run_id):
        if e["event"]=="claim.verified" and not seen:
            seen.append(1)
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                statuses_list.extend(pool.map(
                    lambda _: post("/v1/cancel",{"run_id":run_id})[0], range(3)))
    d = stream("slow",on_event=callback)
    check(statuses(d)==["cancelled"], "race not cancelled")
    check(statuses_list == [202,202,202], "cancel idempotency")
    check(kinds(d).count("run.terminal")==1, "terminal not monotonic")
    d["cancel_statuses"] = statuses_list
    return d

def tampered():
    p = DATA / manifest["delta-B"]["file"]
    original = p.read_bytes()
    try:
        def callback(e, run_id):
            if e["event"]=="claim.verified":
                p.write_bytes(original+b"UNTRUSTED_APPEND\n")
        d = stream("good",on_event=callback)
        check(statuses(d)==["rejected"], "tampered source survived")
        check(any(e.get("reason")=="source_bytes_tampered" for e in d["events"]), "missing source rehash")
        check(len(verified(d))==1, "tampered source published")
        return d
    finally:
        p.write_bytes(original)

def revoked():
    try:
        def callback(e, run_id):
            if e["event"]=="claim.verified" and e["source_id"]=="atlas-A":
                reset_revocations(["atlas-A"])
        d=stream("revoke",on_event=callback,ack=False)
        check("claim.retracted" in kinds(d), "revocation not propagated to published claim")
        check(statuses(d)==["rejected"], "revoked claim counted as success")
        check(len(verified(d))==2, "expected both raw pre-revoke and fresh claim")
        return d
    finally:
        reset_revocations()

def tenant_acl():
    status, obj = post("/v1/stream",{"run_id":new_id("cross"),"tenant":"tenant-alpha",
                                      "source_ids":["cedar-C"],"mode":"good"})
    check(status==403, "cross tenant corpus admitted")
    check("Cedar" not in json.dumps(obj), "other tenant data leaked")
    return {"status":status,"response":obj}

def tenant_spoof():
    status, obj = post("/v1/stream",{"run_id":new_id("spoof"),"tenant":"tenant-beta",
                                      "source_ids":["cedar-C"],"mode":"good"})
    check(status==403, "spoofed identity admitted")
    return {"status":status,"response":obj}

def unauth():
    conn=http.client.HTTPConnection("127.0.0.1", PORT, timeout=4)
    conn.request("POST","/v1/stream",body=b"{}",headers={"Content-Type":"application/json"})
    r=conn.getresponse()
    status=r.status
    body=r.read().decode()
    conn.close()
    check(status==401, "unauth run admitted")
    return {"status":status,"response":body}

def forged_ack():
    status,obj=post("/v1/ack",{"run_id":new_id("absent"),"seq":1,"proof":"x",
                               "client_received_ns":time.monotonic_ns()})
    check(status==404, "unknown run ACK accepted")
    return {"status":status,"response":obj}

def duplicate_run():
    run_id=new_id("dup_run")
    one=stream(run_id=run_id)
    check(statuses(one)==["succeeded"],"first run failed")
    status,obj=post("/v1/stream",{"run_id":run_id,"tenant":"tenant-alpha",
                                  "source_ids":["atlas-A","delta-B"],"mode":"good"})
    check(status==409, "duplicate RunId was accepted")
    return {"first_run":one,"second_status":status,"response":obj}

def disconnect():
    d=stream("slow", disconnect=True, ack=False)
    check(len(verified(d))==1, "disconnect before first claim")
    path=EV/"journals"/(d["run_id"]+".jsonl")
    deadline=time.monotonic()+2.6
    events=[]
    while time.monotonic()<deadline:
        if path.exists():
            events=[json.loads(s) for s in path.read_text().splitlines()]
            if any(e["kind"]=="client.disconnected" for e in events):
                break
        time.sleep(0.05)
    check(any(e["kind"]=="client.disconnected" for e in events), "disconnect not observed")
    check(not any(e["kind"]=="run.closed" and e.get("terminal_sent") for e in events),
          "server marked disconnected client terminal received")
    d["server_disconnect_journal"]=[e for e in events if e["kind"] in
                                    ("client.disconnected","provider.exit","run.closed")]
    return d

if __name__=="__main__":
    reset_revocations()
    suite=[
        ("verified_two_claims_preterminal",good),
        ("safe_refusal",refusal),
        ("forged_citation",lambda:negative("forged_ref","source_not_in_scope")),
        ("forged_digest",lambda:negative("forged_hash","forged_source_digest")),
        ("forged_span",lambda:negative("forged_span","evidence_span")),
        ("contradiction_semantic",lambda:negative("contradiction","semantic_unsupported")),
        ("partial_not_succeeded",one),
        ("duplicate_claim_sequence",duplicate_sequence),
        ("out_of_order_repair_sequence",out_of_order),
        ("invalid_then_repaired",repair),
        ("deadline_timeout",timeout),
        ("cancel_after_claim",cancelled),
        ("cancel_race",cancel_race),
        ("tampered_source_bytes",tampered),
        ("source_revocation_retraction",revoked),
        ("tenant_scope_acl",tenant_acl),
        ("tenant_identity_spoof",tenant_spoof),
        ("unauthenticated_rejected",unauth),
        ("unknown_receipt_ack",forged_ack),
        ("duplicate_run_id",duplicate_run),
        ("client_disconnect",disconnect),
    ]
    for name, fn in suite:
        run_case(name,fn)
    counts={"total":len(results),"pass":sum(r["pass"] for r in results),
            "fail":sum(not r["pass"] for r in results)}
    output={"counts":counts,"cases":results,"provider_kind":"deterministic_external_stub",
            "native_q34":False,"real_model_generated":False,
            "independent_client_pid":os.getpid(),"port":PORT}
    (EV/"acceptance_results.json").write_text(json.dumps(output,indent=2)+"\n")
    print(json.dumps(counts),flush=True)
    sys.exit(0 if counts["fail"]==0 else 1)
