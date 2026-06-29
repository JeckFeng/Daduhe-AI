"""Integration tests for prompt profile loading + single-chunk extraction."""

import pytest

from src.settings import Settings
from src.llm.client import AgentReasoningLLMClient
from src.prompts.loader import load_prompt_profile
from src.extraction.extractor import extract_entities_from_chunk


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def llm_client(settings):
    return AgentReasoningLLMClient(settings)


# ── Prompt Profile Loading ───────────────────────────────────────


def test_profile_loads_entity_types_guidance():
    """YAML profile contains non-empty entity_types_guidance."""
    profile = load_prompt_profile()
    guidance = profile["entity_types_guidance"]
    assert len(guidance) > 100
    assert "Project" in guidance
    assert "DefectType" in guidance
    assert "NormClause" in guidance
    assert "Treatment" in guidance


def test_profile_loads_few_shot_examples():
    """YAML profile contains at least 2 few-shot examples."""
    profile = load_prompt_profile()
    examples = profile["entity_extraction_json_examples"]
    assert isinstance(examples, list)
    assert len(examples) >= 2
    for ex in examples:
        assert "entities" in ex or '"entities"' in str(ex)


def test_profile_fallback_when_file_missing(monkeypatch):
    """Returns built-in default profile when YAML file not found."""
    monkeypatch.setenv("GRAPH_PROMPT_PROFILE_PATH", "/nonexistent/path.yaml")
    profile = load_prompt_profile()
    assert len(profile["entity_types_guidance"]) > 100
    assert len(profile["entity_extraction_json_examples"]) >= 2


# ── Single Chunk Extraction ────────────────────────────────────

SEED_CHUNK_001 = """
5.1 缺陷分类总则
水工建筑物缺陷按性质分为结构缺陷、渗流缺陷、材料劣化缺陷和附属设施缺陷四类。
结构缺陷包括裂缝、变形、沉降、滑坡等影响建筑物整体稳定性的缺陷；
渗流缺陷包括渗漏、管涌、流土等涉及渗流安全的缺陷。
"""


@pytest.mark.integration
async def test_extract_from_single_chunk(llm_client):
    """Single chunk → entities + relationships with valid structure."""
    result = await extract_entities_from_chunk(
        llm_client=llm_client,
        chunk_text=SEED_CHUNK_001,
        profile=load_prompt_profile(),
    )

    assert len(result.entities) > 0, "Should extract at least 1 entity"
    assert len(result.relationships) >= 0

    for e in result.entities:
        assert e.entity_name, "entity_name must not be empty"
        assert e.entity_type, "entity_type must not be empty"
        # entity_type should be one of the 12 known types or "Other"
        assert e.entity_description, "entity_description must not be empty"


@pytest.mark.integration
async def test_extraction_entity_types_valid(llm_client):
    """Extracted entities have valid entity types."""
    result = await extract_entities_from_chunk(
        llm_client=llm_client,
        chunk_text=SEED_CHUNK_001,
        profile=load_prompt_profile(),
    )

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
    for e in result.entities:
        assert e.entity_type in valid_types, (
            f"entity_type '{e.entity_type}' for '{e.entity_name}' not in valid types"
        )
