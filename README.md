# Daduhe-AI

大渡河公司基于大模型的水工建筑物缺陷智能诊疗技术研究与应用 — 课题二：水工缺陷治理知识萃取技术研究及知识库建立。

---


## 架构概览

```
文档解析与数据输入(HT) → 知识抽取层(LSL) → 知识图谱层(FXL) → 检索引擎层(FXL) → Agent推理层(FXL)
```

---

## 服务列表

| 服务 | 开发者 | 语言 | 端口 | 容器名 |
|------|--------|------|------|--------|
| doc-parser | HT | Java | 8080 | `doc-parser` |
| rule-extractor | LSL | TypeScript | 3000 | `rule-extractor` |
| graph-engine | FXL | Python | 8001 | `graph-engine` |
| search-engine | FXL | Python | 8002 | `search-engine` |
| agent-reasoning | FXL | Python | 8003 | `agent-reasoning` |

---

## 基础设施

| 组件 | 端口 |
|------|------|
| PostgreSQL | 5432 |
| MinIO | 9000 (API) / 9001 (Console) |
| Neo4j | 7474 (HTTP) / 7687 (Bolt) |
| Milvus | 19530 |
| Ollama | 11434 |

---

### 服务器配置
IP:10.222.124.211 

用户名：gyyknowledge

密码：gis31415



---

### PostgreSQL数据库配置
数据库用户名：daduhe;

数据库：mydatabase；

密码：gis31415;



### 建立postgre数据库SSH隧道
```bash 
ssh -L 5434:localhost:5432 gyyknowledge@10.222.124.211
```

---

### ollama 配置
embedding模型：bge-m3:latest

bge-m3:latest模型已经在服务器上通过ollama部署；

通过`ollama serve`命令启动ollama 服务

---

### vLLM配置
本地大模型正在部署中，可以先使用API-KEY

---

### Milvus部署
通过服务器podman部署

IP: 10.222.124.211 

端口:19530

账号：daduhe

密码：gis31415

数据库名称：daduhe_milvus_database

---

### 其他配置自行部署

---

## 种子数据约定

开发/测试阶段使用的 mock 数据，所有主键统一使用 `seed` 前缀，以便与正式数据区分：

| 资源 | 种子数据格式 | 正式数据格式 |
|------|------------|------------|
| `doc_id` | `seed-doc-{uuid}` | 由 doc-parser 生成 |
| `chunk_id` | `seed-chunk-{uuid}` | 由 doc-parser 生成 |
| `md_doc_id` | `seed-md-{uuid}` | 由 doc-parser 生成 |
| `embedding_id` | `seed-emb-{uuid}` | 由 doc-parser 生成 |

种子脚本和测试代码中所有自产主键均遵循此约定。检索时可通过 `doc_id` 前缀过滤排除种子数据。

## 快速启动

```bash
docker compose up -d
```

---

## 接口契约文档

详见 `docs/` 目录下的三份 ICD 文档。
