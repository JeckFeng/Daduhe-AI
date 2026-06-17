# ICD-01：文档解析与数据输入层（HT）

## 契约先行、并行开发

| 负责人 | 开发语言 | 服务名 |
|--------|---------|--------|
| HT | Java | doc-parser |

---

## 1. 服务职责

将多格式文档（PDF/Word/Markdown/xlsx/txt/csv）接入系统，完成解析、标准化、分块、向量化和元数据抽取，统一交付四类数据资产供下游消费。

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

## 3. 数据资产与映射关系

HT层产出的四层数据资产及其映射关系：

```
┌──────────────────────────────────────────────────────────────────┐
│                      四层数据资产映射关系                           │
│                                                                  │
│  原始文档 (MinIO: raw-docs/)                                      │
│    doc_id ──────────────────────────── 下载链接的基础              │
│    │  1:1                                                         │
│    ▼                                                              │
│  Markdown文档 (MinIO: markdown-docs/)                             │
│    doc_id (外键 → 原始文档)                                        │
│    │  1:N                                                         │
│    ▼                                                              │
│  Chunk (PostgreSQL + MinIO JSON)                                  │
│    chunk_id (全局唯一)                                             │
│    doc_id (外键 → 原始文档)          ← 溯源的关键: 知道来自哪个文档   │
│    page_number / section_number      ← 溯源的关键: 知道来自哪一页/节│
│    │  1:1                                                         │
│    ▼                                                              │
│  Embedding向量 (Milvus)                                           │
│    milvus_id (Milvus主键)                                         │
│    chunk_id (外键 → Chunk)           ← 检索后反查chunk的唯一桥梁    │
│    vector (浮点数组)                                              │
└──────────────────────────────────────────────────────────────────┘
```

**检索→溯源的完整链路**：

```
用户query → embed(query) → Milvus相似度检索
                              │
        返回: [milvus_id, chunk_id, score]
                              │
                    ┌─────────┘
                    ▼
          通过 chunk_id 查 PostgreSQL metadata.embeddings
            → 确认 embedding_model / vector_dimension
                    │
                    ▼
          通过 chunk_id 查 PostgreSQL metadata.chunks
            → 获取 chunk_text, doc_id, page_number, section_number
                    │
                    ▼
          通过 doc_id 查 PostgreSQL metadata.documents
            → 获取 doc_type, title, file_path(→下载链接)
                    │
                    ▼
          组装LLM上下文:
            chunk_text + doc_type + title + section_number + page_number
                    │
                    ▼
          LLM生成答案，附带引用标注
          前端渲染: 来源标题 + 章节 + 页码 + 下载链接
```

---

## 4. 元数据表结构（PostgreSQL）

以下为HT层写入、下游服务只读的表结构。这是服务间的数据契约，下游按此Schema读取。

### 4.1 原始文档元数据 — `metadata.documents`

```sql
CREATE TABLE metadata.documents (
    doc_id           VARCHAR(64) PRIMARY KEY,         -- UUID，HT入库时生成
    doc_type         VARCHAR(32)  NOT NULL,           -- 枚举: 规范/文献/案例报告/图纸/监测数据
    title            VARCHAR(512) NOT NULL,
    authors          TEXT[],                           -- PostgreSQL数组
    source_org       VARCHAR(256),
    publish_date     DATE,
    version          VARCHAR(32),
    language         VARCHAR(16)  DEFAULT 'zh-CN',
    file_format      VARCHAR(16)  NOT NULL,           -- pdf/word/markdown/xlsx/txt/csv
    file_path        VARCHAR(1024) NOT NULL,          -- MinIO对象路径，下游用于生成预签名下载URL
    file_size_bytes  BIGINT,
    permission_level VARCHAR(16)  DEFAULT 'internal', -- public/internal/restricted
    tags             TEXT[],
    abstract         TEXT,
    uploaded_at      TIMESTAMPTZ  DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  DEFAULT NOW()
);
```

### 4.2 Markdown文档元数据 — `metadata.markdown_docs`

