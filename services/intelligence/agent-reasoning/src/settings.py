"""agent-reasoning 配置 — YAML 文件提供默认值，环境变量 AGENT_ 前缀覆盖。

服务间调用 URL → config/services.yaml
LLM 参数（temperature 等）为业务调优值，保留 Python 默认值。
工具白名单从 config/tools.yaml 加载。
环境变量 > YAML 配置 > Python default
"""

from pathlib import Path
import yaml
from pydantic_settings import BaseSettings

# ── YAML 配置加载 ────────────────────────────────────────────
_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def _yaml(name: str) -> dict:
    path = _CONFIG_DIR / name
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


_services = _yaml("services.yaml")


def _get(d: dict, *keys, default=None):
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k)
        else:
            return default
    return default if d is None else d


class Settings(BaseSettings):
    """agent-reasoning 服务配置，环境变量前缀 AGENT_。

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
        tool_config_path: 工具白名单 YAML 配置文件路径
    """

    model_config = {"env_prefix": "AGENT_"}

    # ── 上游服务 ──
    search_engine_url: str = _get(
        _services, "agent_reasoning", "search_engine_url",
        default="http://localhost:8002",
    )
    llm_gateway_url: str = _get(
        _services, "agent_reasoning", "llm_gateway_url",
        default="http://localhost:8004",
    )
    graph_engine_url: str = _get(
        _services, "agent_reasoning", "graph_engine_url",
        default="http://localhost:8001",
    )
    graph_search_top_k: int = 10

    # ── LLM 默认值（透传至 llm-gateway）──
    default_model: str = _get(
        _services, "agent_reasoning", "default_model", default="vllm-local"
    )

    # ── 各节点 LLM 参数（业务调优）──
    supervisor_temperature: float = 0.0
    supervisor_max_tokens: int = 500

    context_resolution_temperature: float = 0.0
    context_resolution_max_tokens: int = 500

    generator_temperature: float = 0.1
    generator_max_tokens: int = 2000

    # ── 融合 ──
    fusion_top_k: int = 10

    # ── 配置文件路径 ──
    tool_config_path: str = "config/tools.yaml"

    # ── 工具白名单（从 YAML 延迟加载）──
    @property
    def tool_source_types(self) -> list[str]:
        """从 config/tools.yaml 加载启用的 source_type 白名单。

        YAML 格式::

            tool_source_types:
              - chunk
              - graph

        YAML 文件不存在或因其他原因加载失败时，返回最小安全默认值 ["chunk"]。

        Returns:
            list[str]: 启用的 source_type 列表
        """
        try:
            config_path = Path(self.tool_config_path)
            if not config_path.is_absolute():
                config_path = (
                    Path(__file__).resolve().parent.parent / self.tool_config_path
                )
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                types = data.get("tool_source_types", [])
                if isinstance(types, list) and len(types) > 0:
                    return types
        except Exception:
            pass
        return ["chunk"]
