# Knowledge Build Pipeline Contract

- Contract ID: `KOS-BUILD-001`
- Version: `0.1.0`
- Status: Normative Draft
- Producer: Knowledge Builder
- Primary store: Cloudflare R2

## 1. Purpose

本契約把 `knowledge-source -> knowledge-builder -> R2` 展開成可觀測、可重試、可重現、可阻止錯誤發布的狀態機。

## 2. Pipeline modes

| Mode | Use case | Required behavior |
|---|---|---|
| `full` | 首次建置或週期性全量驗證 | 從所有 active sources 重建 |
| `incremental` | 一般更新 | 只重建受影響 lineage，但輸出完整 release |
| `reproducibility` | 驗證可重建性 | 相同 inputs 產生相同 deterministic artifacts |
| `repair` | 修復 quarantine 項目 | 不得略過原始失敗原因 |
| `rollback` | 切回舊 release | 不重寫舊 artifact，只改 channel pointer |

## 3. State machine

```text
queued
 -> acquiring
 -> snapshotted
 -> normalized
 -> extracted
 -> resolved
 -> synthesized
 -> validated
 -> awaiting_review
 -> approved
 -> compiled
 -> packaged
 -> published
 -> promoted
```

失敗分支：

```text
<any active state> -> failed_retryable
<any active state> -> quarantined
<published> -> revoked
<promoted> -> superseded
```

任何狀態變更 `MUST` 產生 audit event。

## 4. Build input contract

每次 build `MUST` 固定以下 inputs：

```json
{
  "build_id": "build_20260702T120000Z_01",
  "mode": "incremental",
  "source_repository": "danielcanfly/knowledge-source",
  "source_commit_sha": "40-char git sha",
  "foundation_repository": "danielcanfly/knowledge-os-foundation",
  "foundation_commit_sha": "40-char git sha",
  "builder_version": "0.1.0",
  "builder_commit_sha": "40-char git sha",
  "profile": "daniel-knowledge-os/0.1",
  "target_channel": "staging",
  "requested_by": "actor-id",
  "requested_at": "UTC ISO 8601"
}
```

Rules：

- Git SHA `MUST` 是完整 40 位小寫十六進位。
- Working tree dirty build `MUST NOT` 進 production。
- Builder config `MUST` 被 canonicalize 並 hash。
- Model name、prompt/template version、temperature 與 seed `MUST` 被記錄。

## 5. Pipeline stages

### Stage 0: Plan

Inputs：build request、change set、current release manifest。

Outputs：

- dependency impact graph
- source acquisition plan
- estimated resource budget
- target release ID

Fatal conditions：

- unsupported contract version
- unknown source connector
- target release ID collision

### Stage 1: Acquire

Builder 從 approved connectors 取得來源。

Rules：

- Network acquisition `MUST` 設 timeout、size limit、allowed host policy。
- Redirect chain `MUST` 記錄。
- Authentication secrets `MUST NOT` 進 log 或 artifact。
- 來源取得失敗不得以舊內容冒充新快照。

### Stage 2: Snapshot

每個 source `MUST` 產生不可變 snapshot metadata：

```text
source_id
source_version
original_uri
retrieved_at
content_sha256
bytes
media_type
license
owner
audience
connector_version
```

Snapshot object key 建議：

```text
sources/<source_id>/<content_sha256>/raw
```

### Stage 3: Normalize

輸出 normalized document 與 source map。

Rules：

- 原始頁碼、line、timestamp 或 DOM selector `SHOULD` 被保留。
- OCR 內容 `MUST` 標示 extraction method 與 confidence。
- 表格、程式碼與 heading boundary `SHOULD` 保留。
- Normalization `MUST` 是 deterministic，除非 manifest 明確記錄 nondeterministic component。

### Stage 4: Extract

辨識 knowledge candidates：

- entities
- concepts
- claims
- definitions
- decisions
- relationships
- contradictions
- dates
- calculations

每個 candidate `MUST` 保留 source locator 與 extraction run ID。

### Stage 5: Resolve

Builder 判斷 candidate 應：

- create
- update
- merge
- alias
- contradict
- ignore
- quarantine

Rules：

- Identity decision `MUST` 優先使用 `x-kos-id`，其次使用 explicit resource URI，最後才用名稱相似度。
- 自動 merge `MUST` 達到 configured threshold。
- 低於 threshold 或多重匹配 `MUST` 進 review queue。
- Merge `MUST` 保存被合併 IDs 與理由。

### Stage 6: Synthesize

Builder 更新 OKF draft bundle。

Rules：

- 不得刪除無關人工內容。
- 每個新增 claim `MUST` 建立 provenance entry。
- 推論 `MUST` 標示 derivation type。
- 衝突來源不得被靜默平均或任選其一。
- LLM edit `MUST` 留下 model、prompt hash、run ID。

### Stage 7: Validate

Validation 分為 deterministic 與 semantic。

Deterministic gates `MUST` 包含：

- YAML parse
- OKF Profile fields
- unique `x-kos-id`
- internal link resolution
- provenance schema
- provenance source references
- ACL propagation
- secret scan
- artifact path safety
- duplicate aliases
- release manifest schema

Semantic gates `SHOULD` 包含：

- claim supportedness
- contradiction disclosure
- stale content detection
- duplicate concept detection
- title and description quality

任何 fatal gate failure `MUST` 阻止發布。

### Stage 8: Review

Review queue item `MUST` 包含：

```text
change summary
before and after diff
source evidence
confidence
risk flags
ACL impact
identity decision
```

Rules：

