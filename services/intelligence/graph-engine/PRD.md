# PRD: graph-engine — 知识图谱实体关系抽取与查询

## Problem Statement

大渡河水工建筑物缺陷智能诊疗系统需要从规范文档中自动构建知识图谱，支持下游 agent-reasoning 服务进行知识图谱维度的检索与推理。目前 graph-engine 仅有 3 个返回 TODO/mock 数据的 stub 端点，业务逻辑全部缺失。

用户（水电站运维人员）通过 agent-reasoning 的自然语言问答，最终需要得到类似 "混凝土坝裂缝宽度超过 0.3mm 时需要灌浆处理，依据是 DL/T 2628-2023 §5.2.3" 这样带溯源引用的专业回答。graph-engine 负责提供回答中涉及的知识图谱数据。

## Solution

graph-engine 从 PostgreSQL 读取文档 chunk，调用 LLM（通过 llm-gateway 的 `/api/v1/completion`，port 8004）自动抽取实体和关系，写入 Memgraph 知识图谱，并对外提供结构化的 Cypher 查询接口。LLM 调用自动享受 PG 缓存（14x+ 加速重复调用）。

核心能力：
- **实体关系抽取**：收到 HT 异步回调 → 读 PG chunk → LLM 抽取（含 gleaning 增强）→ 三层合并去重 → 写入 Memgraph
- **知识图谱查询**：4 种 query_type 的 Cypher 模板化查询，返回结构化 nodes + edges
- **数据溯源**：每个节点/边关联到原始文档的页码、章节、chunk ID

## User Stories

### Issue 1: 实体关系抽取

1. As an **HT(doc-parser)**，I want to POST `/api/v1/graph/extract` with a `doc_id`，so that graph-engine triggers entity/relationship extraction for my processed document.
2. As an **HT**，I want graph-engine to return HTTP 202 immediately and process extraction asynchronously，so that my 2s callback timeout is not blocked by LLM latency.
3. As an **HT**，I want the same `doc_id` repeated to be rejected (idempotent)，so that I don't waste LLM calls on duplicate callbacks.
4. As a **developer**，I want to query extraction task status via PG，so that I can monitor progress and debug failures.
5. As a **developer**，I want entity types and few-shot examples defined in YAML files，so that I can iterate on prompt quality without changing code.
6. As a **developer**，I want LLM responses cached by prompt hash（llm-gateway 内置 PG 缓存），so that repeated extractions during prompt tuning don't incur redundant LLM costs.（实测 cache hit 比 vLLM 推理快 14-28x）
7. As a **domain expert**，I want the entity extraction to cover 12 entity types（Project, Region, Structure, DefectLocation, DefectType, DefectImpact, DefectAssessment, Treatment, Material, DetectionMethod, NormClause, Parameter），so that water conservancy domain knowledge is fully captured.
8. As a **domain expert**，I want the extraction to capture 11 relationship types（BELONGS_TO, REGULATED_BY, TREATED_BY, DETECTED_BY, HAS_THRESHOLD, HAS_IMPACT, ASSESSED_AS, LOCATED_AT, USES_MATERIAL, REFERENCES, APPLIED_IN），so that the knowledge graph supports complex queries.
9. As a **developer**，I want gleaning (multi-round extraction enhancement) enabled by default with 1 extra round，so that recall is higher than single-pass extraction.
10. As an **operator**，I want gleaning rounds configurable via environment variable，so that I can disable it or increase rounds based on quality requirements.

### Issue 2: 知识图谱查询

11. As an **agent-reasoning**，I want to query `related_norms` (which norm clauses regulate a defect type)，so that I can answer "裂缝受哪些规范约束" type questions.
12. As an **agent-reasoning**，I want to query `related_treatments` (which treatments address a defect type)，so that I can answer "渗漏怎么处理" type questions.
13. As an **agent-reasoning**，I want to query `related_cases` (which projects have similar defects)，so that I can answer "哪些工程有过类似裂缝案例" type questions.
14. As an **agent-reasoning**，I want to query `entity_detail` (BFS subgraph around an entity)，so that I can get full context for complex reasoning questions.
15. As an **agent-reasoning**，I want query results to include page numbers, section titles, and doc titles on each node/edge，so that I can generate citations without additional PG queries.

