"""评分卡三态判定（纯函数，无 IO，可独立单测）。

三态（前端设计 §5.1.3）：
- ok      🟢 无明显风险：有数据且未触发风险规则 → 该维度满分
- risk    🔴 确有风险：有数据且触发风险规则   → 按规则扣分（P0 占位 RISK_DIMENSION_SCORE）
- missing ⚪ 数据缺失：无数据                  → 不计分，且不按 0 分算

覆盖率与得分：
    覆盖率 = Σ(有效维度权重) / Σ(全部维度权重)
    得分   = Σ(有效维度得分 × 权重) / Σ(有效维度权重)

一票否决：命中 VETO_KEYWORDS 时无论得分如何，整体判定降级。
"""

from dataclasses import dataclass, field

from .template import COVERAGE_MINIMUM, COVERAGE_USABLE

STATUS_LABELS = {
    "ok": "🟢 无明显风险",
    "risk": "🔴 确有风险",
    "missing": "⚪ 数据缺失（未获取到公开数据，不计分）",
}


@dataclass
class DimensionAssessment:
    key: str
    name: str
    weight: int
    status: str  # ok / risk / missing
    score: int  # 0-100；missing 时忽略
    findings: list[str] = field(default_factory=list)  # risk 时的具体事实


@dataclass
class Scorecard:
    dimensions: list[DimensionAssessment]
    coverage: float  # 0-1
    score: float | None  # None = 无任何有效维度
    verdict: str  # usable / reference_only / insufficient_data / veto
    verdict_label: str
    veto_reasons: list[str] = field(default_factory=list)

    def top_risks(self, limit: int = 3) -> list[DimensionAssessment]:
        """按权重倒序取「确有风险」的维度（摘要章核心风险用）。"""
        risks = [d for d in self.dimensions if d.status == "risk"]
        risks.sort(key=lambda d: d.weight, reverse=True)
        return risks[:limit]


def compute_scorecard(
    assessments: list[DimensionAssessment],
    veto_reasons: list[str] | None = None,
) -> Scorecard:
    """三态判定 + 覆盖率 + 结论分级（纯函数）。"""
    veto_reasons = list(veto_reasons or [])
    total_weight = sum(a.weight for a in assessments)
    valid = [a for a in assessments if a.status != "missing"]

    if total_weight == 0:
        return Scorecard(assessments, 0.0, None,
                         "insufficient_data", "数据不足，拒绝出结论", veto_reasons)

    coverage = sum(a.weight for a in valid) / total_weight

    if not valid:
        score = None
    else:
        valid_weight = sum(a.weight for a in valid)
        score = sum(
            (a.score if a.status == "risk" else 100) * a.weight for a in valid
        ) / valid_weight

    if veto_reasons:
        verdict, label = "veto", "触发一票否决项，建议否决或深度核查"
    elif coverage < COVERAGE_MINIMUM:
        verdict, label = "insufficient_data", (
            f"数据覆盖率 {coverage:.0%} 低于 {COVERAGE_MINIMUM:.0%}，"
            "强制拒绝出结论，仅输出证据不足清单"
        )
    elif coverage < COVERAGE_USABLE:
        verdict, label = "reference_only", (
            f"数据覆盖率 {coverage:.0%}，结论仅供参考"
        )
    else:
        verdict, label = "usable", f"数据覆盖率 {coverage:.0%}，结论可用"

    return Scorecard(assessments, coverage, score, verdict, label, veto_reasons)
