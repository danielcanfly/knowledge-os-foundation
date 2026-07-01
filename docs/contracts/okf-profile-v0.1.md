# Daniel Knowledge OS Profile for OKF v0.1

- Contract ID: `KOS-OKFP-001`
- Profile name: `daniel-knowledge-os/0.1`
- Profile version: `0.1.0`
- Base format: Open Knowledge Format v0.1 Draft
- Status: Normative Draft

## 1. Scope

OKF v0.1 定義最小互通格式。本 Profile 在不破壞 OKF consumer 的前提下，增加 Knowledge OS 發布、身份、ACL、provenance 與 review 規則。

本 Profile 不宣稱新增欄位屬於上游 OKF。所有擴充欄位使用 `x-kos-` 前綴。

## 2. Two conformance levels

### 2.1 Authoring Conformance

供 GitHub、Obsidian 與 Builder draft 使用。

- 可含 wikilinks。
- 可含 unresolved links。
- 可缺少部分 provenance。
- `x-kos-status` 可為 `draft` 或 `review`。
- 不可 promotion 到 Runtime。

### 2.2 Release Conformance

供 R2 immutable release 與 Runtime 使用。

- 所有 wikilinks `MUST` 轉為標準 Markdown links。
- 內部 links `MUST` 可解析。
- 所有 required provenance `MUST` 存在。
- `x-kos-status` `MUST` 為 `published` 或 `deprecated`。
- 所有頁面 `MUST` 通過 frontmatter、citation、ACL 與 identity 驗證。

## 3. Bundle layout

建議 layout：

```text
bundle/
├── index.md
├── log.md
├── concepts/
├── entities/
├── decisions/
├── runbooks/
├── references/
└── _meta/
    ├── redirects.json
    ├── tombstones.json
    └── profile.json
```

規則：

1. `index.md` 與 `log.md` 依 OKF reserved filename semantics。
2. `_meta/` 不得包含 OKF concept documents，consumer 可忽略該目錄。
3. 每個非 reserved `.md` 檔案 `MUST` 是一個 concept。
4. 每個目錄 `SHOULD` 有 `index.md` 以支援 progressive disclosure。

## 4. Concept identity

### 4.1 OKF Concept ID

OKF Concept ID `MUST` 等於檔案在 bundle 內的相對路徑移除 `.md`。

例：

```text
concepts/retrieval-augmented-generation.md
-> concepts/retrieval-augmented-generation
```

### 4.2 Immutable Knowledge ID

每個 concept `MUST` 有：

```yaml
x-kos-id: ko_01JXYZ123456789ABCDEFGHJK
```

規則：

- 格式 `MUST` 符合 `^ko_[0-9A-HJKMNP-TV-Z]{26}$`。
- 頁面搬移或重新命名後 `MUST` 保持不變。
- 不同 concept `MUST NOT` 共用同一 ID。
- 被合併 concept 的舊 ID `MUST` 進入 redirect 或 tombstone registry。

## 5. Required frontmatter

Release-conformant concept `MUST` 包含：

```yaml
---
type: Concept
title: Retrieval-Augmented Generation
description: A retrieval-time context assembly pattern for language models.
timestamp: 2026-07-02T12:00:00Z
x-kos-id: ko_01JXYZ123456789ABCDEFGHJK
x-kos-status: published
x-kos-audience: internal
x-kos-confidence: 0.92
x-kos-provenance: provenance/concepts-retrieval-augmented-generation.json
x-kos-review:
  status: approved
  reviewed_at: 2026-07-02T11:30:00Z
  reviewer: daniel
---
```

### 5.1 Base OKF fields

| Field | Rule |
|---|---|
| `type` | `MUST` be a non-empty string |
| `title` | `MUST` be a non-empty string in this Profile |
| `description` | `MUST` be one sentence, 20 to 300 characters |
| `resource` | `MAY` identify an underlying canonical asset |
| `tags` | `MAY` contain unique lowercase tags |
| `timestamp` | `MUST` be UTC ISO 8601 for release content |

### 5.2 Profile extension fields

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `x-kos-id` | string | yes | Immutable concept identity |
| `x-kos-status` | enum | yes | `draft`, `review`, `published`, `deprecated`, `tombstoned` |
| `x-kos-audience` | enum | yes | `public`, `internal`, `confidential`, `restricted` |
| `x-kos-confidence` | number | yes | 0.0 to 1.0 |
| `x-kos-provenance` | string | yes for published factual concepts | Path to Provenance Record |
| `x-kos-review` | object | yes for published concepts | Approval state |
| `x-kos-aliases` | array | optional | Search aliases, unique after case folding |
| `x-kos-supersedes` | array | optional | Immutable IDs replaced by this concept |
| `x-kos-owner` | string | optional | Responsible owner or team |

## 6. Type policy

OKF consumers必須容忍未知 `type`。本 Profile 建議以下值，但不建立中央 registry：

- `Concept`
- `Entity`
- `Decision`
- `Runbook`
- `Reference`
- `Dataset`
- `API`
- `Metric`
- `Policy`

新 type `MAY` 出現，但 `MUST` 有可理解名稱，且不得把 status 或 audience 塞進 type。

