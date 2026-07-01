# Runtime Query Contract

- Contract ID: `KOS-RUNTIME-001`
- Version: `0.1.0`
- Status: Normative Draft
- Transport: HTTP JSON over TLS
- Normal data source: Cloudflare R2 release artifacts and local cache

## 1. Purpose

本契約定義 Knowledge Runtime 如何解析 release、執行 Wiki-first 查詢、套用 ACL、回傳 citations，並在資料不足時受控地 fallback。

Runtime 在正常查詢路徑 `MUST NOT` 讀 GitHub branch、掃描 source repository 或直接修改 knowledge source。

## 2. Endpoints

### 2.1 `POST /v1/query`

執行知識查詢。

### 2.2 `GET /v1/releases/current`

回傳目前 process 已載入 release，不是僅回傳遠端 pointer。

### 2.3 `POST /v1/releases/refresh`

要求 Runtime 檢查 channel pointer並原子載入新 release。需管理權限。

### 2.4 `GET /v1/health`

回傳 process、release、cache 與 integrity健康狀態。

## 3. Query request

```json
{
  "request_id": "req_01JXYZ123456789ABCDEFGHJK",
  "query": "Karpathy LLM Wiki 和傳統 RAG 的核心差異是什麼？",
  "locale": "zh-TW",
  "audience_context": {
    "principal_id": "user_123",
    "allowed_audiences": ["public", "internal"],
    "tenant_id": "default"
  },
  "options": {
    "mode": "balanced",
    "max_results": 12,
    "max_graph_hops": 1,
    "allow_raw_fallback": false,
    "require_citations": true,
    "release_id": null
  }
}
```

Rules：

- `request_id` `MUST` 唯一。
- `query` 長度預設限制 1 到 8000 Unicode characters。
- `allowed_audiences` `MUST` 由可信 authentication layer產生，不得直接相信 client自報。
- 指定 `release_id` 只允許可存取的 immutable release。
- 未指定 release時使用 process已載入的 channel release。

## 4. Query response

```json
{
  "request_id": "req_01JXYZ123456789ABCDEFGHJK",
  "status": "answered",
  "answer": "...",
  "release": {
    "release_id": "20260702T120000Z-a1b2c3d",
    "manifest_sha256": "64 hex",
    "loaded_at": "2026-07-02T12:05:00Z"
  },
  "citations": [
    {
      "citation_id": "c1",
      "concept_id": "concepts/llm-wiki",
      "x_kos_id": "ko_01JXYZ123456789ABCDEFGHJK",
      "heading": "Core idea",
      "section_sha256": "64 hex",
      "provenance_record_id": "prov_01JXYZ123456789ABCDEFGHJK",
      "source_refs": ["src_github_abcd1234"],
      "support": "supports"
    }
  ],
  "retrieval": {
    "strategy": "wiki_first",
    "candidate_count": 18,
    "selected_count": 5,
    "graph_hops": 1,
    "raw_fallback_used": false
  },
  "warnings": [],
  "timing_ms": {
    "total": 420,
    "release_resolve": 2,
    "retrieve": 68,
    "compose": 330,
    "verify": 20
  }
}
```

## 5. Status values

| Status | Meaning |
|---|---|
| `answered` | 有足夠受支持答案 |
| `partial` | 只回答可支持部分 |
| `insufficient_evidence` | 找到相關內容但不足以作答 |
| `not_found` | 無相關知識 |
| `forbidden` | 請求 release 或資源無權限 |
| `release_unavailable` | 無有效 release可載入 |
| `integrity_failure` | Manifest 或 artifact hash不符 |
| `budget_exceeded` | 查詢超出明確 budget |
| `error` | 未分類 server error |

Runtime `MUST NOT` 為了避免 `not_found` 而編造答案。

## 6. Release resolution

Runtime startup：

1. 讀取 `channels/<channel>.json`。
2. 驗證 pointer schema與 manifest SHA-256。
3. 下載 manifest。
4. 驗證 release manifest JSON Schema。
5. 驗證 required artifacts hashes。
6. 在本機暫存新 release。
7. 完成 warmup與 smoke query。
8. 原子切換 active release handle。

若任一步失敗：

- 已載入舊 release時 `MUST` 繼續服務舊 release並報警。
- 無舊 release時回傳 `release_unavailable`。
- 不得半載入新舊混合 artifacts。

## 7. Wiki-first query algorithm

順序 `MUST` 如下：

### Step 1: Query normalization

- language detection
- spelling and alias normalization
- explicit filters extraction
- no hidden broadening of access scope

### Step 2: Progressive disclosure

先使用 root與directory `index.md`、titles、descriptions與tags縮小範圍。

### Step 3: Lexical retrieval

使用 BM25、full-text或等價 lexical index搜尋：

- title
- aliases
- description
- headings
- section body

### Step 4: Optional semantic retrieval

只搜尋符合 audience 的 sections。

Semantic index unavailable時，Runtime `SHOULD` 降級為 lexical，不得直接失敗。

