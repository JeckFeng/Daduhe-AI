"""Pydantic request/response models for search-engine.

ICD-03 §5.2 defines the search API contract.
"""

from typing import Literal, Annotated, Optional
from datetime import date

from pydantic import BaseModel, Field, Discriminator, Tag


# ═══════════════════════════════════════════════════════════════
# Request
# ═══════════════════════════════════════════════════════════════


class SearchFilters(BaseModel):
    doc_type: Optional[list[str]] = None
    doc_ids: Optional[list[str]] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    mode: Literal["keyword", "fuzzy", "vector", "hybrid"] = "hybrid"
    top_k: int = Field(default=10, ge=1, le=100)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    include_sources: list[Literal["chunks", "rules"]] = Field(default=["chunks"])


# ═══════════════════════════════════════════════════════════════
# Response
# ═══════════════════════════════════════════════════════════════


class ChunkMetadata(BaseModel):
    doc_id: str
    doc_type: str
    title: str
    section_number: Optional[str] = None
    section_title: Optional[str] = None
    page_number: Optional[int] = None
    download_url: str


class ChunkResult(BaseModel):
    chunk_id: str
    text: str
    score: float
    source_type: Literal["chunk"] = "chunk"
    metadata: ChunkMetadata


class RuleMetadata(BaseModel):
    rule_id: str
    title: str
    category: Optional[str] = None
    norm_ref: Optional[str] = None
    doc_id: Optional[str] = None
    section_number: Optional[str] = None


class RuleResult(BaseModel):
    rule_id: Optional[str] = None
    chunk_id: None = None
    text: str
    score: float
    source_type: Literal["rule"] = "rule"
    metadata: RuleMetadata


SearchResult = Annotated[
    Annotated[ChunkResult, Tag("chunk")] | Annotated[RuleResult, Tag("rule")],
    Discriminator("source_type"),
]


class SearchResponse(BaseModel):
    code: int = 0
    data: "SearchResponseData"


class SearchResponseData(BaseModel):
    results: list[SearchResult]
    total_hits: int
    mode_used: str