## 7. Link policy

### 7.1 Canonical release links

Release bundle 內部關係 `MUST` 使用標準 Markdown link：

```markdown
[Vector Search](/concepts/vector-search.md)
```

Bundle-relative absolute link為首選。

### 7.2 Wikilinks

Authoring bundle `MAY` 使用：

```markdown
[[Vector Search]]
```

Builder `MUST`：

1. 解析 alias 與 title。
2. 將唯一匹配轉成標準 Markdown link。
3. 多重匹配時回報 `OKFP-006`。
4. 零匹配時 draft 可保留 warning，release `MUST` 失敗。

### 7.3 Broken links

上游 OKF consumer 可以容忍斷鏈，但本 Profile 的 release conformance 更嚴格：

- Internal broken link count `MUST` 為 0。
- External URL 可在 network-unavailable 時標為 `unchecked`，但不可是 syntactically invalid URI。

## 8. Body policy

1. Body `MUST` 使用 structural Markdown。
2. 第一個 H1 `SHOULD` 與 `title` 相符。
3. H1 `MUST NOT` 超過一個。
4. 發布內容不得含 TODO placeholder、未解決 merge conflict 或 secret。
5. 直接引文 `MUST` 有 citation。
6. 推論段落 `MUST` 明確標記為 `Inference`、`Assessment` 或由 provenance derivation 表示。

建議 section：

```text
# Summary
# Definition
# Key Properties
# Relationships
# Operational Notes
# Limitations
# Citations
```

## 9. Citation policy

外部來源 claim `MUST` 能透過以下兩條路徑至少一條回溯：

1. Body 內 inline citation 或 `# Citations` 條目。
2. `x-kos-provenance` 指向的 claim-level evidence。

Release rules：

- Citation target `MUST` 是絕對 URI、bundle-relative concept 或 `references/` concept。
- 每個 citation `SHOULD` 對應來源 snapshot。
- Citation 不得只指向搜尋結果頁。
- LLM output、聊天回答與無保存內容的臨時頁 `MUST NOT` 作為唯一證據。

## 10. Index and log policy

### 10.1 `index.md`

Root `index.md` `MAY` 使用 frontmatter 宣告：

```yaml
---
okf_version: "0.1"
x-kos-profile: daniel-knowledge-os/0.1
x-kos-bundle-id: kb_main
x-kos-release-id: 20260702T120000Z-a1b2c3d
---
```

其他 `index.md` 預設不含 frontmatter。

Index entries `SHOULD` 包含 title 與 description。

### 10.2 `log.md`

- 日期 heading `MUST` 使用 `YYYY-MM-DD`。
- 新日期在上。
- 發布、棄用、合併、ACL 變更 `MUST` 記錄。

## 11. Status state machine

```text
draft -> review -> published -> deprecated -> tombstoned
                 \-> draft
```

規則：

- `published` 前 `x-kos-review.status` `MUST` 為 `approved`。
- `deprecated` concept `MUST` 指向 replacement 或說明無 replacement。
- `tombstoned` concept 不得進搜尋 index，但 `MAY` 保留 redirect metadata。

## 12. Publish validation rules

| Rule | Severity |
|---|---|
| Parseable YAML frontmatter | fatal |
| Non-empty `type`, `title`, `description` | fatal |
| Unique valid `x-kos-id` | fatal |
| UTC timestamp | fatal |
| Status is publishable | fatal |
| Approved review | fatal |
| Valid audience | fatal |
| Provenance record exists | fatal when required |
| Internal broken links | fatal |
| Duplicate aliases | fatal |
| External URL unreachable | warning unless policy says fatal |
| Missing directory index | warning |

## 13. Failure codes

| Code | Meaning |
|---|---|
| `OKFP-001` | Invalid or missing frontmatter |
| `OKFP-002` | Missing required Profile field |
| `OKFP-003` | Duplicate or malformed `x-kos-id` |
| `OKFP-004` | Non-UTC or invalid timestamp |
| `OKFP-005` | Internal broken link |
| `OKFP-006` | Ambiguous wikilink |
| `OKFP-007` | Missing provenance |
| `OKFP-008` | Unapproved published concept |
| `OKFP-009` | Audience mismatch |
| `OKFP-010` | Forbidden draft marker or secret |

## 14. Minimal release-conformant example

```markdown
---
type: Concept
title: Knowledge Compiler
description: A deterministic pipeline that converts reviewed knowledge sources into immutable runtime artifacts.
timestamp: 2026-07-02T12:00:00Z
x-kos-id: ko_01JXYZ123456789ABCDEFGHJK
x-kos-status: published
x-kos-audience: internal
x-kos-confidence: 0.95
x-kos-provenance: provenance/knowledge-compiler.json
x-kos-review:
  status: approved
  reviewed_at: 2026-07-02T11:30:00Z
  reviewer: daniel
---

# Knowledge Compiler

A Knowledge Compiler turns reviewed source knowledge into validated, versioned runtime artifacts.

# Relationships

It produces a [Release Manifest](/concepts/release-manifest.md).

# Citations

[1] [Open Knowledge Format specification](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
```
