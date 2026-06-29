"""多 chunk 抽取管线：结果合并、LLM map-reduce、Memgraph 写入。

将多个 chunk 的抽取结果进行去重合并（含 LLM 描述融合），
然后写入 Memgraph 图数据库。
"""

from src.models import Entity, EntityExtractionResult, Relationship
from src.store.memgraph import MemgraphStore


def merge_extraction_results(
    results: list[EntityExtractionResult],
) -> EntityExtractionResult:
    """简单合并多个 chunk 的抽取结果（规则去重，不使用 LLM）。

    实体合并：按小写 entity_name 分组，保留最长 description。
    关系合并：按 (source, target) 分组，合并 keywords（去重），保留最长 description。

    Args:
        results: 各 chunk 的抽取结果列表。

    Returns:
        EntityExtractionResult: 去重合并后的结果。
    """
    if not results:
        return EntityExtractionResult(entities=[], relationships=[])

    merged_entities: dict[str, Entity] = {}
    merged_relationships: dict[tuple[str, str], Relationship] = {}

    for result in results:
        for entity in result.entities:
            key = entity.entity_name.lower()
            if key in merged_entities:
                existing = merged_entities[key]
                # 保留 description 更长的版本
                if len(entity.entity_description) > len(existing.entity_description):
                    merged_entities[key] = entity
                elif (
                    len(entity.entity_description) == len(existing.entity_description)
                    and entity.entity_description == existing.entity_description
                ):
                    pass  # 完全相同 → 跳过
            else:
                merged_entities[key] = entity

        for rel in result.relationships:
            key = (rel.source.lower(), rel.target.lower())
            if key in merged_relationships:
                existing = merged_relationships[key]
                # 合并 keywords（中文/英文逗号分隔，去重）
                ekw = set(existing.keywords.replace("，", ",").split(","))
                rkw = set(rel.keywords.replace("，", ",").split(","))
                merged_kw = ", ".join(k.strip() for k in sorted(ekw | rkw) if k.strip())
                if len(rel.description) > len(existing.description):
                    merged_relationships[key] = Relationship(
                        source=existing.source,
                        target=existing.target,
                        keywords=merged_kw,
                        description=rel.description,
                        relation_type=_vote_relation_type([existing, rel]),
                    )
                elif rel.description == existing.description:
                    merged_relationships[key] = Relationship(
                        source=existing.source,
                        target=existing.target,
                        keywords=merged_kw,
                        description=existing.description,
                        relation_type=_vote_relation_type([existing, rel]),
                    )
                else:
                    merged_relationships[key] = Relationship(
                        source=existing.source,
                        target=existing.target,
                        keywords=merged_kw,
                        description=existing.description,
                        relation_type=_vote_relation_type([existing, rel]),
                    )
            else:
                merged_relationships[key] = rel

    return EntityExtractionResult(
        entities=list(merged_entities.values()),
        relationships=list(merged_relationships.values()),
    )


# ============================================================
# LLM map-reduce 合并
# ============================================================


def _build_llm_merge_prompt(
    entity_name: str,
    entity_type: str,
    descriptions: list[str],
    settings,
) -> str:
    """构建 LLM 合并 prompt：将多条描述总结为一条。

    使用 LightRAG 的 summarize_entity_descriptions 模板。
    每条描述格式化为 JSONL：{"Description": "..."}

    Args:
        entity_name: 实体名称。
        entity_type: 实体类型。
        descriptions: 待合并的描述列表。
        settings: 应用配置（控制 summary_length、language）。

    Returns:
        str: 格式化后的 user prompt。
    """
    import json

    from lightrag.prompt import PROMPTS

    template = PROMPTS["summarize_entity_descriptions"]

    json_lines = "\n".join(
        json.dumps({"Description": d}, ensure_ascii=False) for d in descriptions
    )

    description_type = "Relationship" if "->" in entity_name else "Entity"
    label = entity_type if description_type == "Entity" else "Relationship"

    return template.format(
        description_type=description_type,
        description_name=f"[{label}] {entity_name}",
        description_list=json_lines,
        summary_length=settings.merge_summary_max_tokens,
        language=settings.merge_summary_language,
    )


async def _llm_summarize(
    llm_client,
    entity_name: str,
    entity_type: str,
    descriptions: list[str],
    settings,
) -> str:
    """调用 LLM 将一批描述总结为一条。

    Args:
        llm_client: LLM 客户端。
        entity_name: 实体名称。
        entity_type: 实体类型。
        descriptions: 待总结的描述列表。
        settings: 应用配置。

    Returns:
        str: 合并后的描述文本。
    """
    user_prompt = _build_llm_merge_prompt(
        entity_name,
        entity_type,
        descriptions,
        settings,
    )
    resp = await llm_client.completion(
        system_prompt="",
        user_prompt=user_prompt,
    )
    return resp["content"].strip()


