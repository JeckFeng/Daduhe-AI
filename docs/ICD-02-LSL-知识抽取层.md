# ICD-02：知识抽取层（LSL）

## 契约先行、并行开发

| 负责人 | 开发语言 | 服务名 |
|--------|---------|--------|
| LSL | TypeScript | rule-extractor |

---

## 1. 服务职责

从HT层产出的chunk中抽取可执行的结构化规则，构建可检索的规则库。规则库供检索引擎和Agent推理层查询使用。

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

## 3. 需要从其他服务消费的数据

### 3.1 消费HT层Chunk

LSL通过以下方式获取chunk数据：

**方式一：接收HT异步通知（推荐）**

HT处理完成后向LSL的webhook地址 `POST /api/v1/rules/extract` 发送通知（详见 §8.4）。LSL收到通知后通过HT接口拉取chunk。

**方式二：直接查询**

调用HT层接口获取chunk：

```
GET {doc-parser}/api/v1/chunks?doc_id={doc_id}&page={page}&page_size={page_size}
```

HT返回的chunk JSON格式见 ICD-01 §2.4。

### 3.2 消费HT层元数据

需要获取文档元数据时，调用HT层接口：

```
GET {doc-parser}/api/v1/metadata/search?doc_id={doc_id}
```

HT返回的元数据格式见 ICD-01 §2.6。

---

## 4. 对外接口

### 4.1 触发规则抽取

```
POST /api/v1/rules/extract
```

收到HT文档处理完成事件后，由LSL自身或下游调用方触发。

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
    "task_id": "r-task-a1b2c3d4",
    "status": "processing"
  }
}
```

### 4.2 查询规则库

```
GET /api/v1/rules/search?keyword={keyword}&category={category}&page={page}&page_size={page_size}
```

这是LSL对外提供的核心接口，供检索引擎和Agent推理层调用。

**Request 参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| keyword | string | 否 | 搜索关键词，匹配规则标题和内容 |
| category | string | 否 | 规则分类，如"混凝土坝/裂缝" |
| doc_id | string | 否 | 按来源文档过滤 |
| page | integer | 否 | 页码，默认1 |
| page_size | integer | 否 | 每页条数，默认20 |

**Response** (HTTP 200)

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "rule_id": "r-001",
        "title": "裂缝宽度安全阈值",
        "content": "当裂缝宽度大于0.3mm时，应采取灌浆或表面封闭处理措施",
        "category": "混凝土坝/裂缝",
        "norm_ref": "DL/T 2628-2023",
        "parameters": {
          "name": "max_width_mm",
          "value": 0.3,
          "operator": ">",
          "unit": "mm"
        },
        "source": {
          "doc_id": "d9e8f7a6-e5f6-7890-abcd-ef1234567890",
          "chunk_ids": ["c1b2a3d4-e5f6-7890-abcd-ef1234567890"],
          "doc_title": "混凝土坝安全监测技术规范",
          "section_number": "5.2.3"
        },
        "confidence": 0.95,
        "created_at": "2026-06-17T10:08:00Z"
      }
    ],
    "total": 12,
    "page": 1,
    "page_size": 20
  }
}
```

**Response字段说明**

| 字段 | 类型 | 说明 |
|------|------|------|
| rule_id | string | 规则唯一标识 |
| title | string | 规则标题，便于展示和检索 |
| content | string | 规则正文，人类可读 |
| category | string | 多级分类路径 |
| norm_ref | string | 引用的规范编号 |
| parameters | object | 可量化的参数，如阈值、范围等 |
| source.doc_id | string | 来源文档ID，用于溯源 |
| source.chunk_ids | string[] | 来源chunk列表，可精确定位原文 |
| source.doc_title | string | 来源文档标题 |
| source.section_number | string | 来源章节编号 |
| confidence | float | 抽取置信度 (0–1) |

---

## 5. 错误码体系

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
| 5002 | `rule extraction failed: {reason}` | 规则抽取失败 |
| 9001 | `internal error: {detail}` | 内部未知错误 |

错误响应体格式：

```json
{
  "code": 3001,
  "message": "rule not found: r-001",
  "trace_id": "lsl-a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

---

## 6. 超时约定

| 调用类型 | 超时时间 | 说明 |
|---------|---------|------|
| 查询类同步API | 5s | `GET /rules/search` 等 |
| 触发类同步API | 2s | `POST /rules/extract` 返回202即完成 |
| HT层chunk拉取 | 15s | 批量拉取一个文档的全部chunk |

---

## 7. 可观测契约

### 7.1 链路追踪

所有服务间HTTP调用必须通过Header传递 `X-Trace-Id`：

```
X-Trace-Id: {service_short}-{uuid_v4}
示例: lsl-a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

- 外部请求进入时，接收方生成trace_id
- 调用下游时，透传收到的trace_id

### 7.2 日志规范

统一JSON结构化日志，每行一条。

```json
{
  "timestamp": "2026-06-17T10:08:00.123Z",
  "level": "INFO",
  "service": "rule-extractor",
  "trace_id": "lsl-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "message": "rule extraction completed",
  "detail": {
    "doc_id": "d9e8f7a6-e5f6-7890-abcd-ef1234567890",
    "rule_count": 12,
    "duration_ms": 4500
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

### 7.3 Metrics

每个服务暴露 `/metrics` 端点（Prometheus格式）。统一命名：`daduh_{metric}_{unit}`。

各服务必须暴露的指标：

| Metric | 类型 | 说明 |
|--------|------|------|
| `daduh_http_requests_total` | Counter | 按 method/status/endpoint 标记 |
| `daduh_http_request_duration_ms` | Histogram | 请求耗时分布 |
| `daduh_rule_extraction_duration_s` | Histogram | 规则抽取耗时 |

### 7.4 健康检查

每个服务暴露两个端点：

| 端点 | HTTP状态 | 返回体 | 用途 |
|------|---------|--------|------|
| `GET /health` | 200/503 | `{"status":"ok"}` | K8s liveness probe |
| `GET /ready` | 200/503 | `{"status":"ready","checks":{"db":"ok"}}` | K8s readiness probe，列出所有外部依赖的状态 |

---

## 8. 异步通知契约（共享约定）

验证阶段使用 **HTTP POST Callback** 方式传递异步通知，不引入消息队列。

### 8.1 通知方式

生产者完成处理后，向已注册的webhook地址发起HTTP POST，请求体JSON格式。每个回调超时2s，失败仅记WARN日志，不重试。

### 8.2 负载格式

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

### 8.3 本服务接收的通知

`POST /api/v1/rules/extract` 接口接收来自HT的异步通知。Request格式详见 §4.1。

### 8.4 本服务发出的通知

> 验证阶段LSL暂不主动通知下游（规则库由search-engine通过查询接口主动拉取）。
