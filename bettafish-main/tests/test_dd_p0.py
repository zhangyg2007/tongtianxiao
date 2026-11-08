"""P0 投资尽调：评分卡三态判定 + 证据后校验 单测（纯函数，无外部依赖）。

运行：cd bettafish-main && python -m unittest tests.test_dd_p0 -v
"""

import unittest

from backend.dd.report import assess_dimensions, build_blocks, veto_reasons
from backend.dd.scorecard import DimensionAssessment, compute_scorecard
from backend.dd.template import CHAPTERS, SCORECARD_DIMENSIONS
from backend.dd.verify import (
    extract_citations,
    extract_numbers,
    numbers_missing_in_quote,
    verify_report,
)


def _dim(key, name, weight, status, score=0):
    return DimensionAssessment(key, name, weight, status, score)


class TemplateTests(unittest.TestCase):
    def test_12_chapters(self):
        self.assertEqual(len(CHAPTERS), 12)
        self.assertEqual([c["no"] for c in CHAPTERS], list(range(1, 13)))

    def test_scorecard_weights_sum_100(self):
        self.assertEqual(sum(d["weight"] for d in SCORECARD_DIMENSIONS), 100)

    def test_dimension_fact_types_map_to_chapters(self):
        chapter_fact_types = {
            ft for ch in CHAPTERS for ft in ch.get("fact_types", [])
        }
        for dim in SCORECARD_DIMENSIONS:
            for ft in dim["fact_types"]:
                self.assertIn(ft, chapter_fact_types, f"{ft} 未映射到任何章节")


class ScorecardTests(unittest.TestCase):
    def test_all_missing(self):
        card = compute_scorecard([
            _dim("a", "A", 10, "missing"),
            _dim("b", "B", 90, "missing"),
        ])
        self.assertEqual(card.coverage, 0.0)
        self.assertIsNone(card.score)
        self.assertEqual(card.verdict, "insufficient_data")

    def test_coverage_and_score(self):
        # 有效维度：A(10, ok=100) + B(20, risk=40)；缺失 C(70)
        # 覆盖率 = 30/100 = 30% < 60% → 拒绝出结论
        card = compute_scorecard([
            _dim("a", "A", 10, "ok"),
            _dim("b", "B", 20, "risk", 40),
            _dim("c", "C", 70, "missing"),
        ])
        self.assertAlmostEqual(card.coverage, 0.30)
        self.assertAlmostEqual(card.score, (100 * 10 + 40 * 20) / 30)
        self.assertEqual(card.verdict, "insufficient_data")

    def test_reference_only_band(self):
        # 覆盖率 65%：60% <= x < 80%
        card = compute_scorecard([
            _dim("a", "A", 65, "ok"),
            _dim("c", "C", 35, "missing"),
        ])
        self.assertEqual(card.verdict, "reference_only")

    def test_usable(self):
        card = compute_scorecard([_dim("a", "A", 80, "ok"), _dim("c", "C", 20, "missing")])
        self.assertEqual(card.verdict, "usable")
        self.assertAlmostEqual(card.score, 100.0)

    def test_veto_overrides(self):
        card = compute_scorecard(
            [_dim("a", "A", 100, "ok")], veto_reasons=["命中一票否决项「吊销」"]
        )
        self.assertEqual(card.verdict, "veto")
        self.assertTrue(card.veto_reasons)

    def test_top_risks_by_weight(self):
        card = compute_scorecard([
            _dim("a", "A", 5, "risk", 40),
            _dim("b", "B", 20, "risk", 40),
            _dim("c", "C", 10, "ok"),
        ])
        self.assertEqual([d.key for d in card.top_risks(2)], ["b", "a"])


