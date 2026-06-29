"""Issue #7: Full Integration Tests — 45 test cases across 9 categories.

Covers all scenarios defined in issues/issue-07-full-integration.md.
Uses FastAPI TestClient against the real chat endpoint with real LLM + search-engine.

Usage:
    AGENT_VLLM_URL=http://10.222.124.211:8000/v1 \\
    AGENT_SEARCH_ENGINE_URL=http://localhost:8002 \\
    pytest tests/test_full_integration.py -v --tb=short -k "TestCat"

Report output is written to tests/integration_report.json after the full run.
"""

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


from src.main import app

REPORT_PATH = Path(__file__).resolve().parent / "integration_report.json"


@pytest.fixture
def client():
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════


def _chat(client, query, conversation_id=None, retrieval_mode="hybrid"):
    """Send one chat request and return (status_code, body)."""
    body = {"query": query, "retrieval_mode": retrieval_mode}
    if conversation_id:
        body["conversation_id"] = conversation_id
    resp = client.post("/api/v1/chat", json=body)
    return resp.status_code, resp.json()


def _check_ok(status_code, body):
    """Assert 200 + code=0, returning data dict."""
    assert status_code == 200, f"Expected 200, got {status_code}: {body}"
    assert body.get("code") == 0, f"Expected code=0, got {body}"
    data = body.get("data", {})
    assert "answer" in data, "data missing 'answer'"
    assert "citations" in data, "data missing 'citations'"
    return data


def _has_citations(data):
    return len(data.get("citations", [])) > 0


def _answer_contains_any(data, keywords):
    answer = data.get("answer", "")
    return any(kw in answer for kw in keywords)


# ── Report accumulator ──
_results: list[dict] = []


@pytest.fixture(scope="session", autouse=True)
def report_collector():
    """Accumulate results across all tests and write report at session end."""
    global _results
    _results = []
    yield
    if _results:
        passed = sum(1 for r in _results if r["passed"])
        failed = sum(1 for r in _results if not r["passed"])
        report = {
            "total": len(_results),
            "passed": passed,
            "failed": failed,
            "pass_rate": f"{passed / len(_results) * 100:.1f}%" if _results else "N/A",
            "by_category": {},
            "cases": _results,
        }
        # Aggregate by category
        for r in _results:
            cat = r["category"]
            if cat not in report["by_category"]:
                report["by_category"][cat] = {
                    "total": 0,
                    "passed": 0,
                    "failed": 0,
                    "cases": [],
                }
            report["by_category"][cat]["total"] += 1
            if r["passed"]:
                report["by_category"][cat]["passed"] += 1
            else:
                report["by_category"][cat]["failed"] += 1
            report["by_category"][cat]["cases"].append(
                {
                    "id": r["id"],
                    "query": r["query"],
                    "passed": r["passed"],
                    "notes": r.get("notes", ""),
                    "answer_preview": r.get("answer", "")[:200],
                }
            )
        REPORT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n📊 Integration report written to {REPORT_PATH}")
        print(
            f"   Total: {report['total']} | Passed: {report['passed']} | Failed: {report['failed']} | Rate: {report['pass_rate']}"
        )


def _record(category, case_id, query, passed, data=None, notes=""):
    answer_preview = data.get("answer", "")[:300] if data else ""
    _results.append(
        {
            "category": category,
            "id": case_id,
            "query": query,
            "passed": passed,
            "notes": notes,
            "answer": answer_preview,
            "citations_count": len(data.get("citations", [])) if data else 0,
        }
    )


# ═══════════════════════════════════════════════════════════════
# Category 1: 单问题知识问答 (knowledge_qa — 简单事实查询)
# ═══════════════════════════════════════════════════════════════