```sql
CREATE TABLE metadata.markdown_docs (
    md_doc_id          VARCHAR(64) PRIMARY KEY,        -- UUID
    doc_id             VARCHAR(64) NOT NULL REFERENCES metadata.documents(doc_id),
    conversion_method  VARCHAR(32) NOT NULL,            -- direct(直接转换) / ocr(OCR识别)
    conversion_time_ms INTEGER,
    md_file_path       VARCHAR(1024) NOT NULL,          -- MinIO markdown对象路径
    md_hash            VARCHAR(64),                     -- SHA256，完整性校验
    created_at         TIMESTAMPTZ DEFAULT NOW()
);
```

### 4.3 Chunk元数据 — `metadata.chunks`

**这是溯源的核心表。** 检索引擎返回chunk_id后，Agent推理层查此表获取精确定位信息用于引用标注。

```sql
CREATE TABLE metadata.chunks (
    chunk_id         VARCHAR(64) PRIMARY KEY,          -- UUID，全局唯一
    doc_id           VARCHAR(64) NOT NULL REFERENCES metadata.documents(doc_id),
    chunk_index      INTEGER NOT NULL,                 -- 在文档内的序号（从1开始）
    chunk_text       TEXT NOT NULL,                    -- chunk文本内容，直接可用作LLM上下文
    page_number      INTEGER,                          -- 起始页码
    section_title    VARCHAR(256),                     -- 所在章节标题
    section_number   VARCHAR(32),                      -- 章节编号，如 "5.2.3"
    char_start       INTEGER,                          -- 在markdown原文中的起始字符偏移
    char_end         INTEGER,                          -- 在markdown原文中的结束字符偏移
    token_count      INTEGER,                          -- token数估算（基于所用embedding模型的tokenizer）
    parent_chunk_id  VARCHAR(64),                      -- 父子chunk预留: 指向更大的父段落
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_chunks_doc_id ON metadata.chunks(doc_id);
CREATE INDEX idx_chunks_section ON metadata.chunks(doc_id, section_number);
```

### 4.4 Embedding向量元数据 — `metadata.embeddings`

```sql
CREATE TABLE metadata.embeddings (
    embedding_id      VARCHAR(64) PRIMARY KEY,
    chunk_id          VARCHAR(64) NOT NULL REFERENCES metadata.chunks(chunk_id),
    embedding_model   VARCHAR(64) NOT NULL,            -- 如 "bge-m3"
    vector_dimension  INTEGER NOT NULL,                -- 如 1024
    milvus_id         BIGINT NOT NULL,                 -- Milvus中对应向量的主键ID
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- chunk_id唯一约束: 一个chunk只对应一个向量
CREATE UNIQUE INDEX idx_embeddings_chunk_id ON metadata.embeddings(chunk_id);
-- milvus_id索引: 从Milvus检索结果反查chunk
CREATE INDEX idx_embeddings_milvus_id ON metadata.embeddings(milvus_id);
```

---

## 5. Chunk JSON结构

除写入PostgreSQL外，每个chunk也以JSON文件形式存储于MinIO，供下游批量读取或离线处理。

**存储路径**: `chunks/{doc_id}/chunk_{chunk_index:06d}.json`

```json
{
  "chunk_id": "c1b2a3d4-e5f6-7890-abcd-ef1234567890",
  "doc_id": "d9e8f7a6-e5f6-7890-abcd-ef1234567890",
  "chunk_index": 42,
  "chunk_text": "5.2.3 裂缝处理标准\n当裂缝宽度大于0.3mm时，应采取灌浆或表面封闭处理措施。对于深层裂缝，应优先采用灌浆法；对于表层裂缝，可采用表面封闭法。",
  "page_number": 23,
  "section_title": "裂缝处理标准",
  "section_number": "5.2.3",
  "char_start": 18420,
  "char_end": 18650,
  "token_count": 68
}
```

**字段说明（从RAG视角）**:

| 字段 | LLM上下文 | 溯源引用 | 说明 |
|------|:---------:|:-------:|------|
| `chunk_text` | ✅ 注入Prompt | ✅ 引用原文 | chunk核心内容 |
| `chunk_id` | — | — | 全局唯一标识，检索反查的主键 |
| `doc_id` | — | — | 关联文档元数据和下载链接 |
| `chunk_index` | — | — | 文档内顺序，合并相邻chunk时使用 |
| `page_number` | — | ✅ 页码引用 | "见第23页" |
| `section_title` | 可选注入 | ✅ 章节引用 | "裂缝处理标准" |
| `section_number` | 可选注入 | ✅ 条款引用 | "第5.2.3条" |
| `char_start` / `char_end` | — | 定位原文 | 下游如需高亮原文段落时使用 |
| `token_count` | ✅ 控制上下文长度 | — | Agent拼接多个chunk时计算是否超出LLM上下文窗口 |

