# N31: opt-in isolated localhost ASGI task fixture

This artifact is **NOT** an authentic M26 App, a signed nonprod image, a production API
replacement, or authority to call an external Provider. It does not modify the default
OCI command, healthguard, release manifest, I28/I02, coding source, or Production.

## Local wire path

Native OS HTTP `POST /task` with a transient local test-only token
→ strict fixed `tenantA/principalA/rev1` TaskContract fields + `lease_epoch=1`
→ `m27_i28_local_fixture_inputs.make()` constructs AR02 durable journal and immutable
I02 `TaskContract`
→ M28 committed local grant + `I02LocalRuntimeV1.admit()`
→ existing I02 `qa()`, `research_workflow()` or `action_local()`.

- QA-I: I28 fixed source SHA and independent proof; synchronous flush is handed
  through ASGI queue and acknowledges **the ASGI send before I02 completes**.
  Substantive UTF-8 arrives as NDJSON `cited_text` frames with original citation
  IDs before `terminal`. No signed remote-client ACK is claimed.
- RES-L: AR02 SQLite durable checkpoints and reopened research readback. N31 writes
  the returned fixture bytes to an exclusive local Markdown file, fsyncs and hashes.
- ACT-LOCAL: R29 fixed loopback adapter, separate HTTP/SQLite service, same admitted
  I02 action path. Durable UNKNOWN is never automatically retried; the negative
  after-enqueue M28 revocation denies the request before physical POST.
- CODE-L: the existing I28 fixed ephemeral fixture remains as it was; N31 does not
  claim persisted coding source, patch.diff or an independently tested source artifact.

## Flags and health

Required at startup: `APP_ENV=test`, `N31_LOCAL_ONLY=1`, `N31_ROOT`,
`N31_TEST_TOKEN` (local synthetic, >=24 bytes), `N31_FIXTURE_PORT` and
`N31_FIXTURE_TOKEN`. Launch via `scripts/n31_serve.py --host 127.0.0.1 --port PORT`
with local-only ephemeral roots. The launch wrapper denies a nonloopback host and
guards its process against nonloopback TCP connects. The ASGI handler independently
rejects nonloopback client/server addresses, nonloopback Host, and requests without the
local fixture token. The mock token is **not IdP**.

`GET /health` deliberately returns HTTP 503 `not_ready` / `local_fixture_only`.
The wrapper disables lifespan only for **this new N31 fixture ASGI app**, never for
`m26_production_api`. No signed release or authorized bundle is substituted.

## Evidence boundaries

`scripts/n31_os_acceptance.py` starts a physically separate uvicorn ASGI PID and
R29 fixture PID, drives an independent native HTTPConnection client, and launches a
separate read-only SQLite observer. The evidence folder records process PIDs, ephemeral
ports, HTTP 2xx vs denied 403, actual citation frames, artifact hash, effect counts,
revocation, UNKNOWN replay denial, and a process-scoped socket connect log.

AR09 remains **ORACLE_UNAVAILABLE**, with `ar09_evaluator_executed=false`; AR10 stays
**DRAFT**, with `ar10_registration_executed=false`. These response fields are honest
scope labels, not fabricated AR09 grading results or AR10 registration receipts.
Original J29 I28 ten cases and ACT-LOCAL twelve cases remain historical denominators.
N31 HTTP tests are a separate denominator and are not official original523/blind200.

No p95, real invoices, verified source license, signed OCI, provider side effect,
genuine IdP, external client signature or full default-App READY is claimed.
