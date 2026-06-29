# Issue 3a: LLM Client 与缓存

## Parent

PRD: graph-engine 知识图谱实体关系抽取与查询 — Issue 3: 实体关系抽取

## What to build

封装 LLM 调用层，通过 agent-reasoning 的 `/llm/completion` 进行 LLM 调用，并实现 PG 响应缓存。

1. **LLMProvider 接口抽象**：定义 `LLMProvider` protocol，方法为 `async def completion(system_prompt, user_prompt, response_format=None, model="deepseek-chat") -> dict`。默认实现走 agent-reasoning `/llm/completion`，为后续切换到独立 LLM 工⼚服务预留扩展点
2. **agent-reasoning LLM client**：封装 HTTP 调用（`POST /api/v1/llm/completion`），设置 `caller="graph-engine"`, `priority="batch"`，读取 `GRAPH_AGENT_LLM_URL` 配置，透传 `X-Trace-Id` header
3. **LLM 缓存**：实现 PG 缓存 CRUD（`graph_engine.llm_cache` 表）。cache_key = `md5(system_prompt + user_prompt + model)`。缓存命中直接返回 response JSONB，未命中调 LLM 后写入
4. 所有 HTTP 调用必须透传 `X-Trace-Id` header
5. batch 优先级超时 120s，发生超时或 4xx/5xx 错误时抛出明确异常

## Acceptance criteria

- [ ] `LLMProvider` protocol 定义清晰，可替换实现
- [ ] 调 agent-reasoning `/llm/completion` 成功返回 `{"content": "...", "model": "deepseek-chat", "usage": {...}, "latency_ms": N}`
- [ ] 第一次调用 `completion(system, user)` → LLM 实际调用 → 写入缓存
- [ ] 第二次相同参数调用 → 缓存命中，返回相同 content，不再调 LLM
- [ ] 不同 system prompt → 不同 cache_key → 分别缓存
- [ ] LLM 超时或失败 → 抛出异常（不静默吞掉）
- [ ] 调用日志含 trace_id、model、latency_ms

## Blocked by

- Issue 1（项目脚手架与配置基础设施）

## 开发规则

1. 只能使用 uv 虚拟环境（`cd services/intelligence && uv sync`），不要使用系统 python 虚拟环境
2. 开发中遇到的 BUG 都必须写入 `services/intelligence/memory/troubleshooting.md` 文档
