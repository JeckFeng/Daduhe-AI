# rule-extractor 启动指南

## 服务简介

知识抽取层 — 从 doc-parser 产出的 chunk 中抽取结构化规则（参数化阈值、条件），构建可检索规则库。TypeScript + Express，端口 3000。

## 前置依赖

- **Node.js** >= 22（本地开发）
- **PostgreSQL**（存储规则数据）
- **doc-parser**（上游服务，提供 chunk 数据）
- **DeepSeek API Key**（可选，LLM 抽取规则时需要）

## 本地开发启动

```bash
cd services/rule-extractor

# 安装依赖（自动安装到当前项目 node_modules/，不影响系统）
npm install

# 设置环境变量
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=daduhe
export DB_PASSWORD=daduhe_dev
export DB_NAME=daduhe
export DOC_PARSER_URL=http://localhost:8080
export DEEPSEEK_API_KEY=sk-xxxxx    # 可选，使用 LLM 抽取时需要

# 热重载开发模式
npm run dev:watch

# 或者一次性构建 + 运行
npm run build && npm run start
```

### 可用脚本

| 命令 | 说明 |
|------|------|
| `npm run dev:watch` | tsx watch 热重载，改代码自动重启 |
| `npm run build` | TypeScript 编译到 dist/ |
| `npm run dev` | build + start 一键运行 |
| `npm run start` | 直接运行编译产物 dist/index.js |

### 本地运行时基础设施

本地跑需要 PostgreSQL 可用。如果基础设施还没起来，在项目根目录执行：

```bash
docker compose up -d postgres doc-parser
```

这样就可以只跑 rule-extractor 依赖的两个服务，rule-extractor 本身用 npm 本地调试。

## Docker 启动

```bash
# 项目根目录下
docker compose up -d rule-extractor
```

Docker Compose 已配好所有环境变量，无需额外设置。DeepSeek API Key 通过 host 环境变量传入：

```bash
DEEPSEEK_API_KEY=sk-xxxxx docker compose up -d rule-extractor
```

### 构建新镜像

如果代码有变更需要重新构建：

```bash
docker compose build rule-extractor
docker compose up -d rule-extractor
```

## 启动全部服务

```bash
# 项目根目录，启动所有微服务 + 基础设施
docker compose up -d
```

## 健康检查

```bash
# Liveness
curl http://localhost:3000/health

# Readiness（包含外部依赖状态）
curl http://localhost:3000/ready
```

## 注意事项

- rule-extractor 对 `doc_id` 做幂等处理（通过 extraction_tasks 表状态），重复通知不会重复抽取。
- 所有请求需要携带 `X-Trace-Id` Header，格式 `{caller}-{uuid_v4}`。
