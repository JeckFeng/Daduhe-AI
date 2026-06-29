"""Pydantic models for HT doc-parser callback (ICD-03 §5.1).

These are code contracts — the doc-parser service is under development by HT.
The POST /api/v1/search/index endpoint already accepts these fields directly via
request.json(); this module provides typed models for when we switch to Pydantic
validation of the callback payload.
"""

from typing import Optional

from pydantic import BaseModel


class SearchIndexRequest(BaseModel):
    """HT callback payload for POST /api/v1/search/index (ICD-03 §5.1).

    HT sends this after completing document processing. search-engine then
    reads chunks from PG, generates embeddings, and upserts into Milvus.
    """

    event_id: str
    trace_id: str
    doc_id: str
    doc_type: Optional[str] = None
    title: Optional[str] = None
    chunk_count: Optional[int] = None
    embedding_model: Optional[str] = None
    embedding_dimension: Optional[int] = None
    status: str = "completed"
