"""doc-parser（HT）回调模型（ICD-03 §5.1）。

HT 完成文档处理后通过 HTTP POST callback 调用 search-engine 的
POST /api/v1/search/index 端点。此模块提供该回调 Payload 的 Pydantic 类型定义。
"""

from typing import Optional

from pydantic import BaseModel


class SearchIndexRequest(BaseModel):
    """HT callback 负载（POST /api/v1/search/index）。

    HT 发送此 Payload 通知 search-engine 对新文档建立索引。
    search-engine 收到后读取 PG chunks、生成 embedding、upsert 到 Milvus。
    """

    event_id: str                       # HT 事件 ID（幂等去重）
    trace_id: str                       # 链路追踪 ID
    doc_id: str                         # 文档 ID
    doc_type: Optional[str] = None      # 文档类型（pdf/word/markdown）
    title: Optional[str] = None         # 文档标题
    chunk_count: Optional[int] = None   # 文档 chunk 数量
    embedding_model: Optional[str] = None   # HT 使用的 embedding 模型
    embedding_dimension: Optional[int] = None  # embedding 维度
    status: str = "completed"           # 处理状态（completed/failed）
