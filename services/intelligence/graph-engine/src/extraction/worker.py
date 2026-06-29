"""异步抽取任务编排器：编排 chunk 读取 → 并行抽取 → LLM 合并 → Memgraph 写入 → Milvus 向量化。

完整的抽取管线由 process_extraction_task() 驱动，分为四个阶段：
1. 并行 LLM 抽取（asyncio.Semaphore 控制并发）
2. LLM map-reduce 合并
3. Memgraph 图数据库写入
4. Ollama embedding + Milvus 向量写入
"""

import asyncio

import httpx
from daduhe_common import error as log_error, info

from src.models import EntityExtractionResult
from src.settings import Settings
from src.llm.client import AgentReasoningLLMClient
from src.prompts.loader import load_prompt_profile
from src.store.memgraph import MemgraphStore
from src.store.milvus import MilvusStore
from src.store.chunk_reader import PgChunkReader
from src.store.task_store import TaskStore
from src.extraction.extractor import extract_entities_from_chunk
from src.extraction.pipeline import (
    merge_with_llm,
    write_to_memgraph,
    _make_entity_id,
)


async def _parallel_extract_chunks(
    llm_client: AgentReasoningLLMClient,
    chunks: list[dict],
    profile: dict,
    settings: Settings,
    task_store: TaskStore,
    task_id: str,
) -> tuple[list, dict[str, dict]]:
    """并行抽取所有 chunk 的实体和关系。

    使用 asyncio.Semaphore 控制最大并发数（extraction_max_async）。
    采用 fail-fast 策略：任一任务异常时取消所有剩余任务。
    同时构建 entity_meta 溯源映射。

    Args:
        llm_client: LLM 客户端。
        chunks: chunk 列表，每项含 chunk_id, content, page_number 等。
        profile: prompt 配置。
        settings: 应用配置。
        task_store: 任务存储，用于上报进度。
        task_id: 当前任务 ID。

    Returns:
        tuple:
            - list[EntityExtractionResult]: 各 chunk 的抽取结果
            - dict[str, dict]: entity_meta，key 为实体名称，value 为溯源元数据

    Raises:
        Exception: 任一 chunk 抽取失败时抛出（fail-fast）。
    """
    semaphore = asyncio.Semaphore(settings.extraction_max_async)
    total = len(chunks)
    completed = 0
    lock = asyncio.Lock()

    async def _extract_one(chunk: dict) -> tuple:
        """抽取单个 chunk 并更新进度。"""
        nonlocal completed
        async with semaphore:
            result = await extract_entities_from_chunk(
                llm_client=llm_client,
                chunk_text=chunk["content"],
                profile=profile,
            )
            async with lock:
                completed += 1
                task_store.update_progress(
                    task_id,
                    {
                        "phase": "extraction",
                        "completed": completed,
                        "total": total,
                    },
                )
            return result, chunk

    tasks = [asyncio.create_task(_extract_one(c)) for c in chunks]

    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)

    # fail-fast：检查是否有异常
    for t in done:
        exc = t.exception()
        if exc is not None:
            for p in pending:
                p.cancel()
            await asyncio.wait(pending)
            raise exc

    # 收集结果并构建 entity_meta
    results = []
    entity_meta: dict[str, dict] = {}

    for t in done:
        result, chunk = t.result()
        results.append(result)

        src_meta = {
            "chunk_ids": [chunk["chunk_id"]],
            "page_numbers": _to_list(chunk.get("page_number")),
            "section_titles": _to_list(chunk.get("section_title")),
            "doc_titles": _to_list(chunk.get("doc_title")),
        }
        for entity in result.entities:
            name = entity.entity_name
            if name not in entity_meta:
                entity_meta[name] = {
                    "chunk_ids": [],
                    "page_numbers": [],
                    "section_titles": [],
                    "doc_titles": [],
                }
            _extend_meta(entity_meta[name], src_meta)

    return results, entity_meta


