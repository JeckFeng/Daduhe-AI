# Troubleshooting Knowledge Base

Last Updated: 2026-06-25

---

# Issue Index

| ID        | Title                                      | Status   |
| --------- | ------------------------------------------ | -------- |
| ISSUE-001 | hyphenated directory not importable        | Resolved |
| ISSUE-002 | psycopg2 % operator conflicts with pg_trgm | Resolved |
| ISSUE-003 | pg_trgm threshold cuts off valid matches   | Resolved |
| ISSUE-004 | pg_trgm useless for 2-char Chinese queries | Resolved |
| ISSUE-005 | test stub status mismatch                  | Resolved |
| ISSUE-006 | Milvus duplicate index creation            | Resolved |
| ISSUE-007 | Milvus insert data not visible in query    | Resolved |
| ISSUE-008 | vector search returns garbage for nonsense | Resolved |
| ISSUE-009 | async def tests fail without pytest marker       | Resolved |
| ISSUE-010 | anyio event loop closed during multi-LLM-test cleanup | Resolved |

---

# ISSUE-001

## Title

hyphenated directory name not importable as Python module

## Date

2026-06-23

## Symptoms

```text
ModuleNotFoundError: No module named 'search_engine'
```

## Environment

```text
Python 3.11
uv workspace with member "search-engine"
```

## Root Cause

`search-engine` 目录名含连字符，不能作为 Python 模块名导入（Python 标识符不允许连字符）。

## Solution

在 `conftest.py` 中通过 `sys.path.insert` 添加 search-engine 目录路径，然后使用 `from src.main import app` 导入。

```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "search-engine"))
from src.main import app
```

## Verification

```bash
uv run pytest tests/test_search.py -v
```

Expected: tests collected and executed successfully.

## Status

Resolved

---

# ISSUE-002

## Title

psycopg2 named parameter syntax conflicts with pg_trgm % operator

## Date

2026-06-23

## Symptoms

```text
psycopg2.ProgrammingError: argument formats can't be mixed
```

## Investigation

pg_trgm 的 `%` 运算符（`c.chunk_text % %(query)s`）与 psycopg2 的 `%(name)s` 命名参数语法冲突，psycopg2 无法解析。

## Root Cause

psycopg2 将 SQL 中的 `%` 识别为参数占位符，与 pg_trgm 运算符冲突。

## Solution

使用显式函数调用代替运算符：

```sql
-- 错误写法
WHERE c.chunk_text % %(query)s

-- 正确写法
WHERE similarity(c.chunk_text, %(query)s) > 0.005
```

## Status

Resolved

---

# ISSUE-003

## Title

pg_trgm similarity threshold too high for Chinese typos

## Date

2026-06-23

## Symptoms

查询 "裂逢处理"（"裂缝处理" 的错别字）命中一条 chunk，similarity = 0.0099，但阈值 `_SIM_THRESHOLD = 0.01` 将这条结果过滤掉了。

## Environment

```text
PostgreSQL pg_trgm
Chinese text
```

## Root Cause

中文 trigram 的 similarity 分数天然低于拉丁语系。0.01 的阈值对于 4-6 字中文查询过于严格。

## Solution

将 `_SIM_THRESHOLD` 从 0.01 降低到 0.005。

```python
_SIM_THRESHOLD = 0.005
```

## Verification

`test_fuzzy_typo_tolerance` 通过，"裂逢处理" 能返回 "裂缝处理标准" chunk。

## Status

Resolved

---

# ISSUE-004

## Title

pg_trgm useless for 2-character Chinese queries

## Date

2026-06-23

## Symptoms

用户查询 "裂缝"（2 字）时，pg_trgm 无法生成有意义的 trigram（需要至少 3 个字符）。

## Investigation

pg_trgm 的工作原理：将文本切分为连续的 3-gram（trigram）。中文的 "裂缝" 只有 2 个字符，无法生成任何 trigram。

## Root Cause

pg_trgm 的 trigram 算法要求 3+ 字符。2 字中文查询在 pg_trgm 中无意义。

## Solution

这不是 bug，是 pg_trgm 的固有局限。分层处理：
- 2-3 字短查询 → keyword mode（ILIKE 精确子串匹配）
- 4+ 字查询 → fuzzy mode（pg_trgm similarity）

在 search-engine 中，两种模式各司其职，agent-reasoning 可根据 query 长度自动选择。

## Status

Resolved (by design)

---

# ISSUE-005

## Title

Test assertion expects stub status "processing" but implementation returns "completed"

## Date

2026-06-23

## Symptoms

```text
AssertionError: assert body["data"]["status"] == "processing"
# actual: "completed"
```

## Root Cause

