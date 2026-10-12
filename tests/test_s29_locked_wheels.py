"""S29 fail-closed offline dependency-content lock tests."""
import hashlib
import zipfile

import pytest
from scripts.s29_verify_locked_wheels import verify


def make_wheel(root, *, tags="py3-none-any"):
    root.mkdir(exist_ok=True)
    path = root / f"probe-1.0-{tags}.whl"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "probe-1.0.dist-info/METADATA", "Metadata-Version: 2.3\nName: probe\nVersion: 1.0\n"
        )
        z.writestr("probe-1.0.dist-info/WHEEL", f"Wheel-Version: 1.0\nTag: {tags}\n")
        z.writestr("probe/__init__.py", "VALUE = 1\n")
    return path


def lock(tmp_path, wheel):
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    path = tmp_path / "lock.txt"
    path.write_text(f"probe==1.0 --hash=sha256:{digest}\n")
    return path


def test_valid_complete_pure_wheel_lock(tmp_path):
    wheel = make_wheel(tmp_path / "wheels")
    result = verify(wheel.parent, [lock(tmp_path, wheel)], None)
    assert result["status"] == "PASS"
    assert result["wheel_count"] == 1


def test_tamper_rejected(tmp_path):
    wheel = make_wheel(tmp_path / "wheels")
    requirements = lock(tmp_path, wheel)
    with wheel.open("ab") as stream:
        stream.write(b"tamper")
    with pytest.raises(ValueError, match="hash/version mismatch"):
        verify(wheel.parent, [requirements], None)


def test_missing_artifact_rejected(tmp_path):
    wheel = make_wheel(tmp_path / "wheels")
    requirements = lock(tmp_path, wheel)
    wheel.unlink()
    with pytest.raises(ValueError, match="missing wheels"):
        verify(wheel.parent, [requirements], None)


def test_wrong_platform_rejected(tmp_path):
    wheel = make_wheel(tmp_path / "wheels", tags="cp311-cp311-macosx_13_0_arm64")
    requirements = lock(tmp_path, wheel)
    with pytest.raises(ValueError, match="not Linux arm64/pure"):
        verify(wheel.parent, [requirements], None)


def test_conflicting_locks_rejected(tmp_path):
    wheel = make_wheel(tmp_path / "wheels")
    a = lock(tmp_path, wheel)
    b = tmp_path / "bad.lock"
    b.write_text("probe==2.0 --hash=sha256:" + "0" * 64 + "\n")
    with pytest.raises(ValueError, match="conflicting"):
        verify(wheel.parent, [a, b], None)
