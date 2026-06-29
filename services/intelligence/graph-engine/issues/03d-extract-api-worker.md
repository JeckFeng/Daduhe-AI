# Issue 3d: Extract API + 异步 Worker + 幂等

## Parent

PRD: graph-engine 知识图谱实体关系抽取与查询 — Issue 3: 实体关系抽取

## What to build

实现 `POST /api/v1/graph/extract` 端点和后台异步抽取 Worker，打通从 HT 回调到抽取完成的全链路。

1. **POST /api/v1/graph/extract**：
   - 接收 `{"doc_id": "seed-doc-001"}`（未来 HT 回调会额外带 event_id、trace_id，但当前阶段仅需 doc_id）
   - 幂等检查：查 PG `graph_engine.extraction_tasks` 表
     - 若已有 pending/processing 任务 → 返回 HTTP 409 `{"code": 5003, "message": "graph extraction failed: already in progress for doc_id=..."}`
     - 若已有 completed 任务 → 返回 HTTP 200 `{"code": 0, "message": "already done", "data": {"task_id": "...", "status": "completed"}}`
     - 首次请求 → 插入新任务（status=pending），返回 HTTP 202 `{"code": 0, "message": "accepted", "data": {"task_id": "g-task-xxx", "status": "processing"}}`
   - 启动后台异步任务（asyncio.create_task 或 FastAPI BackgroundTasks）

2. **后台异步 Worker**：
   - 从 PG `metadata.chunks` 读取该 doc_id 的全部 chunk（用 Issue 1 中定义的 ChunkReader 接口，当前用 PgChunkReader 直读 PG）
   - 用 Issue 3b 的抽取函数逐 chunk 抽取实体关系
   - 用 Issue 3c 的 Gleaning + 合并去重 + 写入 Memgraph
   - 更新 PG 任务表：status 流转 pending → processing → completed/failed
   - 失败时记录 `error_message`，标记 status=failed
   - 更新 progress JSONB（completed_chunks / total_chunks、current_phase）

3. **错误处理**：
   - LLM 调用失败 → task 标记 failed，记录具体错误信息
   - PG 读 chunk 失败 → task 标记 failed
   - Memgraph 写入失败 → task 标记 failed
   - 所有异常不得导致服务崩溃

4. **数据库连接管理**：
   - PG 连接通过连接池管理（psycopg2 连接池或 asyncpg pool）
   - Memgraph 连接由 MemgraphStorage 管理（neo4j AsyncGraphDatabase driver 自带连接池）

## Acceptance criteria

- [ ] `POST /api/v1/graph/extract` with `{"doc_id": "seed-doc-001"}` → 202 + task_id
- [ ] 同一 doc_id 再次请求（抽取进行中）→ 409
- [ ] 抽取完成后同一 doc_id 再次请求 → 200 "already done"
- [ ] 抽取完成后查询 PG `extraction_tasks` 表：status=completed，result 含实体/关系数量
- [ ] 使用不存在的 doc_id → task 标记 failed（PG 中无对应 chunk）
- [ ] 抽取过程中 progress JSONB 显示当前进度（如 `{"completed": 3, "total": 10, "phase": "extraction"}`）
- [ ] end-to-end：用 seed-doc-001（10 chunks）触发抽取 → Memgraph 中有对应节点和关系 → 数量和类型合理（不要求精确数量，取决于 LLM）
- [ ] 抽取日志含 trace_id、doc_id、chunk 数量、LLM 调用次数、耗时

## Blocked by

- Issue 1（项目脚手架与配置基础设施）
- Issue 3c（Gleaning + 合并去重 + Memgraph 写入）

## 开发规则

1. 只能使用 uv 虚拟环境（`cd services/intelligence && uv sync`），不要使用系统 python 虚拟环境
2. 开发中遇到的 BUG 都必须写入 `services/intelligence/memory/troubleshooting.md` 文档
