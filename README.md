# Knowledge OS Executable Contracts v0.1.0

這個套件定義 Knowledge OS 第一版可執行契約。它不是願景文件，而是 Builder、Runtime、CI 與未來各 Repo 共同遵守的邊界。

## 主契約

1. `docs/contracts/knowledge-layer-model.md`
2. `docs/contracts/okf-profile-v0.1.md`
3. `docs/contracts/knowledge-build-pipeline.md`
4. `schemas/release-manifest.schema.json`
5. `schemas/provenance.schema.json`
6. `docs/contracts/runtime-query-contract.md`
7. `docs/contracts/relation-ontology-v0.1.md`
8. `schemas/relation-ontology-v0.1.schema.json`

## 隨附執行材料

- `examples/`：有效與無效範例，以及最小 OKF bundle。
- `scripts/validate_contracts.py`：執行既有 JSON Schema、跨檔引用、ACL 傳播與 OKF 發布規則驗證。
- `scripts/validate_relation_ontology.py`：執行 relation ontology schema 與跨型別 invariant 驗證。
- `tests/`：自動化與 adversarial tests。
- `reference/knowledge_engine.py`：可執行的 Builder 與 Runtime 垂直切片。
- `requirements-dev.txt`：驗證所需的 Python 套件。

## 快速驗證

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python scripts/validate_contracts.py
python scripts/validate_relation_ontology.py
python -m pytest -q
```

成功時必須看到：

```text
CONTRACT_VALIDATION_PASSED
RELATION_ONTOLOGY_VALIDATION_PASSED
```

## 規範來源

本 Profile 建立在 Open Knowledge Format v0.1 Draft 與 Karpathy LLM Wiki pattern 之上，並另外規定 release、provenance、ACL、Builder state machine、Runtime wire contract 與受治理 typed relations。