---

## 6. Milvus向量库结构

### 6.1 Collection定义

Collection名称: `chunks`

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `id` | int64 (主键, 自增) | Milvus内部ID |
| `chunk_id` | VarChar(64) | **检索结果反查chunk的唯一桥梁** |
| `doc_id` | VarChar(64) | 文档ID，支持按文档过滤检索 |
| `vector` | FloatVector(1024) | embedding向量，维度取决于模型（bge-m3 = 1024） |

### 6.2 索引配置

```python
index_params = {
    "metric_type": "COSINE",          # 余弦相似度
    "index_type": "IVF_FLAT",        # 或 HNSW
    "params": {"nlist": 1024}
}
```

### 6.3 检索反查流程

Milvus检索返回 `[id, chunk_id, doc_id, score]`。下游通过 `chunk_id` 查 `metadata.chunks` 获取chunk全文和页码/章节，再通过 `doc_id` 查 `metadata.documents` 获取文档标题、类型和下载路径。

```python
# 伪代码: 检索并组装溯源信息
results = milvus.search(vector=query_embedding, limit=10)
# results: [{id: 12345, chunk_id: "c1b2...", doc_id: "d9e8...", score: 0.92}, ...]

for r in results:
    chunk  = db.query("SELECT * FROM metadata.chunks WHERE chunk_id = %s", r["chunk_id"])
    doc    = db.query("SELECT * FROM metadata.documents WHERE doc_id = %s", r["doc_id"])
    # 组装LLM上下文:
    #   chunk.chunk_text
    #   + "来源: " + doc.title + " " + chunk.section_number + " 第" + chunk.page_number + "页"
    #   + "下载: /api/v1/documents/" + doc.doc_id + "/download"
```

---

## 7. 对外接口

### 7.1 文档上传

```
POST /api/v1/documents/upload
Content-Type: multipart/form-data
```

**Request**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | binary | 是 | 文档文件 |
| metadata | JSON(string) | 否 | 预填元数据，未填字段由服务自动抽取 |

metadata JSON：

```json
{
  "doc_type": "规范",
  "title": "混凝土坝安全监测技术规范",
  "authors": ["张三", "李四"],
  "source_org": "国家能源局",
  "publish_date": "2023-06-01",
  "version": "1.0",
  "tags": ["混凝土坝", "裂缝", "监测"],
  "permission_level": "internal"
}
```

**Response** (HTTP 202)

```json
{
  "code": 0,
  "message": "accepted",
  "data": {
    "doc_id": "d9e8f7a6-e5f6-7890-abcd-ef1234567890",
    "status": "pending"
  }
}
```

---

### 7.2 查询处理状态

```
GET /api/v1/documents/{doc_id}/status
```

**Response** (HTTP 200)

```json
{
  "code": 0,
  "data": {
    "doc_id": "d9e8f7a6-e5f6-7890-abcd-ef1234567890",
    "status": "completed",
    "stages": {
      "parsed": "done",
      "converted_to_markdown": "done",
      "chunked": "done",
      "embedded": "done",
      "metadata_extracted": "done"
    },
    "chunk_count": 156,
    "error_message": null,
    "created_at": "2026-06-17T10:00:00Z",
    "completed_at": "2026-06-17T10:02:30Z"
  }
}
```

status枚举：`pending` → `parsing` → `converting` → `chunking` → `embedding` → `completed` / `failed`

---

### 7.3 下载原始文档

```
GET /api/v1/documents/{doc_id}/download
```

**Response** (HTTP 302)

重定向到MinIO预签名URL，浏览器直接触发下载。链接有效期1小时。

---

### 7.4 查询Chunk列表

```
GET /api/v1/chunks?doc_id={doc_id}&page={page}&page_size={page_size}
```

