# Knowledge Layer Model Contract

- Contract ID: `KOS-KLM-001`
- Version: `0.1.0`
- Status: Normative Draft
- Owner: Knowledge OS Foundation
- Applies to: source repositories, Builder, R2 releases, Runtime, downstream consumers

## 1. Purpose

本契約定義 Knowledge OS 中四種不同的權威層級，防止證據、整理後知識、治理規則與 Runtime 產物被混成同一種「真相」。

文中的 `MUST`、`MUST NOT`、`SHOULD`、`SHOULD NOT`、`MAY` 為規範性關鍵字。

## 2. The four layers

### 2.1 Evidence Layer

Evidence Layer 保存外部或內部來源的可驗證快照。

例子：

- 網頁快照
- PDF 原檔
- Git commit 內容
- 會議逐字稿
- 資料庫 schema export
- API response snapshot

規則：

1. 每個來源快照 `MUST` 有穩定 `source_id`。
2. 每個快照 `MUST` 有內容雜湊、取得時間、原始 URI、媒體類型與存取等級。
3. 已發布快照 `MUST NOT` 被原地覆寫。
4. 來源更新 `MUST` 產生新快照版本。
5. 來源刪除 `MUST` 以 tombstone 表示，不得抹除既有 lineage。

Evidence Layer 是「某個來源在某個時間點說了什麼」的權威紀錄，不代表來源內容必然正確。

### 2.2 Curated Knowledge Layer

Curated Knowledge Layer 是經過整理、去重、關聯、合成與引用的 OKF knowledge bundle。

例子：

- 概念頁
- 實體頁
- 決策頁
- 比較頁
- Runbook
- 組織術語頁

規則：

1. 每個可發布概念 `MUST` 符合 `KOS-OKFP-001`。
2. 每個外部可驗證 claim `MUST` 能回溯到 Provenance Record。
3. 推論內容 `MUST` 被標示為 `inferred` 或 `synthesized`，不得偽裝成直接來源事實。
4. 概念頁可被更新，但每次發布 `MUST` 對應不可變 release。
5. Curated Knowledge `MUST NOT` 直接覆蓋 Evidence。

此層是「目前系統認可的最佳整理結果」，不是永久不變的絕對真理。

### 2.3 Governance Layer

Governance Layer 定義系統如何產生、驗證、發布與查詢知識。

例子：

- 本契約
- OKF Profile
- JSON Schema
- RFC
- ADR
- ACL policy
- Builder policy
- Runtime contract

規則：

1. Governance 變更 `MUST` 經版本控制與 review。
2. Breaking change `MUST` 提升 major version 或明確提供 migration。
3. Builder 與 Runtime `MUST` 宣告所支援的 Governance contract 版本。
4. Governance 文件 `MUST NOT` 由 Runtime 自動改寫。

此層是「系統必須如何運作」的權威。

### 2.4 Runtime Artifact Layer

Runtime Artifact Layer 是 Builder 從 Curated Knowledge 與 Governance 編譯出的不可變產物。

例子：

- `manifest.json`
- `graph.json`
- section index
- lexical index
- semantic index
- source map
- provenance package
- build report

規則：

1. Artifact `MUST` 能由指定 source commit 與 Builder version 重建。
2. Artifact `MUST NOT` 被人工修改。
3. 每個 Artifact `MUST` 有 SHA-256 與 R2 object key。
4. Artifact `MUST` 綁定單一 `release_id`。
5. Runtime `MUST` 只讀已 promotion 的 immutable release。

此層是「某個 Runtime release 實際讀到什麼」的權威。

## 3. Authority matrix

| 問題 | 權威層 |
|---|---|
| 原始來源在某時間點的內容是什麼 | Evidence |
| 系統目前如何解釋與整理來源 | Curated Knowledge |
| 系統應遵守哪些規則 | Governance |
| Production Runtime 正在使用哪一版資料 | Runtime Artifact release manifest |
| `graph.json` 與 Markdown 不一致時相信誰 | Curated Knowledge source，並使 build 失敗 |
| R2 Artifact 與 release manifest hash 不一致時相信誰 | 兩者皆不可用，release 必須被拒絕 |

## 4. Allowed transitions

```text
External Source
  -> Evidence Snapshot
  -> Normalized Source
  -> Knowledge Candidate
  -> Curated Knowledge
  -> Validated Bundle
  -> Runtime Artifacts
  -> Immutable Release
  -> Promoted Channel Pointer
```

允許的回饋路徑：

```text
Runtime query feedback
  -> Knowledge Candidate
  -> Review
  -> Curated Knowledge
```

禁止的路徑：

