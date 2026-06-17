# ICD-03：知识图谱层 / 检索引擎层 / Agent推理层（FXL）

## 契约先行、并行开发

| 负责人 | 开发语言 | 服务 |
|--------|---------|------|
| FXL | Python | graph-engine（知识图谱层）、search-engine（检索引擎层）、agent-reasoning（Agent推理层） |

> FXL负责三个服务，服务间的内部接口由FXL自行定义。本文档仅规定三个服务对外暴露的接口，以及与HT、LSL服务之间的集成契约。

---

## 1. 服务职责

| 服务 | 职责 |
|------|------|
| **graph-engine** (8001) | LLM实体关系抽取、知识图谱持久化与推理 |
| **search-engine** (8002) | 多模式检索引擎：关键词匹配、模糊查询、语义向量检索、混合检索 |
| **agent-reasoning** (8003) | Query意图识别、检索模式选择、智能问答、Prompt管理、LLM调用工厂、Tool Calling、工作流编排 |

---

## 2. 技术栈

| 组件 | 选型 | 用途 |
|------|------|------|
| 对象存储 | MinIO | 原始文件、markdown文件、chunk JSON存储，提供预签名下载链接 |
| 关系数据库 | PostgreSQL | 四层元数据存储、规则库存储 |
| Embedding模型 | Ollama（本地部署） | 文本向量化，产出embedding向量 |
| LLM（在线） | DeepSeek API | Agent在线推理、图谱离线实体关系抽取 |
| LLM（本地） | vLLM | 本地大模型部署，敏感数据场景使用 |
| 图数据库 | Neo4j | 知识图谱持久化与Cypher推理查询 |
| 向量数据库 | Milvus | Embedding向量存储与相似度检索 |
| 容器化 | Docker + Docker Compose | 开发/测试环境统一部署 |
| 开发语言 | HT: Java / LSL: TypeScript / FXL: Python | 各自擅长 |

### 2.1 服务端口分配

| 服务 | 容器名 | HTTP端口 | 开发者 |
|------|--------|---------|--------|
| doc-parser | `ht-doc-parser` | 8080 | HT |
| rule-extractor | `lsl-rule-extractor` | 3000 | LSL |
| graph-engine | `fxl-graph-engine` | 8001 | FXL |
| search-engine | `fxl-search-engine` | 8002 | FXL |
| agent-reasoning | `fxl-agent-reasoning` | 8003 | FXL |

| 基础设施 | 容器名 | 端口 |
|---------|--------|------|
| PostgreSQL | `postgres` | 5432 |
| MinIO | `minio` | 9000 (API) / 9001 (Console) |
| Neo4j | `neo4j` | 7474 (HTTP) / 7687 (Bolt) |
| Milvus | `milvus-standalone` | 19530 |
| Ollama | `ollama` | 11434 |

---

## 3. 需要从HT、LSL消费的数据

### 3.1 消费HT层接口

| 消费方 | HT接口 | 用途 |
|--------|--------|------|
| graph-engine | `GET /api/v1/chunks?doc_id=...` | 获取chunk以进行实体关系抽取 |
| graph-engine | `GET /api/v1/metadata/search?doc_id=...` | 获取文档元数据 |
| search-engine | `GET /api/v1/chunks?doc_id=...` | 获取chunk以构建检索索引 |
| search-engine | `GET /api/v1/chunks/{chunk_id}` | 获取单个chunk详情（含向量关联） |
| agent-reasoning | `GET /api/v1/documents/{doc_id}/download` | 生成回答中的文档下载链接 |
| agent-reasoning | `GET /api/v1/chunks/{chunk_id}` | 溯源时获取chunk详情 |

HT接口格式详见 **ICD-01-HT-文档解析与数据输入.md**。

### 3.2 消费LSL层接口

| 消费方 | LSL接口 | 用途 |
|--------|---------|------|
| search-engine | `GET /api/v1/rules/search?...` | 检索时将规则库纳入检索范围 |
| agent-reasoning | `GET /api/v1/rules/search?...` | 问答时查询相关规则 |

LSL接口格式详见 **ICD-02-LSL-知识抽取层.md**。

### 3.3 接收HT异步通知

HT处理完成后通过HTTP POST回调以下webhook地址（详见 §11.4）：

