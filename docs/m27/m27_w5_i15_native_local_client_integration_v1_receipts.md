# M27 W5 I15 | Native Local Client Integration V1

## Scope and trust boundary

I15 is a new feature-off nonproduction synthetic fixture transport using AR08 NativeQATransportAdapter, T14 HTTP/SSE encoding and strict header checks, and T09 source rights semantics and fail-closed duration denominator. No existing AR08/T09/T14/I02/B13R code is changed.

Each case uses an ephemeral 127.0.0.1 real TCP socket with an OS server process and a *different* OS client process. The client makes repeated real socket.recv(7) calls and records its own request_ns, first_recv_ns, first_data_ns and terminal_ns monotonic timestamps. Durations compare client-clock values ONLY. Server enqueue/flush and terminal use server-clock values ONLY.

The client accepts first substantive DATA only after verifying contiguous answer byte offsets, frame SHA256, expected answer prefix, native citation ID, source ID/revision/SHA256, original source byte claim/span, proof ID, current synthetic fixture rights and consent, and the stable request/run/trace/tenant/actor binding. It refuses to mistake progress messages for answer text. Terminal must follow a full byte-exact answer and happen strictly later than first answer DATA. Duplicates, spoofed proof/cost/image/ACK, unauthorized tenants, malformed Unicode, stale/revoked rights, and foreign revisions are rejected.

The synthetic local authority ports are explicitly NOT independently authenticated original source authority. A local child PID is NOT a real authenticated app client ACK. An observed TCP frame does NOT qualify as production Provider, signed OCI build, independent original 523 scorer, or commercial billing receipt.

## Twelve dynamic local synthetic examples

| Case | Representative native text | Source revision |
|---|---|---|
| synthetic-00 | 臺北彩虹 | fixture-r01 |
| synthetic-01 | 河內 / Việt | fixture-r02 |
| synthetic-02 | 東京 | fixture-r03 |
| synthetic-03 | 서울 | fixture-r04 |
| synthetic-04 | Singapore 中文 | fixture-r05 |
| synthetic-05 | 香港電車 | fixture-r06 |
| synthetic-06 | 曼谷ภาษาไทย | fixture-r07 |
| synthetic-07 | 高雄 | fixture-r08 |
| synthetic-08 | 大阪 | fixture-r09 |
| synthetic-09 | 新竹 | fixture-r10 |
| synthetic-10 | 檳城 | fixture-r11 |
| synthetic-11 | 峴港 | fixture-r12 |

Each actual answer/source SHA256 differs. The request, run, trace, actor, source, revision and citation bind per case. Three distinct synthetic tenants are used. The first CJK Unicode character is split *inside* its multibyte UTF-8 code point before AR08 push, while actual client recv boundary fragments are only seven bytes.

## Independent socket faults and named negative cases

The actual child-process probe drives 12 local positives and 16 faults: progress-only, dropped terminal, HTTP 500, disconnect, wrong tenant, wrong source revision, corrupt source SHA, wrong trace, wrong citation, invalid UTF-8, duplicate frame, duplicate terminal, forged client ACK, revocation after enqueue, expiry after enqueue, and real bounded client receive timeout. Transport is real, localhost-only and ephemerally bound. Successful cases need server enqueue/flush ordering, actual separate client receive, correct answer and source digest, first DATA before terminal. All fault cases must fail.

A pytest protocol mutation matrix independently runs 19 separately verified fields times five hostile values = 95 named negative cases; seven fake external authority classes; 15 protocol and failure types, plus malformed corpus/denominator cases. All tests must actually execute; their count is not product Q&A benchmark volume.

All socket attempts, including failures, missing terminal, rejected data and abstentions, are retained in T09 DurationCase denominator. Local nearest-rank first-text p95 is emitted only when ALL requests successfully complete; with any incomplete request, p95 is UNKNOWN. A fast localhost fixture does not establish product p95<=15s.

## Reproduction and raw evidence custody

Use pinned Python /Users/huaihsuanhuang/.pyenv/versions/3.11.15/bin/python with PYTHONPATH=src, TMPDIR=/tmp, PYTHONDONTWRITEBYTECODE=1, PYTEST_DISABLE_PLUGIN_AUTOLOAD=1. Run the I15 module as -m knowledge_engine.m27_w5_i15_native_local_client_integration_v1_experimental probe, supplying --worktree absolute I15 worktree and --scratch external-private non-Git directory.

The JSON receipt is I15_REAL_MULTICASE_SOCKET_RECEIPT.json and includes every real server/client PID, 127.0.0.1 endpoint, client recv count/bytes, source SHA/revision, verified answer digest, progress and DATA, request-to-first-DATA and terminal timestamps, failure statuses, and the full fixed denominator. Its on-disk SHA256 is reported in worker REPORT.md. Raw pinned pytest/Ruff command logs and postcommit replay are placed in the same outside-Git scratch; no fake external receipt will be introduced.

## Unchanged explicit gates

REAL_APP_CLIENT_ACK_UNVERIFIED; REAL_PROVIDER_AND_RIGHTS_UNVERIFIED;
ORIGINAL_523_CITED_RATE_UNVERIFIED; PRODUCT_P95_UNVERIFIED;
W4_AR09_PHASE_B_BLOCKED; REL01_NOT_CERTIFIED; REL02_NOT_AUTHORIZED;
B13_RUNTIME_POSITIVE_BLOCKED.

Even I15_LOCAL_MULTICASE_WIRE_PASS permits only local engineering smoke evidence. G15 still must independently inspect committed code and replay the network, rights, original 523, and G09/B13 gates before any broader acceptance. No W6, release, or Production permission is inferred.
