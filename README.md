# Daduhe-AI

大渡河公司基于大模型的水工建筑物缺陷智能诊疗技术研究与应用 — 课题二：水工缺陷治理知识萃取技术研究及知识库建立。

## 架构概览

```
文档解析与数据输入(HT) → 知识抽取层(LSL) → 知识图谱层(FXL) → 检索引擎层(FXL) → Agent推理层(FXL)
```

## 服务列表

| 服务 | 开发者 | 语言 | 端口 | 容器名 |
|------|--------|------|------|--------|
| doc-parser | HT | Java | 8080 | `doc-parser` |
| rule-extractor | LSL | TypeScript | 3000 | `rule-extractor` |
| graph-engine | FXL | Python | 8001 | `graph-engine` |
| search-engine | FXL | Python | 8002 | `search-engine` |
| agent-reasoning | FXL | Python | 8003 | `agent-reasoning` |

## 基础设施

| 组件 | 端口 |
|------|------|
| PostgreSQL | 5432 |
| MinIO | 9000 (API) / 9001 (Console) |
| Neo4j | 7474 (HTTP) / 7687 (Bolt) |
| Milvus | 19530 |
| Ollama | 11434 |

## 快速启动

```bash
docker compose up -d
```

## 接口契约文档

详见 `docs/` 目录下的三份 ICD 文档。