| 服务 | 回调地址 | 触发动作 |
|------|---------|---------|
| graph-engine | `POST /api/v1/graph/extract` | 触发实体关系抽取 |
| search-engine | `POST /api/v1/search/index` | 构建检索索引 |

---

## 4. graph-engine 对外接口

### 4.1 触发实体关系抽取

```
POST /api/v1/graph/extract
```

**Request**

```json
{
  "doc_id": "d9e8f7a6-e5f6-7890-abcd-ef1234567890"
}
```

**Response** (HTTP 202)

```json
{
  "code": 0,
  "message": "accepted",
  "data": {
    "task_id": "g-task-c3d4e5f6",
    "status": "processing"
  }
}
```

### 4.2 知识图谱查询

```
POST /api/v1/graph/query
```

**Request**

```json
{
  "query_type": "related_norms",
  "params": {
    "defect_type": "裂缝",
    "structure_type": "混凝土坝"
  }
}
```

query_type枚举：

| 值 | 说明 | params示例 |
|----|------|------------|
| `related_norms` | 查询缺陷类型关联的规范条款 | `{"defect_type": "裂缝"}` |
| `related_treatments` | 查询缺陷类型对应的治理技术 | `{"defect_type": "渗漏"}` |
| `related_cases` | 查询相似缺陷的历史案例 | `{"defect_type": "裂缝", "structure_type": "混凝土坝"}` |
| `entity_detail` | 查询单个实体详情 | `{"entity_name": "灌浆处理"}` |

**Response** (HTTP 200)

```json
{
  "code": 0,
  "data": {
    "nodes": [
      { "id": "n1", "type": "DefectType", "name": "裂缝" },
      { "id": "n2", "type": "NormClause", "name": "DL/T 2628-2023 §5.2.3" },
      { "id": "n3", "type": "Treatment", "name": "灌浆处理" },
      { "id": "n4", "type": "Case", "name": "深溪沟消力池底板裂缝治理案例" }
    ],
    "edges": [
      { "from": "n1", "to": "n2", "relation": "regulated_by" },
      { "from": "n1", "to": "n3", "relation": "treated_by" },
      { "from": "n4", "to": "n1", "relation": "involves_defect" },
      { "from": "n4", "to": "n3", "relation": "applied_treatment" }
    ],
    "query_type": "related_norms"
  }
}
```

### 4.3 知识图谱推理

```
POST /api/v1/graph/reasoning
```

**Request**

```json
{
  "entity_type": "DefectType",
  "entity_name": "渗漏",
  "depth": 3
}
```

**Response** (HTTP 200)

```json
{
  "code": 0,
  "data": {
    "root": { "type": "DefectType", "name": "渗漏" },
    "paths": [
      {
        "path": ["渗漏", "regulated_by", "DL/T 2628-2023 §6.1", "references", "灌浆技术规程"],
        "confidence": 0.87
      },
      {
        "path": ["渗漏", "treated_by", "帷幕灌浆", "applied_in", "铜街子消力塘治理案例"],
        "confidence": 0.82
      }
    ],
    "depth": 3
  }
}
```

---

## 5. search-engine 对外接口

### 5.1 接收HT异步通知 — 触发索引构建

```
POST /api/v1/search/index
```

HT文档处理完成后回调此接口。search-engine收到通知后拉取chunk和向量数据，构建检索索引。

**Request**

```json
{
  "event_id": "evt-a1b2c3d4-...",
  "trace_id": "ht-a1b2c3d4-...",
  "doc_id": "d9e8f7a6-e5f6-7890-abcd-ef1234567890",
  "doc_type": "规范",
  "title": "混凝土坝安全监测技术规范",
  "chunk_count": 156,
  "embedding_model": "bge-m3",
  "embedding_dimension": 1024,
  "status": "completed"
}
```

**Response** (HTTP 202)

```json
{
  "code": 0,
  "message": "accepted",
  "data": {
    "task_id": "idx-task-d4e5f6a7",
    "status": "processing"
  }
}
```

> 幂等：同一 `doc_id` 重复通知时，若索引已存在则更新，不存在则新建。

### 5.2 统一检索

```
POST /api/v1/search
```

这是检索引擎的唯一对外入口，Agent推理层通过此接口执行所有检索操作。

**Request**

