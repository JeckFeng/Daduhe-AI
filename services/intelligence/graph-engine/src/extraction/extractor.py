"""单 chunk 实体/关系抽取器。

使用 LLM 从单个文本 chunk 中抽取结构化实体和关系。
包含 JSON 解析、截断修复、markdown 代码块剥离等容错逻辑。
"""

import json
import re

from lightrag.prompt import PROMPTS

from src.llm.client import AgentReasoningLLMClient
from src.models import Entity, EntityExtractionResult, Relationship

# 复用 LightRAG 的 prompt 模板
_SYSTEM_PROMPT_TEMPLATE = PROMPTS["entity_extraction_json_system_prompt"]
_USER_PROMPT_TEMPLATE = PROMPTS["entity_extraction_json_user_prompt"]

_MAX_TOTAL_RECORDS = 50
_MAX_ENTITY_RECORDS = 30
_LANGUAGE = "Chinese"


async def extract_entities_from_chunk(
    llm_client: AgentReasoningLLMClient,
    chunk_text: str,
    profile: dict,
    section_context: str = "",
) -> EntityExtractionResult:
    """从单个文本 chunk 中抽取实体和关系。

    构建 system/user prompt → 调用 LLM → 解析 JSON 响应。

    Args:
        llm_client: LLM 客户端。
        chunk_text: 要抽取的文本内容。
        profile: prompt 配置，包含 entity_types_guidance 和 examples。
        section_context: 可选的章节上下文信息。

    Returns:
        EntityExtractionResult: 包含 entities 和 relationships 列表。

    Raises:
        ValueError: LLM 返回的 JSON 无法解析时抛出。
    """
    system_prompt = _build_system_prompt(profile)
    user_prompt = _build_user_prompt(chunk_text, profile, section_context)

    response = await llm_client.completion(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    return _parse_response(response["content"])


def _build_system_prompt(profile: dict) -> str:
    """构建 system prompt：实体类型引导 + 关系类型引导 + 示例。

    将关系类型引导追加到实体类型引导后，使其出现在 LightRAG 模板
    的同一个 {entity_types_guidance} 占位符中。

    Args:
        profile: prompt 配置 dict。

    Returns:
        str: 格式化后的 system prompt。
    """
    guidance = profile["entity_types_guidance"]
    rel_guidance = profile.get("relation_types_guidance", "")
    if rel_guidance:
        guidance = guidance + "\n---Relation Types---\n" + rel_guidance

    return _SYSTEM_PROMPT_TEMPLATE.format(
        entity_types_guidance=guidance,
        examples="\n".join(profile["entity_extraction_json_examples"]),
        max_total_records=_MAX_TOTAL_RECORDS,
        max_entity_records=_MAX_ENTITY_RECORDS,
        language=_LANGUAGE,
    )


def _build_user_prompt(chunk_text: str, profile: dict, section_context: str) -> str:
    """构建 user prompt：将 chunk 文本 + 章节上下文填入模板。

    Args:
        chunk_text: 待抽取的文本内容。
        profile: prompt 配置 dict。
        section_context: 可选的章节路径（如 "§5.2.3 裂缝处理标准"）。

    Returns:
        str: 格式化后的 user prompt。
    """
    heading_context_block = ""
    if section_context:
        heading_context_block = (
            PROMPTS["entity_extraction_section_context"].format(
                heading_path=section_context
            )
            + "\n"
        )
    return _USER_PROMPT_TEMPLATE.format(
        entity_types_guidance=profile["entity_types_guidance"],
        input_text=chunk_text,
        max_total_records=_MAX_TOTAL_RECORDS,
        max_entity_records=_MAX_ENTITY_RECORDS,
        language=_LANGUAGE,
        heading_context_block=heading_context_block,
    )


def _parse_response(content: str) -> EntityExtractionResult:
    """将 LLM 返回的 JSON 字符串解析为 EntityExtractionResult。

    支持以下容错：
    1. 剥离 markdown 代码块（```json ... ```）
    2. 例行 JSON 解析
    3. 截断 JSON 修复（_repair_truncated_json）

    Args:
        content: LLM 返回的原始文本。

    Returns:
        EntityExtractionResult: 解析后的结构化结果。

    Raises:
        ValueError: 所有解析策略均失败时抛出。
    """
    json_str = _strip_code_fences(content)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        data = _repair_truncated_json(json_str)
        if data is None:
            snippet = content[:300]
            raise ValueError(
                f"Failed to parse LLM JSON response. Raw output (first 300 chars): {snippet}"
            )

    entities = [
        Entity(
            entity_name=_first_non_empty(e.get("name"), e.get("entity_name")),
            entity_type=e.get("type", e.get("entity_type", "Other")),
            entity_description=e.get("description", e.get("entity_description", "")),
        )
        for e in data.get("entities", [])
    ]

    relationships = [
        Relationship(
            source=r.get("source", ""),
            target=r.get("target", ""),
            keywords=r.get("keywords", ""),
            description=r.get("description", ""),
            relation_type=r.get("relation_type", "RELATED"),
        )
        for r in data.get("relationships", [])
    ]

    return EntityExtractionResult(entities=entities, relationships=relationships)


def _strip_code_fences(text: str) -> str:
    """移除 markdown 代码块包裹（```json ... ```）。

    Args:
        text: 可能包含 markdown 代码块的文本。

    Returns:
        str: 剥离代码块后的纯 JSON 文本。
    """
    text = text.strip()
    pattern = r"^```(?:json)?\s*\n(.*?)\n```$"
    m = re.match(pattern, text, re.DOTALL)
    if m:
        return m.group(1)
    return text


def _repair_truncated_json(json_str: str) -> dict | None:
    """尝试修复被截断或部分损坏的 JSON 响应。

    依次尝试以下策略：
    1. 闭合最后一行中未关闭的字符串
    2. 用修复后的最后一行再次尝试解析
    3. 截断到最后一条完整记录 + 补全闭合括号

    Args:
        json_str: 可能被截断的 JSON 字符串。

    Returns:
        解析成功返回 dict，所有策略失败返回 None。
    """
    # 策略1：如果最后一行有未关闭的字符串，闭合它
    lines = json_str.split("\n")
    if lines:
        last = lines[-1]
        # 奇数个未转义引号 → 字符串未闭合
        in_string = False
        for i, ch in enumerate(last):
            if ch == '"' and (i == 0 or last[i - 1] != "\\"):
                in_string = not in_string
        if in_string:
            lines[-1] = last + '"'
        json_str = "\n".join(lines)

    # 策略2：用修复后的内容尝试解析
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # 策略3：截断到最后一条完整对象 + 补全闭合
    for marker in ["\n    {", "\n    }"]:
        idx = json_str.rfind(marker)
        if idx > 0:
            for closing in ["\n  ]\n}", "\n  ]", "\n  }\n}", "\n  }"]:
                truncated = json_str[:idx] + closing
                try:
                    return json.loads(truncated)
                except json.JSONDecodeError:
                    continue

    return None


def _first_non_empty(*values: str) -> str:
    """返回第一个非空字符串值（用于兼容不同 JSON 字段名）。

    例如 LLM 可能返回 "name" 或 "entity_name"，此函数优先取前者。

    Args:
        *values: 候选字符串值。

    Returns:
        str: 第一个非空且去空白后的字符串，全为空则返回 ""。
    """
    for v in values:
        if v:
            return str(v).strip()
    return ""
