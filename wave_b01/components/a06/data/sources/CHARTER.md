# M27 / Knowledge OS vNext | Master Architecture & Construction Charter
## 核心主線架構、完整施工計劃、驗收目標與防偏移憲章

**Charter ID:** M27-VNEXT-MASTER-CHARTER-v1.0  
**基準日期：**2026-10-14（Asia/Ho_Chi_Minh）  
**文件角色：**Owner 長期北極星 + Master 唯一施工校準基準；不是本身的 Production 授權、程式碼簽署或驗收 PASS。  
**效力：**固定目標/責任/不可犧牲的設計原則；實際工程狀態以當期獨立實測收據、Git、工作樹和「02_MASTER_GATE_STATE.json」為準。舊報告屬歷史，不得以它覆蓋新實測。  
**原始根據：**2026-10-09 的 M27_KNOWLEDGE_OS_VNEXT_ARCHITECTURE_MASTERPLAN；00_MASTER/ARCHITECTURE_REFERENCE.md 與 ROADMAP_AND_DEPENDENCIES.md；2026-10-14 的 05_MASTER_MAINLINE_PROGRESS_20261014.md、FIX-M26/FIX-M27 Master 驗收、MG09–MG36 reports。  
**Owner 邊界：**Owner 已授權自有資產上的 Nonprod 研發/隔離測試，暫無 Provider 總預算上限（但每次實驗必須有可驗證單次上限與安全停損）；Production 仍明確 NO-GO，必須有新的最後核准。不得取代第三方權利、獨立評測或真實技術證據。

---

# 0. 每次校準先讀的一頁（Executive Compass）

**唯一終極產品：**在現有 Knowledge Engine 之上，完成一套 **Task/Outcome-native + Context-Native Adaptive AI Runtime**。它可以在合法權限內持久完成不同任務：理解需求與成功條件 → 選取最少充分可信上下文 → 適度推理/工具 → 寫入 durable execution state → 驗證答案/檔案/外部效果 → 可恢復、可撤銷、可審計 → 由獨立測試衡量成果；學習只先產生受治理候選改善，不直接改 Production。

**不是本專案最終目標：**只讓 Q&A Benchmark PASS、只讓某張本機測試報表全綠、只做一個 Multi-agent Demo、只替 Q34 修 Ruff、只拿到簽署或健康狀態、只產生文件、反覆讓 Admin Gate 阻擋任何 Nonprod 工程。

**本期可執行 P0：I37，把已核對的 M26 4 個修復與 M27 6 個修復整合到全新獨立 Nonprod worktree，重新執行原始失敗測試＋正反回歸。** 它是工程下一步，不需要為第一方資產再重新要 Owner 授權。絕不能改凍結 Q34、Production、受保護測試或先前遭明確拒絕的等價原始碼範圍。

**本期獨立 P0 產品缺口：**M26 Python3.11 尚有 6 個紅燈；Q34 原生「已驗證的生成文字在 Worker 未完成前就到達 Client」仍 FAIL；AR08 真正同一 TaskContract 的持久 Coding patch 未完成。兩種正式評測仍為 0/523、0/200。這些缺口不能由 MG33 的原型、N31 fixtures、SSE 進度事件、已簽名的較小 artifact 或報告篇數取代。

**本期品質事實（不可錯加）：**MG36 為 4,838 PASS / 17 FAIL 的歷史單一基準；M26 個別分支 857 PASS / 6 FAIL（75 模組）、M27 個別分支 2,770 PASS / 0 FAIL（85 模組）；**這三份不是同一版本的聯合成績**。原始 16 個 M26/M27 失敗已在各自分支修好 10 個，**合併前不得宣稱整合後只剩 6 個**。

## 0.1 不可偏移的五條北極星
1. **Task/Outcome 優先於 Chat 回答**：長任務、研究、Coding/Action 必須有可驗證成果，而非只看 LLM 文句。
2. **Context-native、Deterministic substrate 保留**：R2、Qdrant、BM25、Graph、ACL、Provenance、Compiler、Release/Rollback 保持受治理基礎設施，Agent 不能取代政策。
3. **Durable + Governed Actions**：checkpoint、resume、cancel、approval、未知外部效果 reconcile；不可盲重試不可逆寫入。
4. **Verification before publication**：答案檢驗 Claim/Evidence/Semantic，檔案檢驗 artifact tests，動作檢驗外部真實狀態；各自使用正確驗證器。
5. **Evidence and real product outcomes**：所謂完成必須達到真實整合路徑、真測試、版本鏈、獨立結果。Unknown 必須寫 Unknown。

# 1. 專案終態與三條施工線

## 1.1 Track A：General Agent Architecture（AR00–AR10）【核心長線】
要交付一個可執行、可治理、可恢復的通用 Task Runtime。三個真實垂直切面為：
- **QA**：可信來源 → 生成/驗證引用 → 適當發布；必須能以 Client 確認真正的第一段已驗證生成文字。
- **Research**：多步檢索/整理/中斷恢復 → 帶來源與版本之持久化研究產物 → 依規格被獨立驗收。
- **Coding 或獲批准的真實 Action**：同一 admitted TaskContract → 授權工具 → 原始碼及 patch.diff 真正持久化 → 獨立 OS 測試 / 外部效果觀察；不可使用被拒絕的等價 Source-edit 動作。
三者共享 Task/Policy/Outcome Contracts，不把三個獨立測試拼貼當同一個 E2E。
終態：AR00–AR10 逐關通過，F35 獨立架構 Signoff，無未處理安全 P0。

## 1.2 Track B：Q&A Product & Release（V27 / REL01 / REL02）
產品線可以依自己的驗收門檻先完成，不必等待 AR10 長期學習產品化。但不能犧牲 AR 不變式或把離線憑證當正式品質。
- 已有的高價值成果：Q34 frozen source、局部發行供應鏈簽署、第一方原生 Lexical QA、JWT/TLS、Provider/Client 隔離實測、Nonprod Streaming-OFF Gateway。
- 尚欠的產品能力：合法完整且簽署的 current product image/資料版本；合格實際 App/IdP/Client；可採信的語意及向量檢索；官方固定題庫與真正新盲測；早期生成文字串流；實際 p95、成本與獨立評分。
- REL02 僅能於 REL01 通過、Owner **另外重新核准 Production** 後啟動。

