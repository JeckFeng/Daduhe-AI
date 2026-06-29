"""服务配置 — 通过环境变量注入，前缀 AGENT_。

所有配置项均提供合理默认值，适合本地开发。
生产环境通过环境变量覆盖关键参数（如服务 URL）。
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """agent-reasoning 服务配置。

    Attributes:
        search_engine_url: search-engine 服务地址
        llm_gateway_url: llm-gateway 服务地址
        graph_engine_url: graph-engine 服务地址
        graph_search_top_k: 图谱检索返回结果数上限
        default_model: 默认 LLM 模型
        supervisor_temperature: Supervisor 节点 LLM 温度
        supervisor_max_tokens: Supervisor 节点最大输出 token
        context_resolution_temperature: 指代消解节点 LLM 温度
        context_resolution_max_tokens: 指代消解节点最大输出 token
        generator_temperature: 答案生成节点 LLM 温度
        generator_max_tokens: 答案生成节点最大输出 token
        fusion_top_k: 融合节点保留的 chunk 数量上限
    """

    model_config = {"env_prefix": "AGENT_"}

    # ── 上游服务 ──
    search_engine_url: str = "http://localhost:8002"
    llm_gateway_url: str = "http://localhost:8004"
    graph_engine_url: str = "http://localhost:8001"
    graph_search_top_k: int = 10

    # ── LLM 默认值（透传至 llm-gateway）──
    default_model: str = "vllm-local"

    # ── 各节点 LLM 参数 ──
    supervisor_temperature: float = 0.0
    supervisor_max_tokens: int = 500

    context_resolution_temperature: float = 0.0
    context_resolution_max_tokens: int = 500

    generator_temperature: float = 0.1
    generator_max_tokens: int = 2000

    # ── 融合 ──
    fusion_top_k: int = 10
