"""Gleaning 增强抽取：第二轮 LLM 提取遗漏的实体和关系。

参考 LightRAG 的 gleaning 机制，在首次抽取后通过续写 prompt
让 LLM 补充第一轮遗漏的实体和关系。最多执行 1 轮。
"""

from lightrag.prompt import PROMPTS

from src.llm.client import AgentReasoningLLMClient
from src.models import EntityExtractionResult

_CONTINUE_USER_TEMPLATE = PROMPTS["entity_continue_extraction_json_user_prompt"]
_MAX_TOTAL_RECORDS = 20
_LANGUAGE = "Chinese"


async def run_gleaning(
    llm_client: AgentReasoningLLMClient,
    chunk_text: str,
    first_result: EntityExtractionResult,
    system_prompt: str,
    max_gleaning: int = 1,
) -> EntityExtractionResult:
    """执行 gleaning 轮次，补充抽取第一轮遗漏的实体和关系。

    使用 LightRAG 的 entity_continue_extraction_json_user_prompt 模板，
    LLM 会基于已有结果继续补充遗漏项。

    Args:
        llm_client: LLM 客户端。
        chunk_text: 原始 chunk 文本（当前未直接使用，由 LLM 上下文窗口保留）。
        first_result: 第一轮抽取结果（当前未直接使用，保留用于后续扩展）。
        system_prompt: system prompt（与第一轮相同）。
        max_gleaning: 最大 gleaning 轮数，默认 1。

    Returns:
        EntityExtractionResult: gleaning 中发现的新实体和关系（未与第一轮合并）。
    """
    if max_gleaning < 1:
        return EntityExtractionResult(entities=[], relationships=[])

    all_gleaned = EntityExtractionResult(entities=[], relationships=[])

    for _ in range(max_gleaning):
        glean_user = _CONTINUE_USER_TEMPLATE.format(
            max_total_records=_MAX_TOTAL_RECORDS,
            max_entity_records=_MAX_TOTAL_RECORDS,
            language=_LANGUAGE,
        )

        from src.extraction.extractor import _parse_response

        response = await llm_client.completion(
            system_prompt=system_prompt,
            user_prompt=glean_user,
        )
        gleaned = _parse_response(response["content"])

        # 若本轮未发现新内容，提前终止
        if not gleaned.entities and not gleaned.relationships:
            break

        all_gleaned.entities.extend(gleaned.entities)
        all_gleaned.relationships.extend(gleaned.relationships)

    return all_gleaned