## 1.3 Track C：Independent Evidence / Infrastructure / Quality（橫向支援，不喧賓奪主）
- ABI 規範/權責與兼容、工具安全、CI provenance、source rights、Provider 配額、客戶端真實 ACK、資料治理、評測 Custody、Security/QA。
- 每項必須有指定產品能力/失敗與驗收者；無關主線的泛化整理或新名稱 Gate 不得自動升級為 P0。
- **行政或正式發行 Gate 不等於禁止一切 Nonprod 修復**；非生產工程可進行，正式 Product/Production promotion 另受 Gate 約束。
- Owner 具有自己資產的研發決策權，無需虛構外部 Controller；真實第三方權利、獨立評測資格、Provider 帳戶及第三方簽署各保留實證。

# 2. 目標系統架構（不可任意改成單純 QA Runtime）

```text
User / Tenant / Product / API / Client
      ↓  identity, intent, constraints, permission
TaskContract + Outcome Acceptance (Task-native)
      ↓
DURABLE TASK & EXECUTION PLANE [AR01, AR02]
  RunState | journal | checkpoint | approvals | cancel/resume | reconcile
      ↓
INTELLIGENCE / AGENT HARNESS [AR07, AR08]
  plan ⇄ observe ⇄ reason ⇄ select model/compute ⇄ bounded delegation
      ↕
CONTEXT & CAPABILITY PLANE [AR03, AR04, AR06]
  ContextPlanner → Context Compiler (ACL/freshness/provenance/budget)
  Knowledge (R2 / Qdrant / BM25 / Graph / immutable releases)
  Memory | Skills | Workspace | Tools/MCP | live APIs
      ↓
GOVERNED TOOL / EFFECT BOUNDARY [AR02, AR04]
  actual authority | least privilege | sandbox | side-effect ledger
  idempotency | UNKNOWN reconcile | receipts | cap / approval
      ↓
OUTCOME VERIFICATION & PUBLICATION [AR05, AR09]
  Q&A: claim ↔ evidence ↔ semantic/citation
  Research: artifact/spec/source/test
  Coding: persisted patch + independent OS/test outcome
  Action: externally observed changed state
      ↓
Verified delivery / repair / correction / safe abstain / escalation
      ↘
OFFLINE GOVERNED LEARNING [AR06, AR09, AR10]
  traces → proposed memory/skill/policy changes → independent eval
  → review/approval → versioned optional promotion (NEVER auto-prod)
Cross-cutting: tenant/ACL, security, provenance, cost/latency, telemetry,
             independent evaluation, failure recovery, release/rollback
```

**責任分離：**模型提出 Plan/Claim/Intent，不自發取得權限；MCP 只是能力界面而不是簽核；Contexts 與 Memory 不是 RunState；簽章驗證位元完整性而不是語意真實；本機 HTTP200/health 不是完整產品 READY；CI source signature 不是 transformed release signature。

# 3. 版本化關鍵合約及跨層不變式

| Contract / 介面 | 主責 | 不可少的語意與驗證 |
|---|---|---|
| TaskContract | AR01/02 | tenant/actor/goal/scope/deadline/budget/expected artifact/acceptance/version；每次任務固定 |
| RunState / Event journal | AR02 | run_id、事件序列、terminal 單調、checkpoint、cancel、owner takeover、reconcile |
| ContextRequest/Bundle | AR03/06 | 來源版本/ACL/expiry/trust/provenance/精確證據 ID、最少充分上下文 |
| ToolCapability / ActionIntent / Receipt | AR04/02 | 授權、read/write 分離、idempotency/unknown effect/外部 receipt/rollback |
| VerificationResult | AR05/09 | 分離 policy、source、semantic、artifact、action outcome、人審；Unknown 不算 PASS |
| LearningProposal | AR10 | Origin / rationale / diff / eval / rollback / review，限制為 candidate-only |
| Client Event / ACK | AR05/09 / Product | 順序、first substantive verified text、terminal、correction、可獨立 Client 觀測 |
| Release manifest / ABI sidecars | AR01 / Product | 精確簽署 bytes/版本/讀者相容/授權來源/合法撤回；不改寫 legacy 歷史證據 |

九項已知 ABI-01～ABI-09 衝突仍要正式解決：Envelope/Sidecars、Identity、Approval、T1–T5、Notice/ACK、Revocation、Billing、Independent Verifier、Native Q&A Consumer。Owner 的技術候選是實際進展，不等於 X01～X09 已獨立正式通過。

**硬性行為：**跨 tenant/來源不洩漏；不可逆工具未知結果不能盲重試；失效來源不產生 Citation；由日誌重播不得重送外部動作；沒有驗證結果不得 TERMINAL SUCCEEDED；未完成、拒答、Safe Terminal 不計「成功交付」；撤銷/刪除及後續恢復不破壞治理；feature-off 有可反證行為。


# 4. 模組施工責任、現況、完成定義（AR00～AR10）

本表為**長期架構完整交付定義**，不得被某次單元測試或評測代號改寫。Status 為 2026-10-14 的能力狀態快照，未來只有新證據可以更新狀態。

