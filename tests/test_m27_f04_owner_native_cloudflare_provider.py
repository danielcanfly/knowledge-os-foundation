"""Cloudflare image-native adapter tests; no network and no real secrets."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/knowledge_engine"))
MODULE = ROOT / "packaging/m27_f04_owner_native_01/native_cloudflare_provider.py"
spec = importlib.util.spec_from_file_location("native_cloudflare_provider_test", MODULE)
provider = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider)


class FakeCodec:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def one_bounded_stream(self, **kwargs):
        model = provider.MODEL
        request_id = kwargs["request_id"]
        yield b"one", {"kind": "delta", "text": "First.\n",
                       "model": model, "request_id": request_id}
        yield b"two", {"kind": "delta", "text": "Second.",
                       "model": model, "request_id": request_id}
        yield b"done", {"kind": "done", "text": "",
                        "model": model, "request_id": request_id}


class NativeCloudflareProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.account = Path(self.tmp.name) / "account"
        self.token = Path(self.tmp.name) / "token"
        self.account.write_text("a" * 32)
        self.token.write_text("t" * 40)
        self.account.chmod(0o600)
        self.token.chmod(0o600)

    def test_direct_cloudflare_is_primary_and_terminal(self):
        with mock.patch.object(provider.wire, "DirectWorkersAISSE", FakeCodec):
            events = list(provider.stream(account_file=self.account,
                                          token_file=self.token,
                                          prompt="grounded prompt"))
        self.assertEqual(events[0]["model"], provider.MODEL)
        self.assertEqual(events[0]["route"], provider.ROUTE)
        self.assertEqual(sum(e["event"] == "model_identity" for e in events), 1)
        self.assertEqual(events[-2]["event"], "provider_done")
        self.assertTrue(events[-1]["provider_done"])
        self.assertNotIn("t" * 40, repr(events))

    def test_account_permissions_fail_closed(self):
        self.account.chmod(0o644)
        with self.assertRaisesRegex(provider.Denied, "OWNER_MODE"):
            list(provider.stream(account_file=self.account,
                                 token_file=self.token,
                                 prompt="grounded prompt"))

    def test_http_classification_is_bounded(self):
        error = mock.Mock(code=429)
        error.read.return_value = b'{"errors":[{"code":3036}]}'
        self.assertEqual(provider._http_category(error),
                         "CLOUDFLARE_DAILY_QUOTA_EXHAUSTED_3036")

    def test_known_native_terminal_tail_normalizes_without_answer_text(self):
        answer = "First. Second."
        tail = {"response": answer, "usage": {"prompt_tokens": 20,
                "completion_tokens": 4, "total_tokens": 24},
                "model": provider.MODEL}
        raw = b"data: " + json.dumps(tail).encode() + b"\n"
        frames = [
            b'data: {"model":"gpt-oss-120b","choices":[{"delta":{"content":"First. Second."},"finish_reason":"stop"}]}\n',
            raw,
            b"data: [DONE]\n",
        ]
        audits = []
        normalized = list(provider.compatible_sse(frames, audit=audits.append))
        self.assertEqual(len(normalized), 3)
        self.assertNotIn(answer.encode(), normalized[1])
        self.assertEqual(audits[0]["upstream_raw_line_sha256"],
                         __import__("hashlib").sha256(raw).hexdigest())

    def test_unknown_native_tail_is_not_normalized(self):
        bad = b'data: {"response":"different","usage":{},"secret":"x"}\n'
        frames = [
            b'data: {"model":"gpt-oss-120b","choices":[{"delta":{"content":"First."},"finish_reason":"stop"}]}\n',
            bad,
        ]
        self.assertEqual(list(provider.compatible_sse(frames, audit=lambda _: None))[-1], bad)


if __name__ == "__main__":
    unittest.main()