class VerifyTests(unittest.TestCase):
    def test_extract_citations(self):
        text = "罚款 200 万元（依据 E12）；另见 E3 与 E12"
        self.assertEqual(extract_citations(text), [12, 3])

    def test_extract_numbers_skips_citation_marker(self):
        self.assertEqual(extract_numbers("E12 罚款 200 万元"), ["200"])

    def test_extract_numbers_dates_and_thousands(self):
        nums = extract_numbers("于 2024-03-12 罚款 1,000.50 万元")
        self.assertEqual(nums, ["2024-03-12", "1000.50"])

    def test_numbers_missing_in_quote(self):
        fact = "于 2024-03-12 被罚款 200 万元"
        quote = "……于2024-03-12责令当事人……"
        self.assertEqual(numbers_missing_in_quote(fact, quote), ["200"])
        self.assertEqual(
            numbers_missing_in_quote(fact, "……罚款人民币200万元……"), ["2024-03-12"]
        )

    def test_verify_report_pass(self):
        ev = {
            "evidence_id": 1,
            "object_id": 7,
            "fact": "于 2024-03-12 被罚款 200 万元",
            "quote": "……于2024-03-12罚款人民币200万元……",
        }
        blocks = [
            {"seq": 1, "block_type": "heading", "content_md": "## 6. 行政处罚"},
            {"seq": 2, "block_type": "paragraph",
             "content_md": "- 【事实陈述】于 2024-03-12 被罚款 200 万元（依据 E1）"},
        ]
        result = verify_report(blocks, {1: ev}, 7)
        self.assertEqual(result["passed"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["issues"], [])

    def test_verify_report_number_mismatch(self):
        ev = {
            "evidence_id": 1, "object_id": 7,
            "fact": "被罚款 500 万元",
            "quote": "……罚款人民币200万元……",  # 数字不一致
        }
        blocks = [
            {"seq": 2, "block_type": "paragraph",
             "content_md": "- 被罚款 500 万元（依据 E1）"},
        ]
        result = verify_report(blocks, {1: ev}, 7)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["issues"][0]["type"], "number_mismatch")

    def test_verify_report_missing_and_mismatch_object(self):
        blocks = [
            {"seq": 3, "block_type": "paragraph",
             "content_md": "- 某断言（依据 E9）"},
        ]
        # E9 不存在
        result = verify_report(blocks, {}, 7)
        self.assertEqual(result["issues"][0]["type"], "missing_evidence")
        # E9 归属别的对象
        ev = {"evidence_id": 9, "object_id": 8, "fact": "x", "quote": "y"}
        result = verify_report(blocks, {9: ev}, 7)
        self.assertEqual(result["issues"][0]["type"], "object_mismatch")

    def test_verify_report_line_scoped(self):
        # 同一块内两行各引一条证据：数字回查不得张冠李戴
        ev1 = {"evidence_id": 1, "object_id": 7, "fact": "罚款 100 万元", "quote": "罚款100万元"}
        ev2 = {"evidence_id": 2, "object_id": 7, "fact": "罚款 200 万元", "quote": "罚款200万元"}
        blocks = [
            {"seq": 2, "block_type": "paragraph",
             "content_md": "- 罚款 100 万元（依据 E1）\n- 罚款 200 万元（依据 E2）"},
        ]
        result = verify_report(blocks, {1: ev1, 2: ev2}, 7)
        self.assertEqual(result["failed"], 0)


class ReportBuildTests(unittest.TestCase):
    def _rows(self):
        return [
            {"evidence_id": 1, "object_id": 7, "fact_type": "penalty",
             "fact": "于 2024-03-12 被罚款 200 万元", "source_type": "gsxt",
             "source_name": "公示系统", "source_url": "https://e.gov/1",
             "quote": "……于2024-03-12罚款人民币200万元……",
             "published_at": "2024-03-12T00:00:00+00:00", "confidence": 95},
            {"evidence_id": 2, "object_id": 7, "fact_type": "litigation",
             "fact": "2024-06-20 作为被告开庭", "source_type": "court",
             "source_name": None, "source_url": "https://e.court/2",
             "quote": "定于2024-06-20开庭",
             "published_at": "2024-06-20T00:00:00+00:00", "confidence": 95},
        ]

    def test_assess_and_verdict(self):
        rows = self._rows()
        assessments = assess_dimensions(rows)
        by_key = {a.key: a for a in assessments}
        self.assertEqual(by_key["compliance"].status, "risk")
        self.assertEqual(by_key["litigation"].status, "risk")
        self.assertEqual(by_key["stability"].status, "missing")
        # 覆盖率 = (20+15)/100 = 35% < 60% → 拒绝出结论（诚实的三态设计）
        card = compute_scorecard(assessments, veto_reasons(rows))
        self.assertAlmostEqual(card.coverage, 0.35)
        self.assertEqual(card.verdict, "insufficient_data")

    def test_build_blocks_structure(self):
        rows = self._rows()
        card = compute_scorecard(assess_dimensions(rows), [])
        blocks = build_blocks({"display_name": "某公司"}, rows, card)
        headings = [b for b in blocks if b["block_type"] == "heading"]
        self.assertEqual(len(headings), 12)
        # 事实句带角标
        facts = [b["content_md"] for b in blocks if "（依据 E1）" in (b.get("content_md") or "")]
        self.assertTrue(facts)
        # 无数据章节标注数据不足
        ch3 = [b for b in blocks if b.get("chapter_no") == 3
               and b["block_type"] == "paragraph"]
        self.assertIn("【数据不足】", ch3[0]["content_md"])

    def test_veto_keywords(self):
        rows = [{"evidence_id": 3, "object_id": 7, "fact_type": "penalty",
                 "fact": "该公司已被吊销营业执照", "quote": "吊销",
                 "source_type": "gsxt", "source_url": "u", "confidence": 95,
                 "published_at": None}]
        self.assertEqual(len(veto_reasons(rows)), 1)


if __name__ == "__main__":
    unittest.main()