| 模組 | 架構職責（不能刪） | 10/14 已實證 | 剩餘工程／退出 Gate | 現況 |
|---|---|---|---|---|
| AR00 Truth Baseline | 封存 source/data/image/receipts、能力成熟度、舊 guard 風險 | Q34 HEAD/tree 與 Wheel/OCI、V34 source reconciliation、MG36 baseline | 每個新整合候選版重新固定 commit/tree/dataset/config | 基準完成（有歷史保留風險） |
| AR01 Stable Contract & ADR | Task/Run/Context/Tool/Verifier/Outcome、ABI 跨模組版本與安全威脅模型 | D28 golden、X31 規範差異、MG23 14/14 local consumer | X01–X09 共 9 項 version/sidecar/identity/rollback 結案；真實 Consumers 的否決測試 | 技術部分完成，正式 0/9 |
| AR02 Durable Kernel | CAS journal、checkpoints、cancel、recover、approval、UNKNOWN reconcile | K28 真 OS 故障恢復 6 個，local transaction fixture | 同一個真實任務的中斷/續跑及已執行外部效果不重送 | 本機範圍 PASS，E2E 未結案 |
| AR03 Context/Capability | 最少充分可信上下文、source ACL、Knowledge/Memory/Skills/Tools 接線 | 11 份合法第一方 source、21 source spans、Q34 native lexical citations | 真實已允許 corpus 的 semantic/vector、變更追蹤、多 tenant/權限覆蓋、source freshness | 部分完成 |
| AR04 Governed Tool | least privilege、sandbox、安全 action intent/receipt/權限回撤 | Local Action與負向拒絕、單機 TaskContract | 可授權真實外部效果/rollback/獨立 Observer、注入與跨租戶否決 | 部分完成 |
| AR05 Verification & Publication | Claim/Source/Semantic, Artifact/Test, RemoteOutcome、排序發布/更正 | Q33 42+6、MG33 66/66 proof-of-protocol | 真實模型生成 claim 可早於 worker 結束被驗證，才發布；獨立 outcome verifier | 部分完成；原生 Streaming FAIL |
| AR06 Governed Memory | 記憶 typed lifecycle、consent/TTL/revoke/delete/caches、候選寫回 | M28 撤銷/隔離與 MG33 文件路徑/撤銷測試 | 真實多儲存、備份/衍生引用完整移除與 restore 封鎖、獨立驗證 | 部分完成 |
| AR07 Compute/Model Routing | model/router/decision provider、budget caps、multi-round、ablation | local compute policy、FIX-M27 ProviderQuota / round telemetry 6/6 | 同一 workload 的 cost/quality/latency ablation、真實 Provider usage/cost receipt、未知結果停損 | 部分完成 |
| AR08 Outcome Workloads | QA、Research、Coding/Action 三切面跨模組工作，persist/verify | QA/Research/local action 非正式 E2E；M27 修復本機語意/驗證路徑 | 真正同一 TaskContract coding patch/OS verifier、研究 artifact 與 crash/resume；安全既有拒絕仍有效 | 部分完成 |
| AR09 Eval & FinOps | 長短任務評測、獨立 grader、telemetry、goldens、release SLO | MG36 4,838/17、M27 2,770/0、Client trace、source accuracy 紀錄 | 正式 523/200，當前 image 的客戶端 first-text/p95/quality/cost/false-safe/holdout | 框架完成部分，正式 0/523、0/200 |
| AR10 Candidate Learning | Failure mining → Proposal → adversarial eval → approval → rollback | 離線 Draft、禁止 auto promotion | 選 1 個真實 error class 做候選改善、凍結評測證明 generalization、審核/撤回；不自動 Production | 本機部分完成 |

## 4.1「真正可運作」的最低能力檢驗（非口號）
每個 Workload 的同一 admitted RunID/TaskContract 至少留下：
1. 明確 Owner/Tenant/Scope/Deadline/Budget/Acceptance input。
2. 經 Task Journal 永久化的每輪計畫、上下文來源、工具實際呼叫與事件序列。
3. 資料/記憶/Skills/Workspace 能證明受 ACL 和版本控制，沒有越權取得資料。
4. 工具寫入採 Side Effect Receipt；timeout 造成 Unknown 時只能先 observe/reconcile。
5. Output 給出可獨立核驗的「Artifact/Remote State/Answer」，引用與原始 bytes 對得上。
6. checkpoint→kill→restart/resume 的相同 RunID 線索（或安全新 run 連結），終態合理。
7. 真正客戶端收得到正確內容；對負向/未知情況能安全停下，且不把 Safe Terminal 計入成功。
8. 日誌可重跑、原始測試和版本一致，至少一名非施工者抽驗。

# 5. 2026-10-14 實際工程基準（禁止翻案或錯加）

## 5.1 不再重做的已通過範圍
| 工程波次 | 有物理證據的事實 | 說明/限制 |
|---|---|---|
| Q33/Q34/V34 | 凍結 HEAD 89f1d7be…；本機 Wheel 500/500 對應；Stage30G 42/42 + six extra；F28 scoped 1327 | V34 只保證限定原始碼/測試，不保證 current formal app ready |
| MG05 | Ruff 原始 852 項、27 rules / 63 files 已分類 | Ruff 仍紅；以高風險為主，勿因格式問題癱瘓功能開發 |
| MG06–MG11 | N31 localhost HTTP、120 dev題 API（非正式回答品質）、獨立二跳 SSE/Client | 部分 fixture；不可代表官方 523 的回答正確率 |
| MG12–MG16 | Oracle VM MiniMax 真實 HTTP及跨 Mac Client，有限次 provider/Transport，dev-only ACK | 首輪 grounding fail-closed 有保留；開發者自簽不代表正式 IdP/Client |
| MG17/MG18 | 真實 GitHub Actions OIDC / Sigstore 對 Q34 Wheel 與獨立 linux/amd64 N31-fixture OCI 簽署，實際 oracle-vm Docker | 不是原版 ARM64 Q34 Product App 的完整發布資格 |
| MG19 | 原版 OCI 內容安全掃描、實際 CI policy / negative tests | 原 ARM64 Q34 OCI **REJECT as-is**，不能混成 MG18「已正式簽署可上線」 |
| MG20–MG24 | 第一方資料控制聲明、有限合法簽署來源、實際原生 Q34 發行檔案解析、D28 consumer | 11 docs/21 spans；不能擴稱所有第三方資料都已授權 |
| MG26–MG30 | 原始 Q34 FastAPI 非生產生命周期/Health、內部資料 Lexical Q&A、JWT/TLS JWKS 真 TCP HTTP | 不是正式完整 IdP、模型品質、向量 Qdrant |
| MG31–MG35 | 真正診斷原生 SSE 等 worker 完成才吐內容；MG33 簽名/路徑/撤銷原型 66/66 | **真正早期生成文字原生路徑仍 FAIL**；原型不能當整合成功 |
| MG36 | TEST-only Streaming OFF gateway，15/15 TCP + 23/23 JWT/TLS；292 測試模組 | 凍結 Q34 原生 SSE 無 switch；另外 215 模組沒選，M24 有一個 missing Playwright |

## 5.2 本期可核對的 Failure Ledger
| 項目 | 原始基準 | 實修現況（各自獨立分支） | 待驗證 |
|---|---|---|---|
| Core Channel | MG36 1 FAIL | 正確 KNOWLEDGE_CHANNEL=staging 回歸 1 PASS | 仍須新整合候選版配置一致 |
| FIX-M26 | 原始 10 FAIL | 4 項程式修復在 Python 3.11 PASS；M26 75 模組 857 PASS/6 FAIL | 3 個 FastPublic 契約、2 個不可倒改歷史 SHA/Runtime attestation、1 個 Python3.11 AST |
| FIX-M27 | 原始 6 FAIL | 6/6 修復，85 模組 2770 PASS/0 FAIL | 另有 inherited positive production bridge 1 FAIL |
| Full original MG36 | 4,838 PASS/17 FAIL（當時原始 292 模組） | 尚未有兩修復合併的 full rerun | 重新測 16 原始節點和範圍案例，保留分母 |
| M24 | 1 module 缺 Playwright | 未修 | 僅在 disposable checkout 跑，原 MG36 測試曾寫到 3 個 tracked files 已做精確還原 |
| Native Streaming | Q34 原生 generated first text FAIL | MG33 claim verifier 安全原型 / MG36 stream OFF TEST gateway | Q34原生真生成 Claim 邊產出邊驗證尚未完成 |
| Full Release | 原 ARM64 OCI 不適用直接發布 | signed Wheel / signed N31 fixture / local app 部分證據 | 安全新產品 image + 非正式完整 App + 真正式資格 |