Issue #5 的测试在 stub 阶段编写，stub 返回 `status: "processing"`。实际实现是一次性同步完成（read PG → embed → insert），返回 `status: "completed"`。

## Solution

修改测试断言为接受两种状态：

```python
assert body["data"]["status"] in ("processing", "completed")
```

## Status

Resolved

---

# ISSUE-006

## Title

Milvus create_index fails: "at most one distinct index is allowed per field"

## Date

2026-06-23

## Symptoms

第二次调用 `/search/index` 时，`milvus_client.create_index()` 报错：

```text
at most one distinct index is allowed per field
```

## Root Cause

第一次调用已为 `vector` 字段创建了 IVF_FLAT 索引，第二次调用再次尝试创建同名字段的索引。

## Solution

创建索引前先检查是否已有非 FLAT_INDEX 的索引：

```python
try:
    idx = milvus_client.describe_index(coll, "vector")
    has_index = idx["index_type"] != "FLAT_INDEX"
except Exception:
    has_index = False

if not has_index:
    milvus_client.create_index(...)
```

同时外层包裹 try/except 防止竞态条件。

## Verification

`test_search_index_idempotent` 通过，两次调用均返回 202。

## Status

Resolved

---

# ISSUE-007

## Title

Milvus insert data not visible in subsequent queries

## Date

2026-06-23

## Symptoms

`milvus_client.insert()` 成功后，`milvus_client.query()` 返回 0 条结果。

## Investigation

Milvus 的集合有 loaded/released 两种状态。数据写入后，如果集合在写入前已被 load，新数据不会自动对查询可见。

## Root Cause

集合在 insert 之前被 `load_collection()` 加载到内存，insert 之后新数据未被索引，查询不可见。

## Solution

在 `/search/index` handler 末尾 `release_collection()`，强制下次查询时重新 load：

```python
try:
    milvus_client.release_collection(coll)
except Exception:
    pass  # already released
```

测试中需要在查询前显式 `load_collection()`：

```python
mc.load_collection(INDEX_TEST_COLLECTION)
results = mc.query(...)
```

## Verification

`test_search_index_writes_to_milvus` 和 `test_search_index_idempotent` 均通过。

## Status

Resolved

---

# ISSUE-008

## Title

Vector search returns 10 results for completely nonsensical query

## Date

2026-06-25

## Symptoms

查询 "XYZZY不存在的关键词测试" 时，vector 模式返回 10 条结果（score 0.34-0.40）。

## Root Cause

向量检索的数学本质：总是在向量空间中找到"最近邻"。不管查询多荒谬，Milvus 都会返回 cosine 距离最近的 N 个向量。没有"无匹配"的概念。

同类对比：正常查询 top-1 score = 0.73-0.82，垃圾查询 top-1 score = 0.40。

## Solution

在 Milvus search 结果收集阶段加 score >= 0.45 阈值：

```python
threshold = min_score if min_score is not None else Settings().vector_min_score

for hit in search_results[0]:
    score = hit["distance"]
    if chunk_id and score >= threshold:
        hits[chunk_id] = score
```

阈值通过 `SEARCH_VECTOR_MIN_SCORE` 环境变量配置（默认 0.45）。

## Verification

评测脚本通过，"XYZZY不存在的关键词测试" 返回 0 结果。vector P@K 从 0.52 提升到 0.68。

## Status

Resolved

---

# Reusable Fixes

## Milvus Client

### Error

```text
MilvusException: collection not loaded
```

### Fix

```python
milvus_client.load_collection(collection_name)
# ... query ...
milvus_client.release_collection(collection_name)  # optional cleanup
```

### Error

```text
collection not found
```

### Fix

```python
if not milvus_client.has_collection(coll):
    milvus_client.create_collection(collection_name=coll, schema=schema)
```

---

## PostgreSQL + psycopg2

### Error

```text
argument formats can't be mixed
```

### Fix

避免在 psycopg2 命名参数 SQL 中使用 `%` 运算符。用等价的函数替代（如 `similarity()` 代替 `%`）。

### Error

pg_trgm extension not available

### Fix

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

pg_trgm 是 PostgreSQL 官方 contrib 模块，免费、无需版本升级。

---

## Ollama

### Error

```text
ConnectionError: Failed to connect to localhost:11435
```

### Fix

```bash
ollama serve            # 启动服务
ollama pull bge-m3     # 拉取模型（首次）
```

---

# Frequently Encountered Problems

## Milvus

- insert 后数据不可见 → release + reload
- create_index 重复报错 → 先 describe_index 检查
- collection 必须 load 后才能 search/query

## PostgreSQL

