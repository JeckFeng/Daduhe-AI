# HANDOFF — graph-engine 工作交接

欢迎！本文档帮助你快速接手 graph-engine 的开发。

---

## 1. 这是什么项目？

**大渡河水工建筑物缺陷智能诊疗系统** — 课题二「水工缺陷治理知识萃取技术研究及知识库建立」。

用 AI 帮助水电站运维人员诊断大坝、泄水建筑物的结构缺陷。用户上传规范文档 → 系统自动解析、抽取规则、构建知识图谱 → 最终用户用自然语言提问（"混凝土坝裂缝宽度超过多少需要处理？"），系统自动检索并生成带引用的专业答案。

微服务架构，三个层级、五个服务，三位开发者并行开发：

```
HT(Java)                LSL(TypeScript)           FXL(Python) ← 你所在团队
───────                 ──────────────            ──────────────────────────
doc-parser              rule-extractor            graph-engine   ← 你要开发的
  8080                     3000                      8001
                                                  search-engine (已完成) 8002
                                                  agent-reasoning (已完成) 8003
```

**你的服务 — graph-engine (port 8001)**：负责从文档 chunk 中抽取实体和关系，写入 Memgraph 知识图谱，提供 Cypher 查询和推理接口。同时作为 agent-reasoning 的上游，为最终问答提供知识图谱维度的检索结果。

---

## 2. 已经做了哪些？

### search-engine (port 8002) — 已完成

多模式检索引擎，4 种检索模式（keyword/fuzzy/vector/hybrid），22 个集成测试通过，已经过检索效果评测。

### agent-reasoning (port 8003) — Phase A 完成

完整的 LangGraph RAG 编排服务：
- 查询意图分类（4 类：chitchat / spec_lookup / knowledge_qa / comparison）
- 问题拆解（复合问题自动拆分 2-3 个子问题）
- 多轮对话记忆 + 指代消解（"之前那本规范" → "DL/T 2628-2023"）
- LLM 调用工厂（`POST /api/v1/llm/completion`）—— **这个接口是你的 graph-engine 做实体关系抽取时要调用的**
- 44 项全链路集成测试 100% 通过

### graph-engine (port 8001) — 当前只有 stub

目前只有 3 个返回 TODO/mock 数据的端点骨架（`services/intelligence/graph-engine/src/main.py`）：

| 端点 | 状态 | 用途 |
|------|------|------|
| `POST /api/v1/graph/extract` | stub — 返回硬编码 202 | HT 回调触发实体关系抽取 |
| `POST /api/v1/graph/query` | stub — 返回空 nodes/edges | 知识图谱查询（供 agent-reasoning 调用） |
| `POST /api/v1/graph/reasoning` | stub — 返回空 paths | 知识图谱多跳推理（供 agent-reasoning 调用） |
| `GET /metrics` | placeholder | Prometheus 指标 |

---

## 3. 还有什么没做？（你的工作）

你需要实现 graph-engine 的全部业务逻辑，核心工作分以下阶段：

### Phase A — 核心链路（Priority: P0）

**Issue 1: 实体关系抽取**
- 实现 `POST /api/v1/graph/extract`
- 收到 HT 回调（含 doc_id）后 → 从 PG 的 `metadata.chunks` 读该文档全部 chunk
- 调用 agent-reasoning 的 `POST /api/v1/llm/completion` 做 LLM 实体关系抽取
- 设计 entity/relation schema（建议实体类型: DefectType, Structure, NormClause, Treatment, DetectionMethod, InspectionType, Parameter 等；关系类型: regulated_by, treated_by, detected_by, has_threshold, references 等）
- 将抽取结果写入 Memgraph
- 幂等处理：同一 doc_id 重复通知时更新而非重复创建

**Issue 2: 知识图谱查询**
- 实现 `POST /api/v1/graph/query`
- 支持 ICD-03 §4.2 定义的 4 种 query_type：`related_norms`、`related_treatments`、`related_cases`、`entity_detail`
- 将 query_type + params 翻译为 Cypher 查询，返回 nodes + edges

**Issue 3: 知识图谱推理**
- 实现 `POST /api/v1/graph/reasoning`
- 从指定实体出发做多跳路径探索（depth ≤ 3），返回 paths 数组

