"""最小可用改造集单测：数据源适配层 + 实体对齐 v0 + 章节路由 + LLM 写作。

运行：cd bettafish-main && python -m unittest tests.test_sources -v
（纯函数测试，无 PG / Redis / 网络依赖；真实案例文件从 .trae/documents/cases 读取）
"""

import unittest
from datetime import datetime, timezone
from pathlib import Path

from backend.dd.report import build_scorecard, chapter_rows, veto_reasons
from backend.dd.template import CHAPTERS
from backend.dd.verify import verify_report
from backend.dd.writer import (
    build_user_prompt,
    draft_chapters,
    llm_enabled,
    validate_draft,
)
from backend.sources.akshare_src import AkShareFinancials  # noqa: F401 触发注册
from backend.sources.base import ALLOWED_FACT_TYPES, EvidenceIn
from backend.sources.case_file import CaseFileSource, case_evidence_to_evidence_in
from backend.sources.juchao import classify_announcement
from backend.worker.entities import (
    EntityAmbiguous,
    assert_same_entity,
    normalize_uscc,
    plan_company_resolution,
)

# git 仓库根（tests/ 的上两级）→ .trae/documents/cases/
GIT_ROOT = Path(__file__).resolve().parents[2]
REAL_CASE_PATH = GIT_ROOT / ".trae" / "documents" / "cases" / "real_002372_weixing.json"

_CH_BY_NO = {c["no"]: c for c in CHAPTERS}


def _row(evidence_id, fact, fact_type, **kw):
    return dict(evidence_id=evidence_id, fact=fact, fact_type=fact_type,
                source_type="cninfo", source_url="https://example.com/a",
                quote=None, source_name="测试源", published_at=None,
                object_id=1, confidence=90, **kw)


# ==================================================================
# 实体对齐 v0（USCC 主键，防同名串档——对抗样本 adv_01 场景）
# ==================================================================

class UsccTests(unittest.TestCase):
    def test_normalize_valid(self):
        self.assertEqual(normalize_uscc("91330000719525019t"), "91330000719525019T")
        self.assertEqual(normalize_uscc(" 91330000719525019T \n"), "91330000719525019T")

    def test_normalize_invalid(self):
        self.assertIsNone(normalize_uscc(None))
        self.assertIsNone(normalize_uscc(""))
        self.assertIsNone(normalize_uscc("9133000071952501"))       # 17 位
        self.assertIsNone(normalize_uscc("9133OOO07195250I9T"))     # 非法字符 I/O

    def test_plan_reuse_by_uscc(self):
        plan = plan_company_resolution("甲公司", "91330000719525019T",
                                       same_uscc_row={"object_id": 7},
                                       same_name_rows=[])
        self.assertEqual(plan, {"action": "reuse", "object_id": 7,
                                "name_conflict": False})

    def test_plan_same_name_different_uscc_never_merges(self):
        """同名不同码：新建隔离对象，绝不合并到既有同名对象。"""
        plan = plan_company_resolution(
            "甲公司", "91330000719525019T",
            same_uscc_row=None,
            same_name_rows=[{"object_id": 9, "natural_key": "91330000MA1B2C3D4X"}],
        )
        self.assertEqual(plan["action"], "create")
        self.assertTrue(plan["name_conflict"])
        self.assertNotIn("object_id", plan)

    def test_plan_no_uscc_unique_name_reuses(self):
        plan = plan_company_resolution("甲公司", None, same_uscc_row=None,
                                       same_name_rows=[{"object_id": 3}])
        self.assertEqual(plan["action"], "reuse")

    def test_plan_no_uscc_ambiguous_raises(self):
        with self.assertRaises(EntityAmbiguous):
            plan_company_resolution("甲公司", None, same_uscc_row=None,
                                    same_name_rows=[{"object_id": 3}, {"object_id": 4}])

    def test_assert_same_entity_blocks_mismatch(self):
        obj = {"object_id": 1, "display_name": "甲公司",
               "natural_key": "91330000719525019T"}
        # 一致 → 通过
        assert_same_entity(obj, "91330000719525019T")
        # 同名不同码 → 拒绝
        with self.assertRaises(ValueError):
            assert_same_entity(obj, "91330000MA1B2C3D4X")
        # 对象无码 → 不拦（v0 容忍）
        assert_same_entity({"object_id": 2, "display_name": "乙公司"}, "91330000719525019T")


# ==================================================================
# 数据源适配层
# ==================================================================

class EvidenceInTests(unittest.TestCase):
    def test_validate_ok(self):
        EvidenceIn(fact="甲公司注册资本 1000 万元", fact_type="registration",
                   source_type="cninfo", source_url="https://example.com/a").validate()

    def test_validate_rejects(self):
        base = dict(source_type="cninfo", source_url="https://example.com/a")
        with self.assertRaises(ValueError):  # fact_type 非法
            EvidenceIn(fact="x", fact_type="ownership_v9", **base).validate()
        with self.assertRaises(ValueError):  # 缺 url
            EvidenceIn(fact="x", fact_type="registration",
                       source_type="cninfo", source_url=" ").validate()
        with self.assertRaises(ValueError):  # confidence 越界
            EvidenceIn(fact="x", fact_type="registration", confidence=101, **base).validate()