**Response** (HTTP 200)

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "chunk_id": "c1b2a3d4-e5f6-7890-abcd-ef1234567890",
        "doc_id": "d9e8f7a6-e5f6-7890-abcd-ef1234567890",
        "chunk_index": 42,
        "chunk_text": "5.2.3 裂缝处理标准\n当裂缝宽度大于0.3mm时，应采取灌浆或表面封闭处理措施...",
        "page_number": 23,
        "section_title": "裂缝处理标准",
        "section_number": "5.2.3",
        "char_start": 18420,
        "char_end": 18650,
        "token_count": 68,
        "doc_title": "混凝土坝安全监测技术规范",
        "doc_type": "规范"
      }
    ],
    "total": 156,
    "page": 1,
    "page_size": 50
  }
}
```

---

### 7.5 查询单个Chunk

```
GET /api/v1/chunks/{chunk_id}
```

**Response** (HTTP 200)

```json
{
  "code": 0,
  "data": {
    "chunk_id": "c1b2a3d4-e5f6-7890-abcd-ef1234567890",
    "doc_id": "d9e8f7a6-e5f6-7890-abcd-ef1234567890",
    "chunk_index": 42,
    "chunk_text": "5.2.3 裂缝处理标准\n当裂缝宽度大于0.3mm时，应采取灌浆或表面封闭处理措施...",
    "page_number": 23,
    "section_title": "裂缝处理标准",
    "section_number": "5.2.3",
    "char_start": 18420,
    "char_end": 18650,
    "token_count": 68,
    "doc_title": "混凝土坝安全监测技术规范",
    "doc_type": "规范",
    "download_url": "/api/v1/documents/d9e8f7a6-e5f6-7890-abcd-ef1234567890/download"
  }
}
```

---

### 7.6 跨文档元数据查询

```
GET /api/v1/metadata/search?keyword={keyword}&doc_type={doc_type}&page={page}&page_size={page_size}
```

**Response** (HTTP 200)

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "doc_id": "d9e8f7a6-e5f6-7890-abcd-ef1234567890",
        "doc_type": "规范",
        "title": "混凝土坝安全监测技术规范",
        "authors": ["张三"],
        "source_org": "国家能源局",
        "publish_date": "2023-06-01",
        "version": "1.0",
        "tags": ["混凝土坝", "裂缝"],
        "permission_level": "internal",
        "download_url": "/api/v1/documents/d9e8f7a6-e5f6-7890-abcd-ef1234567890/download"
      }
    ],
    "total": 23,
    "page": 1,
    "page_size": 20
  }
}
```

---

## 8. 异步通知

HT不引入消息队列。处理管线全部完成后，通过HTTP POST逐一回调下游服务已注册的webhook地址。下游服务自身需幂等处理（同一doc_id重复通知不产生副作用）。

### 8.1 回调负载

三个下游回调使用相同的JSON格式：

```json
{
  "event_id": "evt-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "trace_id": "ht-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "doc_id": "d9e8f7a6-e5f6-7890-abcd-ef1234567890",
  "doc_type": "规范",
  "title": "混凝土坝安全监测技术规范",
  "chunk_count": 156,
  "embedding_model": "bge-m3",
  "embedding_dimension": 1024,
  "status": "completed"
}
```

### 8.2 回调目标

| 下游服务 | 回调地址 | 用途 |
|---------|---------|------|
| rule-extractor (LSL) | `POST {lsl}/api/v1/rules/extract` | 触发规则抽取 |
| graph-engine (FXL) | `POST {fxl-graph}/api/v1/graph/extract` | 触发实体关系抽取 |
| search-engine (FXL) | `POST {fxl-search}/api/v1/search/index` | 触发检索索引构建 |

每个回调超时2s，失败仅记录WARN日志（不重试，不阻塞）。处理状态可通过 `GET /api/v1/documents/{doc_id}/status` 中的 `stages` 字段查询。

---

## 9. 需要从其他服务消费的接口

HT层是数据入口，不调用其他服务。

---

## 10. 错误码体系

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
| 5001 | `document processing failed: {reason}` | 文档处理失败 |
| 9001 | `internal error: {detail}` | 内部未知错误 |

错误响应体格式：

