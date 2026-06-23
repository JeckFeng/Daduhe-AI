# PRD: search-engine 多模式检索引擎

## Problem Statement

search-engine（fxl-search-engine, port 8002）是 Daduhe-AI 检索层的核心服务，需要实现 ICD-03 §5 定义的多模式检索能力。目前服务仅有一个返回空结果的 stub，需要从零构建 keyword、fuzzy、vector、hybrid 四种检索模式，并准备好与 LSL（rule-extractor）、HT（doc-parser）的外部集成契约，等协作方开发完成后一行配置即可打通。

## Solution

在 PostgreSQL + Milvus + Ollama 基础设施之上实现完整的检索链路：

- **keyword**：PostgreSQL ILIKE 精确子串匹配，按命中次数排序
- **fuzzy**：pg_trgm 三元组模糊匹配，按相似度降序
- **vector**：Ollama bge-m3 embedding → Milvus IVF_FLAT 语义检索 → PostgreSQL 元数据补全
- **hybrid**：RRF（Reciprocal Rank Fusion）融合框架，当前退化为纯 vector，预留 rules 接入槽位

所有检索结果按 ICD-03 §5.2 定义的 `source_type` 联合类型返回，元数据在 backend 内部通过 SQL JOIN 一次性装配完成。

## User Stories

### 核心检索功能

1. 作为 agent-reasoning 服务，我想要通过 `mode=keyword` 执行精确子串检索，以便在文档 chunk 中找到包含特定关键词的段落
2. 作为 agent-reasoning 服务，我想要通过 `mode=fuzzy` 执行容错模糊匹配，以便在用户输入包含错别字或近义词时仍能召回相关结果
3. 作为 agent-reasoning 服务，我想要通过 `mode=vector` 执行语义向量检索，以便找到与查询语义相关的 chunk（即使关键词不匹配）
4. 作为 agent-reasoning 服务，我想要通过 `mode=hybrid` 执行混合检索，以便获得融合多路召回的最优排序结果
5. 作为 agent-reasoning 服务，我想要通过 `filters.doc_type` 按文档类型过滤结果，以便只检索特定类型的规范文档
6. 作为 agent-reasoning 服务，我想要通过 `filters.doc_ids` 按文档 ID 过滤，以便在特定文档范围内检索
7. 作为 agent-reasoning 服务，我想要检索结果包含完整的溯源元数据（doc_id, title, section_number, page_number, download_url），以便向最终用户展示引用来源

### 可观测性与配置

8. 作为运维人员，我想要通过环境变量配置所有外部依赖（PG DSN、Milvus URI、Ollama URL、RRF k 参数），以便在不同环境灵活部署
9. 作为运维人员，我想要通过 TraceMiddleware 记录每次检索的 trace_id 和结构化日志，以便链路追踪和问题排查

### 异步索引构建

10. 作为 doc-parser（HT）服务，我想要通过 `POST /api/v1/search/index` 回调触发索引构建，以便新文档处理完成后立即可检索
11. 作为 search-engine 运维人员，我想要 `/search/index` 接口支持幂等（相同 doc_id 重复通知时更新而非重复插入），以便应对网络重传

### 外部服务集成

12. 作为后续开发阶段的协作方，我想要 search-engine 已预留 LSL rules 的 HTTP client 接口定义，以便 LSL 服务就绪后直接打通
13. 作为调用方，我想要在 `include_sources` 包含不可用的 `rules` 时收到 400 错误，以便明确知道当前支持的检索范围

## Implementation Decisions

### 架构与模块划分

search-engine 分为以下模块：

- **`models.py`**：Pydantic 数据模型。`SearchRequest`（入参校验）、使用联合类型 + discriminator `source_type` 区分 `ChunkResult` 与 `RuleResult`、`SearchResponse`。ICD-03 §5.2 定义的 chunk metadata（doc_id, doc_type, title, section_number, section_title, page_number, download_url）与 rule metadata（rule_id, title, category, norm_ref, doc_id, section_number）分开建模
- **`settings.py`**：pydantic-settings `BaseSettings`，环境变量前缀 `SEARCH_`，覆盖 PostgreSQL DSN、Milvus URI/credentials/collection_name、Ollama URL、RRF k、LSL base URL 等全部可配置项
- **`backends/keyword.py`**：ILIKE 精确子串匹配。SQL 直接 JOIN `metadata.chunks` + `metadata.documents` 一次查询返回完整 `list[ChunkResult]`，按关键词命中次数降序
- **`backends/fuzzy.py`**：pg_trgm `similarity()` 模糊匹配。SQL JOIN 同样一次装配元数据，按相似度降序
- **`backends/vector.py`**：Ollama embedding（bge-m3, 1024-dim）→ Milvus search（COSINE）→ 按返回的 chunk_id 批量查 PG 补元数据，按 Milvus 相似度降序
- **`backends/hybrid.py`**：RRF 融合，k 可配置。当前 = vector 结果 + 空 slot（rules 接入位），后期加入 keyword/fuzzy/rules 的 rank 列表参与 RRF 计算
- **`clients/lsl.py`**：LSL `GET /api/v1/rules/search` 的 HTTP client 契约定义（请求参数模型 + 响应模型），暂不接线
- **`clients/ht.py`**：HT 回调契约的 Pydantic 模型定义（`SearchIndexRequest`）
- **`main.py`**：FastAPI route handlers，根据 mode dispatch 到对应 backend 函数，handler 不做元数据装配