**Git 基準：**原始 Q34 HEAD 89f1d7be1623cd6926a69e38871544eefe39e584；TREE cde4d6ad61acef348350afcfe18f836d798a2091；凍結 clean。FIX-M26 commit 5697b667ed21f3688487978db2595ff66304555b；FIX-M27 commit 959aa1a4ae5d5855a511c8f29cff200c54348778。兩份 diff 文件所有權互斥、原始日誌 SHA 驗證通過；**合併未執行**。

# 6. 完整施工 Roadmap（工程先行，正式認證不干擾合規的 Nonprod）

| Wave | 目標 | 施工單位與互斥界線 | 前置 | 必交付的真正 Done | 當前 |
|---|---|---|---|---|---|
| W0 Evidence Baseline | 建立一個可追溯的 Q34 本機基準及已有成果 | Master read-only | 已有 | 凍結 SHA + 能力矩陣 + 風險/合法性分類 | 已完成基準 |
| **W1 I37** | 合併 M26 4 項與 M27 6 項修復 | 單一 Integration Owner，**第三個全新 Nonprod worktree** | FIX-M26/M27 commits | 16 原失敗節點在同一版本重測；兩組 75/85 模組、bridge/ACL/source/HTTP；精確剩餘紅燈 | **NEXT READY** |
| W2-A M26 Contract | 結清 FastPublic 3 個衝突，定正確 canonical 行為 | M26 Contract Owner／Tester | I37 baseline 可並行研究，實修改遵守版本 | ADR 指明舊/新契約、failclosed 要求、負測、實際重測；不以刪 metadata 或忽略 provider calls 求綠 | 未完 |
| W2-B M26 Attestation | 結清 2 個歷史 hash/runtime_path 衝突 | 發布證據/版本 Owner，與 W2-A 分工 | 真 provenance chain | 新版本新 evidence / 真實再驗收，不修改舊 acceptance 冒充歷史執行 | 未完 |
| W2-C Python Parser | 決定 Python 3.11 與 protected evaluator 的合法處理 | Evaluator Custodian + Test Owner | 支援範圍與政策確認 | 正式支援環境的 parser/AST test 一致 PASS；若先前受拒，封閉剩餘 blocker 不能繞道 | 未完 |
| W2-D M24 QA | 修復 Playwright 缺依賴並執行被漏掉的 module | 獨立 Dev QA checkout | 安全 disposable checkout | 原始 module 能 collect/run，保存實際結果，無 Q34 檔案副作用 | 未完 |
| W3-A Native Gen Streaming | 真正 preterminal verified generated text | 原生 App/Verifier/Client 跨模組 Owner；只在允許範圍 | MG33 proof + Task/Claim event ABI | Worker 未結束前 Client 收到來源可追蹤的生成文字，序列與更正，負向拒絕；目前原路徑曾遭明確拒絕，不得重試等價修改 | FAIL / 受限 |
| W3-B Q&A Semantic & Context | 發行範圍內完成真實來源檢索與採信 | Source/Context Product Owner | 適法來源版本與安全 scope | 對真 Provider+原生 Product 的引用/語意/ACL/來源更新，超出已驗證 lexical-only/11 docs | 部分 |
| W3-C Real signed Product | Product image/manifest safe from contamination，含 rollback | Release Owner 單點序列化 | W1 版 + MG19 guard + W3 產品接線 | 重新驗證源 Wheel→完整安全 OCI→簽章→真 Nonprod App/Client，拒絕原 ARM64 as-is | 尚未 |
| W4-A Real E2E Workloads | QA/Research/Coding-Action 跨 TaskContract 含 durable 恢復 | AR02/03/04/05/08 E2E Owner；不同 workload 可平行、合版串行 | W1 + 真 Consumer + 相關權限 | 每工作負載 1 正/1 負/1 故障以上，實際 accepted artifact/effect 和 OS 恢復 | 部分 |
| W4-B Memory/Compute/Learning | AR06/07/10 跨 module 正負與成本/候選閉環 | Memory / Cost / Learning 不同 owners 可平行 | W4-A fixture or approved real tasks | 更正撤銷真閉環、Provider 可追溯費用/策略 ablation、offline candidate nonautopromote | 部分 |
| W5-A Formal ABI & G35 | 關閉真正 Release 前的 X01–X09 版本與授權 | ABI/Product Owner + 真的 IdP/Provider/Reader controllers | W3 image / Consumer 資料 | 9/9 contract + formal release compatibility/effective authority；**不阻擋前面合法 offline** | 0/9 |
| W5-B C28 bounded App trial | 以同一整合版本跑真正 App+Provider+Client | 一位 Run Coordinator | W3-C + W5-A + 真財務限額、回滾 | 真實 signed client ACK、side-effect observer、Provider billable usage / failclosed | HOLD |
| W6-A E27 | 523 題官方受權評估 | 獨立評分者（非施工者） | Qualified App/roster/custody | 523/523 有效分母、答案/引用/時延/品質/拒答，抽查反證 | 0/523 |
| W6-B B27 | 全新獨立 200 題盲測 | 獨立保管員（不可向 Master/修復 Worker 洩漏） | qualified sealed corpus + App | 200 個已封存/去重/可驗證標準答案、真評分；不拿舊 dev 200 冒充 | 0/200 |
| W6-C A35/F35 | AR00–10 端到端獨立總驗收 | 獨立架構 Reviewer | W4 + W5 及安全 P0 關閉 | Task/Outcome, failures, telemetry, correction, rights, cost, adaptive and learning proof | HOLD |
| W7-A V27 / REL01 | Q&A product 同版本發行認證 | Product release certifier，區別 F35 | W5+W6 且三指標 | ≥95% cited final、p95≤15s、真 generated first text、品質/rollback | HOLD |
| W7-B REL02 | Production progressive canary | Owner **獨立新授權** + Release Controller | REL01 truly PASS | canary / kill / rollback / monitoring / signed exact version | OWNER NO-GO |
| W8 Archive | 版本與證據封存、可轉交新 Master | Master | 上述按 Track 結案 | 終版 acceptance/gaps/matrix/rollback + 長期演進 backlog | 尚未 |

