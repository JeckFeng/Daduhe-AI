"""共享配置加载工具 — 被各服务的 settings.py 引用。

加载 infrastructure.yaml 和 services.yaml，提供嵌套键读取函数。
YAML 文件不存在时返回空 dict，字段默认值由各 Settings 类的 default 参数兜底。
"""

from pathlib import Path
import yaml

_CONFIG_DIR = Path(__file__).resolve().parent


def _load_yaml(name: str) -> dict:
    path = _CONFIG_DIR / name
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


# 模块加载时一次性读取（文件很小，无需延迟加载）
_infra = _load_yaml("infrastructure.yaml")
_services = _load_yaml("services.yaml")


def get_infra(*keys: str, default=None):
    """从 infrastructure.yaml 按嵌套 key 读取配置值。

    Example: get_infra("postgresql", "host", default="localhost")
    """
    value = _infra
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            return default
    return default if value is None else value


def get_service(*keys: str, default=None):
    """从 services.yaml 按嵌套 key 读取配置值。

    Example: get_service("agent_reasoning", "llm_gateway_url")
    """
    value = _services
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            return default
    return default if value is None else value