async def process_extraction_task(task_id: str, doc_id: str, settings: Settings) -> None:
    """完整的抽取管线：读取 chunk → 并行抽取 → LLM 合并 → 写入 Memgraph → 写入 Milvus。

    四个阶段：
    1. 从 PG 读取 chunks，并行 LLM 抽取实体/关系
    2. LLM map-reduce 合并多 chunk 结果
    3. 写入 Memgraph 图数据库
    4. Ollama embedding → 写入 Milvus 向量数据库

    异常安全：任何阶段失败都会更新任务状态为 failed 并记录错误。
    耗时通过 Prometheus Histogram（extraction_duration_s）记录。

    Args:
        task_id: 任务 ID。
        doc_id: 文档 ID。
        settings: 应用配置。
    """
    import time

    from src.main import extraction_duration_s

    llm_client = AgentReasoningLLMClient(settings)
    store = MemgraphStore(settings)
    profile = load_prompt_profile()
    chunk_reader = PgChunkReader(settings)
    task_store = TaskStore(settings)

    t0 = time.monotonic()
    try:
        await store.initialize()

        chunks = chunk_reader.read_chunks_by_doc_id(doc_id)
        if not chunks:
            task_store.update_status(
                task_id, "failed", f"No chunks found for doc_id={doc_id}"
            )
            return

        total = len(chunks)

        # ── Phase 1: 并行 LLM 抽取 ────────────────────────────
        results, entity_meta = await _parallel_extract_chunks(
            llm_client,
            chunks,
            profile,
            settings,
            task_store,
            task_id,
        )

        # ── Phase 2: LLM map-reduce 合并 ──────────────────────
        task_store.update_progress(
            task_id, {"phase": "merging", "completed": total, "total": total}
        )
        merged = await merge_with_llm(llm_client, results, settings)

        # ── Phase 3: 写入 Memgraph ────────────────────────────
        task_store.update_progress(
            task_id, {"phase": "writing", "completed": total, "total": total}
        )
        stats = await write_to_memgraph(
            store,
            merged,
            entity_meta,
            max_source_ids=settings.max_source_ids_per_entity,
        )

        # ── Phase 4: Embedding + 写入 Milvus ──────────────────
        task_store.update_progress(
            task_id, {"phase": "embedding", "completed": total, "total": total}
        )
        milvus_store = MilvusStore(settings)
        milvus_store.initialize()

        entity_types = _build_entity_type_map(merged)

        if merged.entities:
            entity_texts = [
                f"{e.entity_name}\n{e.entity_description}" for e in merged.entities
            ]
            entity_vectors = await _parallel_embed(entity_texts, settings)
            entity_data = [
                {
                    "entity_id": _make_entity_id(e.entity_name, e.entity_type),
                    "entity_name": e.entity_name,
                    "entity_type": e.entity_type,
                    "entity_description": e.entity_description,
                }
                for e in merged.entities
            ]
            # 仅保留 embedding 成功的实体
            valid_entities = [(d, v) for d, v in zip(entity_data, entity_vectors) if v]
            if valid_entities:
                e_data, e_vecs = zip(*valid_entities)
                milvus_store.upsert_entities(list(e_data), list(e_vecs))
                info(
                    "graph-engine",
                    "entities written to Milvus",
                    task_id,
                    count=len(e_data),
                )

        if merged.relationships:
            rel_texts = []
            rel_data = []
            for rel in merged.relationships:
                src_type = entity_types.get(rel.source.lower(), "Other")
                tgt_type = entity_types.get(rel.target.lower(), "Other")
                src_id = _make_entity_id(rel.source, src_type)
                tgt_id = _make_entity_id(rel.target, tgt_type)
                rel_texts.append(
                    f"{rel.keywords}\t{src_id}\n{tgt_id}\n{rel.description}"
                )
                rel_data.append(
                    {
                        "src_entity_id": src_id,
                        "tgt_entity_id": tgt_id,
                        "relation_type": rel.relation_type,
                        "keywords": rel.keywords,
                        "description": rel.description,
                    }
                )

            rel_vectors = await _parallel_embed(rel_texts, settings)
            valid_rels = [(d, v) for d, v in zip(rel_data, rel_vectors) if v]
            if valid_rels:
                r_data, r_vecs = zip(*valid_rels)
                milvus_store.upsert_relationships(list(r_data), list(r_vecs))
                info(
                    "graph-engine",
                    "relationships written to Milvus",
                    task_id,
                    count=len(r_data),
                )

        milvus_store.close()

        task_store.update_result(
            task_id,
            {
                "entity_count": len(merged.entities),
                "relationship_count": len(merged.relationships),
                "nodes_written": stats["nodes_written"],
                "edges_written": stats["edges_written"],
            },
        )
        extraction_duration_s.labels(doc_id=doc_id).observe(time.monotonic() - t0)

    except Exception as e:
        extraction_duration_s.labels(doc_id=doc_id).observe(time.monotonic() - t0)
        task_store.update_status(task_id, "failed", str(e))
    finally:
        await store.close()


