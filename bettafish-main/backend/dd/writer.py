"""LLM 章节写作（改造模块清单 §7 步骤④）。

把 core.evidence 的事实写成章节草稿，替换 P0 确定性拼装的「事实清单」空壳：
- 复用 InsightEngine 的 OpenAI 兼容客户端（InsightEngine/llms/base.LLMClient，
  INSIGHT_ENGINE_* 配置），不新造 LLM 封装；
- 强约束 prompt：只能引用给定证据、每个事实句带（依据 E{id}）角标、
  禁止引入证据之外的数字、事实与推断分层标注；
- 产出草稿交回 verify.py 后校验（引用存在性 + 数字回查），失败引用标待核实；
- LLM 不可用 / 调用失败 / 草稿无引用角标 → 该章回退确定性拼装（不阻塞报告）。
"""

from loguru import logger

from .report import chapter_rows
from .template import CHAPTERS

# 单章草稿的软上限（防 LLM 跑飞；超出部分由后校验数字回查兜底）
MAX_DRAFT_CHARS = 2000
# 引用原文片段喂给 LLM 时的截断长度（控制 token）
QUOTE_EXCERPT_LEN = 120

_SYSTEM_PROMPT = """你是投资尽调报告的章节撰写助手。严格遵守以下规则：
1. 只能使用「提供的证据」中的信息，禁止使用你自己的知识补充任何事实；
2. 每个事实陈述句的句末必须标注引用角标，格式：（依据 E{编号}）；
3. 禁止出现任何证据中没有的数字（金额、比例、日期、次数），改写数字视为违规；
4. 事实句前标注【事实陈述】；基于事实的推断前标注【分析意见】，且推断不得引入新数字；
5. 证据之间信息冲突时，如实并列表述并注明各自依据，不得自行裁断；
6. 用简体中文 Markdown 输出（可用列表，不用表格），语言克制、无形容词堆砌；
7. 直接输出章节正文，不要输出章节标题，不要任何开场白或解释。"""


def llm_enabled() -> bool:
    """LLM 章节写作是否可用（开关打开且配了 API Key）。"""
    try:
        from config import settings
        return bool(settings.DD_LLM_WRITING_ENABLED and settings.INSIGHT_ENGINE_API_KEY)
    except Exception:
        return False


def _build_client():
    from InsightEngine.llms.base import LLMClient

    from config import settings
    return LLMClient(
        api_key=settings.INSIGHT_ENGINE_API_KEY,
        model_name=settings.INSIGHT_ENGINE_MODEL_NAME,
        base_url=settings.INSIGHT_ENGINE_BASE_URL,
    )


def build_user_prompt(ch: dict, object_row: dict, ch_rows: list[dict]) -> str:
    """组装章节写作的用户提示（纯函数，可单测）。"""
    lines = [
        f"报告对象：{object_row['display_name']}",
        f"章节主题：第 {ch['no']} 章 {ch['title']}",
        "",
        "可用证据（编号、事实、原文片段、发布日期、来源）：",
    ]
    for r in ch_rows:
        pub = r.get("published_at")
        pub = pub.strftime("%Y-%m-%d") if hasattr(pub, "strftime") else (str(pub)[:10] if pub else "未知日期")
        quote = (r.get("quote") or "")[:QUOTE_EXCERPT_LEN] or "（无原文片段）"
        lines.append(
            f"- E{r['evidence_id']}｜{r['fact']}｜原文：{quote}｜{pub}｜"
            f"{r.get('source_name') or r.get('source_type')}"
        )
    lines += [
        "",
        f"请基于且仅基于上述证据撰写本章正文（不超过 {MAX_DRAFT_CHARS} 字），"
        "按系统规则标注事实/分析与引用角标。",
    ]
    return "\n".join(lines)


def validate_draft(draft: str, ch_rows: list[dict]) -> bool:
    """草稿最低门槛：至少含一个本章证据的引用角标（防无引用的通篇空话）。"""
    if not draft or not draft.strip():
        return False
    return any(f"E{r['evidence_id']}" in draft for r in ch_rows)


def draft_chapter(ch: dict, object_row: dict, ch_rows: list[dict],
                  client=None) -> str | None:
    """写一章草稿；失败或校验不过返回 None（调用方回退确定性拼装）。"""
    client = client or _build_client()
    draft = client.invoke(
        _SYSTEM_PROMPT,
        build_user_prompt(ch, object_row, ch_rows),
        temperature=0.2,
    )
    draft = (draft or "").strip()[:MAX_DRAFT_CHARS]
    if not validate_draft(draft, ch_rows):
        logger.warning(f"第 {ch['no']} 章草稿未通过引用校验，回退确定性拼装")
        return None
    return draft


def draft_chapters(object_row: dict, rows: list[dict],
                    client=None) -> dict[int, str]:
    """对所有「有数据」的事实章节生成草稿。

    单章失败只降级该章（回退确定性拼装），不影响其他章节。
    返回 {chapter_no: 草稿 markdown}；LLM 不可用时返回 {}。
    """
    if client is None:
        # 未显式注入客户端时才走环境门禁（注入 client 供测试/程序化调用）
        if not llm_enabled():
            logger.info("LLM 章节写作未启用（开关关闭或缺 INSIGHT_ENGINE_API_KEY），全部章节回退确定性拼装")
            return {}
        client = _build_client()

    drafts: dict[int, str] = {}
    for ch in CHAPTERS:
        if ch.get("source"):  # summary/verdict/appendix 章不走 LLM
            continue
        ch_rows = chapter_rows(ch, rows)
        if not ch_rows:
            continue  # 无数据章节保持【数据不足】，不调用 LLM
        try:
            draft = draft_chapter(ch, object_row, ch_rows, client=client)
            if draft:
                drafts[ch["no"]] = draft
        except Exception as e:
            logger.warning(f"第 {ch['no']} 章 LLM 写作失败，回退确定性拼装：{e}")
    return drafts
