# Issue 1: 项目脚手架与配置基础设施

## Parent

PRD: graph-engine 知识图谱实体关系抽取与查询

## What to build

搭建 graph-engine 的项目基础设施，使后续 issue 有一个可运⾏的开发骨架。

- 使用 pydantic-settings BaseSettings 管理所有配置，环境变量前缀 `GRAPH_`
- 定义 Pydantic 数据模型：ExtractionTaskRequest/Response，GraphQueryRequest/Response，ExtractionTask 状态模型，Chunk 数据模型
- 在 PG 中创建 `graph_engine.extraction_tasks` 表和 `graph_engine.llm_cache` 表（幂等：已存在则跳过）
- FastAPI app 骨架：TraceMiddleware、`/health`、`/ready`（含 Memgraph 连接探测）、`/metrics`（placeholder）
- 配置项需覆盖 PRD §16 列出的所有变量（Memgraph 连接信息、PG 连接信息、agent-reasoning URL、gleaning 轮数、prompt profile 路径等）
- 健康检查的 `/ready` 端点需检测 Memgraph 连接状态（使用 `MATCH (n) RETURN count(n) LIMIT 1` 探测）

## Acceptance criteria

- [ ] `uv sync` 成功安装所有依赖（daduhe-common、neo4j>=5.20.0、psycopg2-binary、httpx、pydantic-settings、pyyaml）
- [ ] `GRAPH_MEMGRAPH_URI`、`GRAPH_PG_HOST` 等环境变量正确加载为 pydantic Settings 对象
- [ ] 访问 `GET /health` 返回 `{"status": "ok"}` (200)
- [ ] 访问 `GET /ready` 返回 readiness 状态，checks 中包含 `memgraph` 状态
- [ ] 访问 `GET /metrics` 返回 Prometheus 格式（placeholder 即可）
- [ ] `graph_engine.extraction_tasks` 和 `graph_engine.llm_cache` 表在 PG 中创建成功
- [ ] `uv run uvicorn src.main:app --port 8001` 能成功启动

## Blocked by

None — 可立即开始。

## 开发规则

1. 只能使用 uv 虚拟环境（`cd services/intelligence && uv sync`），不要使用系统 python 虚拟环境
2. 开发中遇到的 BUG 都必须写入 `services/intelligence/memory/troubleshooting.md` 文档
