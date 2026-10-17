"""Real Google Chrome UI DOM click -> H02 joined HTTP -> CACHE01/02/03/G04 receipts."""
from __future__ import annotations
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import types

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/knowledge_engine"
pkg = types.ModuleType("knowledge_engine")
pkg.__path__ = [str(SOURCE)]
sys.modules["knowledge_engine"] = pkg
from knowledge_engine.m27_b3_h02_cache_join import H02CacheJoin, H02JoinedLoopback

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def execute(output_dir: Path):
    if not CHROME.is_file():
        raise RuntimeError("CHROME_NOT_INSTALLED")
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    with tempfile.TemporaryDirectory(prefix="b3h02-chrome-") as tmp:
        os.environ.update({
            "M27_H02_CACHE_JOIN_FIXTURE_MODE": "1",
            "M27_CACHE02_FIXTURE_TEST_MODE": "1",
            "M27_CACHE05_FIXTURE_TEST_MODE": "1",
        })
        for enabled in (False, True):
            label = "fixture_on" if enabled else "default_off"
            service = H02CacheJoin(
                feature_enabled=enabled, fixture_only=enabled,
                fixture_root=(Path(tmp) / "cache_fixture") if enabled else None)
            if enabled:
                service.provision_test_source()
            server = H02JoinedLoopback(service)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with tempfile.TemporaryDirectory(prefix="b3h02-browserprofile-") as profile:
                    url = (server.origin + "/__cache04/demo/?e2e=1" +
                           ("&fixture_feature=enabled" if enabled else ""))
                    result = subprocess.run([
                        str(CHROME), "--headless=new", "--disable-gpu",
                        "--no-first-run", "--no-default-browser-check",
                        "--disable-background-networking", "--disable-extensions",
                        "--user-data-dir=" + profile,
                        "--virtual-time-budget=6000", "--dump-dom", url],
                        capture_output=True, text=True, timeout=35, check=False)
                dom = result.stdout
                (output_dir / (label + "_chrome_dom.html")).write_text(dom)
                match = re.search(r'<pre id="e2e"[^>]*>(.*?)</pre>', dom, re.S)
                if not match:
                    raise RuntimeError(label + ":NO_BROWSER_DOM_RECEIPT:" + str(result.returncode))
                payload = json.loads(html.unescape(match.group(1)))
                cases = payload["http_results"]
                expected = (["LOOKUP_REQUIRED", "BYPASSED", "REGENERATE_NO_LOOKUP"]
                            if enabled else ["DISABLED", "BYPASSED", "DISABLED"])
                okay = (result.returncode == 0 and
                        payload["verdict"] == "PASS_BROWSER_CLICK_HTTP_RUNTIME" and
                        len(cases) == 3 and
                        [c["cache_status"] for c in cases] == expected and
                        all(c["http_status"] == 200 for c in cases) and
                        all(c["answer_cache_hit_admitted"] is False for c in cases))
                summary.append({
                    "mode": label, "chrome_exit": result.returncode,
                    "dom_sha256": hashlib.sha256(dom.encode()).hexdigest(),
                    "real_clicks": 3, "real_http_requests": 3, "statuses": expected,
                    "response_receipts": cases,
                    "on_disk_answer_cache": bool(enabled and service.store.path.exists()),
                    "verdict": "PASS_SCOPED" if okay else "FAIL",
                })
                if not okay:
                    raise RuntimeError(label + ":WRONG_BROWSER_RESPONSE")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)
    (output_dir / "browser_dual_mode_receipt.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    assert len(summary) == 2 and all(s["verdict"] == "PASS_SCOPED" for s in summary)


if __name__ == "__main__":
    execute(Path(sys.argv[1]))