### Issue 3: 全链路集成

16. As a **developer**，I want integration tests with real Memgraph + real LLM + seed data，so that I can verify the end-to-end extraction and query pipeline.
17. As an **operator**，I want health check (`/health`, `/ready`) and Prometheus metrics (`/metrics`) endpoints，so that graph-engine is observable in production.

## Implementation Decisions

### 1. LLM 调用策略

通过 llm-gateway（port 8004）的 `POST /api/v1/completion` 进行 LLM 调用（`caller="graph-engine"`, `priority="batch"`）。llm-gateway 自动缓存相同 prompt 的响应（PG 缓存，key = `md5(system+user+model+host)`，TTL 7 天），重复 extraction 无需重复调 LLM。

### 2. 抽取流程 — PG 任务表异步模式

`POST /api/v1/graph/extract` 立即返回 HTTP 202，后台异步执行抽取。引入 PG 任务表 `graph_engine.extraction_tasks` 管理任务状态和生命周期。

任务表结构：

```
graph_engine.extraction_tasks
  task_id       VARCHAR(64) PRIMARY KEY
  doc_id        VARCHAR(64) NOT NULL
  status        VARCHAR(20) NOT NULL DEFAULT 'pending'
                -- pending → processing → completed / failed
  progress      JSONB DEFAULT '{}'
                -- {"extracted": 5, "total": 15, "phase": "gleaning"}
  result        JSONB DEFAULT '{}'
                -- {"entities": 42, "relationships": 38}
  error_message TEXT
  created_at    TIMESTAMPTZ DEFAULT now()
  updated_at    TIMESTAMPTZ DEFAULT now()
  completed_at  TIMESTAMPTZ
```

幂等策略：若该 doc_id 已存在 pending/processing/completed 任务，返回 "already in progress" 或 "already done"。

### 3. Chunk 数据来源

当前阶段直读 PostgreSQL `metadata.chunks` 表。引入 `ChunkReader` 接口抽象，HT doc-parser 就绪后切换为调 `GET /api/v1/chunks?doc_id=...`。

### 4. 实体关系 Schema

#### 实体类型（12 类，作为 Memgraph 双 label 之一）

| 类型 | 说明 |
|------|------|
| Project | 工程名称（铜街子水电站、深溪沟水电站） |
| Region | 工程所属区域（大渡河流域、四川省） |
| Structure | 水工建筑物及部件（混凝土坝、消力池、泄水闸、闸门、压力钢管） |
| DefectLocation | 缺陷发生的具体部位（上游面、坝踵、消力池底板、伸缩缝） |
| DefectType | 缺陷类型（裂缝、渗漏、碳化、冲刷、变形、腐蚀、钢筋锈蚀） |
| DefectImpact | 缺陷造成的影响（结构安全性降低、承载能力不足、渗漏量增大） |
| DefectAssessment | 缺陷评价/分级（较大缺陷、轻微渗漏、严重碳化、不安全状态） |
| Treatment | 治理措施与工艺（帷幕灌浆、化学灌浆、表面封闭法、粘贴碳纤维布法） |
| Material | 材料（环氧树脂、聚氨酯浆材、超细水泥浆液、碳纤维布、铜止水） |
| DetectionMethod | 检测方法（回弹法、钻芯法、超声-回弹综合法、酚酞试剂法、超声波探伤） |
| NormClause | 规范条款（DL/T 2628-2023 §5.2.3、DL/T 2700-2023 §6.1） |
| Parameter | 技术参数/阈值（裂缝宽度>0.3mm、渗漏量>1.0L/s、灌浆压力0.3-1.5MPa） |

#### 关系类型（9 类，LLM 直接输出，作为 Memgraph edge type）

| 类型 | 说明 |
|------|------|
| REGULATED_BY | target 是规范条款，定义 defect 的治理依据 |
| TREATED_BY | target 是治理措施，描述 defect 的处理方法 |
| USES_MATERIAL | target 是材料，描述治理中使用的材料 |
| BELONGS_TO | target 是工程/结构，描述实体归属关系 |
| OCCURS_IN | target 是缺陷部位/结构，描述缺陷发生位置 |
| DEFINED_BY | target 是参数，描述技术参数/阈值定义 |
| CAUSES | target 是缺陷影响/评价，描述因果关系 |
| HAS_SUBTYPE | target 是子类别，描述类型层级关系 |
| RELATED | 通用关联，当无其他类型匹配时使用 |

