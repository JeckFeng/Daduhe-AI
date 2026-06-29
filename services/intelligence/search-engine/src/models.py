"""search-engine 的 Pydantic 请求/响应模型。

ICD-03 §5.2 定义了搜索 API 契约（POST /api/v1/search）。
支持 chunk 和 rule 两种数据源的结果，通过 discriminators 实现多态反序列化。
"""

from typing import Literal, Annotated, Optional
from datetime import date

from pydantic import BaseModel, Field, Discriminator, Tag


# ═══════════════════════════════════════════════════════════════
# 请求模型
# ═══════════════════════════════════════════════════════════════


class SearchFilters(BaseModel):
    """搜索过滤条件。

    所有字段均为可选，未设置时不参与过滤。
    """
    doc_type: Optional[list[str]] = None   # 文档类型过滤（如 "pdf", "word"）
    doc_ids: Optional[list[str]] = None     # 指定文档 ID 列表
    date_from: Optional[date] = None        # 日期范围起始
    date_to: Optional[date] = None          # 日期范围结束


class SearchRequest(BaseModel):
    """搜索请求体（POST /api/v1/search）。

    query 为必填字段；mode 默认 hybrid；top_k 限制 1-100。
    """
    query: str = Field(min_length=1)
    mode: Literal["keyword", "fuzzy", "vector", "hybrid"] = "hybrid"
    top_k: int = Field(default=10, ge=1, le=100)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    include_sources: list[Literal["chunks", "rules"]] = Field(default=["chunks"])


# ═══════════════════════════════════════════════════════════════
# 响应模型 — chunk 数据源
# ═══════════════════════════════════════════════════════════════


class ChunkMetadata(BaseModel):
    """Chunk 结果的溯源元数据。

    包含 chunk 所属文档的全部溯源信息，用于构建引用链接。
    """
    doc_id: str
    doc_type: str                     # 文档类型（pdf/word/markdown）
    title: str                        # 文档标题
    section_number: Optional[str] = None  # 章节编号（如 "5.2.3"）
    section_title: Optional[str] = None   # 章节标题（如 "裂缝处理标准"）
    page_number: Optional[int] = None     # 页码
    download_url: str                     # 文档下载链接（预签名 URL）


class ChunkResult(BaseModel):
    """单个 chunk 检索结果。"""
    chunk_id: str
    text: str                         # chunk 文本内容
    score: float                      # 检索相关性分数
    source_type: Literal["chunk"] = "chunk"  # 数据源标识，用于 discriminator 路由
    metadata: ChunkMetadata


# ═══════════════════════════════════════════════════════════════
# 响应模型 — rule 数据源（LSL rule-extractor，尚未集成）
# ═══════════════════════════════════════════════════════════════


class RuleMetadata(BaseModel):
    """Rule 结果的溯源元数据。"""
    rule_id: str
    title: str
    category: Optional[str] = None    # 规则分类（如 "裂缝", "渗漏"）
    norm_ref: Optional[str] = None    # 规范引用（如 "DL/T 2628-2023"）
    doc_id: Optional[str] = None
    section_number: Optional[str] = None


class RuleResult(BaseModel):
    """单个 rule 检索结果。"""
    rule_id: Optional[str] = None
    chunk_id: None = None             # rule 不关联 chunk，始终为 None
    text: str
    score: float
    source_type: Literal["rule"] = "rule"  # 数据源标识，用于 discriminator 路由
    metadata: RuleMetadata


# ═══════════════════════════════════════════════════════════════
# 联合类型 + discriminator（Pydantic 多态反序列化）
# ═══════════════════════════════════════════════════════════════

SearchResult = Annotated[
    Annotated[ChunkResult, Tag("chunk")] | Annotated[RuleResult, Tag("rule")],
    Discriminator("source_type"),
]
"""联合搜索结果类型：根据 source_type 字段自动路由到 ChunkResult 或 RuleResult。"""


class SearchResponse(BaseModel):
    """搜索响应体（最外层封装）。"""
    code: int = 0
    data: "SearchResponseData"


class SearchResponseData(BaseModel):
    """搜索响应数据载荷。"""
    results: list[SearchResult]
    total_hits: int
    mode_used: str
