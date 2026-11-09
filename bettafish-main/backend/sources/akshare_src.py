"""AkShare 财务数据适配器（免费，MIT，无 token）。

接口：akshare.stock_financial_abstract(symbol="002372")
- 返回 DataFrame：每行一个指标（营业收入/净利润/ROE…），列为报告期；
- 只取最近 N 期（默认 3 期）关键指标，一条指标期 → 一条 finance EvidenceIn。

依赖：akshare 未安装时给出明确安装指引（不静默降级，防财务章悄悄空着）。
"""

from datetime import datetime

from loguru import logger

from .base import EvidenceIn, SourceAdapter, register_source

# 关键财务指标（指标名 → 报告用名/单位）
_KEY_INDICATORS = {
    "营业总收入": ("营业总收入", "元"),
    "营业收入": ("营业收入", "元"),
    "归母净利润": ("归属于母公司股东的净利润", "元"),
    "净利润": ("净利润", "元"),
    "扣非净利润": ("扣除非经常性损益后的净利润", "元"),
    "加权ROE": ("加权平均净资产收益率", "%"),
    "资产负债率": ("资产负债率", "%"),
    "经营现金流量净额": ("经营活动产生的现金流量净额", "元"),
}


@register_source("akshare")
class AkShareFinancials(SourceAdapter):
    source_type = "akshare"

    def collect(self, object_row: dict, params: dict) -> list[EvidenceIn]:
        try:
            import akshare as ak
        except ImportError as e:
            raise RuntimeError(
                "akshare 未安装：pip install akshare（免费 MIT，无 token）"
            ) from e

        stock_code = (params.get("stock_code") or "").strip()
        if not stock_code:
            raise ValueError("akshare 采集需要 params.stock_code（6 位代码）")
        periods = int(params.get("periods", 3))

        df = ak.stock_financial_abstract(symbol=stock_code)
        if df is None or df.empty:
            logger.info(f"akshare: {stock_code} 无财务摘要数据")
            return []

        # 列结构：第一列“指标”，其余列按新→旧排列报告期（如 20250930）
        period_cols = [c for c in df.columns if c != "指标"][:periods]
        by_indicator = {
            str(row["指标"]).strip(): row for _, row in df.iterrows()
        }

        items: list[EvidenceIn] = []
        for key, (label, unit) in _KEY_INDICATORS.items():
            row = by_indicator.get(key)
            if row is None:
                continue
            for col in period_cols:
                value = row.get(col)
                if value in (None, "", "--"):
                    continue
                # 报告期列名形如 20250930 → 2025年三季报
                period = str(col)
                period_label = (
                    f"{period[:4]}年{ {'0331': '一季报', '0630': '半年报', '0930': '三季报', '1231': '年报'}.get(period[4:], period[4:] + '期') }"
                )
                pub = datetime.strptime(period[:4] + "-" + period[4:6] + "-" + period[6:], "%Y-%m-%d") if len(period) == 8 else None
                items.append(EvidenceIn(
                    fact=f"{object_row['display_name']}{period_label}{label}为 {value}{unit}",
                    fact_type="finance",
                    source_type=self.source_type,
                    source_url=f"https://akshare.akfamily.xyz/data/stock/stock.html#{stock_code}",
                    quote=f"{key} {col} {value}",
                    source_name="AkShare 财务摘要（东方财富数据）",
                    value_json={"indicator": key, "period": period, "value": str(value), "unit": unit},
                    published_at=pub,
                    confidence=80,
                    confidence_reason="开源财经数据库聚合，建议与年报原文交叉核验",
                ))
        return items


ADAPTER = AkShareFinancials()
