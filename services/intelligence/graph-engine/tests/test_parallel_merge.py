"""Tests for parallel extraction + LLM map-reduce merge."""

import asyncio

import pytest

from src.settings import Settings
from src.models import Entity, EntityExtractionResult, Relationship


# ============================================================
# _build_llm_merge_prompt
# ============================================================


class TestBuildLLMMergePrompt:
    def test_formats_descriptions_as_jsonl(self):
        from src.extraction.pipeline import _build_llm_merge_prompt

        prompt = _build_llm_merge_prompt(
            entity_name="裂缝",
            entity_type="DefectType",
            descriptions=["A structural crack.", "Surface cracking observed."],
            settings=Settings(),
        )
        assert "裂缝" in prompt
        assert "Description List" in prompt or "Description" in prompt
        assert "structural crack" in prompt.lower()
        assert "Surface cracking" in prompt
        # Should contain JSONL formatted descriptions
        assert '{"Description"' in prompt

    def test_includes_entity_name_and_type(self):
        from src.extraction.pipeline import _build_llm_merge_prompt

        settings = Settings()
        settings.merge_summary_language = "English"
        prompt = _build_llm_merge_prompt(
            entity_name="DL/T 2628-2023",
            entity_type="NormClause",
            descriptions=["First desc.", "Second desc."],
            settings=settings,
        )
        assert "DL/T 2628-2023" in prompt
        assert "NormClause" in prompt
        assert "English" in prompt

    def test_formats_relationship_descriptions(self):
        from src.extraction.pipeline import _build_llm_merge_prompt

        prompt = _build_llm_merge_prompt(
            entity_name="裂缝 -> 表面封闭法",
            entity_type="Relationship",
            descriptions=["desc a", "desc b"],
            settings=Settings(),
        )
        assert "裂缝 -> 表面封闭法" in prompt
        assert "Relationship" in prompt


# ============================================================
# _map_reduce_merge
# ============================================================


class TestMapReduceMerge:
    """Tests for _map_reduce_merge — the core map-reduce logic."""

    @pytest.fixture
    def settings(self):
        s = Settings()
        s.merge_summary_context_size = 12000
        s.merge_summary_max_tokens = 500
        return s

    async def test_single_description_returns_as_is(self, settings):
        """1 description → no LLM call, return directly."""
        from src.extraction.pipeline import _map_reduce_merge

        result = await _map_reduce_merge(
            llm_client=None,
            entity_name="裂缝",
            entity_type="DefectType",
            descriptions=["A structural crack in concrete."],
            settings=settings,
        )
        assert result == "A structural crack in concrete."

    async def test_two_descriptions_calls_llm(self, settings):
        """2 descriptions → 1 LLM call to merge."""
        from src.extraction.pipeline import _map_reduce_merge

        class _MockClient:
            async def completion(self, system_prompt, user_prompt, **kwargs):
                return {"content": "Merged: cracks are structural defects."}

        client = _MockClient()
        result = await _map_reduce_merge(
            llm_client=client,
            entity_name="裂缝",
            entity_type="DefectType",
            descriptions=["A crack.", "Surface cracking."],
            settings=settings,
        )
        assert result == "Merged: cracks are structural defects."

    async def test_many_descriptions_splits_into_batches(self, settings):
        """Many descriptions → multiple LLM calls → reduce."""
        from src.extraction.pipeline import _map_reduce_merge

        settings.merge_summary_context_size = 100  # force splitting

        call_count = 0

        class _MockClient:
            async def completion(self, system_prompt, user_prompt, **kwargs):
                nonlocal call_count
                call_count += 1
                # Count how many descriptions are in this batch
                desc_count = user_prompt.count('{"Description"')
                return {"content": f"Batch summary of {desc_count} items."}

        client = _MockClient()
        result = await _map_reduce_merge(
            llm_client=client,
            entity_name="裂缝",
            entity_type="DefectType",
            descriptions=[f"Description {i}" for i in range(50)],
            settings=settings,
        )
        # Should have done multiple LLM calls (map phase + reduce phase)
        assert call_count > 1
        assert "Batch summary" in result

    async def test_llm_failure_falls_back_to_longest(self, settings):
        """LLM raises → fallback to longest description."""
        from src.extraction.pipeline import _map_reduce_merge

        class _FailingClient:
            async def completion(self, **kwargs):
                raise RuntimeError("LLM unavailable")

        client = _FailingClient()
        result = await _map_reduce_merge(
            llm_client=client,
            entity_name="裂缝",
            entity_type="DefectType",
            descriptions=["short", "the longest description here"],
            settings=settings,
        )
        assert result == "the longest description here"


