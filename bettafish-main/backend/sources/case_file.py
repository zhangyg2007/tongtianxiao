"""离线案例文件适配器（回归 / 演示用，无网络依赖）。

加载 .trae/documents/cases/ 下的案例 JSON（如 real_002372_weixing.json），
把其中的 evidence 数组映射为 EvidenceIn 直接入库，用于：
- 服务器不可达 / 数据源未配 token 时端到端跑通背调链路；
- cases 回归：50 条真实证据 → core.evidence → 12 章报告 → 后校验。

防串档：案例 object.natural_key.uscc 必须与目标对象的 natural_key 一致
（同名不同主体拒绝入库，backend/worker/entities.assert_same_entity）。
"""

import json
from datetime import datetime
from pathlib import Path

from loguru import logger

from ..worker.entities import assert_same_entity
from .base import EvidenceIn, SourceAdapter, register_source

# 案例证据 → EvidenceIn 的字段直通映射
_FIELD_MAP = (
    "fact", "fact_type", "source_type", "source_url", "quote",
    "source_name", "value_json", "confidence", "confidence_reason",
)


def case_evidence_to_evidence_in(item: dict) -> EvidenceIn:
    """单条案例证据 → EvidenceIn（published_at ISO 字符串转 datetime）。"""
    kwargs = {k: item[k] for k in _FIELD_MAP if item.get(k) is not None}
    pub = item.get("published_at")
    if isinstance(pub, str):
        kwargs["published_at"] = datetime.fromisoformat(pub)
    elif isinstance(pub, datetime):
        kwargs["published_at"] = pub
    ev = EvidenceIn(**kwargs)
    ev.validate()
    return ev


def load_case(path: str | Path) -> dict:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"案例文件不存在：{path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@register_source("case_file")
class CaseFileSource(SourceAdapter):
    source_type = "case_file"

    def collect(self, object_row: dict, params: dict) -> list[EvidenceIn]:
        case = load_case(params["case_path"])

        # 实体对齐校验：案例对象的 USCC 必须与目标对象一致（防同名串档）
        case_uscc = ((case.get("object") or {}).get("natural_key") or {})
        if isinstance(case_uscc, dict):
            case_uscc = case_uscc.get("uscc")
        assert_same_entity(object_row, case_uscc, label=f"案例 {case.get('case_id')}")

        evidence = case.get("evidence") or []
        logger.info(
            f"case_file: 案例 {case.get('case_id')} 载入 {len(evidence)} 条证据"
        )
        return [case_evidence_to_evidence_in(e) for e in evidence]


ADAPTER = CaseFileSource()
