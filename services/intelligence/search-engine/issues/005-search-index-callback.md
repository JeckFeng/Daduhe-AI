# Issue 5: POST /api/v1/search/index

## Parent

PRD: search-engine 多模式检索引擎

## What to build

实现 ICD-03 §5.1 定义的 `POST /api/v1/search/index` 接口。接收 HT（doc-parser）完成文档处理后的异步回调通知，从 `metadata.chunks` 表读取该文档的所有 chunk，生成 embedding 后写入 Milvus，使新文档可检索。

**数据流**：
```
HT POST /api/v1/search/index {doc_id, title, ...}
  → 从 PG metadata.chunks 读取该 doc_id 的所有 chunk
  → Ollama embed 每个 chunk_text 生成 1024-dim 向量
  → 写入 Milvus (collection 名称从 settings 配置)
  → 返回 202 {task_id, status:"processing"}
```

**幂等策略**：写入前先检查 Milvus 中是否已有该 `doc_id` 的数据（`query(filter='doc_id == "..."')`），有则先删除再插入（update = delete + insert）。

**main.py**：在已有的 `search_index` stub 基础上，替换为完整实现。

## Acceptance criteria

- [ ] `POST /api/v1/search/index -d '{"doc_id":"seed-doc-001","title":"测试"}'` 返回 202 含 `task_id`
- [ ] 调用后，Milvus 中 `seed-doc-001` 的 chunk 向量存在且可被检索
- [ ] 相同 `doc_id` 重复调用不会产生重复数据（旧数据被删除后重新插入）
- [ ] 不存在的 `doc_id` 返回明确的错误信息
- [ ] trace_id 正确记录在响应和日志中
- [ ] 集成测试通过（用种子数据的 doc_id 验证完整链路）
- [ ] 不需要 HT 服务运行即可测试（直接从 PG 读 chunk）

## Blocked by

- #001: Project scaffold + keyword 检索（需要 models.py, settings.py, main.py 骨架已存在）