关系类型由 LLM 通过 few-shot 示例直接输出，替代原来的 `_infer_edge_type()` 规则推断。合并时按多数投票（Counter.most_common）确定最终类型。

### 5. Memgraph 建模策略

**节点 — 双 label**：
- Label 1：workspace label（如 `base`，用于多租户隔离）
- Label 2：entity_type（如 `DefectType`），利用 Memgraph label 索引加速按类型查询
- 属性：见下文 §6

**关系 — 语义化 edge type**：
- 每种关系类型直接用独立的 Cypher edge type（如 `REGULATED_BY`、`TREATED_BY`）
- 替代 LightRAG 默认的通用 `DIRECTED` 类型

### 6. 节点/关系属性字段设计

#### 节点属性

```
entity_id         — 实体名称，MERGE 匹配键（如 "3号坝段上游面横向裂缝"）
entity_type       — 实体类型（如 "DefectType"），同时作为 Memgraph label
description       — LLM 综合摘要后的描述
source_id         — 来源 chunk ID 列表（主溯源键，<SEP> 分隔）
page_numbers      — 来源页码（去重拼接，如 "23, 28, 35"）
section_titles    — 来源章节标题（去重拼接）
doc_titles        — 来源文档名称（去重拼接）
created_at        — 创建时间戳
```

`source_id` 截断策略：`max_source_ids_per_entity` 上限（可配置），超出则按 FIFO 或 KEEP 策略裁剪。

#### 关系属性

```
keywords          — 逗号分隔的关系关键词（如 "处置依据, 阈值判定"）
description       — 关系描述（多 chunk 聚合 + LLM 摘要后）
source_id         — 来源 chunk ID 列表（主溯源键）
page_numbers      — 来源页码（去重拼接）
section_titles    — 来源章节标题（去重拼接）
weight            — 权重（出现次数累加）
```

### 7. 实体关系抽取 Prompt 体系

使用 JSON 结构化输出模式（`entity_extraction_use_json=True`），LLM 返回 `{"entities": [...], "relationships": [...]}` 格式。

Prompt 参数通过 YAML 配置文件管理（LightRAG 的 `entity_type_prompt_file` 机制）：

```yaml
# prompts/entity_type/water_conservancy.yaml
entity_types_guidance: |
  <12 类实体类型的详细描述和分类指引>

entity_extraction_json_examples:
  - |
    <水工领域 few-shot 示例 1>
  - |
    <水工领域 few-shot 示例 2>
```

YAML 配置覆盖项：
- `entity_types_guidance`：实体类型分类指引文本
- `entity_extraction_json_examples`：JSON 模式的 few-shot 示例

### 8. 抽取流程

整体流程：

```
收到 HT 回调 (doc_id)
    │
    ├─ 幂等检查：查 PG 任务表
    ├─ 返回 202 Accepted
    │
    ▼
后台 worker (asyncio.create_task):
    1. INSERT extraction_task (status=pending → processing)
    2. 读 PG metadata.chunks WHERE doc_id = ?
    3. 加载 YAML prompt profile
    4. 并行抽取 (max_async=4):
       a. asyncio.Semaphore 控制并发
       b. 每个 chunk: 调 llm-gateway /api/v1/completion → 自动缓存命中/写入
       c. GLEANING: 再调 LLM（"你漏了哪些？请补充"）
       d. 合并两轮结果（同名实体取描述更长的版本）
    5. Map-Reduce LLM 合并:
       a. 同名 entity 按 entity_type 分组
       b. 同名 relationship 按 (source, target) 分组
       c. 每组 descriptions ≤ merge_summary_context_size 时直接 LLM 摘要
       d. 超过则分批 map → reduce 递归合并
       e. relation_type 按多数投票 (Counter.most_common)
    6. 写入 Memgraph:
       a. 每种 entity_type 作为独立 label
       b. 每种关系类型作为独立 edge type
       c. 冗余溯源信息写入属性
    7. UPDATE extraction_task (status=completed, result=...)
```

