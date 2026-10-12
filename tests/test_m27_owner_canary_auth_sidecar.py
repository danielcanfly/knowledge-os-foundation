from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from scripts.m27_owner_canary_auth_sidecar import _load_first_private_value


def test_private_file_mode_required() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "owner.env"
        p.write_text("OWNER_CANARY_VALUE=example\n")
        os.chmod(p, 0o644)
        with pytest.raises(RuntimeError, match="TOO_PERMISSIVE"):
            _load_first_private_value(p)


def test_private_file_value_loaded() -> None:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "owner.env"
        p.write_text("OWNER_CANARY_VALUE=example\n")
        os.chmod(p, 0o600)
        assert _load_first_private_value(p) == "example"
