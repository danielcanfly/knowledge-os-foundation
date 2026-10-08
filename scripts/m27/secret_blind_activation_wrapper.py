#!/usr/bin/env python3
"""Stage 30M fail-closed, secret-blind activation contract.

This entry point deliberately does not inspect containers or provider configuration.
An independently authorized VM-local activation boundary is required before runtime
swap is supported. No automatic use of Docker env/config migration is permitted.
"""
import argparse
import json
import re
from datetime import datetime, timezone

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--image", required=True)
    p.add_argument("--port", type=int, default=18080)
    p.add_argument("--container", default="m27-owner-canary-28")
    p.add_argument("--rollback-image", required=True)
    p.add_argument("--timeout", type=int, default=30)
    a = p.parse_args()
    safe_image = re.compile(r"^[a-zA-Z0-9_./:@-]{1,200}$")
    safe_name = re.compile(r"^[a-zA-Z0-9_.-]{1,100}$")
    if not (safe_image.fullmatch(a.image) and safe_image.fullmatch(a.rollback_image) and
            safe_name.fullmatch(a.container) and a.port in (18080, 18081, 18082) and
            1 <= a.timeout <= 120):
        raise SystemExit("INVALID_ALLOWLISTED_ARGUMENT")
    print(json.dumps({
        "wrapper_version": "30m-1",
        "target_image": a.image,
        "previous_image": a.rollback_image,
        "candidate_container": a.container,
        "loopback_port": a.port,
        "health_http_code": None,
        "activation_status": "BLOCKED_PROVIDER_CONFIG_BOUNDARY",
        "rollback_status": "NOT_NEEDED_NO_MUTATION",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "receipt_file_path": "docs/m27/research/m27_secret_blind_activation_wrapper_receipts.json"
    }, sort_keys=True))
    return 20

if __name__ == "__main__":
    raise SystemExit(main())