并发控制：`extraction_max_async` 默认 4，通过环境变量可配。

合并去重配置：`merge_summary_context_size`（默认 12000）、`merge_summary_max_tokens`（默认 500）、`merge_summary_language`（默认 "Chinese"）。

### 9. LLM 缓存（llm-gateway 管理）

LLM 响应缓存由 llm-gateway 的 PG 表 `llm_gateway.llm_cache` 统一管理，graph-engine 无需自行实现：

```
llm_gateway.llm_cache
  cache_key     TEXT PRIMARY KEY  -- compute_args_hash(system, user, model, host)
  model         TEXT NOT NULL
  system_prompt TEXT NOT NULL DEFAULT ''
  user_prompt   TEXT NOT NULL DEFAULT ''
  response      JSONB NOT NULL    -- {content, model, prompt_tokens, completion_tokens, latency_ms}
  created_at    TIMESTAMPTZ DEFAULT now()
```

缓存策略：
- Cache key = `md5(system_prompt + user_prompt + model + host)`，切换后端（vllm ↔ deepseek）自动破缓存
- TTL 默认 7 天（`LLM_GATEWAY_CACHE_TTL_SECONDS=604800`），设为 0 禁用
- 每次写入刷新 `created_at`，热条目持续保鲜
- PG 不可达时静默降级（cache miss 走 LLM）

### 10. 知识图谱查询

查询接口 `POST /api/v1/graph/query`，支持 4 种 query_type，全部走纯 Cypher 模板（不调 LLM）。

Cypher 查询模板：

| query_type | 输入 params | Cypher 逻辑 |
|------------|------------|------------|
| `related_norms` | `defect_type`, `structure_type`(可选) | `MATCH (n:DefectType)-[:REGULATED_BY]->(m:NormClause) RETURN n, m` |
| `related_treatments` | `defect_type` | `MATCH (n:DefectType)-[:TREATED_BY]->(m:Treatment) RETURN n, m` |
| `related_cases` | `defect_type`, `structure_type`(可选) | `MATCH (n:DefectType)-[:BELONGS_TO]->(p:Project) RETURN n, p` 或 BFS 扩展 |
| `entity_detail` | `entity_name`, `depth`(可选, 默认3) | 以 entity_name 为起点 BFS `[0..depth]` 跳子图，复用 LightRAG 的 `get_knowledge_graph` |

### 11. 不做推理

graph-engine 不承担推理职责。所有推理逻辑（BFS 子图分析 + LLM 推理）由 agent-reasoning 完成。agent-reasoning 通过调用 `/graph/query` 的 `entity_detail` 获取子图后自行推理。

这保证 graph-engine 遵循单一职责：只负责知识图谱的构建和图查询。

### 12. LightRAG 核心逻辑复用

直接复用 LightRAG 的以下组件：

| 组件 | 来源 | 用途 |
|------|------|------|
| `MemgraphStorage` | `lightrag/kg/memgraph_impl.py` | Memgraph 图操作（upsert/batch/get_knowledge_graph/search_labels） |
| `EntityExtractionResult` | `lightrag/types.py` | 实体关系抽取结果数据结构 |
| `ExtractedEntity` / `ExtractedRelationship` / `KnowledgeGraph` | `lightrag/types.py` | 核心数据模型 |
| 抽取提示词模板 | `lightrag/prompt.py` | JSON 模式 entity extraction prompts |
| YAML prompt profile 加载 | `lightrag/prompt.py` — `resolve_entity_extraction_prompt_profile` | 加载自定义 entity_types_guidance + few-shot |
| 三层合并去重 | `lightrag/operate.py` — `_merge_nodes_then_upsert` / `_merge_edges_then_upsert` / `merge_nodes_and_edges` | 同名 MERGE + 描述去重 + LLM 摘要 |
| Gleaning 增强抽取 | `lightrag/operate.py` — `extract_entities` 的 gleaning 流程 | 多轮抽取增强 |

自建的部分：
- FastAPI 路由层（`POST /api/v1/graph/extract`, `POST /api/v1/graph/query`）
- PG 任务表管理 + 幂等逻辑
- PG chunk 读取 + ChunkReader 抽象
- LLM client（通过 llm-gateway `/api/v1/completion`）
- 并行抽取 + LLM map-reduce 合并
- Cypher 查询模板（4 种 query_type）
- 水工领域 YAML prompt profile（含 relation_types_guidance）