### Step 5: Graph expansion

從初始 concepts擴展最多 `max_graph_hops`。

每個 node與edge `MUST` 再做 ACL filter。

### Step 6: Evidence assembly

每個 selected section `MUST` 保留：

- concept ID
- immutable knowledge ID
- heading path
- section hash
- audience
- provenance refs

### Step 7: Answer composition

Answer `MUST`：

- 只使用 selected evidence中的可見內容
- 區分來源事實與系統推論
- 對不確定或衝突內容明確說明
- 在 require citations時提供 claim-level citations

### Step 8: Verification

至少驗證：

- 每個重要 answer claim有 supporting citation
- citation section hash與 release相符
- 無不可見 source refs洩漏
- 無 evidence外新增專有事實

## 8. Raw-source fallback

Raw fallback預設 `false`。

只有以下條件可啟用：

- caller有權限
- query option允許
- Runtime policy允許
- Wiki evidence不足
- source snapshot位於 approved Evidence Store

Fallback `MUST NOT` 直接查任意外網。

Fallback結果：

- `retrieval.raw_fallback_used` `MUST` 為 true。
- citations `MUST` 指向 source snapshot與locator。
- 有價值的新結論 `SHOULD` 產生 knowledge candidate event，不得直接寫 production bundle。

## 9. ACL enforcement

ACL filter `MUST` 出現在：

1. release selection
2. index navigation
3. lexical retrieval
4. semantic retrieval
5. graph expansion
6. provenance expansion
7. answer context assembly
8. cache lookup與cache write
9. response serialization

禁止先取 restricted內容再要求模型「不要提到」。

Cache key `MUST` 至少包含：

```text
release_id
normalized_query_hash
audience_set_hash
tenant_id
query_mode
```

## 10. Citation contract

每個 citation `MUST` 包含：

- `concept_id`
- `x_kos_id`
- `heading`或selector
- `section_sha256`
- `provenance_record_id`，若該 section需要 provenance
- `source_refs`
- support relation

支援值：

- `supports`
- `contradicts`
- `context`

Runtime `MUST NOT` 回傳僅有網址但無法定位到本次 release內容的裝飾性 citation。

## 11. Query modes

| Mode | Retrieval | Graph | Verification | Intended use |
|---|---|---|---|---|
| `fast` | lexical first | 0 to 1 hop | basic | navigation and simple facts |
| `balanced` | lexical + optional semantic | 1 hop | full | default |
| `deep` | multi-pass | up to 2 hops | full + contradiction scan | synthesis |

Runtime可限制 mode，但不得讓 `fast` 跳過 ACL 或 integrity。

## 12. Budgets

Default per-query limits：

```text
max_results: 20
max_graph_hops: 2
max_context_chars: 120000
max_raw_sources: 5
max_total_ms: 30000
max_model_calls: 3
```

超出時：

- 若已有足夠 evidence，回 `partial` 並附 warning。
- 若不足，回 `budget_exceeded`。

## 13. Freshness and cache

1. Answer cache不得跨 release重用，除非內容 hashes明確相同。
2. Pointer refresh後，新 request `MUST` 使用新 active release。
3. In-flight request `MAY` 完成於舊 release，但 response `MUST` 回報實際 release ID。
4. Emergency revoke後，舊 release cache `MUST` 立即失效。

## 14. Observability

每次 request `MUST` 記錄：

- request ID
- release ID
- principal hash，不記錄明文敏感 identity
- query hash與安全摘要
- mode
- candidate與selected counts
- ACL filtered count
- citation count
- fallback usage
- timings
- status與error code

不得在一般 log寫入完整 restricted evidence或完整生成答案。

## 15. Error codes

| Code | HTTP | Meaning |
|---|---:|---|
| `RUNTIME-001` | 503 | No valid release |
| `RUNTIME-002` | 503 | Artifact integrity failure |
| `RUNTIME-003` | 403 | Release or knowledge forbidden |
| `RUNTIME-004` | 400 | Invalid query request |
| `RUNTIME-005` | 422 | Unsupported query mode or option |
| `RUNTIME-006` | 429 | Budget or rate limit exceeded |
| `RUNTIME-007` | 200 | Insufficient evidence, structured status |
| `RUNTIME-008` | 500 | Citation verification failed |
| `RUNTIME-009` | 503 | Channel refresh failed |

## 16. Required conformance tests

1. Runtime正常查詢時無 GitHub network call。
2. Restricted concept不會出現在 public lexical、semantic或graph結果。
3. 同 query在不同 audience cache不互相命中。
4. Artifact被修改後回 `integrity_failure`。
5. 新 release載入失敗時繼續服務舊 release。
6. Response每個主要 claim都有可定位 citation。
7. `allow_raw_fallback=false` 時不讀 Evidence Store。
8. Emergency revoke後舊 release與cache不可再服務新 request。
9. In-flight request回報其實際使用的 release ID。
10. 無足夠證據時回 structured non-answer，不產生幻覺式補全。