class TestCat1KnowledgeQA:
    """Simple fact lookup from 1-2 chunks."""

    def test_q1_1_crack_width_threshold(self, client):
        """混凝土坝裂缝宽度超过多少需要处理？"""
        query = "混凝土坝裂缝宽度超过多少需要处理？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(
            data, ["0.2", "0.3", "灌浆", "封闭"]
        )
        _record("1-知识问答", "Q1-1", query, ok, data)
        assert ok, f"Answer should mention crack thresholds: {data['answer'][:200]}"

    def test_q1_2_defect_categories(self, client):
        """水工建筑物的缺陷分为哪几类？"""
        query = "水工建筑物的缺陷分为哪几类？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(
            data, ["结构缺陷", "渗流缺陷", "材料劣化", "附属设施"]
        )
        _record("1-知识问答", "Q1-2", query, ok, data)
        assert ok, f"Answer should mention 4 defect categories: {data['answer'][:200]}"

    def test_q1_3_leakage_emergency_threshold(self, client):
        """渗漏量达到多少时需要启动应急响应？"""
        query = "渗漏量达到多少时需要启动应急响应？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(
            data, ["1.0", "应急", "浑浊"]
        )
        _record("1-知识问答", "Q1-3", query, ok, data)
        assert ok, f"Answer should mention >1.0L/s emergency: {data['answer'][:200]}"

    def test_q1_4_carbonation_severe(self, client):
        """混凝土碳化深度达到多少算严重碳化？"""
        query = "混凝土碳化深度达到多少算严重碳化？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(
            data, ["保护层", "碳化", "电化学"]
        )
        _record("1-知识问答", "Q1-4", query, ok, data)
        assert ok, f"Answer should mention carbonation depth: {data['answer'][:200]}"

    def test_q1_5_inspection_types_frequency(self, client):
        """水工建筑物的缺陷检查有哪几种类型？检查频率是多少？"""
        query = "水工建筑物的缺陷检查有哪几种类型？检查频率是多少？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(
            data, ["日常", "年度详查", "特殊检查"]
        )
        _record("1-知识问答", "Q1-5", query, ok, data)
        assert ok, f"Answer should mention inspection types: {data['answer'][:200]}"


# ═══════════════════════════════════════════════════════════════
# Category 2: 多问题/复合问题问答 (knowledge_qa — 需拆解)
# ═══════════════════════════════════════════════════════════════


class TestCat2CompoundQA:
    """Multi-aspect questions requiring decomposition."""

    def test_q2_1_crack_classification_and_treatment(self, client):
        """混凝土裂缝的分类标准有哪些，各等级应如何处理？"""
        query = "混凝土裂缝的分类标准有哪些，各等级应如何处理？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(
            data, ["0.2", "封闭", "灌浆"]
        )
        _record("2-复合问题", "Q2-1", query, ok, data)
        assert ok, (
            f"Answer should cover classification + treatment: {data['answer'][:200]}"
        )

    def test_q2_2_leakage_grading_and_treatment(self, client):
        """渗漏有哪些分级标准？不同等级的渗漏分别怎么治理？"""
        query = "渗漏有哪些分级标准？不同等级的渗漏分别怎么治理？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(
            data, ["0.1", "帷幕", "灌浆"]
        )
        _record("2-复合问题", "Q2-2", query, ok, data)
        assert ok, f"Answer should cover grading + treatment: {data['answer'][:200]}"

    def test_q2_3_strength_detection_and_reinforcement(self, client):
        """水工建筑物混凝土强度不足怎么检测？检测出不足后又该如何加固？"""
        query = "水工建筑物混凝土强度不足怎么检测？检测出不足后又该如何加固？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(
            data, ["回弹", "钻芯", "加固"]
        )
        _record("2-复合问题", "Q2-3", query, ok, data)
        assert ok, (
            f"Answer should cover detection + reinforcement: {data['answer'][:200]}"
        )

    def test_q2_4_discharge_safety_evaluation(self, client):
        """泄水建筑物的安全评价包括哪些方面？泄洪能力不足时该怎么办？"""
        query = "泄水建筑物的安全评价包括哪些方面？泄洪能力不足时该怎么办？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(
            data, ["泄洪", "消能", "复核"]
        )
        _record("2-复合问题", "Q2-4", query, ok, data)
        assert ok, (
            f"Answer should cover evaluation aspects + remedies: {data['answer'][:200]}"
        )


# ═══════════════════════════════════════════════════════════════
# Category 3: 对比问题 (comparison)
# ═══════════════════════════════════════════════════════════════


