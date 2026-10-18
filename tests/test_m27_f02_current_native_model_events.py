"""Behavioral F02 RED/after tests. Live Provider and Product remain NOT_RUN."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
F02_PATH = ROOT / "src/knowledge_engine/m27_f02_current_native_model_events.py"
F02_SPEC = importlib.util.spec_from_file_location("m27_f02_current_native_model_events", F02_PATH)
f02 = importlib.util.module_from_spec(F02_SPEC)
sys.modules[F02_SPEC.name] = f02
F02_SPEC.loader.exec_module(f02)


def hx(obj):
    return hashlib.sha256(obj).hexdigest()


def pin():
    return f02.Pins(
        task_id="current-task", request_id="current-request",
        question_sha256="1" * 64, task_contract_sha256="2" * 64,
        tenant="owner-internal", principal="os-local-f02",
        source_release_sha256="3" * 64, source_manifest_sha256="4" * 64,
        source_rights_epoch=1, source_acl_sha256="5" * 64,
        answer_obligation_ids=("fact_one", "fact_two"),
        model_route_policy_version="route-candidate-v1", max_tokens=100,
        deadline_monotonic_ns=time.monotonic_ns() + 20_000_000_000,
        cache_mode="OFF")


def wire(event, **kwargs):
    return json.dumps({"event": event, **kwargs}, sort_keys=True).encode()


def good():
    return [
        wire("request_start", request_id="current-request"),
        wire("model_identity", provider="mock-local-not-provider", model="fiction-v1"),
        wire("delta", text="First generated fixture claim.\n"),
        wire("delta", text="Second generated fixture claim.\n"),
        wire("provider_done", usage={"input_tokens": 10, "output_tokens": 12}),
        wire("stream_end", provider_done=True),
    ]


class CurrentNativeTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.journal = Path(self.folder.name) / "journal.jsonl"

    def producer(self, pins=None, **kwargs):
        return f02.NativeEventProducer(pins or pin(), f02.EventJournal(self.journal), **kwargs)

    def test_positive_causal_model_origin_fixture_never_product(self):
        producer = self.producer()
        result = f02.capture_ndjson(good(), producer)
        self.assertEqual("stream_end", result["event_kind"])
        self.assertEqual(2, result["proposed_claims"])
        self.assertFalse(result["publishable_answer"])
        self.assertFalse(result["semantic_issuer_qualified"])
        self.assertFalse(result["actual_client_ack"])
        self.assertEqual("UNKNOWN", result["actual_complete_answer_ms"])
        self.assertTrue(result["usage_observed"])
        self.assertEqual("SYNTHETIC_FIXTURE", result["model_origin_class"])
        self.assertEqual(2, len(producer.proposals))
        self.assertTrue(all(p["wire"]["raw_delta_event_ids"] for p in producer.proposals))
        self.assertEqual(
            hx(producer.proposals[0]["text"].encode()),
            producer.proposals[0]["wire"]["text_sha256"])
        self.assertEqual(len(producer.events), len(f02.verify_record_chain(self.journal)))
        self.assertNotIn(b"First generated fixture claim", self.journal.read_bytes())
        self.assertNotIn(b"Second generated fixture claim", self.journal.read_bytes())

    def test_legacy_missing_model_provenance_behavioral_red_to_green(self):
        """Before: legacy validates fabricated answer_text without true model origin.

        Run identical assertion with F02_RED_BASELINE=1 against legacy behavior.
        After: new accepted contract evaluates actual observed event origin.
        No module-missing/import failure is used as RED evidence.
        """
        text_a = "The semantic answer cache is initially OFF in Nonprod."
        text_b = "All MacBook engineering work uses Remote Desktop Commander first."
        old_file = ROOT / "src/knowledge_engine/m27_f02_reliability_stream.py"
        spec = importlib.util.spec_from_file_location("legacy_f02", old_file)
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        obs = list(old.OBLIGATIONS)
        r = [{"event": "request_started",
              "body": {"seq": 1, "request_id": "fake-old"}, "received_monotonic_ns": 10}]
        for i, (line, obligation) in enumerate(zip((text_a, text_b), obs), 2):
            r.append({"event": "answer_text", "received_monotonic_ns": i * 10,
                      "ack_monotonic_ns": i * 10 + 1, "ack_status": 200,
                      "body": {"request_id": "fake-old", "seq": i,
                               "text": line, "text_sha256": hx(line.encode()),
                               "obligation": obligation, "generated": True,
                               "verified": True, "provider_stream_open_at_emit": True,
                               "model_origin_class": "SYNTHETIC_FIXTURE",
                               "citation": {"source_sha256":
                                            old.b1.B1_PINNED_OWNER_SOURCE_SHA256}}})
        r.append({"event": "terminal", "received_monotonic_ns": 40,
                  "body": {"seq": 4, "request_id": "fake-old", "status": "answered",
                           "obligations": obs,
                           "answer_sha256": hx((text_a + "\n" + text_b).encode()),
                           "genuine_provider_done": False}})
        if os.environ.get("F02_RED_BASELINE") == "1":
            accepts_as_current = old.validate(r, require_live=False)
        else:
            # This is the new F02 admission rule, NOT an old replay signal.
            accepts_as_current = f02.has_fresh_verified_origin(r)
        self.assertFalse(accepts_as_current, "Fabricated legacy generated=True cannot imply a fresh event")

    def test_provenance_spoof_rejected(self):
        p = self.producer()
        with self.assertRaisesRegex(f02.Refused, "SPOOF"):
            p.ingest(wire("request_start", request_id="current-request",
                          model_origin_class="LIVE_NEW_PROVIDER"))

    def test_unauthorized_live_and_forged_receipt_rejected(self):
        with self.assertRaisesRegex(f02.Refused, "NEW_LIVE_GRANT"):
            self.producer(origin_class=f02.LIVE)
        for i, fake_verifier in enumerate((lambda value: False, lambda value: True)):
            with self.subTest(i=i):
                with self.assertRaisesRegex(f02.Refused, "NEW_LIVE_GRANT"):
                    f02.NativeEventProducer(pin(), f02.EventJournal(
                        Path(self.folder.name) / f"fake-grant-{i}.jsonl"),
                        origin_class=f02.LIVE,
                        live_receipt_verifier=fake_verifier,
                        authenticated_provider_receipt={"self_asserted": True})

    def test_incomplete_claims_no_provider_done(self):
        p = self.producer()
        data = good()[:3] + good()[-1:]
        with self.assertRaisesRegex(f02.Refused, "PROVIDER_DONE_REQUIRED"):
            f02.capture_ndjson(data, p)

    def test_second_obligation_missing_fail_closed(self):
        p = self.producer()
        rows = good()[:3] + good()[4:]
        with self.assertRaisesRegex(f02.Refused, "INCOMPLETE_OBLIGATIONS"):
            f02.capture_ndjson(rows, p)
        records = f02.verify_record_chain(self.journal)
        self.assertEqual("safe_abstention", records[-1]["event"]["event_kind"])
        self.assertFalse(records[-1]["event"]["publishable_answer"])

    def test_duplicate_and_forged_task_identity(self):
        p = self.producer()
        with self.assertRaisesRegex(f02.Refused, "REQUEST_ID_MISMATCH"):
            p.ingest(wire("request_start", request_id="other-task"))
        p.ingest(good()[0])
        with self.assertRaisesRegex(f02.Refused, "DUPLICATE_START"):
            p.ingest(good()[0])

    def test_delta_requires_model_identity(self):
        p = self.producer()
        p.ingest(good()[0])
        with self.assertRaisesRegex(f02.Refused, "MODEL_IDENTITY_REQUIRED"):
            p.ingest(good()[2])

    def test_source_pins_cache_and_deadline_fail_closed(self):
        for change, expected in [
            ({"cache_mode": "AUTO"}, "CACHE_NOT_AUTHORIZED"),
            ({"source_acl_sha256": "bad"}, "INVALID_HASH_PIN"),
            ({"deadline_monotonic_ns": 1}, "DEADLINE_EXPIRED"),
            ({"answer_obligation_ids": ("x", "x")}, "INVALID_OBLIGATIONS"),
        ]:
            raw = dict(pin().__dict__)
            raw.update(change)
            with self.subTest(change=change):
                with self.assertRaisesRegex(f02.Refused, expected):
                    f02.Pins(**raw).validate()

    def test_extra_tail_and_token_budget(self):
        p = self.producer()
        rows = good()[:4] + [wire("delta", text="Unsupported third.\n")] + good()[4:]
        with self.assertRaisesRegex(f02.Refused, "TOO_MANY_CLAIMS"):
            f02.capture_ndjson(rows, p)

    def test_usage_not_fabricated(self):
        p = self.producer()
        rows = good()
        rows[-2] = wire("provider_done")
        result = f02.capture_ndjson(rows, p)
        self.assertFalse(result["usage_observed"])
        self.assertEqual("UNKNOWN", result["provider_usage"])

    def test_journal_tamper_detected(self):
        p = self.producer()
        f02.capture_ndjson(good(), p)
        saved = self.journal.read_bytes()
        self.journal.write_bytes(saved.replace(b"provider_delta", b"provider_Delta", 1))
        with self.assertRaisesRegex(f02.Refused, "JOURNAL_BYTES_TAMPER"):
            f02.verify_record_chain(self.journal)

    def test_no_event_after_done(self):
        p = self.producer()
        for event in good()[:-1]:
            p.ingest(event)
        with self.assertRaisesRegex(f02.Refused, "EVENT_AFTER_PROVIDER_DONE"):
            p.ingest(wire("delta", text="late"))

    def test_remote_http_rejected_and_zero_cache(self):
        p = self.producer()
        self.assertEqual("OFF", f02.live_request_status()["cache"])
        with self.assertRaisesRegex(f02.Refused, "LOCAL_SYNTHETIC_TRANSPORT_ONLY"):
            f02.capture_loopback_http("https://model.provider.example/run", p)

    def test_real_os_loopback_tcp_fixture_only(self):
        ready = Path(self.folder.name) / "ready.json"
        server_code = """
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        if self.path != '/nonprod/f02/synthetic-wire':
            self.send_error(404);return
        self.send_response(200)
        self.send_header('Content-Type', 'application/x-ndjson')
        self.end_headers()
        rows = [
          {'event':'request_start','request_id':'current-request'},
          {'event':'model_identity','provider':'os-local-fixture','model':'fiction-v1'},
          {'event':'delta','text':'One source-bound fixture claim.\\n'},
          {'event':'delta','text':'Second fixture claim.\\n'},
          {'event':'provider_done'},
          {'event':'stream_end','provider_done':True}
        ]
        for row in rows:
            self.wfile.write(json.dumps(row).encode()+b'\\n')
            self.wfile.flush()
srv = HTTPServer(('127.0.0.1',0), Handler)
Path(sys.argv[1]).write_text(json.dumps({'port':srv.server_port}))
srv.handle_request()
srv.server_close()
"""
        child = subprocess.Popen([sys.executable, "-u", "-c", server_code,
                                  str(ready)], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.PIPE)
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)
        for _ in range(100):
            if ready.exists():
                break
            time.sleep(0.025)
        self.assertTrue(ready.exists(), child.stderr.read().decode() if child.poll() is not None else "")
        port = json.loads(ready.read_text())["port"]
        p = self.producer()
        result = f02.capture_loopback_http(
            f"http://127.0.0.1:{port}/nonprod/f02/synthetic-wire", p)
        self.assertEqual("SYNTHETIC_FIXTURE", result["model_origin_class"])
        self.assertFalse(result["publishable_answer"])
        self.assertEqual(2, len(p.proposals))
        self.assertEqual(0, child.wait(timeout=4))
        child.stderr.close()
        self.assertTrue(f02.verify_record_chain(self.journal))


if __name__ == "__main__":
    unittest.main()
