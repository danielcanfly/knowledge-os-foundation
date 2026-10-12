"""P28R diagnostic health readiness must not mistake 200/starting for READY."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

_SOURCE = Path(__file__).resolve().parents[1] / "src/knowledge_engine/p28r_local_healthcheck.py"
_SPEC = importlib.util.spec_from_file_location("p28r_local_healthcheck", _SOURCE)
assert _SPEC and _SPEC.loader
hc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(hc)

HASH = "a" * 64
EXPECTED = dict(
    expected_channel="p28-nonprod",
    expected_release_id="p28r-test-owned",
    expected_manifest_sha256=HASH,
)


class Response:
    status = 200

    def __init__(self, payload: object):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _: int) -> bytes:
        return json.dumps(self.payload).encode()


@pytest.mark.parametrize(
    "payload,passed",
    [
        ({"status": "starting", "channel": "p28-nonprod"}, False),
        (
            {
                "status": "healthy",
                "channel": "p28-nonprod",
                "release_id": "p28r-test-owned",
                "manifest_sha256": HASH,
            },
            True,
        ),
        (
            {
                "status": "healthy",
                "channel": "p28-nonprod",
                "release_id": "wrong",
                "manifest_sha256": HASH,
            },
            False,
        ),
        (
            {
                "status": "healthy",
                "channel": "wrong",
                "release_id": "p28r-test-owned",
                "manifest_sha256": HASH,
            },
            False,
        ),
        (
            {
                "status": "healthy",
                "channel": "p28-nonprod",
                "release_id": "p28r-test-owned",
                "manifest_sha256": "b" * 64,
            },
            False,
        ),
    ],
)
def test_health_status_and_bound_identity(payload: dict, passed: bool) -> None:
    with patch.object(hc, "urlopen", return_value=Response(payload)):
        assert hc.probe(**EXPECTED) is passed


def test_missing_authority_identity_is_closed() -> None:
    with patch.object(hc, "urlopen", return_value=Response({})):
        assert not hc.probe(**{**EXPECTED, "expected_release_id": ""})
        assert not hc.probe(**{**EXPECTED, "expected_manifest_sha256": "not-a-sha"})
        assert not hc.probe(**EXPECTED, url="https://example.org/health")


@pytest.mark.parametrize(
    "env,expected_exit",
    [
        ({}, 1),
        (
            {
                "APP_ENV": "production",
                "OBJECT_STORE_BACKEND": "filesystem",
                "P28R_NONPROD_TEST_SCOPE": "authorized",
            },
            1,
        ),
        (
            {
                "APP_ENV": "test",
                "OBJECT_STORE_BACKEND": "r2",
                "P28R_NONPROD_TEST_SCOPE": "authorized",
            },
            1,
        ),
        (
            {
                "APP_ENV": "test",
                "OBJECT_STORE_BACKEND": "filesystem",
                "P28R_NONPROD_TEST_SCOPE": "authorized",
            },
            0,
        ),
    ],
)
def test_main_requires_test_scope(env: dict[str, str], expected_exit: int) -> None:
    values = {
        "KNOWLEDGE_CHANNEL": "p28-nonprod",
        "P28R_EXPECTED_TEST_RELEASE_ID": "p28r-test-owned",
        "P28R_EXPECTED_TEST_MANIFEST_SHA256": HASH,
        **env,
    }
    payload = {
        "status": "healthy",
        "channel": "p28-nonprod",
        "release_id": "p28r-test-owned",
        "manifest_sha256": HASH,
    }
    with (
        patch.dict("os.environ", values, clear=True),
        patch.object(hc, "urlopen", return_value=Response(payload)),
    ):
        assert hc.main() == expected_exit