### 13. 模块设计

| 模块 | 职责 | 接口 |
|------|------|------|
| **extract/orchestrator** | 抽取流程编排：读 chunk → LLM 抽取 → Gleaning → 合并去重 → 写入 Memgraph | `async def run_extraction(doc_id: str) -> None` |
| **extract/prompts** | YAML prompt profile 加载与管理 | `def load_prompt_profile(path: str) -> PromptProfile` |
| **llm/client** | LLM 调用抽象层（封装 llm-gateway `/api/v1/completion`） | `class AgentReasoningLLMClient: async def completion(...)` |
| **store/memgraph** | 从 LightRAG 导入 MemgraphStorage，封装初始化与配置 | `async def get_memgraph_storage() -> MemgraphStorage` |
| **store/pg** | PG 任务表 CRUD + chunk 读取 | `class ChunkReader: async def get_chunks(doc_id) -> list[Chunk]` |
| **query/searcher** | Cypher 查询模板化引擎 | `async def query(query_type, params) -> GraphResult` |
| **models** | Pydantic 数据模型（请求/响应/task/chunk） | — |
| **settings** | pydantic-settings 配置 | 前缀 `GRAPH_` |

LLM 缓存由 llm-gateway 统一管理，graph-engine 无需自行实现缓存层。

### 14. 外部接口

#### POST /api/v1/graph/extract

```
Request:  { "doc_id": "seed-doc-001" }
Response: HTTP 202 { "code": 0, "message": "accepted",
                     "data": { "task_id": "g-task-xxx", "status": "processing" } }
```

幂等行为：
- 同一 doc_id 已有 pending/processing 任务 → 409 "already in progress"
- 同一 doc_id 已有 completed 任务 → 200 "already done"

#### POST /api/v1/graph/query

```
Request:
{
  "query_type": "related_norms",
  "params": { "defect_type": "裂缝", "structure_type": "混凝土坝" }
}

Response:
{
  "code": 0,
  "data": {
    "nodes": [
      { "id": "n1", "type": "DefectType", "name": "裂缝",
        "description": "...", "page_numbers": "23", "section_titles": "裂缝处理标准",
        "doc_titles": "DL/T 2628-2023" },
      { "id": "n2", "type": "NormClause", "name": "DL/T 2628 §5.2.3",
        "description": "裂缝宽度>0.3mm需灌浆...", "page_numbers": "23",
        "section_titles": "裂缝处理标准", "doc_titles": "DL/T 2628-2023" }
    ],
    "edges": [
      { "from": "n1", "to": "n2", "relation": "REGULATED_BY",
        "keywords": "处置依据, 阈值判定", "description": "..." }
    ],
    "query_type": "related_norms"
  }
}
```

对于 `entity_detail` 查询类型，额外支持 `depth` 参数（默认 3），返回 BFS 子图。

### 15. 架构

```
HT(doc-parser) ──POST /extract──→ graph-engine
       ←──202──                       │
                                      ├─ 读 PG metadata.chunks
                                      ├─ 并行抽取 (max_async=4) → llm-gateway /api/v1/completion
                                      ├─ Map-Reduce LLM 合并
                                      ├─ 写 Memgraph (双label + 语义化edge type)
                                      └─ 写 PG extraction_tasks

agent-reasoning ──POST /query──→ graph-engine
                                      │
                                      └─ Cypher 模板 → Memgraph → nodes + edges

graph-engine     ──LLM调用──→ llm-gateway:8004
agent-reasoning  ──LLM调用──→ llm-gateway:8004
```

### 16. 配置项

