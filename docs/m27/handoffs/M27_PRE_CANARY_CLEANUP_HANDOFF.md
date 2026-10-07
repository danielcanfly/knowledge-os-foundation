# M27 Pre-Canary Cleanup Handoff

State: `M27_PRE_CANARY_CLEANUP_READY_FOR_ACTIVATION_SESSION`

Workspace: `/home/ubuntu/LLM_Wiki-m27-pre-canary-cleanup-27`  
Branch: `m27/pre-canary-cleanup-27`  
Base: `dd3275bbb9b2c65772005ca468387a9b76500eeb`

Stage 27 closed the required pre-canary cleanup without activating traffic. The next session may be an explicit canary activation session only if the Owner authorizes it.

Carry forward these non-negotiables:
- preserve the Stage 25 missing raw-compare provenance warning
- instantiate telemetry identity before admitting any request
- record route id, candidate id, candidate SHA, immutable runtime identity/digest if available, and canary mode
- record pre/post Nginx checksums
- keep production M26 on 8080 and candidate loopback-only on 18080 until explicit route authorization
- route to zero immediately on any documented stop condition
- do not connect M27 to the M26 mature answer composer

See `docs/m27/canary/M27_ROUTE_TO_ZERO_RUNBOOK.md` and `docs/m27/research/m27_stage25_raw_compare_provenance_repair.json`.