**Issue 4: 全链路集成**
- 端到端验证：HT 回调 → extract → Memgraph 写入 → query/reasoning 返回正确
- 编写集成测试（使用 TestClient + 真实 Memgraph + 真实 LLM）
- agent-reasoning 后续会调用你的 `/graph/query` 和 `/graph/reasoning` 作为多源检索的一部分

### Phase B — 优化增强

- LLM 抽取质量优化（few-shot prompt 工程、schema 约束）
- Memgraph 索引优化（支持 label+property 索引和 label 索引，不支持 composite index）
- 大规模文档的批量抽取 + 并发控制

### 待确认

- Memgraph 连接信息：`bolt://localhost:17687`（通过 SSH 隧道 `ssh -L 17687:localhost:17687 gyyknowledge@10.222.124.211`），默认无需认证（用户名/密码均为空字符串），数据库名使用 `"memgraph"`
- HT 回调的真实 payload 格式参见 ICD-03 §5.1
- LLM 抽取调用 agent-reasoning 的 `/llm/completion`，caller 填 `"graph-engine"`, priority 用 `"batch"`（离线任务 120s 超时）

---

## 4. 必须阅读的文档（按优先级排序）

| # | 文档 | 位置 | 说明 |
|---|------|------|------|
| 1 | **process.md** | `services/intelligence/memory/process.md` | 项目历程、当前状态、下一步计划、未完成功能清单 |
| 2 | **project_overview.md** | `services/intelligence/memory/project_overview.md` | 架构总览、服务清单、基础设施、数据模型、代码约定 |
| 3 | **troubleshooting.md** | `services/intelligence/memory/troubleshooting.md` | 已知问题知识库（10 个 ISSUE + 常见修复方案），开发时遇到问题先查这里 |
| 4 | **ICD-03** | `docs/ICD-03-FXL-知识图谱检索Agent.md` | 你的服务接口定义（§4: graph-engine 三个端点、§6: agent-reasoning 的 llm/completion、§8: 错误码） |
| 5 | **CLAUDE.md** | 项目根目录 | 整体架构、基础设施凭据、开发命令、跨服务约定（X-Trace-Id、错误码、日志规范） |
| 6 | **ICD-01** | `docs/ICD-01-HT-文档解析与数据输入.md` | HT 服务接口定义（你需要消费的 chunk API + 回调 payload 格式） |

---

## 5. 开发规范

### 技术栈
- Python 3.11 + FastAPI
- 使用 **uv** 管理依赖和虚拟环境（工作区根目录 `services/intelligence/`）
- `pyproject.toml` 已有基础依赖：`daduhe-common`, `httpx`, `neo4j>=5.20.0`（Memgraph 兼容 Bolt 协议，可直接使用 neo4j 驱动）, `psycopg2-binary`
- 如需新增依赖：`uv add <package>`，会自动更新 pyproject.toml

### 启动命令

```bash
cd services/intelligence/graph-engine

# 同步依赖（首次或依赖变更后）
uv sync

# 开发运行
AGENT_LLM_URL="http://localhost:8003" \
uv run uvicorn src.main:app --reload --port 8001
```

### 必须遵守的约定

1. **链路追踪**：所有 HTTP 调用（调用 agent-reasoning 时）必须透传 `X-Trace-Id` header
2. **错误码**：遵循 ICD-03 §8（段号×1000+序号），0=成功，1xxx=参数，4xxx=上游失败，5xxx=业务，9xxx=内部
3. **响应格式**：统一 `{"code": N, "message": "...", "trace_id": "...", "data": {...}}`
4. **日志**：使用 `daduhe_common` 的 `info()`/`error()`/`warn()`，输出 JSON 结构化日志到 stderr
5. **配置**：环境变量前缀建议 `GRAPH_`，通过 pydantic-settings BaseSettings 管理
6. **健康检查**：`GET /health` (liveness) + `GET /ready` (readiness, 含 Memgraph 连接状态，使用 `SHOW DATABASES` 或 `MATCH (n) RETURN count(n) LIMIT 1` 探测)
7. **幂等**：`/graph/extract` 对同一 doc_id 重复调用必须幂等
8. **LLM 调用**：必须走 agent-reasoning 的 `POST /api/v1/llm/completion`，不要直连 DeepSeek API 或 vLLM
9. **测试**：集成测试风格（参考 `search-engine/tests/` 和 `agent-reasoning/tests/`），连接真实 Memgraph 和真实 LLM

