# M27 hot-patch provenance Direct100 pass handoff

Decision: `M27_DIRECT100_TARGETED_GUARD_RERUN_PASS`

A secret-safe hot-patch of the isolated candidate on `127.0.0.1:18080` closed the Stage 30J provenance false-safe failures. The Direct100 rerun completed with 100/100 HTTP success, 87/87 answerable cited final, 13/13 expected safe correct, 0 false safe terminal, 0 missed safe terminal, 0 thin cited answer, 0 topic contamination, 0 semantic bad publish, p95 final 7735.191 ms, p95 first-material 7734.305 ms, and no M26 mature composer delegation.

The active container is still named `m27-owner-canary-28`; its original image tag remains `knowledge-engine:m27-direct100-targeted-guard-30j-2dc7990e`, but two runtime files were hot-patched in-place from the Stage 30K workspace. A proper immutable image rebuild/activation can be prepared later using this committed source state and an authorized activation executor.

No owner-only route certification, public rollout, production deploy, release pointer mutation, public percentage canary, admission/full523, Stage13/14, Chunk002, Nginx edit/reload, production M26 restart/rebuild, test backend restart/rebuild, production datastore write, or protected owner verification material usage occurred.

Owner-only route certification remains pending and must not be inferred from this result.