class TestCat3Comparison:
    """Comparison questions — validates comparison query_type and contrasting answers."""

    def test_q3_1_surface_sealing_vs_grouting(self, client):
        """表面封闭法和灌浆法处理裂缝各适用于什么情况？有什么区别？"""
        query = "表面封闭法和灌浆法处理裂缝各适用于什么情况？有什么区别？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(
            data, ["封闭", "灌浆", "0.2"]
        )
        _record("3-对比问题", "Q3-1", query, ok, data)
        assert ok, f"Answer should compare two methods: {data['answer'][:200]}"

    def test_q3_2_curtain_vs_chemical_grouting(self, client):
        """帷幕灌浆和化学灌浆在处理渗漏时各有什么适用条件和优缺点？"""
        query = "帷幕灌浆和化学灌浆在处理渗漏时各有什么适用条件和优缺点？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(data, ["帷幕", "化学"])
        _record("3-对比问题", "Q3-2", query, ok, data)
        assert ok, f"Answer should compare grouting methods: {data['answer'][:200]}"

    def test_q3_3_rebound_vs_core_drilling(self, client):
        """回弹法和钻芯法检测混凝土强度各有什么优缺点？什么情况下应优先用钻芯法？"""
        query = "回弹法和钻芯法检测混凝土强度各有什么优缺点？什么情况下应优先用钻芯法？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(
            data, ["回弹", "钻芯", "承重"]
        )
        _record("3-对比问题", "Q3-3", query, ok, data)
        assert ok, f"Answer should compare detection methods: {data['answer'][:200]}"

    def test_q3_4_stilling_basin_vs_flip_bucket(self, client):
        """消力池底流消能和挑流消能的安全评价标准有什么不同？"""
        query = "消力池底流消能和挑流消能的安全评价标准有什么不同？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(
            data, ["底流", "挑流", "30%", "冲刷"]
        )
        _record("3-对比问题", "Q3-4", query, ok, data)
        assert ok, (
            f"Answer should compare energy dissipation standards: {data['answer'][:200]}"
        )


# ═══════════════════════════════════════════════════════════════
# Category 4: 多轮对话问题（检测记忆和指代消解）
# ═══════════════════════════════════════════════════════════════


