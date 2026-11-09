"""天眼查开放平台适配器（免费额度，需 TIANYANCHA_API_TOKEN）。

接口（v4 开放平台，Authorization 头直接带 token）：
- GET {base}/services/open/company/baseinfo/normal?name=公司名 → 工商基本信息
  （注册资本/法定代表人/成立日期/企业状态/经营范围 → registration）

司法涉诉、招投标接口在 P1 按免费额度逐步接入，v0 先落工商基本信息。
未配置 token 时抛明确错误（不静默返回空，防主体基本信息章悄悄空着）。
"""

from datetime import datetime

from .base import EvidenceIn, SourceAdapter, register_source


@register_source("tianyancha")
class TianyanchaCompany(SourceAdapter):
    source_type = "tianyancha"

    def collect(self, object_row: dict, params: dict) -> list[EvidenceIn]:
        import requests

        from config import settings

        token = settings.TIANYANCHA_API_TOKEN
        if not token:
            raise RuntimeError(
                "天眼查采集需要 TIANYANCHA_API_TOKEN（.env 配置，"
                "申请地址 https://open.tianyancha.com/，有免费额度）"
            )

        name = params.get("name") or object_row["display_name"]
        resp = requests.get(
            f"{settings.TIANYANCHA_BASE_URL}/services/open/company/baseinfo/normal",
            params={"name": name},
            headers={"Authorization": token},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("error_code") != 0 or not payload.get("result"):
            # 天眼查错误码：常见 300006=额度用尽
            raise RuntimeError(
                f"天眼查接口返回异常：error_code={payload.get('error_code')} "
                f"reason={payload.get('reason')}"
            )
        r = payload["result"]
        company_name = r.get("name") or name

        # 公司名必须与对象一致（同名不同主体防串档）
        if company_name != object_row["display_name"]:
            raise ValueError(
                f"天眼查返回主体「{company_name}」与对象"
                f"「{object_row['display_name']}」名称不一致，拒绝入库"
            )

        items: list[EvidenceIn] = []
        base = dict(
            fact_type="registration",
            source_type=self.source_type,
            source_url=f"https://www.tianyancha.com/company/{r.get('id', '')}",
            source_name="天眼查工商信息",
            confidence=85,
            confidence_reason="商业数据 API，关键事实建议与官方源交叉核验",
        )

        field_specs = [
            ("regStatus", "企业状态为{v}"),
            ("legalPersonName", "法定代表人为{v}"),
            ("regCapital", "注册资本为{v}"),
            ("estiblishTime", None),  # 成立日期（ms 时间戳，单独处理）
            ("businessScope", "经营范围为{v}"),
        ]
        for key, tpl in field_specs:
            v = r.get(key)
            if not v:
                continue
            if key == "estiblishTime":
                try:
                    dt = datetime.fromtimestamp(int(v) / 1000)
                except (ValueError, OSError, TypeError):
                    continue
                items.append(EvidenceIn(
                    fact=f"{company_name}成立于 {dt.strftime('%Y-%m-%d')}",
                    published_at=dt, quote=f"成立日期 {dt.strftime('%Y-%m-%d')}", **base,
                ))
            else:
                text = str(v)
                items.append(EvidenceIn(
                    fact=f"{company_name}{tpl.format(v=text)}",
                    quote=text, **base,
                ))
        return items


ADAPTER = TianyanchaCompany()
