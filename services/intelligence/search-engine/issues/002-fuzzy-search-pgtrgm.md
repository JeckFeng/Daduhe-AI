# Issue 2: Fuzzy 检索 + pg_trgm

## Parent

PRD: search-engine 多模式检索引擎

## What to build

实现 fuzzy 检索模式，基于 pg_trgm 三元组模糊匹配。用户输入包含错别字或近义词时也能召回相关 chunk。完成后 `mode=fuzzy` 可独立使用。

**pg_trgm 扩展安装**：在 `scripts/seed_data.py` 的 `create_schema()` 中添加 `CREATE EXTENSION IF NOT EXISTS pg_trgm`。

**backends/fuzzy.py**：函数 `search_fuzzy(conn, query, filters, top_k) -> list[ChunkResult]`。使用 `similarity(chunk_text, query)` 函数，`WHERE chunk_text % query`（% 是 pg_trgm 的相似度操作符）。SQL JOIN 一次装配完整元数据，按相似度降序。支持 filters。

**main.py**：在 route handler 中增加 `mode=fuzzy` 分支，dispatch 到 `search_fuzzy()`。

## Acceptance criteria

- [ ] `CREATE EXTENSION IF NOT EXISTS pg_trgm` 在 seed_data.py 中执行成功
- [ ] `POST /api/v1/search -d '{"query":"裂缝","mode":"fuzzy"}'` 返回结果，`mode_used="fuzzy"`
- [ ] 输入包含错别字的查询（如 "裂逢"）仍能召回包含 "裂缝" 的 chunk
- [ ] 输入近似词（如 "渗水"）能召回 "渗漏" 相关的 chunk
- [ ] 结果按 `similarity()` 分数降序，score 字段反映相似度
- [ ] top_k 和 filters 生效
- [ ] 集成测试通过（连接真实 PG）

## Blocked by

- #001: Project scaffold + keyword 检索（需要 models.py, settings.py, main.py 骨架已存在）