# ============================================================
# merge_with_llm
# ============================================================


class TestMergeWithLLM:
    """Tests for merge_with_llm — group-and-merge logic."""

    @pytest.fixture
    def settings(self):
        return Settings()

    async def test_single_entity_passes_through(self, settings):
        """Entity appearing in 1 chunk → keep as-is."""
        from src.extraction.pipeline import merge_with_llm

        r1 = EntityExtractionResult(
            entities=[
                Entity(
                    entity_name="裂缝",
                    entity_type="DefectType",
                    entity_description="A structural crack.",
                ),
            ],
            relationships=[],
        )
        merged = await merge_with_llm(None, [r1], settings)
        assert len(merged.entities) == 1
        assert merged.entities[0].entity_name == "裂缝"

    async def test_duplicate_entity_merged_via_llm(self, settings):
        """Entity in 2 chunks → LLM merge descriptions."""
        from src.extraction.pipeline import merge_with_llm

        class _MockClient:
            async def completion(self, system_prompt, user_prompt, **kwargs):
                return {"content": "Merged entity description."}

        client = _MockClient()
        r1 = EntityExtractionResult(
            entities=[
                Entity(
                    entity_name="裂缝",
                    entity_type="DefectType",
                    entity_description="A crack.",
                ),
            ],
            relationships=[],
        )
        r2 = EntityExtractionResult(
            entities=[
                Entity(
                    entity_name="裂缝",
                    entity_type="DefectType",
                    entity_description="Surface crack observed.",
                ),
            ],
            relationships=[],
        )
        merged = await merge_with_llm(client, [r1, r2], settings)
        assert len(merged.entities) == 1
        assert merged.entities[0].entity_name == "裂缝"
        assert merged.entities[0].entity_description == "Merged entity description."

    async def test_entity_type_uses_most_common(self, settings):
        """When same entity has different types across chunks, use most common."""
        from src.extraction.pipeline import merge_with_llm

        class _MockClient:
            async def completion(self, system_prompt, user_prompt, **kwargs):
                return {"content": "merged desc"}

        client = _MockClient()
        r1 = EntityExtractionResult(
            entities=[
                Entity(
                    entity_name="裂缝", entity_type="DefectType", entity_description="a"
                ),
            ],
            relationships=[],
        )
        r2 = EntityExtractionResult(
            entities=[
                Entity(
                    entity_name="裂缝",
                    entity_type="DefectImpact",
                    entity_description="b",
                ),
            ],
            relationships=[],
        )
        r3 = EntityExtractionResult(
            entities=[
                Entity(
                    entity_name="裂缝", entity_type="DefectType", entity_description="c"
                ),
            ],
            relationships=[],
        )
        merged = await merge_with_llm(client, [r1, r2, r3], settings)
        assert len(merged.entities) == 1
        assert merged.entities[0].entity_type == "DefectType"  # 2 votes vs 1

    async def test_relationships_unioned_keywords(self, settings):
        """Relationship keywords merged from all occurrences."""
        from src.extraction.pipeline import merge_with_llm

        class _MockClient:
            async def completion(self, system_prompt, user_prompt, **kwargs):
                return {"content": "merged rel desc"}

        client = _MockClient()
        r1 = EntityExtractionResult(
            entities=[
                Entity(
                    entity_name="裂缝", entity_type="DefectType", entity_description=""
                ),
                Entity(
                    entity_name="表面封闭法",
                    entity_type="Treatment",
                    entity_description="",
                ),
            ],
            relationships=[
                Relationship(
                    source="裂缝",
                    target="表面封闭法",
                    keywords="修补",
                    description="rel a",
                ),
            ],
        )
        r2 = EntityExtractionResult(
            entities=[
                Entity(
                    entity_name="裂缝", entity_type="DefectType", entity_description=""
                ),
            ],
            relationships=[
                Relationship(
                    source="裂缝",
                    target="表面封闭法",
                    keywords="处理",
                    description="rel b",
                ),
            ],
        )
        merged = await merge_with_llm(client, [r1, r2], settings)
        assert len(merged.relationships) == 1
        kw = merged.relationships[0].keywords
        assert "修补" in kw
        assert "处理" in kw

    async def test_relation_type_uses_most_common(self, settings):
        """When same relationship has different relation_types, vote for most common."""
        from src.extraction.pipeline import merge_with_llm

        class _MockClient:
            async def completion(self, system_prompt, user_prompt, **kwargs):
                return {"content": "merged rel desc"}

        client = _MockClient()
        r1 = EntityExtractionResult(
            entities=[
                Entity(
                    entity_name="裂缝", entity_type="DefectType", entity_description="a"
                ),
                Entity(
                    entity_name="表面封闭法",
                    entity_type="Treatment",
                    entity_description="",
                ),
            ],
            relationships=[
                Relationship(
                    source="裂缝",
                    target="表面封闭法",
                    keywords="修补",
                    description="rel a",
                    relation_type="TREATED_BY",
                ),
            ],
        )
        r2 = EntityExtractionResult(
            entities=[
                Entity(
                    entity_name="裂缝", entity_type="DefectType", entity_description="b"
                ),
            ],
            relationships=[
                Relationship(
                    source="裂缝",
                    target="表面封闭法",
                    keywords="处理",
                    description="rel b",
                    relation_type="TREATED_BY",
                ),
            ],
        )
        r3 = EntityExtractionResult(
            entities=[
                Entity(
                    entity_name="裂缝", entity_type="DefectType", entity_description="c"
                ),
            ],
            relationships=[
                Relationship(
                    source="裂缝",
                    target="表面封闭法",
                    keywords="治理",
                    description="rel c",
                    relation_type="RELATED",
                ),
            ],
        )
        merged = await merge_with_llm(client, [r1, r2, r3], settings)
        assert len(merged.relationships) == 1
        assert merged.relationships[0].relation_type == "TREATED_BY"  # 2 votes vs 1

    async def test_mixed_single_and_duplicate_entities(self, settings):
        """Some entities appear once, others appear multiple times."""
        from src.extraction.pipeline import merge_with_llm

        class _MockClient:
            async def completion(self, system_prompt, user_prompt, **kwargs):
                return {"content": "merged"}

        client = _MockClient()
        r1 = EntityExtractionResult(
            entities=[
                Entity(
                    entity_name="裂缝", entity_type="DefectType", entity_description="a"
                ),
                Entity(
                    entity_name="渗漏",
                    entity_type="DefectType",
                    entity_description="only once",
                ),
            ],
            relationships=[],
        )
        r2 = EntityExtractionResult(
            entities=[
                Entity(
                    entity_name="裂缝", entity_type="DefectType", entity_description="b"
                ),
            ],
            relationships=[],
        )
        merged = await merge_with_llm(client, [r1, r2], settings)
        assert len(merged.entities) == 2
        names = {e.entity_name for e in merged.entities}
        assert names == {"裂缝", "渗漏"}

        # 裂缝 was merged
        feng = next(e for e in merged.entities if e.entity_name == "裂缝")
        assert feng.entity_description == "merged"

        # 渗漏 was not merged (single appearance)
        shen = next(e for e in merged.entities if e.entity_name == "渗漏")
        assert shen.entity_description == "only once"


