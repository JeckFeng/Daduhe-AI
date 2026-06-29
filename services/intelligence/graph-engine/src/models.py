"""Pydantic 数据模型：请求体、响应体、领域对象。

定义了 graph-engine 服务中所有 API 请求/响应的数据结构，
以及抽取管线中的核心领域对象（Entity、Relationship 等）。
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ExtractionTaskRequest(BaseModel):
    """POST /api/v1/graph/extract 请求体。

    Attributes:
        doc_id: 要抽取的文档 ID。
    """

    doc_id: str = Field(..., min_length=1)


class GraphQueryRequest(BaseModel):
    """POST /api/v1/graph/query 请求体。

    Attributes:
        query_type: 查询类型，entity_search（实体搜索）或 relation_search（关系搜索）。
        params: 查询参数，至少包含 query 文本和可选的 top_k。
    """

    query_type: Literal["entity_search", "relation_search"]
    params: dict[str, Any] = Field(default_factory=dict)


class ExtractionTask(BaseModel):
    """graph_engine.extraction_tasks 表中的一行。

    Attributes:
        task_id: 任务唯一标识。
        doc_id: 关联的文档 ID。
        status: 任务状态（pending/processing/completed/failed）。
        progress: JSONB 进度信息。
        result: JSONB 结果数据。
        error_message: 失败时的错误信息。
        created_at: 创建时间。
        updated_at: 最后更新时间。
        completed_at: 完成时间。
    """

    task_id: str
    doc_id: str
    status: str = "pending"
    progress: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None


class Chunk(BaseModel):
    """metadata.chunks 表中的一行。

    Attributes:
        chunk_id: chunk 唯一标识。
        doc_id: 所属文档 ID。
        content: chunk 文本内容。
        page_number: 页码。
        section_title: 章节标题。
        doc_title: 文档标题。
    """

    chunk_id: str
    doc_id: str
    content: str
    page_number: int | None = None
    section_title: str | None = None
    doc_title: str | None = None


class Entity(BaseModel):
    """抽取出的单个实体。

    Attributes:
        entity_name: 实体名称，如"裂缝"、"帷幕灌浆"。
        entity_type: 实体类型，如 DefectType、Treatment。
        entity_description: 实体描述文本。
    """

    entity_name: str
    entity_type: str
    entity_description: str


class Relationship(BaseModel):
    """抽取出的实体间关系。

    Attributes:
        source: 源实体名称。
        target: 目标实体名称。
        keywords: 关系关键词。
        description: 关系描述。
        relation_type: 语义关系类型，如 REGULATED_BY、TREATED_BY。
    """

    source: str
    target: str
    keywords: str
    description: str
    relation_type: str = "RELATED"


class EntityExtractionResult(BaseModel):
    """单个 chunk 的抽取结果。

    Attributes:
        entities: 抽取出的实体列表。
        relationships: 抽取出的关系列表。
    """

    entities: list[Entity]
    relationships: list[Relationship]
