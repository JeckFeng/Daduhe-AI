"""llm-gateway 服务模块。

- main.py:   FastAPI 应用入口，提供 completion/completion/stream 端点
- client.py: LLMClient — OpenAI 兼容客户端，支持 vLLM / DeepSeek 路由
- cache.py:  LLMCache — PG 持久化 LLM 缓存，带 TTL + 缓存键身份感知
- settings.py: Settings — 环境变量配置（LLM_GATEWAY_ 前缀）
"""