async def _map_reduce_merge(
    llm_client,
    entity_name: str,
    entity_type: str,
    descriptions: list[str],
    settings,
) -> str:
    """Map-reduce 合并实体描述。

    策略：
    - 1 条描述 → 直接返回（不调用 LLM）
    - 2+ 条描述 → 若 token 估算在 context_size 内则单次 LLM 调用；
      否则分批 → 每批 LLM 总结 → 递归 reduce 直到剩余一条。
    - LLM 失败时回退为取最长描述。

    Args:
        llm_client: LLM 客户端。
        entity_name: 实体名称。
        entity_type: 实体类型。
        descriptions: 待合并的描述列表。
        settings: 应用配置。

    Returns:
        str: 最终合并后的描述文本。
    """
    if not descriptions:
        return ""
    if len(descriptions) == 1:
        return descriptions[0]

    # Token 估算：中文约 2 chars/token
    total_chars = sum(len(d) for d in descriptions)
    estimated_tokens = total_chars // 2

    if estimated_tokens <= settings.merge_summary_context_size:
        # 单次 LLM 调用即可
        try:
            return await _llm_summarize(
                llm_client,
                entity_name,
                entity_type,
                descriptions,
                settings,
            )
        except Exception:
            return max(descriptions, key=len)

    # Map 阶段：分批
    batch_size = len(descriptions) // max(
        1, (estimated_tokens // settings.merge_summary_context_size) + 1
    )
    batch_size = max(2, batch_size)

    batches = []
    for i in range(0, len(descriptions), batch_size):
        batch = descriptions[i : i + batch_size]
        batches.append(batch)

    # 总结每批
    summaries = []
    for batch in batches:
        try:
            s = await _llm_summarize(
                llm_client,
                entity_name,
                entity_type,
                batch,
                settings,
            )
            summaries.append(s)
        except Exception:
            # 单批失败时回退取该批最长描述
            summaries.append(max(batch, key=len))

    # Reduce：递归合并总结
    return await _map_reduce_merge(
        llm_client,
        entity_name,
        entity_type,
        summaries,
        settings,
    )


async def merge_with_llm(
    llm_client,
    results: list[EntityExtractionResult],
    settings,
) -> EntityExtractionResult:
    """使用 LLM map-reduce 合并多个 chunk 的抽取结果。

    实体按小写名称分组，关系按 (source, target) 分组。
    每组出现 2+ 次时通过 LLM 合并描述，否则保持原样。
    实体类型取组内出现次数最多的类型，关系类型同理。

    Args:
        llm_client: LLM 客户端。
        results: 各 chunk 的抽取结果列表。
        settings: 应用配置。

    Returns:
        EntityExtractionResult: 合并后的最终结果。
    """
    from collections import Counter

    if not results:
        return EntityExtractionResult(entities=[], relationships=[])

    # ── 实体分组 ──────────────────────────────────────────────
    entity_groups: dict[str, list[Entity]] = {}
    for r in results:
        for e in r.entities:
            key = e.entity_name.lower()
            entity_groups.setdefault(key, []).append(e)

    merged_entities: list[Entity] = []
    for key, group in entity_groups.items():
        if len(group) == 1:
            merged_entities.append(group[0])
        else:
            # 取最常见的 entity_type
            types = [e.entity_type for e in group]
            most_common_type = Counter(types).most_common(1)[0][0]
            canonical_name = group[0].entity_name  # 首次出现的名称
            descriptions = [e.entity_description for e in group if e.entity_description]

            merged_desc = await _map_reduce_merge(
                llm_client,
                canonical_name,
                most_common_type,
                descriptions,
                settings,
            )
            merged_entities.append(
                Entity(
                    entity_name=canonical_name,
                    entity_type=most_common_type,
                    entity_description=merged_desc,
                )
            )

    # ── 关系分组 ──────────────────────────────────────────────
    rel_groups: dict[tuple[str, str], list[Relationship]] = {}
    for r in results:
        for rel in r.relationships:
            key = (rel.source.lower(), rel.target.lower())
            rel_groups.setdefault(key, []).append(rel)

    merged_relationships: list[Relationship] = []
    for (src_lower, tgt_lower), group in rel_groups.items():
        canonical_source = group[0].source
        canonical_target = group[0].target

        # 合并 keywords（去重）
        all_kw: set[str] = set()
        for rel in group:
            for kw in rel.keywords.replace("，", ",").split(","):
                kw = kw.strip()
                if kw:
                    all_kw.add(kw)
        merged_kw = ", ".join(sorted(all_kw))

        # 投票取最常见的 relation_type
        rel_types = [rel.relation_type for rel in group]
        most_common_rel_type = Counter(rel_types).most_common(1)[0][0]

        if len(group) == 1:
            rel = group[0]
            merged_relationships.append(
                Relationship(
                    source=canonical_source,
                    target=canonical_target,
                    keywords=merged_kw,
                    description=rel.description,
                    relation_type=most_common_rel_type,
                )
            )
        else:
            descriptions = [rel.description for rel in group if rel.description]
            label = f"{canonical_source} -> {canonical_target}"
            merged_desc = await _map_reduce_merge(
                llm_client,
                label,
                "Relationship",
                descriptions,
                settings,
            )
            merged_relationships.append(
                Relationship(
                    source=canonical_source,
                    target=canonical_target,
                    keywords=merged_kw,
                    description=merged_desc,
                    relation_type=most_common_rel_type,
                )
            )

    return EntityExtractionResult(
        entities=merged_entities,
        relationships=merged_relationships,
    )