**並行規則：**W2-A/B/C/D 可同時進行不重疊的調查/隔離測試；W3-A/B 可以獨立設計/試驗，但共用原生 Runtime/ABI 修改與 final source merge 必須有一位整合 Owner；W4 多 workload 可並行，各 E2E 接線需最後回一個 shared build；W6-A 和 W6-B 必須不同評測 custody，不能交叉洩漏；REL02 絕不可與正式驗收並行。


# 7. 驗收矩陣：怎樣才算 DONE

## 7.1 通用能力成熟度（不可跳級）
1. SPEC_ONLY：僅 schema / 文件 / 原型；**不算運作**。
2. COMPONENT_TESTED：單元與負向例通過；**不等於接入產品**。
3. ISOLATED_EXECUTABLE：獨立 OS/process/local HTTP 真實執行；**不等於正式服務**。
4. PRODUCT_PATH_WIRED：原生 Runtime／公開 App 設計入口使用相同 source/version/identity/verification。
5. END_TO_END_EVALUATED：有獨立 client、實際 artifacts/effects、故障/回復、品質與成本。
6. RELEASE_CANDIDATE_CERTIFIED：Source/rights/image/IdP/benchmark/rollback 契約完全合格。
7. OWNER_CANARY：有特定 Owner 正式批准和觀測回滾。
8. PUBLIC_ROLLOUT：另外批准與追蹤，絕不能由前一級自動晉升。

每一個 AR 模組獨立標「已達等級」，不得用全專案最新最高等級蓋過它的低成熟度。候選學習的 PROPOSAL_ONLY 是權限屬性，**不是**成熟度第七級。

## 7.2 指標區分（禁止一個 523 mixed numbers 包山包海）
| Track / 測試 | 最少應測什麼 | 絕不接受 |
|---|---|---|
| Q&A 發布 | eligible 523 固定 denominator 的 cited final ≥95%；答題相關性、事實與引用、拒答正確、品質獨立 rubric（原始架構提議成功答案 ≥85/100）、final-answer p95 ≤15s | 341 live +182 replay 自稱 523 真獨立答案；品質代理值=100；高 abstain 充當高正確率 |
| Client early text | 外部 Client 真正收到 **經驗證的實質生成文字**，早於 Worker/backend 完成與 terminal；有 timestamp／event seq／source ID；再測 cancel/timeout/correction | progress/start 事件、空文字、模板、純 extractive / deterministic source-only、terminal 前瞬間補送 |
| Long-task Execution | QA/Research/Coding 三 workload、checkpoint/kill/recover/cancel、tenant/revoke/unknown reconcile、同一 TaskContract 真 accepted outcome | Q&A 分數取代 coding/research；只用 test fixtures 測到模型沒做真事 |
| Artifact/Action | 實際來源/檔案可驗 SHA；真 OS tests；有授權真 side effect 前後外部 observer/receipt | 說「執行成功」但無持久結果；工具回傳 ok 即認成功；未知狀態直接重發 |
| Security/Governance | 越權寫 100% 拒絕（測試集內）；跨租戶資料 0 洩露；consent/expiry/kill/rollback/unknown | 模型 prompt「不允許」代替 infra enforcement |
| Cost/Compute | 真 Provider log、使用量/費率/重試上限/超時、每個成功 outcome 花費；與 fixed rules/baseline 公平 ablation | Owner 沒設總金額上限就讓單次無限重試；只看 token 少，忽略失敗重做與 p95 |
| Blind eval | 新的獨立 unseen200 防洩漏、seed/QA/來源與 grader custody；和 development 題集去重 | 用舊 M26 200 或 Brutal100 冒充「全新盲測」；向修復者曝光答案 |
| CI/Product Release | Exact integrated source/clean Git → build SHA → scanner → signed safe image → App startup/IdP → rollback/launch | original Q34 ARM64 OCI 被 MG19 REJECT 還繼續當可發行，或拿 signed N31 fixture 取代 signed Product App |

**跨版本一致性**：同一 Release Gate 必須同時指向一組 exact source tree / ABI / data release / evaluator / provider config / Client contract，才能合法談 523/p95/Streaming 指標；不同版本的 PASS 不可直接加總。

# 8. 本期唯一 Next Dispatch：I37 真正整合版

**目的：**將兩份獨立修復轉為同一個可重現 Nonprod 候選版，這是目前最短工程關鍵路徑。

**現有不可變輸入**
- Q34 baseline：HEAD 89f1d7be1623cd6926a69e38871544eefe39e584、TREE cde4d6ad61acef348350afcfe18f836d798a2091、clean。
- M26 source-only commit：5697b667ed21f3688487978db2595ff66304555b，改 3 個 M26 files。
- M27 source-only commit：959aa1a4ae5d5855a511c8f29cff200c54348778，改 1 個 M27 file。
- Master 驗收：02_REPORTS/REGRESSION_RECOVERY/MASTER_FIX_M26_M27_ACCEPTANCE_20261014.md。
- Baseline：MG36 Nonprod 原始 4,838/17 與檔案/模組選取清單；保留失敗日誌。

**I37 必做次序**
1. 用 RDC 從 Q34 建 **新的第三獨立 checkout/worktree**，保護原 Q34 與兩 Worker 工作樹。確認同 Git ancestry、source SHA 和 status。
2. 按固定版本將兩 commit 套入候選版，明列 exact diff 和四個檔案的來源；不順手包含評測修補/Production/Streaming/Protected Script。
3. 在隔離 Python3.11 + network guard + 不碰非本機網路的環境，重新跑原始 **M26 10 節點、M27 6 節點**（包含原始參數化），保存統一分母/原樣輸出、失敗訊息。
4. 再跑原 MG36 75 模組 M26 + 85 模組 M27，確認數字與新增 regression；針對剩餘 6 M26 契約差異明確標 preexisting/changed。
5. 跑 M27 positive production-equivalent bridge 和 failclosed negatives，跨 M26 semantic/ProviderQuota integration；真 local Q34 app / first-party citation / JWT 體系可做經允許的隔離 HTTP smoke。
6. 對 ABI、Graph/citation evidence boundary、unknown-effect/budget、ACL、finalization telemetry 做差異測試。任何未驗證來源不得當 cited fact。
7. 交付乾淨或明確隔離候選版本的 Git HEAD/TREE、改檔清單、patch SHA、真實 runner/log、before/after 分母和非本次可修的剩餘 blocker。只有主控核對後可 MASTER_ACCEPTED。
8. **不發行、不 CI push、不替換 Q34 release pointer、不跑受保護 official 523/200、不碰曾明確遭拒的 AR08/native streaming/Qdrant/CI 相同操作。**

