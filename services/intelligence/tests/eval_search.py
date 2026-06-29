"""Search-engine evaluation: response time, accuracy, relevance.

Run: uv run python tests/eval_search.py
"""

import time
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "search-engine"))

from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

# ═══════════════════════════════════════════════════════════════
# Test queries designed against known seed data content
# Each query has: query text, expected_keywords (terms that SHOULD
# appear in top results for a correct hit), and category.
# ═══════════════════════════════════════════════════════════════

TEST_CASES = [
    # === Exact keyword matches ===
    {
        "id": "K1",
        "query": "裂缝",
        "modes": ["keyword", "fuzzy", "vector", "hybrid"],
        "expected_terms": ["裂缝"],
        "category": "short keyword (2 chars)",
    },
    {
        "id": "K2",
        "query": "渗漏",
        "modes": ["keyword", "fuzzy", "vector", "hybrid"],
        "expected_terms": ["渗漏"],
        "category": "short keyword (2 chars)",
    },
    {
        "id": "K3",
        "query": "灌浆",
        "modes": ["keyword", "fuzzy", "vector", "hybrid"],
        "expected_terms": ["灌浆"],
        "category": "keyword (2 chars, common term)",
    },
    # === Multi-word keywords ===
    {
        "id": "K4",
        "query": "裂缝处理",
        "modes": ["keyword", "fuzzy", "vector", "hybrid"],
        "expected_terms": ["裂缝", "处理"],
        "category": "multi-char keyword",
    },
    {
        "id": "K5",
        "query": "渗漏检测",
        "modes": ["keyword", "fuzzy", "vector", "hybrid"],
        "expected_terms": ["渗漏"],
        "category": "multi-char keyword",
    },
    {
        "id": "K6",
        "query": "帷幕灌浆",
        "modes": ["keyword", "fuzzy", "vector", "hybrid"],
        "expected_terms": ["帷幕灌浆"],
        "category": "technical term",
    },
    {
        "id": "K7",
        "query": "混凝土碳化",
        "modes": ["keyword", "fuzzy", "vector", "hybrid"],
        "expected_terms": ["碳化"],
        "category": "technical term",
    },
    # === Natural language questions (semantic) ===
    {
        "id": "S1",
        "query": "裂缝宽度大于0.3mm时需要采取什么处理措施？",
        "modes": ["vector", "hybrid"],
        "expected_terms": ["0.3mm", "灌浆", "处理", "裂缝"],
        "category": "natural language question",
    },
    {
        "id": "S2",
        "query": "泄水建筑物的安全评价包括哪些内容？",
        "modes": ["vector", "hybrid"],
        "expected_terms": ["泄水", "安全评价"],
        "category": "natural language question",
    },
    {
        "id": "S3",
        "query": "混凝土强度不足时应该怎么办？",
        "modes": ["vector", "hybrid"],
        "expected_terms": ["强度", "混凝土"],
        "category": "natural language question",
    },
    # === Typo tolerance (fuzzy) ===
    {
        "id": "TY1",
        "query": "裂逢处理",
        "modes": ["fuzzy", "keyword"],
        "expected_terms": ["裂缝", "处理"],
        "category": "typo tolerance",
    },
    # === Non-existent term ===
    {
        "id": "NE1",
        "query": "XYZZY不存在的关键词测试",
        "modes": ["keyword", "fuzzy", "vector"],
        "expected_terms": [],
        "category": "nonexistent term (expect empty)",
    },
]

WARMUP_ITERATIONS = 1
MEASURE_ITERATIONS = 3


def run_query(query, mode, top_k=10):
    """Run a single search and return (elapsed_ms, response_json)."""
    r = client.post(
        "/api/v1/search",
        json={
            "query": query,
            "mode": mode,
            "top_k": top_k,
        },
    )
    return r.status_code, r.json()


def timed_run(query, mode, top_k=10):
    """Run search with timing."""
    start = time.perf_counter()
    status, body = run_query(query, mode, top_k)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return elapsed_ms, status, body