def _to_list(value) -> list[str]:
    """将单个值包装为列表。

    Args:
        value: 任意值，None 返回空列表。

    Returns:
        list[str]: 包含 str(value) 的列表。
    """
    if value is None:
        return []
    return [str(value)]


def _extend_meta(target: dict, source: dict) -> None:
    """将 source 中的列表字段扩展到 target 中。

    用于累积 entity_meta 的溯源信息（chunk_ids、page_numbers 等）。

    Args:
        target: 目标 dict，列表字段会被扩展。
        source: 源 dict，列表字段的值会被追加到 target。
    """
    for key in ("chunk_ids", "page_numbers", "section_titles", "doc_titles"):
        target[key].extend(source[key])


async def _parallel_embed(
    texts: list[str],
    settings: Settings,
    max_async: int = 4,
) -> list[list[float]]:
    """并行生成 embedding 向量。

    使用 asyncio.Semaphore 控制并发，单个失败不影响其他任务。
    失败项对应位置返回空列表。

    Args:
        texts: 待向量化的文本列表。
        settings: 应用配置。
        max_async: 最大并发数，默认 4。

    Returns:
        list[list[float]]: 与 texts 顺序对应的向量列表，失败项为空列表。
    """
    if not texts:
        return []

    semaphore = asyncio.Semaphore(max_async)

    async def _embed_one(text: str) -> list[float]:
        """调用 Ollama API 生成单个文本的 embedding。"""
        async with semaphore:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{settings.ollama_url}/api/embeddings",
                    json={"model": settings.embedding_model, "prompt": text},
                )
                resp.raise_for_status()
                return resp.json()["embedding"]

    tasks = [asyncio.create_task(_embed_one(t)) for t in texts]

    done, pending = set(), set(tasks)
    try:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_EXCEPTION)
    finally:
        for t in pending:
            t.cancel()

    # 按原始顺序收集结果，失败项返回空列表
    vectors: list[list[float]] = []
    for t in tasks:
        exc = t.exception()
        if exc is None:
            vectors.append(t.result())
        else:
            vectors.append([])
            if not t.cancelled():
                log_error("graph-engine", "embedding failed", None, error=str(exc))
    return vectors


def _build_entity_type_map(merged: EntityExtractionResult) -> dict[str, str]:
    """从合并结果构建 name → type 查找表（小写 key）。

    Args:
        merged: 合并后的 EntityExtractionResult。

    Returns:
        dict[str, str]: 小写实体名 → 实体类型的映射。
    """
    entity_types: dict[str, str] = {}
    for entity in merged.entities:
        entity_types[entity.entity_name.lower()] = entity.entity_type
    return entity_types
