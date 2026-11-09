"""12 章报告组装（纯函数，无 IO，可独立单测）。

输入：对象行 + 证据行（core.evidence 形状的 dict）+ 评分卡 + 后校验结果
输出：blocks 列表（backend.worker.objects.write_artifact_blocks 的入参形状）
"""

from .scorecard import STATUS_LABELS, DimensionAssessment, Scorecard, compute_scorecard
from .template import (
    CHAPTERS,
    COMPLIANCE_NOTE,
    RISK_DIMENSION_SCORE,
    SCORECARD_DIMENSIONS,
    VETO_KEYWORDS,
)


def _matches_spec(row: dict, fact_types: list[str] | None,
                  fact_keywords: list[str] | None = None,
                  exclude_keywords: list[str] | None = None) -> bool:
    """按 fact_type +（可选）事实文本关键词过滤（第 2/3 章互补路由的基础）。"""
    if fact_types and row["fact_type"] not in fact_types:
        return False
    fact = row.get("fact") or ""
    if fact_keywords and not any(k in fact for k in fact_keywords):
        return False
    if exclude_keywords and any(k in fact for k in exclude_keywords):
        return False
    return True


def chapter_rows(ch: dict, rows: list[dict]) -> list[dict]:
    """一章的取数：fact_type 路由 + 关键词细分（第 3 章股权关键词命中项）。"""
    return [
        r for r in rows
        if _matches_spec(r, ch.get("fact_types"),
                         ch.get("fact_keywords"), ch.get("exclude_keywords"))
    ]


def assess_dimensions(rows: list[dict]) -> list[DimensionAssessment]:
    """按评分卡配置对证据做三态评估（确定性规则，无 LLM）。"""
    assessments = []
    for dim in SCORECARD_DIMENSIONS:
        data_rows = [
            r for r in rows
            if _matches_spec(r, dim["fact_types"], dim.get("fact_keywords"))
        ]
        risky = [
            r for r in rows
            if _matches_spec(r, dim["risk_types"])
        ]
        if not data_rows:
            assessments.append(DimensionAssessment(
                dim["key"], dim["name"], dim["weight"], "missing", 0))
            continue
        if risky:
            assessments.append(DimensionAssessment(
                dim["key"], dim["name"], dim["weight"], "risk",
                RISK_DIMENSION_SCORE, findings=[r["fact"] for r in risky]))
        else:
            assessments.append(DimensionAssessment(
                dim["key"], dim["name"], dim["weight"], "ok", 100))
    return assessments


def veto_reasons(rows: list[dict]) -> list[str]:
    """一票否决关键词扫描（前端设计 §5.1.3）。"""
    reasons = []
    for r in rows:
        for kw in VETO_KEYWORDS:
            if kw in (r.get("fact") or ""):
                reasons.append(
                    f"命中一票否决项「{kw}」：{r['fact']}（依据 E{r['evidence_id']}）"
                )
    return reasons


def build_scorecard(rows: list[dict]) -> Scorecard:
    return compute_scorecard(assess_dimensions(rows), veto_reasons(rows))


def _fmt_score(score: float | None) -> str:
    return "—" if score is None else f"{score:.0f}"


def _fmt_pub(value) -> str:
    """发布日期统一显示（兼容 datetime / ISO 字符串 / 空）。"""
    if not value:
        return "—"
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value)[:10] or "—"


def build_blocks(
    object_row: dict,
    rows: list[dict],
    card: Scorecard,
    verify_result: dict | None = None,
    drafts: dict[int, str] | None = None,
) -> list[dict]:
    """组装 12 章 markdown 块（heading + paragraph 交替）。

    drafts: {chapter_no: 草稿 markdown}——LLM 章节写作的产物。
    有草稿的章节直接使用草稿（后续经 verify.py 后校验），
    无草稿或有数据但草稿缺失的章节回退确定性事实清单。
    """
    name = object_row["display_name"]
    blocks: list[dict] = []

    def add(chapter_no: int, block_type: str, content_md: str,
            heading: str | None = None):
        blocks.append({
            "seq": len(blocks) + 1,
            "chapter_no": chapter_no,
            "block_type": block_type,
            "heading": heading,
            "content_md": content_md,
        })

    for ch in CHAPTERS:
        no, title = ch["no"], ch["title"]
        add(no, "heading", f"## {no}. {title}", title)
        source = ch.get("source")

        if source == "summary":
            lines = [
                f"**对象**：{name}",
                f"**评分卡得分**：{_fmt_score(card.score)} / 100"
                f"（数据覆盖率 {card.coverage:.0%}）",
                f"**判定**：{card.verdict_label}",
                "",
                "| 维度 | 权重 | 状态 | 得分 |",
                "|---|---|---|---|",
            ]
            for d in card.dimensions:
                status = STATUS_LABELS.get(d.status, d.status)
                score = "—" if d.status == "missing" else str(d.score)
                lines.append(f"| {d.name} | {d.weight} | {status} | {score} |")
            risks = card.top_risks()
            if risks:
                lines += ["", "**核心风险**："]
                for i, d in enumerate(risks, 1):
                    for f in d.findings[:2]:
                        lines.append(f"{i}. {d.name}（权重 {d.weight}）：{f}")
            else:
                lines += ["", "**核心风险**：暂未发现触发风险规则的维度。"]
            add(no, "paragraph", "\n".join(lines))

        elif source == "verdict":
            lines = [f"**判定**：{card.verdict_label}"]
            if card.verdict == "insufficient_data":
                lines.append(
                    "\n数据覆盖率不足，本报告不输出投资结论，"
                    "仅保留证据不足清单（见各章【数据不足】标注与第 12 章附录）。"
                )
            if card.veto_reasons:
                lines.append("\n**一票否决**：")
                lines += [f"- {r}" for r in card.veto_reasons]
            lines += ["", "---", COMPLIANCE_NOTE]
            add(no, "paragraph", "\n".join(lines))

        elif source == "appendix":
            lines = ["证据编号 → 来源 / 发布日期 / 原文摘录：", ""]
            for r in sorted(rows, key=lambda x: x["evidence_id"]):
                pub = _fmt_pub(r.get("published_at"))
                quote = r.get("quote") or "（未保存原文片段）"
                lines += [
                    f"- **E{r['evidence_id']}** {r['fact']}",
                    f"  - 来源：{r.get('source_name') or r['source_type']}"
                    f" · {r['source_url']}",
                    f"  - 发布日期：{pub} · 置信度：{r['confidence']}",
                    f"  - 原文摘录：{quote}",
                ]
            if verify_result:
                lines += ["", "**后校验结果**："]
                lines.append(
                    f"- 引用共 "
                    f"{verify_result['passed'] + verify_result['failed']} 处，"
                    f"通过 {verify_result['passed']}，"
                    f"待核实 {verify_result['failed']}"
                )
                for issue in verify_result["issues"]:
                    lines.append(
                        f"- ⚠️ {issue['detail']}（第 {issue['block_seq']} 块）"
                    )
            add(no, "paragraph", "\n".join(lines))

        else:
            ch_rows = chapter_rows(ch, rows)
            if not ch_rows:
                add(no, "paragraph", "【数据不足】未获取到该章的公开数据。")
                continue
            draft = (drafts or {}).get(no)
            if draft:
                # LLM 草稿：引用角标与数字随后经 verify.py 后校验
                add(no, "paragraph", draft)
                continue
            lines = [
                f"- 【事实陈述】{r['fact']}（依据 E{r['evidence_id']}）"
                for r in ch_rows
            ]
            add(no, "paragraph", "\n".join(lines))

    return blocks