- Security、ACL downgrade、declassification 與 destructive merge `MUST` 人工 review。
- 一般低風險變更可依 policy 自動 approve。
- Reviewer identity 與時間 `MUST` 寫入 concept frontmatter 或 review registry。

### Stage 9: Compile

Builder 從 approved OKF bundle 產生：

```text
bundle/
pages/
sections/
graph.json
lexical-index/
semantic-index/          optional
source-map/
provenance/
build-report.json
```

Rules：

- `graph.json` `MUST` 完全由 OKF links 與明確 relation metadata 生成。
- `graph.json` `MUST NOT` 是人工 source of truth。
- 每個 section `MUST` 保留 concept ID、heading path、text hash、audience 與 provenance refs。
- Semantic index model與dimension `MUST` 寫入 manifest。

### Stage 10: Package

所有 artifacts `MUST`：

- 計算 SHA-256
- 記錄 byte size與media type
- 放入單一 immutable release prefix
- 寫入 release manifest
- 驗證 manifest 指向的 object 全部存在

R2 layout：

```text
knowledge-store/
├── releases/<release_id>/manifest.json
├── releases/<release_id>/bundle/...
├── releases/<release_id>/artifacts/...
└── channels/<channel>.json
```

### Stage 11: Publish

Publish 將 immutable objects 上傳 R2。

Rules：

- Object key collision with different hash `MUST` 失敗。
- Multipart upload未完成不得產生 channel pointer。
- Manifest `MUST` 最後上傳。
- 發布完成不等於 promotion。

### Stage 12: Promote

Promotion 原子更新 channel pointer：

```json
{
  "channel": "production",
  "release_id": "20260702T120000Z-a1b2c3d",
  "manifest_key": "releases/20260702T120000Z-a1b2c3d/manifest.json",
  "manifest_sha256": "64 hex",
  "promoted_at": "UTC ISO 8601",
  "promoted_by": "actor-id"
}
```

Rules：

- Pointer update `MUST` 使用 conditional write、ETag compare或等價 CAS。
- Production promotion `MUST` 只指向 quality overall `passed` 的 manifest。
- Previous pointer `MUST` 被保留供 rollback。

## 6. Incremental impact calculation

Changed source `S` 的受影響集合：

```text
I0 = concepts directly supported by S
I1 = concepts linking to or derived from I0
I2 = indexes, graph partitions, search sections, caches containing I0 or I1
```

Builder `MUST` 重建 `I0 + I1 + I2`，並輸出一個完整一致 release。

不得只覆蓋零散 production object。

## 7. Idempotency and reproducibility

在以下 inputs 相同時：

- source snapshots
- source commit
- foundation commit
- builder commit
- builder config
- model outputs or deterministic response cache

Builder `SHOULD` 產生相同 artifact hashes。

若 LLM 造成 nondeterminism：

1. 原始 model response `MUST` 被 snapshot。
2. Compile 階段 `MUST` 使用已固定 response。
3. Reproducibility build 不得重新呼叫模型。

## 8. Retry and quarantine

| Failure type | Retry | Behavior |
|---|---:|---|
| transient network | yes | exponential backoff with cap |
| rate limit | yes | respect retry-after |
| schema invalid | no | quarantine |
| ambiguous identity | no automatic | review queue |
| ACL downgrade | no | security quarantine |
| hash mismatch | one clean re-fetch | quarantine if repeated |
| secret detected | no | revoke logs/artifacts as needed |

同一 stage 最大自動 retry 次數 `MUST` 可配置，預設 3。

## 9. Observability

每次 build `MUST` 輸出：

- build ID
- stage durations
- source counts
- created/updated/deprecated concepts
- warning and failure codes
- token and model usage
- artifact sizes
- quality gate results
- release ID
- promotion result

Logs `MUST` 使用 structured JSON，且不得包含來源全文或 secrets。

## 10. Quality gates

Production promotion 最低 gates：

| Gate | Requirement |
|---|---|
| `okf_profile` | passed |
| `internal_links` | 0 broken |
| `provenance` | 100% required records valid |
| `acl_propagation` | 0 downgrade |
| `secret_scan` | passed |
| `artifact_integrity` | passed |
| `golden_queries` | threshold met |
| `reproducibility` | passed or explicitly waived outside production |

Waiver `MUST NOT` 用於 ACL、secret、artifact integrity。

## 11. Failure codes

| Code | Meaning |
|---|---|
| `BUILD-001` | Unsupported contract or profile version |
| `BUILD-002` | Source acquisition failed |
| `BUILD-003` | Snapshot hash mismatch |
| `BUILD-004` | Normalization lost required locator |
| `BUILD-005` | Identity resolution ambiguous |
| `BUILD-006` | Synthesis deleted protected content |
| `BUILD-007` | Deterministic validation failed |
| `BUILD-008` | Semantic review failed |
| `BUILD-009` | Artifact compile inconsistency |
| `BUILD-010` | R2 object collision |
| `BUILD-011` | Manifest incomplete |
| `BUILD-012` | Promotion CAS conflict |
| `BUILD-013` | Production release not reproducible |
| `BUILD-014` | Secret or restricted data leak |

## 12. Required acceptance tests

1. 同一 fixed input 連續 build 兩次，artifact hashes 相同。
2. 中途 upload 失敗時，production pointer 不變。
3. Manifest 缺少任何 required artifact 時，promotion 被拒絕。
4. ACL downgrade 時 build 進 security quarantine。
5. Wikilink 多重匹配時 release build 失敗。
6. 修改已發布 R2 object 後，Runtime integrity check 失敗。
7. Rollback 只修改 channel pointer，不重寫舊 release。
8. Source deletion 能找到並失效所有直接衍生 claim。