class TestCat4MultiTurn:
    """Multi-turn conversations — validates ConversationStore memory + anaphora resolution."""

    CONV_ID = f"conv-mt-{uuid.uuid4().hex[:8]}"

    def test_q4_1_turn1_crack_classification(self, client):
        """Turn 1: DL/T 2628 里对裂缝是怎么分类处理的？"""
        query = "DL/T 2628 里对裂缝是怎么分类处理的？"
        status, body = _chat(client, query, conversation_id=self.CONV_ID)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(data, ["0.2", "裂缝", "mm"])
        _record("4-多轮对话", "Q4-1-T1", query, ok, data)
        assert ok, f"Turn 1 crack classification: {data['answer'][:200]}"

    def test_q4_1_turn2_leakage_in_same_spec(self, client):
        """Turn 2: 那这本规范里对渗漏又是怎么分级的？"""
        query = "那这本规范里对渗漏又是怎么分级的？"
        status, body = _chat(client, query, conversation_id=self.CONV_ID)
        data = _check_ok(status, body)
        ok = _answer_contains_any(data, ["渗漏", "0.1", "L/s", "严重"])
        _record(
            "4-多轮对话",
            "Q4-1-T2",
            query,
            ok,
            data,
            notes="Should resolve '这本规范' → DL/T 2628-2023",
        )
        assert ok, (
            f"Turn 2 should resolve '这本规范' → DL/T 2628: {data['answer'][:200]}"
        )

    CONV_ID_2 = f"conv-mt-{uuid.uuid4().hex[:8]}"

    def test_q4_2_turn1_curtain_grouting(self, client):
        """Turn 1: 什么是帷幕灌浆？用在什么场景？"""
        query = "什么是帷幕灌浆？用在什么场景？"
        status, body = _chat(client, query, conversation_id=self.CONV_ID_2)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(data, ["帷幕", "灌浆"])
        _record("4-多轮对话", "Q4-2-T1", query, ok, data)
        assert ok, f"Turn 1 curtain grouting: {data['answer'][:200]}"

    def test_q4_2_turn2_grouting_pressure(self, client):
        """Turn 2: 你刚才说的这种灌浆方法的灌浆压力一般控制在什么范围？"""
        query = "你刚才说的这种灌浆方法的灌浆压力一般控制在什么范围？"
        status, body = _chat(client, query, conversation_id=self.CONV_ID_2)
        data = _check_ok(status, body)
        ok = _answer_contains_any(data, ["0.3", "1.5", "MPa"])
        _record(
            "4-多轮对话",
            "Q4-2-T2",
            query,
            ok,
            data,
            notes="Should resolve '这种灌浆方法' → 帷幕灌浆, answer 0.3-1.5MPa",
        )
        assert ok, (
            f"Turn 2 should resolve → 帷幕灌浆 pressure range: {data['answer'][:200]}"
        )

    CONV_ID_3 = f"conv-mt-{uuid.uuid4().hex[:8]}"

    def test_q4_3_turn1_carbonation_detection(self, client):
        """Turn 1: 水工建筑物混凝土碳化深度怎么检测和评定？"""
        query = "水工建筑物混凝土碳化深度怎么检测和评定？"
        status, body = _chat(client, query, conversation_id=self.CONV_ID_3)
        data = _check_ok(status, body)
        ok = _has_citations(data)
        _record("4-多轮对话", "Q4-3-T1", query, ok, data)
        assert ok, f"Turn 1 carbonation: {data['answer'][:200]}"

    def test_q4_3_turn2_water_level_variation_zone(self, client):
        """Turn 2: 上面提到的水位变动区的检测周期应该缩短到多久？"""
        query = "上面提到的水位变动区的检测周期应该缩短到多久？"
        status, body = _chat(client, query, conversation_id=self.CONV_ID_3)
        data = _check_ok(status, body)
        ok = _answer_contains_any(data, ["3", "年", "水位变动"])
        _record(
            "4-多轮对话",
            "Q4-3-T2",
            query,
            ok,
            data,
            notes="Should resolve '上面提到的' → carbonation detection zone",
        )
        assert ok, f"Turn 2 should resolve → 水位变动区 3年检测: {data['answer'][:200]}"

    CONV_ID_4 = f"conv-mt-{uuid.uuid4().hex[:8]}"

    def test_q4_4_turn1_energy_dissipation_types(self, client):
        """Turn 1: 泄水建筑物的消能设施有哪些类型？"""
        query = "泄水建筑物的消能设施有哪些类型？"
        status, body = _chat(client, query, conversation_id=self.CONV_ID_4)
        data = _check_ok(status, body)
        ok = _has_citations(data)
        _record("4-多轮对话", "Q4-4-T1", query, ok, data)
        assert ok, f"Turn 1 energy dissipation: {data['answer'][:200]}"

    def test_q4_4_turn2_stilling_basin_damage(self, client):
        """Turn 2: 之前说的底流消能工的消力池底板破坏到什么程度算不安全？"""
        query = "之前说的底流消能工的消力池底板破坏到什么程度算不安全？"
        status, body = _chat(client, query, conversation_id=self.CONV_ID_4)
        data = _check_ok(status, body)
        ok = _answer_contains_any(data, ["30%", "50%", "不安全"])
        _record(
            "4-多轮对话",
            "Q4-4-T2",
            query,
            ok,
            data,
            notes="Should resolve → 消力池底板破坏>30% 不安全",
        )
        assert ok, f"Turn 2 should resolve → stilling basin: {data['answer'][:200]}"

    CONV_ID_5 = f"conv-mt-{uuid.uuid4().hex[:8]}"

    def test_q4_5_turn1_metal_structures(self, client):
        """Turn 1: 水工金属结构主要有哪些？常见的缺陷是什么？"""
        query = "水工金属结构主要有哪些？常见的缺陷是什么？"
        status, body = _chat(client, query, conversation_id=self.CONV_ID_5)
        data = _check_ok(status, body)
        ok = _has_citations(data)
        _record("4-多轮对话", "Q4-5-T1", query, ok, data)
        assert ok, f"Turn 1 metal structures: {data['answer'][:200]}"

    def test_q4_5_turn2_pipe_wall_thinning(self, client):
        """Turn 2: 那刚才提到的压力钢管壁厚减薄多少时需要强度复核？"""
        query = "那刚才提到的压力钢管壁厚减薄多少时需要强度复核？"
        status, body = _chat(client, query, conversation_id=self.CONV_ID_5)
        data = _check_ok(status, body)
        ok = _answer_contains_any(data, ["15%", "壁厚", "减薄"])
        _record(
            "4-多轮对话",
            "Q4-5-T2",
            query,
            ok,
            data,
            notes="Should resolve → 压力钢管壁厚减薄>15%",
        )
        assert ok, f"Turn 2 should resolve → wall thinning >15%: {data['answer'][:200]}"