**I37 Done**：兩 commit 皆確實在同一版本，無合併時新增的測試失敗；M27 六項全部仍 PASS；M26 四項修復仍 PASS；剩餘六項完整列出；真實交叉/安全回歸完成，Master 確認證據真實。不能因 6 項 M26 歷史紅燈而把已證實整合成功的 *限定工程 Gate* 說成整個不能施工；也不能因 I37 scoped PASS 宣稱 REL01 完成。

## 8.1 並行但不阻塞 I37 的準備
- M26 CONTRACT：比較舊 FastPublic 的單次 provider call vs 新 canonical bounded retry，按 safety/quality/cost 判斷正確契約，提具可測版 ADR。
- M26 ATTESTATION：保留歷史 SHA/actual runtime，不倒改紀錄；若要 current acceptance，建立新合法 re-admission 證據。
- EVALUATOR：Python3.11 兼容性只允許檢查/必要合法替代；不可再執行先前遭明確拒絕的等價編輯。
- M24：只有隔離副本可裝 Playwright/跑會寫檔的測試；新基準要求具體測試實證。
- Streaming：獨立設計 source→verifier→native Claim event→Client ACK 的接口/對照矩陣；遇已明確禁止原生等價修改，保留拒絕、停止該操作，不藉其他工具/主機重試；其他合法模組照常推進。
- 523/200：真正的獨立評測保管員可做全新盲測封存、roster/rubric/right/denominator 凍結準備；不能讀回給 Master/修復者。

# 9. 風險登錄與排序（沒有資格自動新增 P0）

| 風險 ID | 根因與實際影響 | 建議等級 | 解除證據 |
|---|---|---|---|
| R1 | **兩個來源分支尚未整合**，多套 PASS 不可合算；可能跨模組不相容 | P0 NOW | I37 同版原始測試 + integration + negative |
| R2 | M26 三項舊 FastPublic contract 不一致，無法判斷 retry 語意規範 | P0 focused | Owner ABI/Canonical semantic contract + 原測試和新反證，不弱化証據 |
| R3 | M26 兩項歷史 attestation SHA/path 不一致，若硬改造假可污染來源治理 | P0 release-provenance | 現版真實 re-admission/new receipts；保留舊證據 |
| R4 | Python3.11 AST 與 protected evaluator f-string 不相容 | P1 scoped, or P0 if gate actually invokes | 在被允許的正式 runner 提供相容 proof；禁止繞過拒絕 |
| R5 | **Q34 native generated first-text Streaming FAIL**（大硬指標） | Release P0 | 真 Client 早於 backend end 收到 source-bound verified generated text |
| R6 | 真 Qdrant vectors/多來源 Model QA 未驗證；MG25 部署明確拒絕 | Product blocker | 合法新權限或非等價可用的既有 read-only 資料/產品路線；不得用替代工具重試原拒操作 |
| R7 | 原 Q34 ARM64 OCI source/package-path safety REJECT（MG19） | Release P0 | 全新合規安全 Product artifact scanned/signed/rollback |
| R8 | 正式 ABI 0/9、IdP/source rights/evaluator custody 未閉合 | Release P0 | 具版本、真發證者、consumer/negative ACK 的合法證據 |
| R9 | AR08 Coding same TaskContract 實際 persisted patch 缺，先前修改曾明確遭拒 | Architecture P0 | 在核准範圍完成真正 outcome；不可重試遭拒等價 scope |
| R10 | 官方 523、獨立 unseen200 都未評估，沒有正式引用率、品質、p95 | Release P0 | 按同版同設定真 523/200 全量獨立分母與分數 |
| R11 | Ruff 852 inherited，多為格式噪音但有 F601/F822/invalid-syntax | Risk-based P1 | changed-path risk gate，已證明到達路徑的具體問題才修；無全面跳過 |
| R12 | M24 Playwright missing + 3 tracked side effects | P1 | 全新 disposable worktree 中實際執行，禁止寫 Q34 |
| R13 | 壓力測試重複啟動/Provider 無硬上限與未知 effect 重試 | P0 safety | 實際 per-experiment cap / concurrency / timeout / rate/kill + receipts，不能無上限 |

P0 定義：影響下一個真實產品能力、違反 hard invariant、阻止下一個有證據的 Gate。只是出現形式性合約缺口、別名 Stage 或過時的報告標題，不可自動當新 P0。


# 10. 長期協作與防偏移操作合約

## 10.1 每個新施工 Session 只能做一個 bounded objective
每包必須同時有：唯一 WorkID／原始目標 AR/REL／來源依賴 SHA／允許改檔／禁止範圍／前後原始測試／負向與反證／成功退出條件／輸出絕對路徑／明確 blocker/owner。若其中任一缺少，Master 先修包，不讓 Worker 自行把一個週期延長成無限 Stage。

**角色分開：**
- Owner：定 Product Outcome、批准自己控制的 Nonprod 資產與必要 ADR、最後 Production 是否上線；不需每一輪重給已批准授權。
- Master：守北極星、拆依賴、合併版本、獨立核對 logs/receipts、更新當期全局狀態、決定唯一下一個工程 Critical Path。
- Worker：只修自己可改檔案/測試；回報路徑+PASS/PARTIAL/BLOCKED；不得自行總專案簽核或修改 Master 狀態。
- Independent Evaluator/Custodian：獨立新盲測、正式 graded outcome/cost/latency；不能同時替考題做特調與評分。
- Release/Provider/IdP controllers：只有實際對資源具有合法控制權的人/系統負責相應簽署、使用權和外部效果；不虛構不必要的企業多方核准。

**協作粒度：**不同改檔 Owner 可平行（AR02/03/04；M26 契約、M24 環境、非洩漏盲測準備），但 Merge 與共享 Runtime/API/ABI 必須單一 Integration Owner 串行；嚴禁兩 Worker 同時改 Q34 或同一 Release pointer。

