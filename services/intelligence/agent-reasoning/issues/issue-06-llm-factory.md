# Issue 6: LLM Completion Factory — LLM 调用工厂

## Type

AFK

## Blocked by

- Issue #1 (Foundation) — 仅依赖 Settings + 现有的 LLMClient

## What to build

实现 `POST /api/v1/llm/completion` 端点，作为 LLM 统一调用工厂供 graph-engine 等外部消费者使用。

**1. LLM 调用工厂端点**（`src/main.py` 更新已有 stub）

- 接收 `LLMCompletionRequest`：model / messages / temperature / max_tokens / priority / caller
- 模型路由：
  - `deepseek-chat` → DeepSeek API（使用 Settings.deepseek_api_key + deepseek_api_url）
  - `vllm-local` → 本地 vLLM（使用 Settings.vllm_url，api_key="none"）
- priority 超时策略：
  - `realtime` → Settings.realtime_timeout（默认 30s）
  - `batch` → Settings.batch_timeout（默认 120s）
- 调用 `LLMClient.completion()`
- 返回 `LLMCompletionResponse`：含 content、model、usage（prompt_tokens + completion_tokens）、latency_ms
- 日志记录：caller、model、priority、latency_ms

**2. LLMClient 完善**（`src/llm/client.py`）

当前 LLMClient 已实现惰性客户端创建。本 issue 只需确认：
- 支持本地 vLLM（model="vllm-local"）
- 支持 DeepSeek API（model="deepseek-chat"）
- token 用量统计正确
- 超时处理

**3. 端点测试**

使用真实本地 LLM 测试：
- 基本调用：发送单条 user message，返回 content
- 模型路由：指定 vllm-local 使用本地模型
- 超时：batch priority 使用更长超时
- 参数校验：缺少 messages 字段返回 422
- caller 字段记录在日志中

## Acceptance criteria

- [ ] `POST /api/v1/llm/completion` 调用本地 vLLM 返回正确 content
- [ ] model 参数路由到正确的后端（vllm-local vs deepseek-chat）
- [ ] priority 参数控制超时（realtime 30s, batch 120s）
- [ ] 返回 latency_ms 和 token 用量（prompt_tokens + completion_tokens）
- [ ] 参数校验：缺少 messages 返回 422
- [ ] 日志中包含 caller、model、priority、latency_ms
- [ ] 集成测试：真实本地 LLM，验证完整请求响应周期
