"""Prompt 配置加载器：加载实体抽取的 YAML prompt 配置。

优先从 YAML 文件加载，文件不存在时回退到内置默认配置。
内置默认配置覆盖水利工程领域的实体类型和关系类型。
"""

from pathlib import Path

import yaml

from src.settings import Settings

# 内置默认实体类型引导（水利工程领域）
_BUILTIN_ENTITY_TYPES_GUIDANCE = """
- Project: 水电站工程的名称，如"铜街子水电站"、"深溪沟水电站"。
- Region: 工程所属的地理区域或流域，如"大渡河流域"、"四川省"。
- Structure: 水工建筑物及其结构部件，如混凝土坝、消力池、泄水闸、闸门等。
- DefectLocation: 缺陷发生的具体部位，如"上游面"、"坝踵"、"消力池底板"、"伸缩缝"。
- DefectType: 缺陷类型，如"裂缝"、"渗漏"、"碳化"、"冲刷"、"变形"、"沉降"、"滑坡"等。
- DefectImpact: 缺陷造成的影响，如"结构安全性降低"、"承载能力不足"。
- DefectAssessment: 缺陷评价/分级，如"较大缺陷"、"轻微渗漏"、"严重碳化"。
- Treatment: 治理措施与工艺，如"帷幕灌浆"、"化学灌浆"、"表面封闭法"。
- Material: 材料，如"环氧树脂"、"聚氨酯浆材"、"碳纤维布"。
- DetectionMethod: 检测方法，如"回弹法"、"钻芯法"、"超声-回弹综合法"。
- NormClause: 规范条款，如"DL/T 2628-2023 §5.2.3"。
- Parameter: 技术参数/阈值，如"裂缝宽度>0.3mm"、"渗漏量>1.0L/s"。
"""

# 内置默认关系类型引导
_BUILTIN_RELATION_TYPES_GUIDANCE = """
Classify each relationship using one of the following semantic types. If no type fits, use `RELATED`.

- REGULATED_BY: target is a NormClause (technical standard or specification) that governs the source
- TREATED_BY: target is a Treatment (repair/remediation method) applied to the source defect
- USES_MATERIAL: target is a Material consumed or applied during the treatment or detection
- BELONGS_TO: target is a Project that the source entity belongs to
- OCCURS_IN: target is a DefectLocation or Structure where the source defect occurs
- DEFINED_BY: target is a Parameter (threshold or metric) that defines or constrains the source
- CAUSES: target is a DefectImpact or DefectAssessment that the source leads to or results in
- HAS_SUBTYPE: target is a subcategory or more specific classification of the source
- RELATED: general association when no other type fits
"""

# 内置默认 JSON 示例
_BUILTIN_EXAMPLES = [
    """{
  "entities": [
    {
      "name": "<entity_name>",
      "type": "<entity_type>",
      "description": "<entity_description>"
    }
  ],
  "relationships": [
    {
      "source": "<entity_name>",
      "target": "<related_entity_name>",
      "keywords": "<keywords>",
      "description": "<description>",
      "relation_type": "<relation_type>"
    }
  ]
}"""
]

_LOADED_PROFILE: dict | None = None


def load_prompt_profile(profile_path: str | None = None) -> dict:
    """加载 prompt 配置。

    优先从 YAML 文件加载；YAML 不存在或格式不合法时使用内置默认配置。
    结果会被缓存到模块级变量 _LOADED_PROFILE 中。

    Args:
        profile_path: YAML 配置路径，默认使用 Settings().prompt_profile_path。

    Returns:
        dict: 包含以下键的配置：
            - entity_types_guidance: str, 实体类型引导文本
            - entity_extraction_json_examples: list[str], JSON 示例
            - relation_types_guidance: str, 关系类型引导文本
    """
    global _LOADED_PROFILE
    if _LOADED_PROFILE is not None:
        return _LOADED_PROFILE

    path = profile_path or Settings().prompt_profile_path

    try:
        resolved = Path(path)
        if not resolved.is_absolute():
            # 相对路径解析：相对于 graph-engine 的 prompts 目录
            import os

            base = os.environ.get(
                "GRAPH_PROMPT_BASE_DIR",
                str(Path(__file__).resolve().parent.parent.parent / "prompts"),
            )
            resolved = Path(base) / path

        if resolved.exists():
            with open(resolved, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            _LOADED_PROFILE = _validate_profile(data)
            return _LOADED_PROFILE
    except Exception:
        pass

    # YAML 加载失败 → 回退到内置默认
    _LOADED_PROFILE = {
        "entity_types_guidance": _BUILTIN_ENTITY_TYPES_GUIDANCE,
        "entity_extraction_json_examples": _BUILTIN_EXAMPLES,
        "relation_types_guidance": _BUILTIN_RELATION_TYPES_GUIDANCE,
    }
    return _LOADED_PROFILE


def _validate_profile(data: dict) -> dict:
    """验证 YAML 配置的完整性。

    entity_types_guidance 必须是非空字符串（>=50 字符），
    entity_extraction_json_examples 必须是非空列表。

    Args:
        data: YAML 解析后的 dict。

    Returns:
        dict: 验证通过的配置。

    Raises:
        ValueError: 必需字段缺失或不符合格式要求。
    """
    guidance = data.get("entity_types_guidance", "")
    if not guidance or not isinstance(guidance, str) or len(guidance.strip()) < 50:
        raise ValueError("entity_types_guidance must be a non-empty string")

    examples = data.get("entity_extraction_json_examples", [])
    if not examples or not isinstance(examples, list):
        raise ValueError("entity_extraction_json_examples must be a non-empty list")

    rel_guidance = data.get("relation_types_guidance", _BUILTIN_RELATION_TYPES_GUIDANCE)

    return {
        "entity_types_guidance": guidance.rstrip(),
        "entity_extraction_json_examples": examples,
        "relation_types_guidance": rel_guidance.rstrip()
        if isinstance(rel_guidance, str)
        else _BUILTIN_RELATION_TYPES_GUIDANCE.rstrip(),
    }
