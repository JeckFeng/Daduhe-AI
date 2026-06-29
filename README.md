# Daduhe-AI

大渡河公司基于大模型的水工建筑物缺陷智能诊疗技术研究与应用 — 课题二：水工缺陷治理知识萃取技术研究及知识库建立。

---


## 架构概览

```
文档解析与数据输入(HT) → 知识抽取层(LSL) → 知识图谱层(FXL) → 检索引擎层(FXL) → Agent推理层(FXL)
                                                    ↑                        │
                                                    │     llm-gateway:8004    │
                                                    └────────── 共 用 ────────┘
                                          (LLM调用工厂 + PG缓存)
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
| llm-gateway | FXL | Python | 8004 | `llm-gateway` |

---

## 基础设施

| 组件 | 端口 |
|------|------|
| PostgreSQL | 5432 |
| MinIO | 9000 (API) / 9001 (Console) |
| Memgraph | 17687 (Bolt) / 17444 (HTTP/Lab) |
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

### 建立Memgraph SSH隧道
```bash 
ssh -L 17687:localhost:17687 gyyknowledge@10.222.124.211
```

---

### ollama 配置
embedding模型：bge-m3:latest

bge-m3:latest模型已经在服务器上通过ollama部署；

通过`ollama serve`命令启动ollama 服务

### 建立Ollama的SSH隧道
```bash 
ssh -L 11435:localhost:11434 gyyknowledge@10.222.124.211
```
---

## 服务器已部署的大模型

### Qwen3.6-27B-GGUF

**部署方式**: 通过 llama.cpp 部署

```bash
cd /home/gyyknowledge/llama.cpp/build/bin
./llama-server -m ~/modelscope/Qwen3.6-27B-GGUF/Qwen3.6-27B-Q4_K_M.gguf \
  --mmproj ~/modelscope/Qwen3.6-27B-GGUF/mmproj-Qwen3.6-27B-BF16.gguf \
  --port 8000 --host 0.0.0.0 -ngl 99 --jinja -cb -t 12 -b 1024 -ub 512 \
  --reasoning off --flash-attn on --spec-type ngram-map-k4v
```

**推荐使用场景**: 知识推理

### Qwen3.6-35B-A3B-GGUF

**部署方式**: 通过 llama.cpp 部署

```bash
cd /home/gyyknowledge/llama.cpp/build/bin
./llama-server -m ~/modelscope/Qwen3.6-35B-A3B-GGUF/Qwen3.6-35B-A3B-Q4_K_M.gguf \
  --mmproj ~/modelscope/Qwen3.6-35B-A3B-GGUF/mmproj-Qwen3.6-35B-A3B-BF16.gguf \
  --port 8000 --host 0.0.0.0 -ngl 99 --jinja -cb -t 12 -b 1024 -ub 512 \
  --reasoning off --flash-attn on --spec-type ngram-map-k4v
```

**推荐使用场景**: 图像识别、知识推理

### llama-server 参数说明

| 参数 | 含义 | 详细说明 |
| :--- | :--- | :--- |
| `-m` | 模型路径 (Model) | 指定加载的 GGUF 格式主模型文件路径。 |
| `--mmproj` | 多模态投影文件 | 用于视觉模型，将视觉特征投射到文本空间；纯文本模型可省略。 |
| `--port` | 服务端口 | 指定 HTTP 服务监听的端口号（如 8000）。 |
| `--host` | 监听地址 | `0.0.0.0` 允许远程访问，`127.0.0.1` 仅限本机。 |
| `-ngl` | GPU 卸载层数 | 强制将 99 层模型加载至 GPU，速度最快 |
| `--jinja` | Jinja 模板引擎 | 启用对话模板，确保输入格式与模型训练时一致。 |
| `-cb` | 上下文缓存优化 | 是否启用连续分批功能，有助于批量请求时更高效管理内存 |
| `-t` | CPU线程数 | CPU 并行推理的线程数量（如 12）。 |
| `-b` | 逻辑批次 | 每次推理处理的Token批大小。1024较大，适合吞吐量，但显存占用高 |
| `-ub` | 实际批次大小 | 单次内核调用所处理的最大Token数 |
| `--reasoning off` | 推理模式 | `off` 关闭思维链输出，`on` 则显示推理过程。 |
| `--flash-attn on` | 快速注意力机制 | 开启后可降低显存并加速长文本推理。 |
| `--spec-type` | 推测解码类型 | 使用 n-gram 缓存加速生成（如 `ngram-map-k4v`）。 |

---

### Milvus部署
通过服务器podman部署

IP: 10.222.124.211 

端口:19530

账号：daduhe

密码：gis31415

数据库名称：daduhe_milvus_database

---

容器启动命令：
```bash
podman run -d   --name milvus-standalone   --security-opt seccomp:unconfined   -e ETCD_USE_EMBED=true   -e ETCD_DATA_DIR=/var/lib/milvus/etcd   -e ETCD_CONFIG_PATH=/milvus/configs/embedEtcd.yaml   -e COMMON_STORAGETYPE=local   -e DEPLOY_MODE=STANDALONE   -v $(pwd)/volumes/milvus:/var/lib/milvus   -v $(pwd)/embedEtcd.yaml:/milvus/configs/embedEtcd.yaml   -v $(pwd)/user.yaml:/milvus/configs/user.yaml   -p 19530:19530   -p 9091:9091   -p 2379:2379   --health-cmd="curl -f http://localhost:9091/healthz"   --health-interval=30s   --health-start-period=90s   --health-timeout=20s   --health-retries=3   docker.m.daocloud.io/milvusdb/milvus:v3.0-beta   milvus run standalone

```

### 其他配置自行部署

---

<<<<<<< HEAD
=======
## LLM 缓存

llm-gateway 内置 PG 缓存，key=`md5(system+user+model+host)`，TTL 默认 7 天。

| 配置项 | 环境变量 | 默认值 |
|--------|---------|--------|
| 缓存 TTL | `LLM_GATEWAY_CACHE_TTL_SECONDS` | `604800`（7天），设为 0 禁用缓存 |
| PG 连接 | `LLM_GATEWAY_PG_HOST/PORT/USER/PASSWORD/DATABASE` | 同 graph-engine |

---

>>>>>>> intelligence
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
