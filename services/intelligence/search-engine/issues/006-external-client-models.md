# Issue 6: 外部 client 模型 + rules guard

## Parent

PRD: search-engine 多模式检索引擎

## What to build

定义 search-engine 与外部服务（LSL rule-extractor、HT doc-parser）的 HTTP 集成契约模型，并在 handler 层加上 rules 数据源的校验逻辑。本 issue 不执行任何 HTTP 调用——只定义 Pydantic 类型和参数校验。

**clients/lsl.py**：定义 LSL `GET /api/v1/rules/search` 的请求参数模型（`RuleSearchParams`: keyword, category, doc_id, page, page_size）和响应模型（`RuleSearchResponse`: items 列表含 `RuleResult` 全部字段）。这些模型与 ICD-02 §4.2 定义契约一致。

**clients/ht.py**：定义 HT `POST /api/v1/search/index` 回调的请求体模型（`SearchIndexRequest`），与 ICD-03 §5.1 定义契约一致。

**models.py**：`RuleResult`（如果 Issue #1 中已预留则跳过），字段：rule_id, text(=content), score, source_type="rule", metadata(rule_id, title, category, norm_ref, doc_id, section_number)。

**main.py**：在 `POST /api/v1/search` handler 中，增加 `include_sources` 的校验逻辑——如果请求中包含 `"rules"`，返回 400 `{"code": 1001, "message": "rules source is not available yet"}`。

## Acceptance criteria

- [ ] `clients/lsl.py` 中定义了 `RuleSearchParams` 和 `RuleSearchResponse` Pydantic 模型
- [ ] `clients/ht.py` 中定义了 `SearchIndexRequest` Pydantic 模型
- [ ] `POST /api/v1/search -d '{"query":"裂缝","mode":"vector","include_sources":["chunks","rules"]}'` 返回 400，提示 rules 不可用
- [ ] `POST /api/v1/search -d '{"query":"裂缝","mode":"vector","include_sources":["chunks"]}'` 正常返回结果
- [ ] LSL 和 HT client 模型无任何 HTTP 调用代码
- [ ] 模型字段与 ICD-02 §4.2 和 ICD-03 §5.1 一致
- [ ] 集成测试通过（验证 400 行为和正常检索不中断）

## Blocked by

- #001: Project scaffold + keyword 检索（需要 models.py, main.py 骨架已存在）