环境变量前缀：`GRAPH_`

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `GRAPH_MEMGRAPH_URI` | `bolt://localhost:17687` | Memgraph Bolt 连接 |
| `GRAPH_MEMGRAPH_USERNAME` | `` | Memgraph 用户名 |
| `GRAPH_MEMGRAPH_PASSWORD` | `` | Memgraph 密码 |
| `GRAPH_MEMGRAPH_DATABASE` | `memgraph` | Memgraph 数据库名 |
| `GRAPH_PG_HOST` | `localhost` | PG 主机 |
| `GRAPH_PG_PORT` | `5434` | PG 端口 |
| `GRAPH_PG_USER` | `daduhe` | PG 用户 |
| `GRAPH_PG_PASSWORD` | — | PG 密码 |
| `GRAPH_PG_DATABASE` | `daduhe` | PG 数据库名 |
| `GRAPH_LLM_GATEWAY_URL` | `http://localhost:8004` | llm-gateway 地址 |
| `GRAPH_ENTITY_EXTRACT_MAX_GLEANING` | `1` | Gleaning 轮数 |
| `GRAPH_EXTRACTION_LLM_MAX_TOKENS` | `4000` | LLM 抽取输出的 max_tokens |
| `GRAPH_EXTRACTION_MAX_ASYNC` | `4` | 并发 chunk 抽取数 |
| `GRAPH_MAX_SOURCE_IDS_PER_ENTITY` | `10` | 每个实体最大 source_id 数 |
| `GRAPH_MERGE_SUMMARY_CONTEXT_SIZE` | `12000` | map-reduce 每批输入 token 上限 |
| `GRAPH_MERGE_SUMMARY_MAX_TOKENS` | `500` | LLM 合并输出 token 上限 |
| `GRAPH_MERGE_SUMMARY_LANGUAGE` | `Chinese` | 合并 prompt 语言 |
| `GRAPH_PROMPT_PROFILE_PATH` | `prompts/entity_type/water_conservancy.yaml` | Prompt profile YAML 路径 |

## Testing Decisions

### 测试原则

只测试外部可观测行为，不耦合实现细节。集成测试连接真实 Memgraph + 真实 LLM（通过 agent-reasoning 或直连），不 mock。真实 LLM 的随机性通过断言关键词集合而非精确匹配来吸收。

参考 `agent-reasoning/tests/test_full_integration.py`（44 项集成测试）和 `search-engine/tests/test_search.py`（22 个集成测试）的测试风格。

### 测试覆盖

| 测试模块 | 覆盖内容 |
|---------|---------|
| 抽取集成测试 | 用种子数据 seed-doc-001（10 chunks）触发抽取，验证：task 状态流转、Memgraph 写入、节点 label 和属性、关系 type 和属性、溯源字段不为空 |
| 查询集成测试 | 4 种 query_type 的 Cypher 查询：返回 nodes/edges 结构正确、溯源字段完整 |
| 幂等测试 | 重复 doc_id 回调返回 409/200、同步等待后 completed 再回调 |
| 健康检查测试 | `/health` 200、`/ready` 含 memgraph 状态 |
| 异常测试 | 无效 doc_id 返回错误码、LLM 超时 task 标记 failed |

## Out of Scope

- **图推理（`/graph/reasoning`）**：不在 graph-engine 实现，推理逻辑由 agent-reasoning 负责
- **流式响应**：抽取结果和查询结果均为非流式返回
- **批量抽取**：当前为单文档抽取，多文档并行抽取后续迭代
- **规则库检索**：由 search-engine 负责，不在 graph-engine 范围
- **向量存储**：graph-engine 不引入向量数据库，不使用 LightRAG 的 entities_vdb/relationships_vdb
- **KV 存储**：不使用 LightRAG 的 entity_chunks_storage/relation_chunks_storage，溯源信息直接冗余在节点属性上
- **ConversationStore**：由 agent-reasoning 负责，graph-engine 无状态
- **用户直接调用**：graph-engine 不对最终用户暴露，仅由 agent-reasoning 和 HT 调用

## Further Notes

- graph-engine 开发完成后，agent-reasoning 的 ToolRegistry 只需增加 `graph_query` 工具（调用 `POST /api/v1/graph/query`），无需改动 Graph 拓扑
- LLM 工厂服务（llm-gateway，port 8004）已独立上线，graph-engine 和 agent-reasoning 均通过其 `/api/v1/completion` 调用 LLM，自动享受 PG 缓存
- 种子数据（seed-doc-001、seed-doc-002，共 15 chunks）可直接用于开发和测试
- 开发期间需要 SSH 隧道连接远程 Memgraph：`ssh -L 17687:localhost:17687 gyyknowledge@10.222.124.211`
