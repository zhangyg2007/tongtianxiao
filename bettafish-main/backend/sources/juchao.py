"""巨潮资讯网公告检索适配器（免费，无需 token）。

接口：POST {JUCHAO_BASE_URL}/new/hisAnnouncement/query
- 按 stock（如 "002372,gssz0002372"）或 searchkey（公司名）检索公告；
- 返回 announcementTitle / announcementTime(ms) / adjunctUrl（PDF 相对路径）。

映射：一条公告 → 一条 EvidenceIn（fact=公告标题，quote=公告标题）。
公告 PDF 正文解析（quote 取正文片段）在 P1 补，v0 用标题自证。
fact_type 由 classify_announcement 按标题关键词路由（确定性规则，可单测）。
"""

import re
from datetime import datetime, timezone

from loguru import logger

from .base import EvidenceIn, SourceAdapter, register_source

# 标题关键词 → fact_type（顺序即优先级：先命中先归类）
_TITLE_RULES = [
    (("诉讼", "仲裁", "判决"), "litigation"),
    (("处罚", "监管", "警示", "整改", "问询函", "关注函"), "penalty"),
    (("年度报告", "季度报告", "半年报告", "业绩预告", "业绩快报", "利润分配",
      "财务决算", "审计报告"), "finance"),
    (("中标", "合同", "重大项目"), "bid"),
    (("增持", "减持", "质押", "解除质押", "股权激励", "回购", "收购",
      "实际控制人", "股东大会", "董事会", "监事会", "章程"), "registration"),
    (("专利", "商标", "知识产权"), "ip"),
]

_EM_RE = re.compile(r"</?em>")


def classify_announcement(title: str) -> str:
    """公告标题 → fact_type（确定性关键词路由，默认 registration）。"""
    for keywords, fact_type in _TITLE_RULES:
        if any(k in title for k in keywords):
            return fact_type
    return "registration"


def _guess_plate(stock_code: str) -> tuple[str, str]:
    """按股票代码推断巨潮 plate 参数（深交所 002/300/000，上交所 60x/68x）。"""
    if stock_code.startswith(("6", "9")):
        return "sse", f"{stock_code},gssh0{stock_code}"
    return "szse", f"{stock_code},gssz0{stock_code}"


@register_source("juchao")
class JuchaoAnnouncements(SourceAdapter):
    source_type = "cninfo"

    def collect(self, object_row: dict, params: dict) -> list[EvidenceIn]:
        import requests

        from config import settings

        stock_code = (params.get("stock_code") or "").strip()
        if not stock_code:
            # 允许从对象 display_meta 里带 stock_code（实体注册时写入）
            meta = object_row.get("display_meta") or ""
            m = re.search(r"\b(\d{6})\b", meta)
            if not m:
                raise ValueError("juchao 采集需要 params.stock_code（6 位代码）")
            stock_code = m.group(1)

        max_items = int(params.get("max_items", 30))
        se_date = params.get("se_date", "2023-01-01~2026-12-31")
        column, stock = _guess_plate(stock_code)

        resp = requests.post(
            f"{settings.JUCHAO_BASE_URL}/new/hisAnnouncement/query",
            data={
                "pageNum": 1,
                "pageSize": max_items,
                "column": column,
                "tabName": "fulltext",
                "plate": "",
                "stock": stock,
                "searchkey": "",
                "secid": "",
                "category": params.get("category", ""),
                "trade": "",
                "seDate": se_date,
                "sortName": "",
                "sortType": "",
                "isHLtitle": "true",
            },
            headers={"User-Agent": "Mozilla/5.0 (bettafish-evidence-collector)"},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        announcements = (payload or {}).get("announcements") or []
        if not announcements:
            logger.info(f"juchao: {stock_code} 无公告返回（announcements 为空）")
            return []

        items: list[EvidenceIn] = []
        for ann in announcements[:max_items]:
            title = _EM_RE.sub("", ann.get("announcementTitle") or "").strip()
            adjunct = ann.get("adjunctUrl") or ""
            ts = ann.get("announcementTime")
            if not title or not adjunct:
                continue
            items.append(EvidenceIn(
                fact=f"{object_row['display_name']}发布《{title}》",
                fact_type=classify_announcement(title),
                source_type=self.source_type,
                source_url=f"https://static.cninfo.com.cn/{adjunct}",
                quote=title,
                source_name="巨潮资讯网公告",
                published_at=(
                    datetime.fromtimestamp(ts / 1000, tz=timezone.utc) if ts else None
                ),
                confidence=90,
                confidence_reason="交易所指定信息披露平台直采",
            ))
        return items


ADAPTER = JuchaoAnnouncements()