def relevance_score(result, expected_terms):
    """Simple relevance: fraction of expected terms found in result text."""
    text = result.get("text", "")
    if not expected_terms:
        return 0.0
    found = sum(1 for t in expected_terms if t in text)
    return found / len(expected_terms)


def eval_case(tc):
    """Evaluate one test case across all its applicable modes."""
    results = {}
    for mode in tc["modes"]:
        timings = []
        body = None
        status = None

        # Warmup
        timed_run(tc["query"], mode)

        # Measure
        for _ in range(MEASURE_ITERATIONS):
            elapsed, s, b = timed_run(tc["query"], mode)
            timings.append(elapsed)
            status = s
            body = b

        hits = body.get("data", {}).get("results", []) if status == 200 else []
        total_hits = body.get("data", {}).get("total_hits", 0)

        # Precision@K: fraction of top-k results containing at least one expected term
        if tc["expected_terms"] and hits:
            relevant = sum(
                1
                for h in hits
                if any(t in h.get("text", "") for t in tc["expected_terms"])
            )
            precision_at_k = relevant / len(hits)
        else:
            precision_at_k = (
                0.0 if tc["expected_terms"] else None
            )  # None = not applicable

        # Average relevance across all results
        if hits:
            avg_rel = statistics.mean(
                relevance_score(h, tc["expected_terms"]) for h in hits
            )
        else:
            avg_rel = 0.0

        results[mode] = {
            "status": status,
            "total_hits": total_hits,
            "result_count": len(hits),
            "avg_ms": statistics.mean(timings),
            "p50_ms": statistics.median(timings),
            "p95_ms": max(timings),
            "min_ms": min(timings),
            "top_scores": [h.get("score", 0) for h in hits[:5]],
            "top_texts_preview": [h.get("text", "")[:80] for h in hits[:3]],
            "precision_at_k": precision_at_k,
            "avg_relevance": round(avg_rel, 3),
            "top_source_types": list({h.get("source_type") for h in hits}),
        }
    return results


def color_for_precision(p):
    if p is None:
        return ""
    if p >= 0.8:
        return "✓"
    elif p >= 0.3:
        return "△"
    else:
        return "✗"


def color_for_latency(ms):
    if ms < 200:
        return "✓"  # fast
    elif ms < 1000:
        return "△"  # acceptable
    else:
        return "✗"  # slow


