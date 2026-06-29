"""Integration tests for gleaning enhancement — requires LLM."""

import pytest
import pytest_asyncio

from src.settings import Settings
from src.llm.client import AgentReasoningLLMClient
from src.prompts.loader import load_prompt_profile
from src.extraction.extractor import extract_entities_from_chunk, _build_system_prompt
from src.extraction.gleaning import run_gleaning
from src.models import EntityExtractionResult

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
def settings():
    return Settings()


@pytest_asyncio.fixture
async def llm_client(settings):
    return AgentReasoningLLMClient(settings)


CHUNK_TEXT = """
5.2 裂缝处理标准
水工建筑物混凝土裂缝按宽度分类：细微裂缝（宽度<0.2mm）采用表面封闭法处理，
中等裂缝（0.2-0.3mm）采用化学灌浆处理，较大裂缝（>0.3mm）应采取灌浆处理。
裂缝宽度大于0.3mm时判定为较大缺陷，需参照DL/T 2628-2023 §5.2.3执行。
"""


class TestGleaning:
    async def test_gleaning_disabled_returns_empty(self, llm_client):
        """max_gleaning=0 → returns empty EntityExtractionResult immediately."""
        result = await run_gleaning(
            llm_client=llm_client,
            chunk_text=CHUNK_TEXT,
            first_result=EntityExtractionResult(entities=[], relationships=[]),
            system_prompt="",
            max_gleaning=0,
        )
        assert len(result.entities) == 0
        assert len(result.relationships) == 0

    async def test_gleaning_runs_and_returns_valid_result(self, llm_client):
        """Gleaning runs LLM call and returns valid EntityExtractionResult."""
        profile = load_prompt_profile()
        system_prompt = _build_system_prompt(profile)

        # First extraction
        first_result = await extract_entities_from_chunk(
            llm_client=llm_client,
            chunk_text=CHUNK_TEXT,
            profile=profile,
        )
        assert len(first_result.entities) > 0

        # Gleaning
        gleaned = await run_gleaning(
            llm_client=llm_client,
            chunk_text=CHUNK_TEXT,
            first_result=first_result,
            system_prompt=system_prompt,
            max_gleaning=1,
        )

        # Gleaning may or may not find additional entities — both are valid
        # Verify the result structure is valid
        valid_types = {
            "Project",
            "Region",
            "Structure",
            "DefectLocation",
            "DefectType",
            "DefectImpact",
            "DefectAssessment",
            "Treatment",
            "Material",
            "DetectionMethod",
            "NormClause",
            "Parameter",
            "Other",
        }
        for e in gleaned.entities:
            assert e.entity_name
            assert e.entity_type in valid_types
            assert e.entity_description