## 10.2 每次收到 Worker 報告，Master 必做的十項核對
1. WorkID 是否對應本憲章的 AR/REL 真正能力和眼前故障？沒有的 Stage 不加權。
2. 原始「before」是否真失敗、版本/runner/環境/資料分母明確？
3. 是否真的改到實作原始碼或真 Product 路徑（不是只有文件、mock 或 setup）？
4. Git HEAD/TREE/clean、diff/touched files 與 frozen baseline 比對。
5. after 的原始失敗節點是否在 **同一版本、相同要求** PASS；沒有就 PARTIAL。
6. 正/負回歸、安全 Fail Closed、Unknown、引用 provenance 是否保留？
7. 來源是自有/授權且未曝光 protected original523 / sealed200 / secrets？
8. 正確分開 LOCAL / REAL PROVIDER / AUTHENTIC SIGNED ARTIFACT / OFFICIAL EVAL / PRODUCTION？
9. 哪一個真正的 P0 降低？下一個被解鎖的實際動作是什麼？
10. 更新全局表及交接紀錄後，**禁止再派原封不動的重複 Audit**。

## 10.3 「一直 BLOCKED」如何處理
先把該 Blocker 分成以下互斥類型：
- **TECHNICAL_FAILURE**：測試/執行真失敗，可在另開 Nonprod scope 修復；保留最小重現，寫 patch 和 rerun。
- **ENV_MISSING**：依賴/設定/模型缺失；在獨立 disposable 環境復原，不能把它當產品缺陷。
- **CONTRACT_CONFLICT**：新舊接口彼此矛盾；由 Owner/Consumer ADR 決定版本；暫停改錯合約，不阻擋其餘無依賴工作。
- **AUTHENTIC_RIGHTS_OR_INDEPENDENT_CUSTODY**：真實外部權利/身分/獨立評測尚缺；保留發行和正式 grade HOLD，不禁止無依賴的自有 Nonprod 模組開發。
- **EXPLICIT_PLATFORM_REFUSAL**：明確平台安全拒絕；不可換工具、Mac、repo 或 agent 做等價重試。保留拒絕證據，對該工作標限定 BLOCKED，轉往其他獨立允許的模組。
- **NO_EVIDENCE**：只有 Worker 自述、沒有 raw traces/sha/原始程式；不能 MASTER_ACCEPTED，要求提交實物而非再生一份描述。

每次至少提出一個「**實際可推進的相鄰模組**」，除非所有工作都真的依賴同一不可解除條件；不能用「等外部授權」當萬用失敗理由。

## 10.4 一項工作何時不值得做
- 不能證明服務 AR00–10/REL 中至少一項、沒有衡量指標。
- 只是把已有 PASS 重新跑成另一個名字的 PASS、沒有失敗假設/新增風險覆蓋。
- 一次超過一個主要模組 Owner 或碰觸受保護範圍，但不具正式整合計畫。
- 需要造假驗收數值、修改原始 grading 或過去 SHA 紀錄。
- 新增功能只針對指定 benchmark 字串修，而無 paraphrase/反證/generalization。
- 因為有個格式 Ruff 項目就放棄更高優先的穩定性與安全修復。

# 11. 防偏移校準頁（每次新 Master Session 開工先填）

本表只能引用最新實際證據，這次的預設答案對應 2026-10-14，未來需標註 as-of。

| 校準問句 | 基準答案／填入方法 |
|---|---|
| 1. 最終要做什麼？ | 通用、持久、受治理、Context-Native、可驗證 Task/Outcome Agent Runtime，不只是 Q&A |
| 2. 哪三個 Outcome 要能實際完成？ | 可信 QA、持久多步 Research、持久 Coding patch 或核准真 Action |
| 3. 哪些不可被 Agent 取代？ | Knowledge Engine deterministic substrate：R2/Qdrant/BM25/Graph/Compiler/ACL/Provenance/Release |
| 4. 真正的當前主線是？ | 2026-10-14：**I37 第三工作樹合併與實測**；未來以最新主控 JSON 更新 |
| 5. 原始 16 個程式失敗？ | M26 各分支 4 fixed／6 fail Py311；M27 各分支 6 fixed／0 fail；**尚未同版** |
| 6. 現在最危險的硬缺口？ | native verified generated first-text FAIL、Coding E2E not proven、官方 523/200＝0、正式 Product image/signer/rights |
| 7. 本期有沒有真的做出改進？ | 必填：changed Git files/commit、原始原失敗 test before/after、Client/Provider/artifact receipts |
| 8. 什麼不可動？ | Production、Q34 frozen、protected grader/holdout、原 M26 功能服務、先前明確遭拒等價操作 |
| 9. 下一個必交付可量測內容？ | I37 同版原始 16 節點 + 75/85 模組 + negative regression + 乾淨 HEAD/TREE |
| 10. 是否偷把正式發行 Gate 當工程全部禁止？ | 不可以。發布/外部認證 HOLD 僅限制有依賴的發行／真外部行為，不攔合法獨立 Nonprod |
| 11. 是否冒用正式數字？ | 官方 523/200 與 p95/first-text 沒有完整合格收據就寫 NOT VERIFIED |
| 12. 這次有沒有偏移？ | 逐一檢查下面 6 條，任何一個 YES 必須修正下一派工與註記原因 |

**偏移警報（任一 YES 即觸發 Master review）**
- 新 WorkID 超過 1 個，卻無新測試覆蓋或真 P0 降低？
- 只增加報告、審計、簽章或 CI，但沒有產品主線進度與新驗收定義？
- 因 0/9 ABI 正式 ratified 而禁止修復純 Nonprod M26/M27 功能？
- 把 source-signature、N31 fixture、health200、dev signed ACK 當 full App ready？
- 把 MG33 安全 Proto 的 PASS 當 Q34 genuine first generated answer streaming PASS？
- 把自己修過的評測題、舊 200、固定 20 unique admission lines 當成 200 fresh unseen / 官方 523？

若報表缺少定義/依賴/原始證據，Master 應先校正該項，不得用自信的漂亮百分比替代觀察。

# 12. 進度衡量與每期更新流程

**不使用假的全局精確百分比。** 歷史 45.5% 是舊版 22 項等權行政估算，不能用於 2026-10-14 的實際架構/產品完工率。