```json
{
  "code": 40001,
  "message": "doc_id not found: d9e8f7a6-e5f6-7890-abcd-ef1234567890",
  "trace_id": "ht-a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

---

## 11. 超时约定

| 调用类型 | 超时时间 | 说明 |
|---------|---------|------|
| 查询类同步API | 5s | `GET /chunks`, `GET /metadata/search` 等 |
| 触发类同步API | 2s | `POST /documents/upload` 返回202即完成，不阻塞 |
| 文档全管线异步处理 | 15min | 上传→解析→chunk→向量→元数据全部完成 |
| LLM同步调用 | 30s | 在线推理 |
| LLM批量调用 | 120s | 离线抽取 |

---

## 12. 可观测契约

### 12.1 链路追踪

所有服务间HTTP调用必须通过Header传递 `X-Trace-Id`：

```
X-Trace-Id: {service_short}-{uuid_v4}
示例: ht-a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

- 外部请求进入时，接收方生成trace_id
- 调用下游时，透传收到的trace_id

### 12.2 日志规范

统一JSON结构化日志，每行一条。

```json
{
  "timestamp": "2026-06-17T10:02:30.123Z",
  "level": "INFO",
  "service": "doc-parser",
  "trace_id": "ht-a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "message": "chunk splitting completed",
  "detail": {
    "doc_id": "d9e8f7a6-e5f6-7890-abcd-ef1234567890",
    "chunk_count": 156,
    "duration_ms": 2300
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

### 12.3 Metrics

每个服务暴露 `/metrics` 端点（Prometheus格式）。统一命名：`daduh_{metric}_{unit}`。

各服务必须暴露的指标：

| Metric | 类型 | 说明 |
|--------|------|------|
| `daduh_http_requests_total` | Counter | 按 method/status/endpoint 标记 |
| `daduh_http_request_duration_ms` | Histogram | 请求耗时分布 |
| `daduh_doc_processing_duration_s` | Histogram | 文档全管线耗时（HT） |

### 12.4 健康检查

每个服务暴露两个端点：

| 端点 | HTTP状态 | 返回体 | 用途 |
|------|---------|--------|------|
| `GET /health` | 200/503 | `{"status":"ok"}` | K8s liveness probe |
| `GET /ready` | 200/503 | `{"status":"ready","checks":{"db":"ok","milvus":"ok"}}` | K8s readiness probe，列出所有外部依赖的状态 |

---

## 13. 异步通知契约（共享约定）

验证阶段使用 **HTTP POST Callback** 方式传递异步通知，不引入消息队列。

### 13.1 通知方式

生产者（如HT）完成处理后，向已注册的下游webhook地址发起HTTP POST，请求体JSON格式。每个回调超时2s，失败仅记WARN日志，不重试。

### 13.2 负载格式

所有异步通知统一使用以下JSON结构：

```json
{
  "event_id": "evt-{uuid}",
  "trace_id": "{service_short}-{uuid_v4}",
  "doc_id": "...",
  "status": "completed"
}
```

具体业务字段由各接口的Request定义（如LSL §3.1 `POST /rules/extract`、FXL §3.1 `POST /graph/extract`）。

### 13.3 幂等要求

所有接收异步通知的接口必须对 `doc_id` 做幂等处理——同一 `doc_id` 的重复通知不产生副作用（如重复抽取应跳过或覆盖而非追加）。

---

## 14. 下游集成约定

HT不关心下游如何使用数据，但为确保多开发者并行时不出现集成断层，约定以下最低要求：

| 约定项 | 要求 |
|--------|------|
| **chunk_id作为检索反查主键** | 检索引擎（FXL）在Milvus中必须以`chunk_id`为外键关联向量。检索结果必须返回`chunk_id` |
| **溯源链路完整性** | Agent推理层生成答案引用时，必须通过`chunk_id`→查chunk表获取`page_number/section_number`→通过`doc_id`查documents表获取`title/download_url`——不得跳过任何一级 |
| **下载链接生成** | 前端渲染引用时，调用 `GET /api/v1/documents/{doc_id}/download` 获取预签名URL。不得直接拼接MinIO路径 |
| **多chunk拼接时Token管理** | Agent推理层通过 `token_count` 字段累加计算是否超出LLM上下文窗口上限 |