# ═══════════════════════════════════════════════════════════════
# Category 5: 规范条文查询 (spec_lookup)
# ═══════════════════════════════════════════════════════════════


class TestCat5SpecLookup:
    """Standard/specification reference queries."""

    def test_q5_1_penetrating_crack_treatment(self, client):
        """DL/T 2628 对贯穿性裂缝的处理有什么规定？"""
        query = "DL/T 2628 对贯穿性裂缝的处理有什么规定？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(data, ["灌浆", "贯穿"])
        _record("5-规范条文查询", "Q5-1", query, ok, data)
        assert ok, f"Spec lookup for penetrating cracks: {data['answer'][:200]}"

    def test_q5_2_discharge_capacity_review(self, client):
        """根据 DL/T 2700，泄洪能力复核应该按什么步骤进行？"""
        query = "根据 DL/T 2700，泄洪能力复核应该按什么步骤进行？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(
            data, ["水文", "过流", "调洪"]
        )
        _record("5-规范条文查询", "Q5-2", query, ok, data)
        assert ok, f"Spec lookup for discharge review steps: {data['answer'][:200]}"

    def test_q5_3_monitoring_precision(self, client):
        """DL/T 2628 对混凝土坝的安全监测精度有什么要求？"""
        query = "DL/T 2628 对混凝土坝的安全监测精度有什么要求？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(
            data, ["1mm", "变形", "渗流"]
        )
        _record("5-规范条文查询", "Q5-3", query, ok, data)
        assert ok, f"Spec lookup for monitoring precision: {data['answer'][:200]}"

    def test_q5_4_weld_inspection(self, client):
        """DL/T 2628 第 5.5 节对金属结构焊缝的无损检测有什么规定？"""
        query = "DL/T 2628 第 5.5 节对金属结构焊缝的无损检测有什么规定？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(
            data, ["焊缝", "超声", "5年", "磁粉"]
        )
        _record("5-规范条文查询", "Q5-4", query, ok, data)
        assert ok, f"Spec lookup for weld inspection: {data['answer'][:200]}"

    def test_q5_5_annual_report_deadline(self, client):
        """按照 DL/T 2628 的要求，缺陷年度统计分析报告应该在什么时候完成？"""
        query = "按照 DL/T 2628 的要求，缺陷年度统计分析报告应该在什么时候完成？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(data, ["1月31", "年度"])
        _record("5-规范条文查询", "Q5-5", query, ok, data)
        assert ok, f"Spec lookup for report deadline: {data['answer'][:200]}"


# ═══════════════════════════════════════════════════════════════
# Category 6: 多跳推理 (Multi-Hop Reasoning)
# ═══════════════════════════════════════════════════════════════


