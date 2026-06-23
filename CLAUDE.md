# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

大渡河水工建筑物缺陷智能诊疗系统 — 课题二「水工缺陷治理知识萃取技术研究及知识库建立」。采用微服务架构，分为三个层级、五个服务，由三位开发者并行开发。

## 架构与数据流

```
文档上传 → doc-parser(HT/Java) → 产出 chunk + embedding + 元数据
                │
                │ HTTP POST callback (异步通知, 无消息队列)
                ▼
        rule-extractor(LSL/TS) ──→ 规则库
                │                      │
                ▼                      ▼
        search-engine(FXL/Python) ←───┘
                │
                ▼
        agent-reasoning(FXL/Python) ←── graph-engine(FXL/Python) → Neo4j
                │
                ▼
        用户问答 (POST /api/v1/chat)
```

- **doc-parser** (HT, Java 21, Spring Boot 3.3, port 8080): 多格式文档解析（PDF/Word/Markdown/xlsx）、分块、向量化、元数据抽取。写入四层数据资产：`metadata.documents → metadata.markdown_docs → metadata.chunks → metadata.embeddings` + Milvus 向量。
- **rule-extractor** (LSL, TypeScript, Express, port 3000): 从 chunk 中抽取结构化规则（参数化阈值、条件），构建可检索规则库供下游查询。
- **graph-engine** (FXL, Python, FastAPI, port 8001): LLM 驱动的实体关系抽取，写入 Neo4j，提供 Cypher 推理查询。
- **search-engine** (FXL, Python, FastAPI, port 8002): 多模式检索（keyword/fuzzy/vector/hybrid），同时检索 Milvus 中的 chunk 和 LSL 的规则库。
- **agent-reasoning** (FXL, Python, FastAPI, port 8003): 意图识别 → 检索模式选择 → 调用 search-engine → LLM 生成答案 → 组装溯源引用。也作为 LLM 调用工厂供 graph-engine 使用。

## 基础设施

| 组件 | 端口 | 凭据/备注 |
|------|------|----------|
| PostgreSQL (pgvector) | 5432 | `daduhe`/`daduhe_dev`, 数据库 `daduhe` |
| MinIO | 9000 (API), 9001 (Console) | `minioadmin`/`minioadmin` |
| Neo4j | 7474 (HTTP), 7687 (Bolt) | `neo4j`/`daduhe123` |
| Milvus | 19530 | 生产环境: `daduhe`/`gis31415`@10.222.124.211 |
| Ollama | 11434 | 本地 embedding 模型 `bge-m3:latest` |
| etcd | 2379 | Milvus 依赖 |

**服务器**: 10.222.124.211, 用户 `gyyknowledge`/`gis31415`

**SSH 隧道连接远程 PostgreSQL**:
```bash
ssh -L 5434:localhost:5432 gyyknowledge@10.222.124.211
```

## 开发命令

### 全部启动
```bash
docker compose up -d
```

### doc-parser (Java)
```bash
cd services/doc-parser
./mvnw spring-boot:run          # 开发运行
./mvnw clean package -DskipTests # 构建 JAR
```

### rule-extractor (TypeScript)
```bash
cd services/rule-extractor
npm run dev      # tsx watch 热重载开发
npm run build    # tsc 编译
npm run start    # 运行编译产物
```

### intelligence 三个服务 (Python)
```bash
cd services/intelligence
# graph-engine
cd graph-engine && pip install -r requirements.txt && uvicorn src.main:app --reload --port 8001
# search-engine
cd search-engine && pip install -r requirements.txt && uvicorn src.main:app --reload --port 8002
# agent-reasoning
cd agent-reasoning && pip install -r requirements.txt && uvicorn src.main:app --reload --port 8003
```

## 跨服务约定（ICD 文档详见 docs/）

### 异步通知
验证阶段不引入消息队列，使用 **HTTP POST callback**。doc-parser 完成处理后向三个下游 webhook 发通知（超时 2s，失败仅记 WARN 日志不重试）。所有接收方必须对 `doc_id` 做幂等处理。

### 链路追踪
所有服务间 HTTP 调用必须通过 Header 传递 `X-Trace-Id`，格式 `{service}-{uuid_v4}`（如 `ht-a1b2c3d4-...`）。接收方透传收到的 trace_id。

### 错误码体系
业务错误码 = `段号 × 1000 + 序号`（0=成功，1xxx=参数错误，3xxx=资源不存在，4xxx=上游失败，5xxx=业务错误，9xxx=内部错误）。所有响应体统一 `{"code": N, "message": "...", "trace_id": "..."}`。

### 日志规范
JSON 结构化日志，必含字段: `timestamp` `level` `service` `trace_id` `message`。输出到 stderr。

### 健康检查
每个服务暴露 `GET /health`（liveness）和 `GET /ready`（readiness，列出外部依赖状态）。另暴露 `GET /metrics`（Prometheus 格式，命名前缀 `daduh_`）。

### 溯源链路完整性
检索结果通过 `chunk_id` → `metadata.chunks`（获取 page_number/section_number）→ `doc_id` → `metadata.documents`（获取 title/download_url），不得跳过任何一级。下载链接统一调用 `GET /api/v1/documents/{doc_id}/download`（MinIO 预签名 URL），不得直接拼接 MinIO 路径。

### LLM 调用
通过 agent-reasoning 的 `POST /api/v1/llm/completion` 统一调用。`deepseek-chat` 走 DeepSeek API，`vllm-local` 走本地 vLLM。realtime 超时 30s，batch 超时 120s。

## 当前实现状态

所有五个服务均已搭建框架（仅 stubs），共同模块（tracing/logging/health/error_codes）已实现，业务逻辑标记为 TODO。doc-parser 的 Maven 依赖（Tika、MinIO SDK、Milvus SDK）已配置。