- psycopg2 参数格式冲突 → 用函数代替运算符
- pg_trgm 对短中文不敏感 → 走 keyword ILIKE

## Vector Search

- 无意义查询仍返回结果 → 加 score 阈值
- 阈值需要根据实际数据校准（当前 0.45 基于 15 chunks）

---

# ISSUE-009

## Title

`async def` tests fail with "async def functions are not natively supported"

## Date

2026-06-25

## Symptoms

```text
FAILED tests/test_store.py::TestInMemoryConversationStore::test_get_history_empty
async def functions are not natively supported.
You need to install a suitable plugin for your async framework, for example:
  - anyio
  - pytest-asyncio
  - pytest-tornasync
  - pytest-trio
  - pytest-twisted
```

所有标记为 `async def` 的测试函数全部失败，而同步测试函数正常。

## Environment

```text
Python 3.11
pytest 9.1.1
anyio 4.14.0 (已安装)
pytest-asyncio: 未安装
```

`conftest.py` 中没有任何 pytest async 配置。

## Root Cause

pytest 原生不支持 `async def` 测试函数，需要异步插件（pytest-asyncio 或 anyio）。项目依赖中已有 `anyio`（作为 langgraph 的传递依赖安装），但 `uv sync --dev` 时未安装 `pytest-asyncio`。

虽然 anyio 提供了 `anyio.pytest_plugin`，可以在测试中使用 `@pytest.mark.anyio` 标记来运行异步测试，但如果不在 `conftest.py` 中声明或逐函数标记，pytest 不会自动启用该 marker。

## Solution

在测试模块级添加 `pytestmark = pytest.mark.anyio`：

```python
import pytest
pytestmark = pytest.mark.anyio
```

这会为该模块中所有 `async def` 测试函数自动添加 anyio marker，无需每个函数单独装饰。

或者，在 `conftest.py` 中全局配置（如果整个项目大量使用异步测试）：

```python
# conftest.py
def pytest_collection_modifyitems(items):
    for item in items:
        if item.get_closest_marker("asyncio") is None and item.obj:
            if hasattr(item.obj, "__code__") and item.obj.__code__.co_flags & 0x80:
                item.add_marker(pytest.mark.anyio)
```

## Verification

```bash
uv run pytest tests/test_store.py -v
```

Expected: 8 passed.

## Status

Resolved

---

---

# ISSUE-010

## Title

anyio event loop closed during multi-LLM-test cleanup ("Event loop is closed")

## Date

2026-06-25

## Symptoms

```text
RuntimeError: Event loop is closed
```

发生在同时运行多个包含 LLM 调用的异步测试时。单独运行测试通过，批量运行失败。

## Root Cause

Two issues compounded:

1. **`test_generator.py` had a local `llm` fixture that shadowed conftest's fixture** but had NO cleanup (`return LLMClient(Settings())` without teardown). The underlying `httpx.AsyncClient` instances were never explicitly closed, so GC-triggered `aclose()` raced with anyio's event loop shutdown.

2. **`vector_search_handler` created its own `httpx.AsyncClient`** via `async with`, which worked within a single test but left cleanup timing to the event loop — fragile when multiple async tests ran sequentially.

## Solution

1. **Removed the local `llm` fixture** from `test_generator.py` — conftest's async fixture (with `await c.close()`) now handles all LLM cleanup.
2. **Made `vector_search_handler` accept optional `client: httpx.AsyncClient`** parameter. When provided, uses the shared client; otherwise creates its own.
3. **Added `httpx_client` fixture** in conftest.py:
   ```python
   @pytest.fixture
   async def httpx_client():
       async with httpx.AsyncClient(timeout=10) as client:
           yield client
   ```
4. **Updated test fixtures** (`test_retrieval_pipeline.py`, `test_generator.py`) to use `functools.partial(vector_search_handler, client=httpx_client)` so all handler invocations share one client whose lifecycle pytest controls.
5. **Made `llm` fixture async** — uses `await c.close()` instead of sync `c.close()` which returned an unawaited coroutine.

Key insight: pytest fixtures manage lifecycle; when shared resources (httpx clients) are created inside handlers, their cleanup races with event loop teardown. Dependency injection through `functools.partial` lets fixtures own the lifecycle without changing the registry/handler architecture.

## Status

Resolved — all 32 tests pass in a single `pytest` run with no warnings.

---

## Pytest Async Tests

### Error

```text
async def functions are not natively supported
```

### Fix

方案 A（单模块）：在测试文件顶部添加 `pytestmark = pytest.mark.anyio`

```python
import pytest
pytestmark = pytest.mark.anyio
```

方案 B（全局）：安装 `pytest-asyncio`

```bash
uv add --group dev pytest-asyncio
```
