"""LLM 调用层：客户端、缓存、协议抽象。

- client.py:   AgentReasoningLLMClient — 通过 agent-reasoning 网关调用 LLM
- cache.py:    LLMCache — PostgreSQL 缓存的 LLM 响应缓存
- provider.py: LLMProvider — LLM 后端的 Protocol 抽象
"""