class TestCat6MultiHop:
    """Questions requiring cross-chunk reasoning chains."""

    def test_q6_1_crack_and_leakage_combined(self, client):
        """大坝同时出现裂缝和渗漏，评估严重程度和处理优先级"""
        query = "如果一个大坝同时出现了裂缝和渗漏问题，应该分别按照什么标准来评估严重程度和处理优先级？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(data, ["裂缝", "渗漏"])
        _record(
            "6-多跳推理",
            "Q6-1",
            query,
            ok,
            data,
            notes="Should chain crack + leakage standards from 2+ chunks",
        )
        assert ok, f"Multi-hop crack + leakage: {data['answer'][:200]}"

    def test_q6_2_30yr_safety_review_scour(self, client):
        """泄水建筑物运行>30年安全评价重点 + 冲刷坑过深处理"""
        query = "泄水建筑物运行超过 30 年后，安全评价需要重点关注哪些方面？如果同时发现冲刷坑过深该怎么办？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(
            data, ["复核", "冲刷", "30年"]
        )
        _record(
            "6-多跳推理",
            "Q6-2",
            query,
            ok,
            data,
            notes="Should chain: 30yr safety review → scour evaluation → remedies",
        )
        assert ok, f"Multi-hop 30yr + scour: {data['answer'][:200]}"

    def test_q6_3_water_level_variation_zone(self, client):
        """水位变动区混凝土结构碳化检测和日常检查特殊要求"""
        query = "对于水位变动区的混凝土结构，碳化检测和日常检查分别有什么特殊要求？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = _has_citations(data) and _answer_contains_any(
            data, ["3年", "碳化", "水位变动"]
        )
        _record(
            "6-多跳推理",
            "Q6-3",
            query,
            ok,
            data,
            notes="Should chain carbonation detection cycle + daily inspection requirements",
        )
        assert ok, f"Multi-hop water level variation zone: {data['answer'][:200]}"


# ═══════════════════════════════════════════════════════════════
# Category 7: 检索无结果
# ═══════════════════════════════════════════════════════════════


class TestCat7NoResults:
    """Topics outside the knowledge base — must not hallucinate."""

    def test_q7_1_seismic_design_standards(self, client):
        """水电站大坝的抗震设计标准是什么？设防烈度怎么确定？"""
        query = "水电站大坝的抗震设计标准是什么？设防烈度怎么确定？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        answer = data.get("answer", "")
        ok = (
            len(data.get("citations", [])) == 0
            or "未找到" in answer
            or "没有" in answer
            or "不在" in answer
        )
        _record(
            "7-检索无结果",
            "Q7-1",
            query,
            ok,
            data,
            notes=f"Should NOT fabricate seismic standards: {answer[:150]}",
        )
        assert ok, f"Should indicate no results for seismic design: {answer[:200]}"

    def test_q7_2_earth_rock_dam_compaction(self, client):
        """土石坝的碾压施工质量控制要点有哪些？"""
        query = "土石坝的碾压施工质量控制要点有哪些？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        answer = data.get("answer", "")
        ok = (
            len(data.get("citations", [])) == 0
            or "未找到" in answer
            or "没有" in answer
            or "不在" in answer
        )
        _record(
            "7-检索无结果",
            "Q7-2",
            query,
            ok,
            data,
            notes=f"Should indicate no results for earth-rock dam: {answer[:150]}",
        )
        assert ok, f"Should indicate no results: {answer[:200]}"

    def test_q7_3_turbine_vibration_standards(self, client):
        """水电站水轮发电机组的振动标准是什么？"""
        query = "水电站水轮发电机组的振动标准是什么？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        answer = data.get("answer", "")
        ok = (
            len(data.get("citations", [])) == 0
            or "未找到" in answer
            or "没有" in answer
            or "不在" in answer
        )
        _record(
            "7-检索无结果",
            "Q7-3",
            query,
            ok,
            data,
            notes=f"Should indicate no electromechanical content: {answer[:150]}",
        )
        assert ok, f"Should indicate no results: {answer[:200]}"

    def test_q7_4_arch_gravity_dam_temperature(self, client):
        """拱坝和重力坝在温控设计上有什么区别？"""
        query = "拱坝和重力坝在温控设计上有什么区别？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        answer = data.get("answer", "")
        ok = (
            len(data.get("citations", [])) == 0
            or "未找到" in answer
            or "没有" in answer
            or "不在" in answer
        )
        _record(
            "7-检索无结果",
            "Q7-4",
            query,
            ok,
            data,
            notes=f"Should indicate no dam-type comparison content: {answer[:150]}",
        )
        assert ok, f"Should indicate no results: {answer[:200]}"


# ═══════════════════════════════════════════════════════════════
# Category 8: Chitchat
# ═══════════════════════════════════════════════════════════════