# ============================================================
# _parallel_extract_chunks
# ============================================================


class TestParallelExtractChunks:
    """Tests for parallel chunk extraction."""

    @pytest.fixture
    def settings(self):
        return Settings()

    @pytest.fixture
    def chunks(self):
        return [
            {
                "chunk_id": f"c{i}",
                "content": f"text-{i}",
                "page_number": i,
                "section_title": f"s{i}",
                "doc_title": "doc",
            }
            for i in range(6)
        ]

    async def test_returns_all_results(self, settings, chunks):
        """Parallel extraction returns correct number of results."""
        from src.extraction.worker import _parallel_extract_chunks

        class _FakeLLM:
            async def completion(self, **kwargs):
                return {"content": '{"entities":[],"relationships":[]}'}

        class _FakeStore:
            def update_progress(self, task_id, progress):
                pass

        results, meta = await _parallel_extract_chunks(
            llm_client=_FakeLLM(),
            chunks=chunks,
            profile={
                "entity_types_guidance": "",
                "entity_extraction_json_examples": [],
            },
            settings=settings,
            task_store=_FakeStore(),
            task_id="t1",
        )
        assert len(results) == 6
        assert all(isinstance(r, EntityExtractionResult) for r in results)

    async def test_fail_fast_cancels_remaining(self, settings, chunks):
        """When one chunk fails, remaining tasks are cancelled."""
        from src.extraction.worker import _parallel_extract_chunks

        call_count = 0

        class _SelectiveFailingLLM:
            async def completion(self, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 3:  # Third chunk fails
                    raise RuntimeError("LLM error")
                await asyncio.sleep(0.05)  # Let other tasks start
                return {"content": '{"entities":[],"relationships":[]}'}

        class _FakeStore:
            def update_progress(self, task_id, progress):
                pass

        with pytest.raises(RuntimeError, match="LLM error"):
            await _parallel_extract_chunks(
                llm_client=_SelectiveFailingLLM(),
                chunks=chunks,
                profile={
                    "entity_types_guidance": "",
                    "entity_extraction_json_examples": [],
                },
                settings=settings,
                task_store=_FakeStore(),
                task_id="t1",
            )
        # Max 4 concurrent (semaphore), so at most 5 could have started
        # before the 3rd failed (1-2-3-4 start, 3 fails → cancel 4-5-6)
        assert call_count <= 5

    async def test_respects_semaphore_limit(self, settings, chunks):
        """With max_async=2, max concurrent calls never exceeds 2."""
        from src.extraction.worker import _parallel_extract_chunks

        settings.extraction_max_async = 2
        concurrent = 0
        max_concurrent = 0
        lock = asyncio.Lock()

        class _CountingLLM:
            async def completion(self, **kwargs):
                nonlocal concurrent, max_concurrent
                async with lock:
                    concurrent += 1
                    max_concurrent = max(max_concurrent, concurrent)
                await asyncio.sleep(0.05)
                async with lock:
                    concurrent -= 1
                return {"content": '{"entities":[],"relationships":[]}'}

        class _FakeStore:
            def update_progress(self, task_id, progress):
                pass

        await _parallel_extract_chunks(
            llm_client=_CountingLLM(),
            chunks=chunks,
            profile={
                "entity_types_guidance": "",
                "entity_extraction_json_examples": [],
            },
            settings=settings,
            task_store=_FakeStore(),
            task_id="t1",
        )
        assert max_concurrent <= 2

    async def test_builds_entity_meta(self, settings):
        """Entity meta has correct chunk_ids and page_numbers."""
        from src.extraction.worker import _parallel_extract_chunks

        chunks = [
            {
                "chunk_id": "c0",
                "content": "text",
                "page_number": 1,
                "section_title": "Intro",
                "doc_title": "Doc A",
            },
            {
                "chunk_id": "c1",
                "content": "text",
                "page_number": 2,
                "section_title": "Methods",
                "doc_title": "Doc A",
            },
        ]

        class _FakeLLM:
            def __init__(self):
                self._idx = 0

            async def completion(self, **kwargs):
                self._idx += 1
                if self._idx == 1:
                    return {
                        "content": '{"entities":[{"name":"裂缝","type":"DefectType","description":"a"}],"relationships":[]}'
                    }
                else:
                    return {
                        "content": '{"entities":[{"name":"裂缝","type":"DefectType","description":"b"}],"relationships":[]}'
                    }

        class _FakeStore:
            def update_progress(self, task_id, progress):
                pass

        _, meta = await _parallel_extract_chunks(
            llm_client=_FakeLLM(),
            chunks=chunks,
            profile={
                "entity_types_guidance": "",
                "entity_extraction_json_examples": [],
            },
            settings=settings,
            task_store=_FakeStore(),
            task_id="t1",
        )
        assert "裂缝" in meta
        assert sorted(meta["裂缝"]["chunk_ids"]) == ["c0", "c1"]
        assert sorted(meta["裂缝"]["page_numbers"]) == ["1", "2"]