### 关键参考代码

| 参考什么 | 路径 | 用途 |
|---------|------|------|
| search-engine settings | `search-engine/src/settings.py` | pydantic-settings 写法模板 |
| search-engine models | `search-engine/src/models.py` | Pydantic 数据模型模板 |
| agent-reasoning LLM client | `agent-reasoning/src/llm/client.py` | LLMClient 写法（你可能需要类似的封装调 /llm/completion） |
| agent-reasoning conftest | `agent-reasoning/tests/conftest.py` | pytest async fixture + DI 模式 |
| agent-reasoning 集成测试 | `agent-reasoning/tests/test_full_integration.py` | TestClient 集成测试写法 |

### Agent Skill（Claude Code 开发辅助命令）

本项目的 Claude Code 配置了以下 skill，开发时可以直接调用：

- `/tdd` — TDD 开发流程：先写测试，再写实现，逐测试通过。**强烈建议使用**
- `/to-issues` — 将 PRD/需求拆分为可独立开发的 issue 文件
- `/to-prd` — 将讨论整理为 PRD 文档
- `/grill-with-docs` — 追问需求细节直到完全理解

---

## 6. 故障排查

开发过程中遇到问题时：

1. **先查 `troubleshooting.md`**（`services/intelligence/memory/troubleshooting.md`）— 这里有 10 个已知 ISSUE 的完整分析和修复方案，涵盖 Milvus、PostgreSQL、pytest async、httpx 生命周期等
2. 如果是新问题，按 troubleshooting.md 的格式记录（症状 → 根因 → 方案 → 验证），添加到 ISSUE 列表中
3. 常见坑：
   - Milvus: insert 后数据不可见 → `release_collection()` + `load_collection()`
   - pg_trgm: 2 字中文查询无效（pg_trgm 固有局限），短查询走 ILIKE
   - pytest: `async def` 测试需要在模块顶加 `pytestmark = pytest.mark.anyio`
   - httpx: 在测试中不要自己创建 `AsyncClient`，通过 pytest fixture DI 注入以控制生命周期
   - Memgraph: 注意事务管理和连接池配置；Memgraph 使用 `database_="memgraph"` 作为默认数据库名

---

## 7. 当前数据库内容

PostgreSQL `metadata` schema 中有 2 份规范文档，共 15 个 chunks，这是你开发抽取逻辑时可以直接用的测试数据：

| 文档 | chunks | 内容 |
|------|--------|------|
| DL/T 2628-2023 水电站水工建筑物缺陷管理规范 | 10 | 缺陷分类、裂缝处理、渗漏分级、混凝土检测、碳化评定、金属结构、检查周期、安全监测、档案管理 |
| DL/T 2700-2023 水电站泄水建筑物水力安全评价导则 | 5 | 安全评价总则、泄洪能力复核、消能设施评价、冲刷评价标准、维护要求 |

你可以用这 15 个 chunk 来设计和验证实体关系抽取的 prompt schema。

---

## 8. 快速检查清单

在开始写代码之前，确认以下项目：

- [ ] 已阅读 process.md、project_overview.md、troubleshooting.md
- [ ] 已阅读 ICD-03 §4（你的接口定义）和 §6.2（你要调用的 LLM 接口）
- [ ] agent-reasoning 的 `/llm/completion` 可调用：`curl -X POST http://localhost:8003/api/v1/llm/completion -H "Content-Type: application/json" -d '{"model":"vllm-local","messages":[{"role":"user","content":"你好"}],"caller":"graph-engine-test","priority":"batch"}'`
- [ ] uv 环境就绪：`cd services/intelligence/graph-engine && uv sync`
- [ ] 理解 TDD 流程：一个测试 → 一个实现 → 循环

有任何问题，先查文档，文档里找不到答案再问同事。
