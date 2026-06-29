"""SSE streaming test — simulates frontend token-by-token consumption.

加 --speed 参数控制打字速度（毫秒/字符），默认 30ms，设为 0 关掉延迟。
"""

import asyncio
import json
import sys
import time

import httpx


async def test_sse(base_url: str, query: str, char_delay_ms: int = 0):
    """Connect to the chat SSE endpoint and print tokens as they arrive.

    char_delay_ms: 每个字符之间的延迟（毫秒），0 表示不延迟。
    """
    t0 = time.perf_counter()
    token_count = 0
    answer: list[str] = []
    citations: list[dict] = []

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            f"{base_url}/api/v1/chat",
            json={"query": query, "stream": True},
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                print(f"HTTP {resp.status_code}: {body.decode()}")
                return

            print("=" * 60)
            print(f"📤 问题: {query}")
            print("-" * 60)

            event_type = ""
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    event_type = line[7:]
                elif line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue

                    if event_type == "status":
                        node = data.get("node", "")
                        extra = ""
                        if node == "supervisor":
                            extra = f" [类型={data.get('query_type', '')}]"
                        elif node == "retrieval":
                            extra = f" [检索到 {data.get('total_results', 0)} 条]"
                        print(f"\n[{event_type}] {node} 完成{extra}")

                    elif event_type == "answer_chunk":
                        token = data.get("token", "")
                        answer.append(token)
                        token_count += 1

                        if char_delay_ms > 0:
                            # 逐字符打印，模拟打字机效果
                            delay = char_delay_ms / 1000
                            for ch in token:
                                print(ch, end="", flush=True)
                                await asyncio.sleep(delay)
                        else:
                            print(token, end="", flush=True)

                    elif event_type == "references":
                        citations = data
                        ref_count = len(citations)
                        print(f"\n\n[{event_type}] 共 {ref_count} 条引用:")
                        for c in citations[:5]:
                            title = c.get("doc_title", "?")
                            section = c.get("section", "")
                            page = c.get("page", "")
                            url = c.get("download_url", "?")
                            print(f"  [{c['index']}] {title} · {section} · 第{page}页")
                            print(f"      下载: {url}")

                    elif event_type == "done":
                        elapsed = data.get("elapsed_ms", 0)
                        conv_id = data.get("conversation_id", "")
                        print(f"\n\n[{event_type}] 完毕")
                        print(f"  会话ID: {conv_id}")
                        print(f"  耗时: {elapsed}ms")
                        print(f"  Token 数: {token_count}")

                    elif event_type == "error":
                        print(f"\n❌ 错误: {data.get('error', 'unknown')}")

        elapsed = round((time.perf_counter() - t0) * 1000)
        print("-" * 60)
        print(f"✅ 总耗时 {elapsed}ms, answer 长度 {len(''.join(answer))} 字")
        print("=" * 60)


def main():
    if len(sys.argv) < 2:
        print("用法: python tests/test_sse_stream.py <问题> [base_url] [--speed ms]")
        print(
            '示例: python tests/test_sse_stream.py "混凝土坝裂缝宽度超过多少需要处理"'
        )
        print(
            '      python tests/test_sse_stream.py "渗漏处理" http://10.222.124.211:8003 --speed 50'
        )
        sys.exit(1)

    query = sys.argv[1]
    base_url = "http://localhost:8003"
    char_delay = 0  # ms per char, 0 = no delay

    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg.startswith("http"):
            base_url = arg.rstrip("/")
        elif arg == "--speed" and i + 1 < len(sys.argv):
            char_delay = int(sys.argv[i + 1])
            i += 1
        i += 1

    asyncio.run(test_sse(base_url, query, char_delay))


if __name__ == "__main__":
    main()
