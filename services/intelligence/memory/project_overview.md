# 工程概览

## 项目背景

**大渡河水工建筑物缺陷智能诊疗系统** — 课题二「水工缺陷治理知识萃取技术研究及知识库建立」。

采用微服务架构，分三个层级、五个服务，由三位开发者（HT / LSL / FXL）并行开发。

## 架构总览

```
文档上传 → doc-parser(HT/Java) → 产出 chunk + embedding + 元数据
                │
                │ HTTP POST callback (异步通知)
                ▼
        rule-extractor(LSL/TS) ──→ 规则库
                │                      │
                ▼                      ▼
        search-engine(FXL/Python) ←───┘
                │
                ▼
        agent-reasoning(FXL/Python) ←── graph-engine(FXL/Python) → Memgraph
                │
                ▼
        用户问答 (POST /api/v1/chat)
```

## 服务清单

| 服务 | 负责人 | 语言 | 端口 | 状态 |
|------|--------|------|------|------|
| doc-parser | HT | Java 21 / Spring Boot | 8080 | 待开发 |
| rule-extractor | LSL | TypeScript / Express | 3000 | 待开发 |
| graph-engine | FXL | Python / FastAPI | 8001 | stub（HANDOFF 已就绪，待新同事接手） |
| **search-engine** | **FXL** | **Python / FastAPI** | **8002** | **已完成** |
| **agent-reasoning** | **FXL** | **Python / FastAPI** | **8003** | **Phase A 完成（44 集成测试通过）** |

## 基础设施

| 组件 | 端口 | 用途 |
|------|------|------|
| PostgreSQL + pgvector | 5432 (远程 5434 via SSH) | metadata 四层存储 + pg_trgm 模糊检索 |
| Milvus | 19530 | 向量存储与 COSINE 相似度检索 |
| Ollama | 11434 | bge-m3 embedding 模型（1024-dim） |
| MinIO | 9000 | 文档对象存储 |
| Memgraph | 17687 (Bolt) / 17444 (HTTP/Lab) | 知识图谱（graph-engine 使用） |
| etcd | 2379 | Milvus 依赖 |

## search-engine 检索模式

| 模式 | 技术栈 | 延迟 | P@K | 适用场景 |
|------|--------|------|-----|---------|
| keyword | PG ILIKE + hit_count 排序 | ~45ms | 0.75 | 精确关键词查找（2-3 字） |
| fuzzy | pg_trgm similarity() | ~47ms | 0.92 | 错别字容错，多字查询 |
| vector | Ollama bge-m3 → Milvus COSINE → PG 补全 | ~143ms | 0.68 | 自然语言语义检索 |
| hybrid | RRF 融合（当前 = vector only） | ~145ms | 0.68 | 多路融合检索（后期扩展） |

## 关键代码位置

```
services/intelligence/
├── common/daduhe_common/         # 共享库（tracing, logging, health）
├── search-engine/                # 已完成
│   ├── src/
│   │   ├── main.py               # FastAPI app, POST /api/v1/search + /search/index
│   │   ├── models.py             # Pydantic 数据模型
│   │   ├── settings.py           # 环境变量配置 (SEARCH_)
│   │   └── backends/{keyword,fuzzy,vector,hybrid}.py
│   ├── tests/test_search.py      # 22 个集成测试
│   └── tests/eval_search.py      # 检索效果评测
├── agent-reasoning/              # Phase A 完成
│   ├── src/
│   │   ├── main.py               # FastAPI app, POST /api/v1/chat + /llm/completion
│   │   ├── models.py             # ChatRequest/Response, LLMCompletion 等
│   │   ├── settings.py           # 环境变量配置 (AGENT_)
│   │   ├── graph/                # LangGraph 6 节点（supervisor, context_resolution, call_tools, fusion, generator, citation）
│   │   ├── llm/                  # LLMClient + prompts
│   │   ├── tools/                # ToolRegistry + vector_search
│   │   └── store/                # InMemoryConversationStore
│   ├── tests/test_full_integration.py  # 44 个全链路集成测试
│   └── tests/integration_test_report.md
├── graph-engine/                 # stub, 待新同事接手
│   ├── src/main.py               # 3 个 stub 端点（extract/query/reasoning）
│   └── HANDOFF.md                # ★ 工作交接文档（必读）
├── memory/
│   ├── process.md                # ★ 项目历程 + 未完成功能清单
│   ├── project_overview.md       # ★ 本文档
│   └── troubleshooting.md        # ★ 已知问题知识库
└── scripts/
    └── seed_data.py              # 种子数据持久化
```

## 数据模型（metadata schema, PG）

```
metadata.documents           — 文档主表
    doc_id, title, doc_type, ...

metadata.chunks               — 文档分块
    chunk_id, doc_id, chunk_text, chunk_index,
    page_number, section_number, section_title, ...
```

## 代码约定

- **ID 前缀**：种子数据 `seed-`，生产数据 UUID
- **环境变量前缀**：`SEARCH_`（search-engine），`AGENT_`（agent-reasoning 建议）
- **配置管理**：pydantic-settings BaseSettings
- **错误码**：段号 × 1000 + 序号（0=成功，1xxx=参数，3xxx=资源，4xxx=上游，9xxx=内部）
- **链路追踪**：X-Trace-Id header 透传
- **日志**：JSON 结构化，`daduhe_common.info()` / `.error()`
- **测试**：集成测试，连接真实 PG/Milvus/Ollama，不 mock

## 开发环境

```bash
# 启动全部基础设施
docker compose up -d

# SSH 隧道连接远程 PG
ssh -L 5434:localhost:5432 gyyknowledge@10.222.124.211

# search-engine 启动
cd services/intelligence
uv run uvicorn src.main:app --reload --port 8002 --app-dir search-engine

# 种子数据
uv run python scripts/seed_data.py

# 运行测试
uv run pytest tests/test_search.py -v

# 检索评测
uv run python tests/eval_search.py
```

## 文档索引

| 文档 | 位置 | 内容 |
|------|------|------|
| CLAUDE.md | 项目根目录 | 架构、命令、约定 |
| README.md | 项目根目录 | 基础设施配置、种子数据约定 |
| ICD-01 | `docs/ICD-01-HT-文档解析与数据输入.md` | HT 服务接口 |
| ICD-02 | `docs/ICD-02-LSL-知识抽取层.md` | LSL 服务接口 |
| ICD-03 | `docs/ICD-03-FXL-知识图谱检索Agent.md` | FXL 三服务接口 |
| PRD | `search-engine/PRD.md` | search-engine 设计 |
| HANDOFF (graph-engine) | `graph-engine/HANDOFF.md` | **graph-engine 工作交接（新同事必读）** |
| HANDOFF (agent-reasoning) | `agent-reasoning/tests/integration_test_report.md` | agent-reasoning 集成测试报告 |
| Memory | `memory/process.md` | 项目历程 + 未完成功能清单 |
| Memory | `memory/troubleshooting.md` | 已知问题知识库（10 个 ISSUE） |
