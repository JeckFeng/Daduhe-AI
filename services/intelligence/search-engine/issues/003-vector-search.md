# Issue 3: Vector 检索

## Parent

PRD: search-engine 多模式检索引擎

## What to build

实现 vector 语义向量检索模式。将用户查询通过 Ollama bge-m3 向量化（1024-dim），在 Milvus 中按 COSINE 相似度检索 top-k 最近向量，再用 PG 的 chunk_id 批量补全元数据。完成后 `mode=vector` 可独立使用。

**backends/vector.py**：函数 `search_vector(milvus_client, ollama_url, pg_conn, query, filters, top_k, collection_name) -> list[ChunkResult]`。流程：
1. `httpx.post(ollama_url + "/api/embeddings", json={"model":"bge-m3","prompt":query})` 获取 query vector
2. `milvus_client.search(collection_name, data=[query_vector], limit=top_k, output_fields=["chunk_id","doc_id"])` 获取相似向量
3. 用返回的 `chunk_id` 列表去 PG `metadata.chunks JOIN metadata.documents WHERE chunk_id = ANY(%s)` 批量补元数据
4. 保持 Milvus 返回的 COSINE 分数，按分数降序

filter 支持：如果 filters 中有 `doc_type` 或 `doc_ids`，在 PG 查询阶段用 WHERE 过滤。

**main.py**：在 route handler 中增加 `mode=vector` 分支。

## Acceptance criteria

- [ ] `POST /api/v1/search -d '{"query":"裂缝宽度大于0.3mm时需要采取什么处理措施？","mode":"vector"}'` 返回语义相关的 chunk 结果，`mode_used="vector"`
- [ ] 结果中第一条的 chunk_text 应包含裂缝处理相关内容（验证语义检索正确性）
- [ ] 每条结果包含完整 metadata（与 keyword 结果字段一致）
- [ ] score 字段反映 COSINE 相似度（0-1 范围）
- [ ] top_k 限制返回条数生效
- [ ] filters.doc_ids 过滤在 PG 端生效
- [ ] Milvus collection 名称可从 `settings.milvus_collection` 配置
- [ ] Milvus 连接失败时返回有意义的错误
- [ ] 集成测试通过（连接真实 Milvus + Ollama + PG）

## Blocked by

- #001: Project scaffold + keyword 检索（需要 models.py, settings.py, main.py 骨架已存在）
