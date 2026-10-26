"""Cloudflare image-native adapter tests; no network and no real secrets."""
from __future__ import annotations

import importlib.util
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


if __name__ == "__main__":
    unittest.main()