def main():
    print("=" * 90)
    print("SEARCH-ENGINE EVALUATION REPORT")
    print("=" * 90)
    print("Data: 2 documents, 15 chunks (水利规范)")
    print(
        "Infra: PG (localhost:5434), Milvus (10.222.124.211), Ollama (localhost:11435)"
    )
    print(
        f"Iterations per test: {MEASURE_ITERATIONS} (after {WARMUP_ITERATIONS} warmup)"
    )
    print()

    all_results = {}

    for tc in TEST_CASES:
        print(f"[{tc['id']}] {tc['query'][:60]}")
        print(f"    Category: {tc['category']} | Expected: {tc['expected_terms']}")
        results = eval_case(tc)
        all_results[tc["id"]] = results

        for mode, r in results.items():
            lat = color_for_latency(r["avg_ms"])
            prec = color_for_precision(r["precision_at_k"])
            pk_str = (
                f"{r['precision_at_k']:.2f}"
                if r["precision_at_k"] is not None
                else "N/A"
            )
            print(
                f"    {mode:8s} {lat} {r['avg_ms']:7.1f}ms avg  "
                f"P@K={pk_str} {prec}  "
                f"rel={r['avg_relevance']:.2f}  "
                f"hits={r['total_hits']}  "
                f"scores={r['top_scores'][:3]}"
            )
            if r["top_texts_preview"]:
                for ti, t in enumerate(r["top_texts_preview"]):
                    print(f"            #{ti + 1}: {t[:75]}...")
        print()

    # ═══════════════════════════════════════════════════════════════
    # Summary statistics
    # ═══════════════════════════════════════════════════════════════
    print("=" * 90)
    print("SUMMARY")
    print("=" * 90)

    mode_stats = {}
    for tc_id, results in all_results.items():
        for mode, r in results.items():
            if mode not in mode_stats:
                mode_stats[mode] = {
                    "timings": [],
                    "precisions": [],
                    "rel_scores": [],
                    "hit_counts": [],
                }
            mode_stats[mode]["timings"].append(r["avg_ms"])
            if r["precision_at_k"] is not None:
                mode_stats[mode]["precisions"].append(r["precision_at_k"])
            mode_stats[mode]["rel_scores"].append(r["avg_relevance"])
            mode_stats[mode]["hit_counts"].append(r["result_count"])

    print(
        f"\n{'Mode':<10} {'Avg Lat':>8} {'P50 Lat':>8} {'Max Lat':>8} {'Avg Prec':>9} {'Avg Rel':>8} {'Avg Hits':>9}"
    )
    print("-" * 65)
    for mode in ["keyword", "fuzzy", "vector", "hybrid"]:
        if mode not in mode_stats:
            continue
        s = mode_stats[mode]
        avg_lat = statistics.mean(s["timings"])
        p50_lat = statistics.median(s["timings"])
        max_lat = max(s["timings"])
        avg_prec = statistics.mean(s["precisions"]) if s["precisions"] else 0
        avg_rel = statistics.mean(s["rel_scores"])
        avg_hits = statistics.mean(s["hit_counts"])
        print(
            f"{mode:<10} {avg_lat:7.1f}ms {p50_lat:7.1f}ms {max_lat:7.1f}ms "
            f"{avg_prec:8.2f} {avg_rel:8.3f} {avg_hits:8.1f}"
        )

    # ═══════════════════════════════════════════════════════════════
    # Evaluation
    # ═══════════════════════════════════════════════════════════════
    print()
    print("=" * 90)
    print("ASSESSMENT")
    print("=" * 90)

    issues = []
    passes = []

    # Latency check
    for mode in ["keyword", "fuzzy", "vector", "hybrid"]:
        if mode not in mode_stats:
            continue
        avg = statistics.mean(mode_stats[mode]["timings"])
        if avg < 100:
            passes.append(f"{mode} latency: avg={avg:.0f}ms — excellent")
        elif avg < 500:
            passes.append(f"{mode} latency: avg={avg:.0f}ms — acceptable")
        elif avg < 1000:
            issues.append(f"{mode} latency: avg={avg:.0f}ms — needs optimization")
        else:
            issues.append(f"{mode} latency: avg={avg:.0f}ms — too slow for production")

    # Precision check
    for mode in ["keyword", "fuzzy", "vector", "hybrid"]:
        if mode not in mode_stats or not mode_stats[mode]["precisions"]:
            continue
        avg_prec = statistics.mean(mode_stats[mode]["precisions"])
        if avg_prec >= 0.8:
            passes.append(f"{mode} precision@{10}: {avg_prec:.2f} — good")
        elif avg_prec >= 0.5:
            passes.append(
                f"{mode} precision@{10}: {avg_prec:.2f} — adequate for RRF fusion"
            )
        else:
            issues.append(
                f"{mode} precision@{10}: {avg_prec:.2f} — may need threshold tuning"
            )

    # Non-existent query handling
    ne_results = all_results.get("NE1", {})
    for mode, r in ne_results.items():
        if r["result_count"] == 0:
            passes.append(f"{mode} non-existent query: correctly returned empty")
        else:
            issues.append(
                f"{mode} non-existent query: returned {r['result_count']} results (should be 0)"
            )

    print("\nPASSES:")
    for p in passes:
        print(f"  ✓ {p}")
    print("\nISSUES:")
    if issues:
        for i in issues:
            print(f"  ⚠ {i}")
    else:
        print("  (none)")

    print()
    print("=" * 90)
    if len(issues) == 0:
        print("VERDICT: READY FOR PRODUCTION PILOT")
    elif len(issues) <= 2:
        print("VERDICT: CONDITIONALLY READY (minor issues noted)")
    else:
        print("VERDICT: NEEDS IMPROVEMENT BEFORE PRODUCTION")
    print("=" * 90)


if __name__ == "__main__":
    main()