```json
{
  "query": "混凝土坝裂缝宽度超过多少需要处理",
  "mode": "hybrid",
  "filters": {
    "doc_type": ["规范"],
    "doc_ids": [],
    "section_number": null,
    "date_from": "2020-01-01",
    "date_to": null
  },
  "top_k": 10,
  "include_sources": ["chunks", "rules"]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | string | 是 | 查询语句 |
| mode | string | 是 | `keyword` / `fuzzy` / `vector` / `hybrid` |
| filters.doc_type | string[] | 否 | 按文档类型过滤 |
| filters.doc_ids | string[] | 否 | 按文档ID过滤 |
| filters.date_from | string | 否 | 发布日期下限 |
| filters.date_to | string | 否 | 发布日期上限 |
| top_k | integer | 否 | 返回结果数，默认10 |
| include_sources | string[] | 否 | 指定检索范围：`chunks`(文档chunk) / `rules`(规则库)。默认仅`chunks` |

**Response** (HTTP 200)

```json
{
  "code": 0,
  "data": {
    "results": [
      {
        "chunk_id": "c1b2a3d4-e5f6-7890-abcd-ef1234567890",
        "text": "当裂缝宽度大于0.3mm时，应采取灌浆或表面封闭处理措施...",
        "score": 0.92,
        "source_type": "chunk",
        "metadata": {
          "doc_id": "d9e8f7a6-e5f6-7890-abcd-ef1234567890",
          "doc_type": "规范",
          "title": "混凝土坝安全监测技术规范",
          "section_number": "5.2.3",
          "section_title": "裂缝处理标准",
          "page_number": 23,
          "download_url": "/api/v1/documents/d9e8f7a6-e5f6-7890-abcd-ef1234567890/download"
        }
      },
      {
        "chunk_id": null,
        "rule_id": "r-001",
        "text": "当裂缝宽度大于0.3mm时，应采取灌浆或表面封闭处理措施",
        "score": 0.88,
        "source_type": "rule",
        "metadata": {
          "rule_id": "r-001",
          "title": "裂缝宽度安全阈值",
          "category": "混凝土坝/裂缝",
          "norm_ref": "DL/T 2628-2023",
          "doc_id": "d9e8f7a6-e5f6-7890-abcd-ef1234567890",
          "section_number": "5.2.3"
        }
      }
    ],
    "total_hits": 5,
    "mode_used": "hybrid"
  }
}
```

检索结果中 `source_type` 字段区分来源：
- `chunk`：结果来自文档chunk（通过关键词/模糊/向量检索命中）
- `rule`：结果来自LSL规则库（通过关键词匹配命中）

Agent推理层调用时设置 `include_sources: ["chunks", "rules"]` 可同时搜文档chunk和规则库。

---

## 6. agent-reasoning 对外接口

### 6.1 智能问答

```
POST /api/v1/chat
```

这是最终用户使用的问答入口。Agent推理层负责：意图识别 → 检索模式选择 → 调用search-engine检索 → 调用LLM生成答案 → 组装溯源引用。

**Request**

```json
{
  "query": "混凝土坝裂缝宽度超过多少需要处理？",
  "conversation_id": "conv-a1b2c3d4",
  "retrieval_mode": "auto",
  "stream": false
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | string | 是 | 用户问题 |
| conversation_id | string | 否 | 会话ID，用于多轮对话上下文关联。首次对话不传 |
| retrieval_mode | string | 否 | 强制检索模式（`keyword`/`fuzzy`/`vector`/`hybrid`），默认`auto`由Agent自行判断 |
| stream | boolean | 否 | 是否流式返回，默认false |

**Response** (HTTP 200)

```json
{
  "code": 0,
  "data": {
    "answer": "根据《混凝土坝安全监测技术规范》DL/T 2628-2023 第5.2.3条规定，当裂缝宽度大于0.3mm时，应采取灌浆或表面封闭处理措施。[1]\n\n此外，《水工建筑物缺陷管理规范》第6.1.2条进一步将裂缝宽度>0.3mm判定为较大缺陷，建议优先采用灌浆法处理。[2]",
    "citations": [
      {
        "index": 1,
        "chunk_id": "c1b2a3d4-e5f6-7890-abcd-ef1234567890",
        "doc_title": "混凝土坝安全监测技术规范",
        "doc_type": "规范",
        "section": "第5章 5.2.3 裂缝处理标准",
        "page": 23,
        "download_url": "/api/v1/documents/d9e8f7a6-e5f6-7890-abcd-ef1234567890/download",
        "excerpt": "当裂缝宽度大于0.3mm时，应采取灌浆或表面封闭处理措施"
      },
      {
        "index": 2,
        "chunk_id": "e5f6g7h8-a1b2-3456-cdef-789012345678",
        "doc_title": "水工建筑物缺陷管理规范",
        "doc_type": "规范",
        "section": "第6章 6.1.2 裂缝分级",
        "page": 31,
        "download_url": "/api/v1/documents/a1b2c3d4-e5f6-7890-abcd-ef1234567890/download",
        "excerpt": "裂缝宽度>0.3mm判定为较大缺陷"
      }
    ],
    "retrieval_mode_used": "hybrid",
    "conversation_id": "conv-a1b2c3d4",
    "trace_id": "t1r2a3c4-e5f6-7890-abcd-ef1234567890"
  }
}
```

citations数组与answer中 `[1]` `[2]` 标记一一对应。前端渲染时将 `[1]` 替换为可点击的引用链接，展示对应的doc_title、section、page，并提供download_url下载原始文档。

### 6.2 LLM调用（内部共享服务）

```
POST /api/v1/llm/completion
```

LLM调用工厂，供graph-engine离线实体关系抽取使用。

**Request**

```json
{
  "model": "deepseek-chat",
  "messages": [
    { "role": "system", "content": "你是水工缺陷领域的实体关系抽取专家..." },
    { "role": "user", "content": "从以下文本中抽取实体和关系: ..." }
  ],
  "temperature": 0.1,
  "max_tokens": 2000,
  "caller": "graph-engine",
  "priority": "batch"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| model | string | 是 | `deepseek-chat`（DeepSeek API）/ `vllm-local`（本地vLLM）/ `ollama-embed`（Ollama，仅用于向量化） |
| messages | array | 是 | OpenAI兼容的messages格式 |
| temperature | float | 否 | 默认0.1 |
| max_tokens | integer | 否 | 默认2000 |
| caller | string | 是 | 调用方服务名，用于鉴权和计费统计 |
| priority | string | 是 | `realtime`（在线推理，低延迟）/ `batch`（离线任务，高吞吐） |

**Response** (HTTP 200)

```json
{
  "code": 0,
  "data": {
    "id": "llm-resp-d4e5f6a7",
    "content": "{\"entities\": [...], \"relations\": [...]}",
    "model": "deepseek-chat",
    "usage": {
      "prompt_tokens": 500,
      "completion_tokens": 300
    },
    "latency_ms": 1200
  }
}
```

---

## 7. FXL三个服务间的调用关系（内部约定）

以下为FXL内部的调用流向，具体接口格式由FXL自行定义，不纳入跨开发者契约。但调用关系需与HT、LSL的集成协同：

```
agent-reasoning ──调用──→ search-engine    (POST /api/v1/search)
agent-reasoning ──调用──→ graph-engine     (POST /api/v1/graph/query)
agent-reasoning ──调用──→ graph-engine     (POST /api/v1/graph/reasoning)
graph-engine    ──调用──→ agent-reasoning  (POST /api/v1/llm/completion)
```

---

## 8. 错误码体系

所有服务统一使用以下错误码。业务错误码 = `段号 × 1000 + 序号`。

| 段号 | 范围 | 含义 |
|------|------|------|
| 0 | 0 | 成功 |
| 1 | 1000–1999 | 参数校验错误 |
| 2 | 2000–2999 | 认证鉴权错误 |
| 3 | 3000–3999 | 资源不存在 |
| 4 | 4000–4999 | 服务调用失败 |
| 5 | 5000–5999 | 业务逻辑错误 |
| 9 | 9000–9999 | 系统内部错误 |

通用错误码：

| code | message模板 | 说明 |
|------|------------|------|
| 0 | `ok` | 成功 |
| 1001 | `missing required field: {field}` | 必填字段缺失 |
| 1002 | `invalid value for {field}: {value}` | 字段值非法 |
| 3001 | `{resource} not found: {id}` | 资源未找到 |
| 4001 | `upstream service unavailable: {service}` | 下游服务不可达 |
| 4002 | `upstream timeout: {service}` | 下游服务超时 |
| 5003 | `graph extraction failed: {reason}` | 图谱抽取失败 |
| 5004 | `search failed: {reason}` | 检索失败 |
| 5005 | `LLM call failed: {reason}` | LLM调用失败 |
| 9001 | `internal error: {detail}` | 内部未知错误 |

错误响应体格式：

```json
{
  "code": 4001,
  "message": "upstream service unavailable: search-engine",
  "trace_id": "fxl-a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

---

## 9. 超时约定

| 调用类型 | 超时时间 | 说明 |
|---------|---------|------|
| 查询类同步API | 5s | `POST /search`, `POST /graph/query` 等 |
| 触发类同步API | 2s | `POST /graph/extract` 返回202即完成 |
| LLM completion (realtime) | 30s | 在线推理 |
| LLM completion (batch) | 120s | 离线抽取 |
| HT层chunk拉取 | 15s | 批量拉取一个文档的全部chunk |

---

## 10. 可观测契约

### 10.1 链路追踪

所有服务间HTTP调用必须通过Header传递 `X-Trace-Id`：

```
X-Trace-Id: {service_short}-{uuid_v4}
示例: fxl-a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

- 外部请求进入时，接收方生成trace_id
- 调用下游时，透传收到的trace_id

### 10.2 日志规范

统一JSON结构化日志，每行一条。

```json
{
  "timestamp": "2026-06-17T10:05:00.123Z",
  "level": "INFO",
  "service": "search-engine",
  "trace_id": "fxl-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "message": "search completed",
  "detail": {
    "query": "混凝土坝裂缝宽度",
    "mode": "hybrid",
    "hit_count": 5,
    "duration_ms": 120
  }
}
```

必含字段: `timestamp` `level` `service` `trace_id` `message`

| 级别 | 使用场景 |
|------|---------|
| ERROR | 需人工介入（服务不可达、数据损坏） |
| WARN | 可自动恢复（重试、降级、熔断触发） |
| INFO | 关键业务节点（处理开始/完成） |
| DEBUG | 开发调试，生产环境关闭 |

### 10.3 Metrics

每个服务暴露 `/metrics` 端点（Prometheus格式）。统一命名：`daduh_{metric}_{unit}`。

各服务必须暴露的指标：

| Metric | 类型 | 说明 |
|--------|------|------|
| `daduh_http_requests_total` | Counter | 按 method/status/endpoint 标记 |
| `daduh_http_request_duration_ms` | Histogram | 请求耗时分布 |
| `daduh_search_query_duration_ms` | Histogram | 检索耗时 |
| `daduh_llm_call_duration_ms` | Histogram | LLM调用耗时 |
| `daduh_graph_extraction_duration_s` | Histogram | 图谱抽取耗时 |
| `daduh_circuit_breaker_state` | Gauge | 熔断器状态 (0=closed, 1=half-open, 2=open) |

### 10.4 健康检查

每个服务暴露两个端点：

| 端点 | HTTP状态 | 返回体 | 用途 |
|------|---------|--------|------|
| `GET /health` | 200/503 | `{"status":"ok"}` | K8s liveness probe |
| `GET /ready` | 200/503 | `{"status":"ready","checks":{"db":"ok","neo4j":"ok","milvus":"ok"}}` | K8s readiness probe，列出所有外部依赖的状态 |

---

## 11. 异步通知契约（共享约定）

验证阶段使用 **HTTP POST Callback** 方式传递异步通知，不引入消息队列。

### 11.1 通知方式

生产者完成处理后，向已注册的webhook地址发起HTTP POST，请求体JSON格式。每个回调超时2s，失败仅记WARN日志，不重试。

### 11.2 负载格式

所有异步通知统一使用以下JSON结构：

```json
{
  "event_id": "evt-{uuid}",
  "trace_id": "{service_short}-{uuid_v4}",
  "doc_id": "...",
  "status": "completed"
}
```

具体业务字段由各接口的Request定义。

### 11.3 本服务接收的通知

| 服务 | 回调地址 | 用途 | 详见 |
|------|---------|------|------|
| graph-engine | `POST /api/v1/graph/extract` | 触发实体关系抽取 | §3.1 |
| search-engine | `POST /api/v1/search/index` | 触发检索索引构建 | §4 |

### 11.4 本服务发出的通知

> 验证阶段FXL暂不主动通知下游。