### 检索模式设计

**keyword**：`WHERE LOWER(chunk_text) LIKE LOWER('%keyword%')`，排序用 `(LENGTH(chunk_text) - LENGTH(REPLACE(LOWER(chunk_text), keyword, ''))) / LENGTH(keyword)` 计算命中次数。

**fuzzy**：`WHERE chunk_text % keyword ORDER BY similarity(chunk_text, keyword) DESC`。依赖 pg_trgm 扩展（`CREATE EXTENSION IF NOT EXISTS pg_trgm` 在 seed_data.py 中安装）。

**vector**：Ollama `/api/embeddings` 获取 query vector → Milvus `search()` 返回 (ids, scores) → PG `SELECT ... FROM metadata.chunks JOIN metadata.documents WHERE chunk_id = ANY(%s)` 批量补元数据，按 score 降序。

**hybrid**：RRF = `Σ 1/(k + rank_i)`，k 可配置（默认 60）。结果列表去重后按 RRF 分数降序返回。当前只有 vector 一路参与排名，预留 `keyword_ranks`、`fuzzy_ranks`、`rules_ranks` 参数位。

### 元数据装配策略

每个 backend 内部负责装配完整结果，遵循 Information Expert（GRASP）原则：

- keyword/fuzzy：PG 查询时直接 JOIN，一次 SQL 完成
- vector：Milvus 返回后，用 `chunk_id IN (...)` 批量查 PG 补全
- handler 不接触 PG schema，只做 dispatch + 返回

### /search/index 设计与幂等

收到 HT 回调后：解析 `doc_id` → 直接从 `metadata.chunks` 表查询该 doc 的 chunks → 生成 embeddings → 写入 Milvus（按 doc_id 分批）。

幂等策略：插入前检查 Milvus collection 中是否已有该 doc_id 的数据（`query(filter='doc_id == "..."')`），有则先删除再插入（update = delete + insert）。

### 外部依赖接口

- LSL client：定义 `RuleSearchRequest`（keyword, category, doc_id, page, page_size）和 `RuleSearchResponse`，不执行实际 HTTP 调用
- `include_sources` 含 `"rules"` 时在 handler 层返回 400，提示 rules 源当前不可用
- `download_url` 通过字符串拼接生成 `/api/v1/documents/{doc_id}/download`，不调用外部服务

### pg_trgm 扩展

在 `seed_data.py` 的 `create_schema()` 中添加 `CREATE EXTENSION IF NOT EXISTS pg_trgm`。pg_trgm 是 PostgreSQL 官方 contrib 模块，免费、无需升级。

### 后续 DM8 迁移

本轮不实现 DM8 兼容。DM8 提供 `CONTEXT INDEX` + `CONTAINS()` + `UTL_MATCH.EDIT_DISTANCE_SIMILARITY()` 作为 pg_trgm 的替代方案，等正式上线时再处理。

## Testing Decisions

### 测试策略

延续 test_seed.py 的集成测试风格——连接真实 PostgreSQL、Milvus、Ollama。所有测试使用隔离的 collection（`seed_chunks_test` 或类似命名），与 CLI 持久化的 `seed_chunks` 互不干扰。

### 好测试标准

- 测试 observable behavior（"keyword 模式能查到包含'裂缝'的 chunk"），不测试实现细节（不 mock PG connection、不验证 SQL 文本）
- 使用 public API（通过 FastAPI TestClient 调 `/api/v1/search`）或 backend 函数的公开接口
- 测试应能承受内部重构（如换 ILIKE 为 ts_vector）而不需要修改

### 测试范围

- **models 验证**：SearchRequest 参数校验（必填字段、枚举值、类型约束）
- **keyword backend**：中文关键词检索、空结果、排序正确性
- **fuzzy backend**：容错匹配（错别字、近似词）、相似度阈值
- **vector backend**：语义检索、top_k 限制、Milvus 无结果时的处理
- **hybrid backend**：RRF 去重、k 参数有效性
- **/search handler**：mode dispatch、filters 过滤、include_sources 含 rules 时 400
- **/search/index handler**：幂等性、PG 读 chunk 正确性、Milvus 写入
- **健康检查**：`/health` 200 且报告 PG + Milvus 状态

### 测试隔离

- 使用独立的 Milvus collection（如 `search_test`），teardown 时删除
- 依赖 fixture 注入 PG connection、MilvusClient、Ollama URL

## Out of Scope

- DM8 数据库兼容或回退
- LSL rules 的实际 HTTP 调用与数据融合
- HT doc-parser 的 HTTP client 实现
- MinIO 预签名 URL 的实际生成
- 多语言支持（当前仅中文场景）
- 索引的增量更新（仅全量重建）
- 检索结果的缓存
- 检索性能基准测试

## Further Notes

- ICD-03 规定的四种 mode 是互斥的单次请求模式，`mode_used` 为单数。hybrid 内部的多路召回对调用方透明
- `source_type` 字段用于区分 chunk 和 rule 结果，客户端按此字段解析不同的 metadata 结构，不再需要 search-engine 做 schema 归一化
- 种子数据通过 `uv run python scripts/seed_data.py` 持久化到服务器 PostgreSQL + Milvus，供开发和测试共用
- Ollama embedding 超时参考值 30s（与 ICD 中的 realtime LLM 调用一致），实际 bge-m3 单次约 200ms
