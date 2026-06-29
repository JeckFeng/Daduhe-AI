"""Search-engine HTTP 客户端 — 封装对 search-engine 服务的 HTTP 调用。

生产代码应通过 tools/search_engine_tool.py 工具层调用，以获得错误封装、
日志和延迟追踪等横切能力。本客户端仅为薄封装层，用于测试和简单场景。
"""

import httpx


class SearchEngineClient:
    """Search-engine 服务（端口 8002）的异步 HTTP 客户端。

    封装 POST /api/v1/search 端点的调用细节。
    """

    def __init__(self, base_url: str = "http://localhost:8002") -> None:
        """初始化客户端。

        Args:
            base_url: search-engine 服务的基础 URL
        """
        self.base_url = base_url

    async def search(
        self,
        query: str,
        mode: str = "hybrid",
        top_k: int = 10,
        filters: dict[str, str | list[str]] | None = None,
        include_sources: list[str] | None = None,
        trace_id: str = "",
    ) -> dict:
        """调用 search-engine 的检索接口。

        Args:
            query: 检索查询文本
            mode: 检索模式，可选 "keyword"、"fuzzy"、"vector"、"hybrid"
            top_k: 返回结果数量上限
            filters: 过滤条件，如 {"doc_type": ["规范"]}
            include_sources: 包含的数据源，如 ["chunks"]
            trace_id: 链路追踪 ID

        Returns:
            dict: search-engine 返回的完整 JSON 响应体

        Raises:
            httpx.HTTPError: HTTP 请求失败时抛出
        """
        payload: dict = {
            "query": query,
            "mode": mode,
            "top_k": top_k,
            "filters": filters or {},
            "include_sources": include_sources or ["chunks"],
        }
        headers = {"X-Trace-Id": trace_id} if trace_id else {}

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{self.base_url}/api/v1/search",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()