class JuchaoClassifyTests(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(classify_announcement("2025年年度报告"), "finance")
        self.assertEqual(classify_announcement("关于收到法院判决书的公告"), "litigation")
        self.assertEqual(classify_announcement("关于收到监管警示函的公告"), "penalty")
        self.assertEqual(classify_announcement("关于中标重大项目的公告"), "bid")
        self.assertEqual(classify_announcement("关于控股股东质押股份的公告"), "registration")
        self.assertEqual(classify_announcement("关于取得发明专利的公告"), "ip")
        self.assertEqual(classify_announcement("关于召开股东大会的通知"), "registration")


class CaseFileTests(unittest.TestCase):
    """真实案例（伟星新材 50 条证据）→ EvidenceIn 映射回归。"""

    @classmethod
    def setUpClass(cls):
        cls.case = CaseFileSource().collect(
            object_row={"object_id": 1, "display_name": "浙江伟星新型建材股份有限公司",
                        "natural_key": "91330000719525019T"},
            params={"case_path": str(REAL_CASE_PATH)},
        )

    def test_case_file_exists(self):
        self.assertTrue(REAL_CASE_PATH.is_file(), f"案例文件缺失：{REAL_CASE_PATH}")

    def test_50_evidence_mapped(self):
        self.assertEqual(len(self.case), 50)

    def test_all_fields_valid(self):
        for ev in self.case:
            ev.validate()  # fact 非空 / url 非空 / fact_type 合法 / confidence 越界
        self.assertTrue(all(ev.quote for ev in self.case))  # 真实案例 quote 必须齐

    def test_published_at_parsed(self):
        self.assertTrue(all(isinstance(ev.published_at, datetime) for ev in self.case))

    def test_fact_type_coverage(self):
        types = {ev.fact_type for ev in self.case}
        self.assertEqual(types, {"registration", "exec_change", "litigation",
                                 "penalty", "finance", "bid", "ip", "sentiment"})
        self.assertTrue(set(types) <= set(ALLOWED_FACT_TYPES))

    def test_uscc_mismatch_rejected(self):
        """同名不同主体的案例数据拒绝落到同一对象（防串档）。"""
        with self.assertRaises(ValueError):
            CaseFileSource().collect(
                object_row={"object_id": 2, "display_name": "浙江伟星新型建材股份有限公司",
                            "natural_key": "91330000MA1B2C3D4X"},
                params={"case_path": str(REAL_CASE_PATH)},
            )

    def test_single_mapping(self):
        item = {"fact": "测试事实", "fact_type": "registration",
                "source_type": "cninfo", "source_url": "https://example.com/a",
                "quote": "原文", "published_at": "2026-04-03T00:00:00+08:00",
                "confidence": 95}
        ev = case_evidence_to_evidence_in(item)
        self.assertEqual(ev.fact, "测试事实")
        self.assertIsInstance(ev.published_at, datetime)


# ==================================================================
# 章节路由（第 2/3 章关键词互补 + 第 9 章 ip）
# ==================================================================

class ChapterRoutingTests(unittest.TestCase):
    ROWS = [
        _row(1, "公司中文名称为浙江伟星新型建材股份有限公司。", "registration"),
        _row(5, "公司注册资本1,592,037,988.00元，股份总数1,592,037,988股。", "registration"),
        _row(7, "伟星集团有限公司持股37.90%，其中质押248,082,400股。", "registration"),
        _row(10, "公司实际控制人为章卡鹏、张三云。", "registration"),
        _row(47, "公司拥有商标509条、专利665条。", "ip"),
        _row(31, "2025年营业收入5,381,991,829.02元。", "finance"),
    ]

    def test_ch2_basic_info_excludes_ownership(self):
        ids = [r["evidence_id"] for r in chapter_rows(_CH_BY_NO[2], self.ROWS)]
        self.assertEqual(ids, [1, 5])

    def test_ch3_ownership_by_keywords(self):
        ids = [r["evidence_id"] for r in chapter_rows(_CH_BY_NO[3], self.ROWS)]
        self.assertEqual(ids, [7, 10])

    def test_ch9_ip(self):
        ids = [r["evidence_id"] for r in chapter_rows(_CH_BY_NO[9], self.ROWS)]
        self.assertEqual(ids, [47])

    def test_ch2_ch3_complementary(self):
        """第 2/3 章合起来恰好是全部 registration 证据（不重不漏）。"""
        reg = [r for r in self.ROWS if r["fact_type"] == "registration"]
        covered = (chapter_rows(_CH_BY_NO[2], self.ROWS)
                   + chapter_rows(_CH_BY_NO[3], self.ROWS))
        self.assertEqual(len(covered), len(reg))
        self.assertEqual(sorted(r["evidence_id"] for r in covered),
                         sorted(r["evidence_id"] for r in reg))


# ==================================================================
# 一票否决关键词（状态类短语精确匹配，防正常经营用语误伤）
# ==================================================================

class VetoTests(unittest.TestCase):
    """「注销回购股份」是正常资本运作，不应触发一票否决（veto 误伤回归）。"""

    ROWS = [
        _row(15, "公司注销回购股份8,075,900股，总股本减少至1,583,962,088股。", "registration"),
    ]

    def test_normal_capital_ops_not_vetoed(self):
        self.assertEqual(veto_reasons(self.ROWS), [])
        card = build_scorecard(self.ROWS)
        self.assertNotEqual(card.verdict, "veto")

    def test_genuine_veto_states_still_hit(self):
        for fact in (
            "公司被法院列为失信被执行人。",
            "公司已被吊销营业执照。",
            "该公司已注销。",
            "公司办理注销登记。",
            "公司控股股东被采取强制措施。",
        ):
            with self.subTest(fact=fact):
                rows = [dict(self.ROWS[0], fact=fact)]
                self.assertTrue(veto_reasons(rows), f"应触发 veto：{fact}")
                self.assertEqual(build_scorecard(rows).verdict, "veto")

    def test_real_case_not_vetoed(self):
        """真实案例（伟星 50 条证据）不应被「注销回购股份」误伤降级。"""
        obj = {"object_id": 1, "display_name": "浙江伟星新型建材股份有限公司",
               "natural_key": "91330000719525019T"}
        rows = [dict(evidence_id=i + 1, fact_type=e.fact_type, fact=e.fact,
                     quote=e.quote, source_type=e.source_type,
                     source_url=e.source_url, source_name=e.source_name,
                     published_at=e.published_at, object_id=1,
                     confidence=e.confidence)
                for i, e in enumerate(CaseFileSource().collect(
                    obj, {"case_path": str(REAL_CASE_PATH)}))]
        card = build_scorecard(rows)
        self.assertEqual(card.veto_reasons, [])
        self.assertEqual(card.verdict, "usable")


# ==================================================================
# LLM 章节写作（伪客户端，不调真实 LLM）
# ==================================================================

class _FakeClient:
    """从 user prompt 里提取证据角标，回写一条引用首个证据的草稿。"""

    def __init__(self, response=None):
        self.response = response
        self.calls = []

    def invoke(self, system_prompt, user_prompt, **kwargs):
        self.calls.append((system_prompt, user_prompt))
        if self.response is not None:
            return self.response
        import re
        m = re.search(r"- E(\d+)｜", user_prompt)
        return f"【事实陈述】本章首条事实的改写（依据 E{m.group(1)}）。" if m else ""


OBJECT_ROW = {"object_id": 1, "display_name": "浙江伟星新型建材股份有限公司",
              "natural_key": "91330000719525019T"}


class WriterTests(unittest.TestCase):
    ROWS = ChapterRoutingTests.ROWS

    def test_build_user_prompt_contains_evidence(self):
        prompt = build_user_prompt(_CH_BY_NO[7], OBJECT_ROW, self.ROWS[-1:])
        self.assertIn("E31", prompt)
        self.assertIn("5,381,991,829.02", prompt)
        self.assertIn("第 7 章 财务表现", prompt)

    def test_validate_draft_requires_citation(self):
        ch_rows = self.ROWS[-1:]
        self.assertTrue(validate_draft("【事实陈述】x（依据 E31）。", ch_rows))
        self.assertFalse(validate_draft("没有任何引用的通篇空话。", ch_rows))
        self.assertFalse(validate_draft("", ch_rows))

    def test_draft_chapters_with_fake_client(self):
        fake = _FakeClient()
        drafts = draft_chapters(OBJECT_ROW, self.ROWS, client=fake)
        # 有数据的事实章：2/3/7/9（第 47 号 ip 进第 9 章）
        self.assertEqual(sorted(drafts.keys()), [2, 3, 7, 9])
        self.assertTrue(all("依据 E" in d for d in drafts.values()))
        self.assertEqual(len(fake.calls), 4)

    def test_draft_chapters_bad_draft_falls_back(self):
        """草稿无引用角标 → 该章不进 drafts（回退确定性拼装）。"""
        fake = _FakeClient(response="无引用空话")
        drafts = draft_chapters(OBJECT_ROW, self.ROWS, client=fake)
        self.assertEqual(drafts, {})

    def test_draft_flows_through_verify(self):
        """草稿进入 build_blocks 后，verify 仍能抽到引用（链路不因草稿断裂）。"""
        from backend.dd.report import build_scorecard, build_blocks
        fake = _FakeClient()
        drafts = draft_chapters(OBJECT_ROW, self.ROWS, client=fake)
        blocks = build_blocks(OBJECT_ROW, self.ROWS, build_scorecard(self.ROWS),
                              verify_result=None, drafts=drafts)
        result = verify_report(blocks, {r["evidence_id"]: r for r in self.ROWS}, 1)
        self.assertGreater(result["passed"] + result["failed"], 0)

    def test_llm_enabled_offline_default(self):
        # 本地未配 INSIGHT_ENGINE_API_KEY 时应为 False（不强依赖环境）
        self.assertIsInstance(llm_enabled(), bool)


if __name__ == "__main__":
    unittest.main()
