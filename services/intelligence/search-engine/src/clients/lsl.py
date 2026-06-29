"""rule-extractor（LSL）客户端模型（ICD-02 §4.2）。

LSL 服务完成后，search-engine 将通过 httpx 调用其规则检索 API：
    GET {lsl_base_url}/api/v1/rules/search?keyword=...&category=...&page=...&page_size=...

此模块提供该 API 的请求参数和响应模型的 Pydantic 类型定义，
用于后续集成时直接使用。
"""

from typing import Optional

from pydantic import BaseModel


class RuleSearchParams(BaseModel):
    """规则搜索查询参数（GET /api/v1/rules/search，ICD-02 §4.2）。"""
    keyword: Optional[str] = None       # 搜索关键词
    category: Optional[str] = None      # 规则分类（如 "裂缝", "渗漏"）
    doc_id: Optional[str] = None        # 限定文档 ID
    page: int = 1                       # 页码（从 1 开始）
    page_size: int = 20                 # 每页条数


class RuleSource(BaseModel):
    """规则的来源文档和 chunk 信息。"""
    doc_id: str                         # 来源文档 ID
    chunk_ids: list[str]                # 来源 chunk ID 列表
    doc_title: str                      # 来源文档标题
    section_number: Optional[str] = None  # 章节编号


class RuleItem(BaseModel):
    """单条规则。"""
    rule_id: str                        # 规则 ID
    title: str                          # 规则标题
    content: str                        # 规则内容（结构化文本）
    category: str                       # 规则分类
    norm_ref: Optional[str] = None      # 规范引用（如 "DL/T 2628-2023 §5.2.3"）
    parameters: Optional[dict] = None   # 参数化阈值（如 {"裂缝宽度": ">0.3mm"}）
    source: RuleSource                  # 来源溯源信息
    confidence: float                   # 抽取置信度（0-1）
    created_at: str                     # 创建时间（ISO 8601）


class RuleSearchData(BaseModel):
    """规则搜索响应数据载荷。"""
    items: list[RuleItem]
    total: int
    page: int
    page_size: int


class RuleSearchResponse(BaseModel):
    """规则搜索响应体（最外层封装）。"""
    code: int = 0
    data: RuleSearchData
