# Issue 4: Hybrid 检索 (RRF)

## Parent

PRD: search-engine 多模式检索引擎

## What to build

实现 hybrid 混合检索模式，使用 RRF（Reciprocal Rank Fusion）融合多路召回结果。当前阶段 hybrid = vector 结果 + 空 rules slot，后续 LSL 就绪后直接将 rules 结果喂入 RRF 框架。

**backends/hybrid.py**：函数 `search_hybrid(milvus_client, ollama_url, pg_conn, query, filters, top_k, rrf_k, collection_name) -> list[ChunkResult]`。内部：
1. 调用 vector backend 获取向量检索结果
2. 预留 `keyword_ranks`、`fuzzy_ranks`、`rules_results` 参数位（当前为空）
3. RRF 计算：`score = Σ 1/(rrf_k + rank_i)`，对所有参与源的结果按 chunk_id 去重后计算
4. 按 RRF 分数降序返回 top_k

当只有 vector 参与时，RRF 退化为纯 vector 排序（所有结果 rank 相同分母，保持原始顺序）。

**main.py**：增加 `mode=hybrid` 分支，dispatch 到 `search_hybrid()`。

## Acceptance criteria

- [ ] `POST /api/v1/search -d '{"query":"裂缝宽度处理措施","mode":"hybrid"}'` 返回结果，`mode_used="hybrid"`
- [ ] 当前 hybrid 结果与 vector 模式结果一致（仅 vector 参与 RRF 时）
- [ ] `rrf_k` 可通过环境变量 `SEARCH_RRF_K` 配置，默认 60
- [ ] RRF 分数计算正确（单源时保持原始排序）
- [ ] `search_hybrid()` 函数签名明确预留了 `keyword_ranks`、`fuzzy_ranks`、`rules_results` 可选参数
- [ ] 集成测试通过

## Blocked by

- #003: Vector 检索（hybrid 内部调用 vector backend）
