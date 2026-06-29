"""Pydantic models for LSL rule-extractor client (ICD-02 §4.2).

These are code contracts — the rule-extractor service is under development by LSL.
When the service is live, these models can be used directly with httpx to call:
    GET {lsl_base_url}/api/v1/rules/search?keyword=...&category=...&page=...&page_size=...
"""

from typing import Optional

from pydantic import BaseModel


class RuleSearchParams(BaseModel):
    """Query parameters for GET /api/v1/rules/search (ICD-02 §4.2)."""

    keyword: Optional[str] = None
    category: Optional[str] = None
    doc_id: Optional[str] = None
    page: int = 1
    page_size: int = 20


class RuleSource(BaseModel):
    doc_id: str
    chunk_ids: list[str]
    doc_title: str
    section_number: Optional[str] = None


class RuleItem(BaseModel):
    rule_id: str
    title: str
    content: str
    category: str
    norm_ref: Optional[str] = None
    parameters: Optional[dict] = None
    source: RuleSource
    confidence: float
    created_at: str


class RuleSearchData(BaseModel):
    items: list[RuleItem]
    total: int
    page: int
    page_size: int


class RuleSearchResponse(BaseModel):
    code: int = 0
    data: RuleSearchData
