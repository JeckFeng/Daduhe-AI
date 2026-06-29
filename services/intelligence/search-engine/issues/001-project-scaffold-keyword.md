# Issue 1: Project scaffold + keyword 检索

## Parent

PRD: search-engine 多模式检索引擎

## What to build

建立 search-engine 的工程骨架并实现 keyword 检索模式的完整端到端链路。这是第一个 tracer bullet——完成后可以通过 `POST /api/v1/search` 以 `mode=keyword` 执行精确子串匹配，返回真实的 PostgreSQL 种子数据结果。

**目录结构**（在 `src/` 下展开）：
```
src/
├── main.py           # FastAPI app + route handlers (在已有骨架基础上扩展)
├── models.py         # Pydantic 数据模型
├── settings.py       # pydantic-settings 配置
├── backends/
│   ├── __init__.py
│   └── keyword.py    # ILIKE 检索 + PG JOIN 元数据装配
└── clients/
    └── __init__.py
```

**models.py**：`SearchRequest`（query, mode, top_k, filters, include_sources）、`ChunkResult`（chunk_id, text, score, source_type, metadata）、`RuleResult`（rule_id, text, score, source_type, metadata）、`SearchResponse`（results, total_hits, mode_used）。使用 Pydantic 联合类型 + `discriminator="source_type"` 区分 chunk 和 rule 结果。`mode` 字段校验枚举值。

**settings.py**：`pydantic-settings` BaseSettings，前缀 `SEARCH_`。覆盖：`pg_dsn`、`milvus_uri`/`milvus_user`/`milvus_password`/`milvus_db`/`milvus_collection`、`ollama_url`、`rrf_k`、`lsl_base_url`。全部有开发环境默认值。

**backends/keyword.py**：单一函数 `search_keyword(conn, query, filters, top_k) -> list[ChunkResult]`。SQL 用 ILIKE + JOIN `metadata.chunks` + `metadata.documents` 一次查询返回完整元数据（chunk_id, chunk_text, doc_id, doc_type, title, section_number, section_title, page_number, download_url 拼接）。按关键词命中次数降序。WHERE 条件支持 filters（doc_type, doc_ids）。

**main.py**：根据 `mode` dispatch，先实现 `keyword` 分支。handler 不做元数据装配。

**依赖添加**：`pydantic-settings` 加入 `pyproject.toml` 和 `requirements.txt`（如果用到）。

## Acceptance criteria

- [ ] `POST /api/v1/search -d '{"query":"裂缝","mode":"keyword"}'` 返回 `source_type="chunk"` 的结果列表，`mode_used="keyword"`
- [ ] 结果按关键词命中次数降序排列
- [ ] 每条结果包含完整 metadata：`doc_id`, `doc_type`, `title`, `section_number`, `section_title`, `page_number`, `download_url`
- [ ] `top_k` 限制返回条数生效
- [ ] `filters.doc_type` 过滤生效（如 `["规范"]` 只返回规范类型文档的 chunk）
- [ ] `filters.doc_ids` 过滤生效
- [ ] 环境变量 `SEARCH_*` 可覆盖所有配置项，未设置时使用默认值
- [ ] `GET /health` 返回 200
- [ ] `GET /ready` 包含 PG 连接状态
- [ ] 集成测试通过（连接真实 PG，keyword 检索 seed 数据）

## Blocked by

None — can start immediately.