class TestCat8Chitchat:
    """Casual conversation — should skip retrieval, produce friendly response, no citations."""

    def test_q8_1_greeting(self, client):
        """你好，请问你是谁？"""
        query = "你好，请问你是谁？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = len(data.get("answer", "")) > 0 and not _has_citations(data)
        _record("8-Chitchat", "Q8-1", query, ok, data)
        assert ok, (
            f"Greeting should have answer but no citations: {data['answer'][:150]}"
        )

    def test_q8_2_capabilities(self, client):
        """你能帮我做什么？"""
        query = "你能帮我做什么？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = len(data.get("answer", "")) > 0 and not _has_citations(data)
        _record("8-Chitchat", "Q8-2", query, ok, data)
        assert ok, f"Capability intro: {data['answer'][:150]}"

    def test_q8_3_thanks(self, client):
        """谢谢你刚才的回答！"""
        query = "谢谢你刚才的回答！"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = len(data.get("answer", "")) > 0 and not _has_citations(data)
        _record("8-Chitchat", "Q8-3", query, ok, data)
        assert ok, f"Thanks response: {data['answer'][:150]}"

    def test_q8_4_weather_chitchat(self, client):
        """今天天气真不错，适合去大坝看看吗？"""
        query = "今天天气真不错，适合去大坝看看吗？"
        status, body = _chat(client, query)
        data = _check_ok(status, body)
        ok = len(data.get("answer", "")) > 0 and not _has_citations(data)
        _record("8-Chitchat", "Q8-4", query, ok, data)
        assert ok, f"Weather chat: {data['answer'][:150]}"


# ═══════════════════════════════════════════════════════════════
# Category 9: 错误处理
# ═══════════════════════════════════════════════════════════════


class TestCat9ErrorHandling:
    """Error handling — validates error codes and trace_id."""

    def test_q9_1_missing_query(self, client):
        """缺少 query 字段 → 422, code=1002"""
        resp = client.post("/api/v1/chat", json={"retrieval_mode": "hybrid"})
        body = resp.json()
        ok = resp.status_code == 422 and body.get("code") == 1002
        _record(
            "9-错误处理",
            "Q9-1",
            "missing query",
            ok,
            notes=f"status={resp.status_code}, body={body}",
        )
        assert ok, f"Expected 422 code=1002: {body}"

    def test_q9_2_invalid_retrieval_mode(self, client):
        """非法 retrieval_mode → 422, code=1002"""
        resp = client.post(
            "/api/v1/chat", json={"query": "test", "retrieval_mode": "invalid"}
        )
        body = resp.json()
        ok = resp.status_code == 422 and body.get("code") == 1002
        _record(
            "9-错误处理",
            "Q9-2",
            "invalid retrieval_mode",
            ok,
            notes=f"status={resp.status_code}, body={body}",
        )
        assert ok, f"Expected 422 code=1002: {body}"

    def test_q9_3_empty_query(self, client):
        """空 query → 422, code=1002 (min_length=1)"""
        resp = client.post(
            "/api/v1/chat", json={"query": "", "retrieval_mode": "hybrid"}
        )
        body = resp.json()
        ok = resp.status_code == 422 and body.get("code") == 1002
        _record(
            "9-错误处理",
            "Q9-3",
            "empty query",
            ok,
            notes=f"status={resp.status_code}, body={body}",
        )
        assert ok, f"Expected 422 code=1002: {body}"

    def test_q9_4_very_long_query(self, client):
        """超长 query 不崩溃 → 200"""
        query = "裂缝。" * 2000
        status, body = _chat(client, query)
        ok = status == 200 and body.get("code") == 0
        data = body.get("data", {})
        _record(
            "9-错误处理",
            "Q9-4",
            "very long query",
            ok,
            data,
            notes=f"status={status}, answer_len={len(data.get('answer', ''))}",
        )
        assert ok, (
            f"Long query should return 200: status={status}, body_keys={list(body.keys())}"
        )

    def test_q9_5_symbols_only_query(self, client):
        """纯符号 query 不崩溃 → 200"""
        query = "?!@#$%^&*()"
        status, body = _chat(client, query)
        ok = status == 200 and body.get("code") == 0
        data = body.get("data", {})
        _record(
            "9-错误处理",
            "Q9-5",
            "symbols only",
            ok,
            data,
            notes=f"status={status}, answer_preview={data.get('answer', '')[:100]}",
        )
        assert ok, (
            f"Symbols query should return 200: status={status}, body_keys={list(body.keys())}"
        )
