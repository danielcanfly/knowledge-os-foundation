"""Fail-closed LOCAL nonproduction container readiness; never a release/rights attestation.

A 200 HTTP response is insufficient: /v1/health emits 200 with status=starting
when the nonprod channel pointer/bundle is absent. Verify explicit scoped
test identity, manifest digest, and actual loaded channel.
"""

from __future__ import annotations

import json
import os
import re
from urllib.request import urlopen

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def probe(
    *,
    expected_channel: str,
    expected_release_id: str,
    expected_manifest_sha256: str,
    url: str = "http://127.0.0.1:8080/v1/health",
) -> bool:
    """Trust only loopback and an independently supplied scoped test identity."""
    if not url.startswith("http://127.0.0.1:"):
        return False
    if not all(
        (expected_channel, expected_release_id, _SHA256.fullmatch(expected_manifest_sha256))
    ):
        return False
    try:
        with urlopen(url, timeout=3) as response:  # noqa: S310 - loopback validated above
            if response.status != 200:
                return False
            data = json.loads(response.read(32768))
    except (OSError, ValueError, TypeError):
        return False
    return (
        isinstance(data, dict)
        and data.get("status") == "healthy"
        and data.get("channel") == expected_channel
        and data.get("release_id") == expected_release_id
        and data.get("manifest_sha256") == expected_manifest_sha256
    )


def main() -> int:
    # Explicit externally provided test scope, NOT authority to build a bundle.
    if os.environ.get("APP_ENV") != "test":
        return 1
    if os.environ.get("OBJECT_STORE_BACKEND") != "filesystem":
        return 1
    if os.environ.get("P28R_NONPROD_TEST_SCOPE") != "authorized":
        return 1
    ok = probe(
        expected_channel=os.getenv("KNOWLEDGE_CHANNEL", ""),
        expected_release_id=os.getenv("P28R_EXPECTED_TEST_RELEASE_ID", ""),
        expected_manifest_sha256=os.getenv("P28R_EXPECTED_TEST_MANIFEST_SHA256", ""),
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
