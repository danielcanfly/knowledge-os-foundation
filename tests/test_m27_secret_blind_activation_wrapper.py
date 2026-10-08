import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/m27/secret_blind_activation_wrapper.py"

def test_fail_closed_receipt():
    p = subprocess.run([sys.executable, str(SCRIPT), "--image", "knowledge-engine:m27-direct100-provenance-30k", "--rollback-image", "knowledge-engine:m27-direct100-targeted-guard-30j-2dc7990e"], capture_output=True, text=True)
    assert p.returncode == 20
    r = json.loads(p.stdout)
    assert r["activation_status"] == "BLOCKED_PROVIDER_CONFIG_BOUNDARY"
    assert r["rollback_status"] == "NOT_NEEDED_NO_MUTATION"
    assert not any(x in r for x in ("env", "secrets", "provider_config", "credentials", "headers", "cookies", "command_line"))
    assert "TOKEN" not in p.stdout and "PASSWORD" not in p.stdout

def test_rejects_untrusted_input():
    p = subprocess.run([sys.executable, str(SCRIPT), "--image", "bad;echo", "--rollback-image", "safe"], capture_output=True, text=True)
    assert p.returncode != 0
    assert "INVALID_ALLOWLISTED_ARGUMENT" in p.stderr