保留五種可核對的「實際進度」：
A. **AR00–10 Maturity Matrix**：每項 1–8 最高「被驗證等級」，附證據，不跨行套用。  
B. **Program Gate Table**：I37、M26 residual、native Streaming、AR08 E2E、X01–09、C28、E27、B27、F35、REL01、REL02 實際狀態。  
C. **Regression Closure**：以凍結原測試節點分母和同一 merged source 計算 pass/failed；新 test 和歷史 test 分開。  
D. **Real Outcome Success**：QA/Research/Coding 依同一 TaskContract 的真正 accepted artifact/fault retry/Source verification 和 Client ACK。  
E. **Release Certification**：523、200、≥95%、p95≤15s、verified generated streaming、cost & safety，沒有 qualified evidence 不填 PASS。

**每次交付後更新本機：**
1. 先寫 immutable evidence report 及 raw logs/hashes（歷史報告不能無聲覆寫）。
2. Master 實際讀原始 log 與執行版本，做必要 read-only 狀態與抽查。
3. 更新「02_MASTER_GATE_STATE.json」的相應欄位和下一個 Critical Path（不是直接改 MASTER_STATE_V3 歷史記錄）。
4. 更新「05_MASTER_MAINLINE_PROGRESS_20261014.md」或之後新日期的進度快照，保留歷史。
5. 若架構目標/依賴/硬驗收本身變動，另開 **Charter v1.1 ADR + 明確 Owner 認可**；不能讓 Worker 偷改北極星。
6. 新 Session 讀 **本憲章 + 最新 State + 最近一次 Master Acceptance** 就能接手；不要把幾十個前 Session 文字全貼入 Context。

## 12.1 單一工作報告固定格式（可供任務派工使用）
- Work ID / Architectural Goal / Allowed Scope / Forbidden Scope
- Baseline Git HEAD/TREE、工作樹、Python/Provider/CI 環境
- 原始題目/測試或 real workload，基準分母、失敗原因、可反證假設
- 實際原始碼或 contract ADR 變更、檔案 diff SHA、來源權利
- before/after original tests、正負/故障回歸、相同分母、exit codes
- 客戶端/外部效果/產物 observed receipt、限制/不確定性
- PASS/PARTIAL/BLOCKED 的範圍；remaining failures；下一個唯一 action
- 完整本機 Report Absolute Path（最後對話只需路徑 + 狀態）

# 13. 真正完工之判準與最終決策權

**Architecture DONE（F35）**：AR01 契約結案 + AR02–AR07 同版真 E2E + AR08 三個實際可驗收任務 + AR09 獨立效能安全評測 + AR10 有治理的 candidate 改善、no autoprod；所有 P0 都有明確解除/保留且不以假 PASS 隱藏；獨立 Reviewer 驗過真 log/receipts。

**Q&A Product DONE（REL01）**：一個 current source/ABI/data/Provider/Client/signed Safe Product Image，持續正常啟動、安全 rollback，在獨立合格 523 與新 200 盲測證明 ≥95% cited final、final p95≤15sec、前端真收到 verified generated first text、正確性/品質/拒答/cost 指標達合約。對原始架構建議的獨立 answer quality ≥85/100 須以正式 rubric 定義、不能用 proxy 取代。

**Public DONE（REL02）**：REL01 通過後有 Owner 新的明確 Production GO，部署可控 canary、觀測、降級、kill-switch/rollback、保留簽署與計費證據；沒授權就標完成到 REL01 為止，不得偷跑。

**不能過度承諾**：Context-native 技術架構可隨模型演進、Jev/multiagent 可選且須 ablation；不強迫所有任務 p95≤15sec（該門檻適用 Q&A final answer），不把單次真 Provider/Client 成功當普遍品質保證，不把所有 852 Ruff 一夕清零當成功。

# 14. Source-of-Truth 指引（不要繞回舊 Master）
以下相對路徑皆相對於目前 Master 目錄：

- 本憲章：06_M27_VNEXT_MASTER_ARCHITECTURE_AND_CONSTRUCTION_CHARTER_V1_20261014.md
- 最新 10/14 全部能力與 Gate 進度：05_MASTER_MAINLINE_PROGRESS_20261014.md
- 現行 machine 狀態：02_MASTER_GATE_STATE.json
- 分工：03_DISPATCH_INDEX.md、01_DISPATCH/REGRESSION_RECOVERY/
- 兩份個別 worker 報告：02_REPORTS/REGRESSION_RECOVERY/FIX_M26_REPORT.md、FIX_M27_REPORT.md
- 獨立 Master 驗收：02_REPORTS/REGRESSION_RECOVERY/MASTER_FIX_M26_M27_ACCEPTANCE_20261014.md
- 關鍵本機測試 MG36：02_REPORTS/MG36_STREAM_OFF_NONSTREAM_REGRESSION_REPORT_20261014.md
- Q34/V34 immutable admission：上層 02_ACCEPTANCE/V34_MASTER_INDEPENDENT_CURRENT_SOURCE_ACCEPTANCE_20261013.md
- 原始 Master intent：使用者提供的 M27_KNOWLEDGE_OS_VNEXT_ARCHITECTURE_MASTERPLAN_20261009.md
- 先前 2026-10-13 Gate 文件：04_OWNER_UNLOCK_ACTIONS_20261013.md；其中早期「所有 G35 外部授權等待」不可覆蓋較新的真 Nonprod 工程證據或重新索求 Owner 已授權的事。
- 所有未提到的最近實際工程結果，僅依原始 log、源 Git、簽署證書與完整驗收提升狀態；不得以此文件預先認證。

## 14.1 版本與更改紀錄
| 版次 | 日期 | 變更 | 效力 |
|---|---|---|---|
| v1.0 | 2026-10-14 | 原始 10/09 架構北極星 + 10/14 MG36/FIX-M26/FIX-M27 真實進度 + I37 至 REL02 施工主線與反偏移合約 | 本版正式作為 Master 的方向基準；不追溯改動舊報告或已凍結程式碼 |
| 未來 v1.1+ | 需 Owner 明確同意 | 任何使命、三 Workload、AR/REL 總責任或硬發行 Gate 改動，附 ADR 與回歸影響 | 不得由 Worker 或新 Session 自行產生既成事實 |

---

### 最短校準口令

**「先讀 M27 Charter v1 + 最新 Gate State + 最近 Master Acceptance。指出現在真正可交付哪個 Task/Outcome 能力、上一 Gate 哪個原始失敗被修好、下一個只做哪件事。不要重跑無意義稽核；不要把 Nonprod 限定 PASS 冒稱 Production；不要因正式發行 Gate 未簽就停止所有合法工程。」**

**本版唯一 Next：I37 合併 M26/M27 真修復，實際測試後再決定接下來的 P0。**