```text
Runtime Artifact -> direct manual edit
Runtime answer -> direct production knowledge write
Curated Knowledge -> overwrite Evidence
GitHub branch head -> normal production Runtime read
```

## 5. Identity rules

### 5.1 Evidence identity

格式：

```text
src_<provider>_<stable-id>_<snapshot-hash-prefix>
```

同一 URI 的不同內容快照 `MUST` 有不同 `source_id` 或 snapshot version。

### 5.2 Knowledge identity

- OKF Concept ID `MUST` 等於 bundle 內相對路徑移除 `.md`。
- `x-kos-id` `MUST` 是搬移檔案後仍不變的 immutable identity。
- 重新命名或移動頁面時，Builder `MUST` 保留 `x-kos-id`，並產生 redirect map 或 tombstone。

### 5.3 Release identity

格式：

```text
YYYYMMDDTHHMMSSZ-<source-git-sha-prefix>
```

例：

```text
20260702T120000Z-a1b2c3d
```

Release ID `MUST` 唯一且不可重用。

## 6. Mutability and retention

| Object | Mutability | Minimum retention |
|---|---|---|
| Evidence snapshot | Immutable | 依 policy，預設永久 |
| Curated source file | Mutable in Git history | Git history preserved |
| Governance file | Mutable by reviewed commit | Git history preserved |
| Runtime artifact | Immutable | 至少保留 current + previous 2 releases |
| Channel pointer | Mutable atomic pointer | 保留 pointer change audit log |
| Tombstone | Append-only | 不短於被刪物件 retention |

## 7. Provenance rules

1. 每個 published concept `MUST` 有至少一個 Provenance Record，除非 `type` 為純治理或索引文件。
2. 每個 claim 的來源集合 `MUST` 指明 `supports`、`contradicts` 或 `context`。
3. 若來源互相衝突，Curated Knowledge `MUST` 揭露衝突或降低 confidence。
4. Builder `MUST NOT` 以「LLM 說過」作為來源。
5. Calculated claim `MUST` 保存公式或計算輸入摘要。

## 8. ACL propagation

Audience 嚴格度順序：

```text
public < internal < confidential < restricted
```

規則：

1. 任何衍生物件的 effective audience `MUST` 不低於其所有 supporting source 的最高限制。
2. 自動降級 audience `MUST NOT` 發生。
3. 降級只能透過顯式 declassification review，且 `MUST` 留下 reviewer、理由與時間。
4. Runtime 在 lexical、semantic、graph expansion 與 cache 回傳階段都 `MUST` 執行 ACL filter。
5. 一個 release 可包含多 audience，但每個 artifact `MUST` 宣告 audience coverage。

## 9. Deletion and invalidation

來源被刪除、撤回或權限提高時：

1. Builder `MUST` 找出所有直接與間接衍生 concept、claim、index 與 cache key。
2. 受影響物件 `MUST` 被重建、隔離或 tombstone。
3. 尚未完成影響分析前，相關內容 `MUST NOT` 被 promotion 到 production。
4. 若 production 已暴露內容，系統 `MUST` 支援 emergency revoke 與 channel rollback。

## 10. Conformance gates

發布前以下條件全部 `MUST` 為真：

- Evidence snapshots 可讀且 hash 相符。
- 所有 published concepts 符合 OKF Profile。
- 所有 required provenance 可解析。
- ACL propagation 無降級。
- Runtime artifacts 可重建且 hash 相符。
- Release manifest 通過 JSON Schema。
- Quality gates 全部為 `passed`。

## 11. Failure codes

| Code | Meaning | Required action |
|---|---|---|
| `KLM-001` | Layer authority conflict | 阻止發布並輸出差異 |
| `KLM-002` | Artifact was manually modified | 隔離 artifact 並重建 |
| `KLM-003` | Missing provenance | 阻止發布 |
| `KLM-004` | ACL downgrade | 阻止發布並列為 security failure |
| `KLM-005` | Non-reproducible artifact | 阻止發布 |
| `KLM-006` | Deleted source still reachable | 阻止 promotion 或緊急 revoke |

## 12. Machine-checkable acceptance tests

實作 `MUST` 至少具備以下測試：

1. 修改 artifact 內容後，hash 驗證失敗。
2. 將 restricted source 派生為 public concept 時，ACL 驗證失敗。
3. 刪除 provenance source reference 時，發布失敗。
4. 將同一 `release_id` 指向不同內容時，發布失敗。
5. 移動 concept path 但保留 `x-kos-id` 時，identity continuity 通過。
6. `graph.json` 指向不存在 concept 時，release build 失敗。
