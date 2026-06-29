# Issue 5: 全链路集成验证

## Parent

PRD: graph-engine 知识图谱实体关系抽取与查询 — Issue 3: 全链路集成

## What to build

编写全链路集成测试，端到端验证抽取 → 写入 → 查询的完整链路，并完善健康检查和 metrics 端点。

1. **抽取集成测试**：
   - 使用种子数据 seed-doc-001（10 chunks）触发 `POST /extract`
   - 轮询 PG 任务表直到 status=completed（最多等待 120s）
   - 验证 Memgraph 中写入的节点数量 > 0
   - 验证 Memgraph 中写入的关系数量 > 0
   - 验证节点包含所有 8 个属性字段
   - 验证至少存在 REGULATED_BY、TREATED_BY 类型的关系
   - 验证溯源字段（page_numbers、section_titles）不为空

2. **查询集成测试**：
   - 4 种 query_type 各至少 1 个测试用例
   - 验证返回结构符合 ICD-03 §4.2 格式
   - 验证 `related_norms` 返回的 NormClause 节点包含规范编号

3. **幂等集成测试**：
   - 重复调用 `POST /extract` 同一 doc_id → 验证幂等行为（409 或 200 "already done"）

4. **健康检查测试**：
   - `/health` → 200
   - `/ready` → 200 且 checks 含 memgraph 状态

5. **完善 `/metrics` 端点**：
   - 实现 `daduh_graph_extraction_duration_s` Histogram（抽取耗时）
   - 实现 `daduh_http_requests_total` Counter

### 测试原则

- 集成测试连接真实 Memgraph + 真实 LLM（通过 agent-reasoning）
- 不 mock 任何外部依赖
- 真实 LLM 的随机性通过断言关键词集合而非精确匹配来吸收（例如：验证 entity_type 属于 12 种类型之一，而非等于某个精确字符串）
- 使用 pytest + pytest-asyncio + httpx TestClient
- 测试需支持通过环境变量跳过（如 `GRAPH_SKIP_INTEGRATION_TESTS=1`），适应没有 LLM/Memgraph 的环境

### 参考

- `agent-reasoning/tests/test_full_integration.py`（44 项集成测试，使用真实 LLM + 真实 search-engine）
- `agent-reasoning/tests/conftest.py`（pytest async fixture + DI 模式）
- `search-engine/tests/test_search.py`（22 个集成测试，TestClient 写法）

## Acceptance criteria

- [ ] 所有集成测试通过（`uv run pytest tests/ -v`）
- [ ] seed-doc-001 的抽取测试：任务完成 → Memgraph 有节点和关系
- [ ] 4 种 query_type 查询测试：各至少 1 个用例通过
- [ ] 幂等测试通过
- [ ] `/health` 200，`/ready` 含 memgraph 状态
- [ ] `/metrics` 返回的 Prometheus 文本中包含 `daduh_graph_extraction_duration_s` 和 `daduh_http_requests_total`
- [ ] 设置 `GRAPH_SKIP_INTEGRATION_TESTS=1` → 集成测试跳过而非失败

## Blocked by

- Issue 3d（Extract API + 异步 Worker）
- Issue 4（知识图谱查询 API）

## 开发规则

1. 只能使用 uv 虚拟环境（`cd services/intelligence && uv sync`），不要使用系统 python 虚拟环境
2. 开发中遇到的 BUG 都必须写入 `services/intelligence/memory/troubleshooting.md` 文档