def _make_entity_id(entity_name: str, entity_type: str) -> str:
    """生成稳定的 entity_id：{entity_type}-{entity_name}。

    替换空格和路径分隔符为连字符，确保 ID 不含特殊字符。

    Args:
        entity_name: 实体名称。
        entity_type: 实体类型。

    Returns:
        str: 格式为 "DefectType-裂缝" 的 entity_id。
    """
    safe_name = entity_name.replace(" ", "-").replace("/", "-").replace("\\", "-")
    return f"{entity_type}-{safe_name}"


async def write_to_memgraph(
    store: MemgraphStore,
    result: EntityExtractionResult,
    source_metadata: dict[str, dict] | None = None,
    max_source_ids: int = 10,
) -> dict:
    """将合并后的抽取结果写入 Memgraph 图数据库。

    实体写入为双标签节点（base + entity_type），
    关系写入为语义类型边（如 REGULATED_BY）。
    每条实体/关系携带溯源元数据（chunk_id、页码、章节标题、文档标题）。

    Args:
        store: Memgraph 图存储实例。
        result: 合并后的抽取结果。
        source_metadata: 溯源元数据，key 为实体名称，value 为 chunk/page/doc 信息。
        max_source_ids: 每条实体的最大 source_id 数量，默认 10。

    Returns:
        dict: {"nodes_written": N, "edges_written": M}
    """
    meta = source_metadata or {}
    node_count = 0
    edge_count = 0

    for entity in result.entities:
        entity_id = _make_entity_id(entity.entity_name, entity.entity_type)
        em = meta.get(entity.entity_name, {})
        chunk_ids = em.get("chunk_ids", [])
        page_numbers = em.get("page_numbers", [])
        section_titles = em.get("section_titles", [])
        doc_titles = em.get("doc_titles", [])

        props = {
            "entity_name": entity.entity_name,
            "description": entity.entity_description,
            "source_id": ",".join(chunk_ids[:max_source_ids]),
            "page_numbers": _join_dedup(page_numbers),
            "section_titles": _join_dedup(section_titles),
            "doc_titles": _join_dedup(doc_titles),
        }
        await store.upsert_node(entity_id, entity.entity_type, props)
        node_count += 1

    # 构建 name → type 映射，用于边的端点类型推断
    entity_types: dict[str, str] = {}
    for entity in result.entities:
        entity_types[entity.entity_name.lower()] = entity.entity_type

    for rel in result.relationships:
        src_type = entity_types.get(rel.source.lower(), "Other")
        tgt_type = entity_types.get(rel.target.lower(), "Other")
        src_id = _make_entity_id(rel.source, src_type)
        tgt_id = _make_entity_id(rel.target, tgt_type)
        rel_type = rel.relation_type

        rel_meta = meta.get(f"{rel.source}->{rel.target}", {})
        props = {
            "keywords": rel.keywords,
            "description": rel.description,
            "source_id": ",".join(rel_meta.get("chunk_ids", [])[:max_source_ids]),
            "page_numbers": _join_dedup(rel_meta.get("page_numbers", [])),
            "section_titles": _join_dedup(rel_meta.get("section_titles", [])),
            "weight": 1.0,
        }
        await store.upsert_edge(src_id, tgt_id, rel_type, props)
        edge_count += 1

    return {"nodes_written": node_count, "edges_written": edge_count}


def _vote_relation_type(rels: list[Relationship]) -> str:
    """从关系列表中选择出现次数最多的 relation_type。

    Args:
        rels: Relationship 对象列表。

    Returns:
        str: 得票最多的 relation_type。
    """
    from collections import Counter

    types = [r.relation_type for r in rels]
    return Counter(types).most_common(1)[0][0]


def _join_dedup(items: list[str]) -> str:
    """去重并以逗号连接字符串列表。

    Args:
        items: 字符串列表。

    Returns:
        str: 去重后以 ", " 连接的字符串。
    """
    seen = set()
    out = []
    for item in items:
        s = str(item).strip()
        if s and s not in seen:
            out.append(s)
            seen.add(s)
    return ", ".join(out)
