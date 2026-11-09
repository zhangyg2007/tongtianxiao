"""数据源适配层基座：EvidenceIn 统一入参形状 + SourceAdapter 抽象。

新增数据源三步：
1. 继承 SourceAdapter，实现 collect(object_row, params) -> list[EvidenceIn]；
2. 模块底部实例化并用 @register_source("name") 注册（参考 juchao.py）；
3. 在 __init__.py 的 _SOURCE_MODULES / SOURCE_LABELS 里登记。

约束（多 Agent Prompt 工程方案 §证据采集）：
- fact 是归一化事实断言（可进评分卡），quote 是原文片段（LLM 不可改写）；
- fact_type 必须在 ALLOWED_FACT_TYPES 内（章节路由与评分卡依赖它）；
- 采不到就返回空列表，**禁止编造填充**（缺失维度由报告层如实标注）。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

# core.evidence.fact_type 的合法集合（与 backend/dd/template.py 章节映射对齐）
ALLOWED_FACT_TYPES = (
    "registration",  # 工商与股权（基础信息 + 股权事实，章节路由用关键词细分）
    "exec_change",   # 高管与任职变动
    "litigation",    # 涉诉
    "penalty",       # 行政处罚与监管
    "finance",       # 财务表现
    "bid",           # 招投标/中标
    "ip",            # 知识产权
    "sentiment",     # 舆情
)


@dataclass
class EvidenceIn:
    """适配器输出、core.evidence 输入的统一形状。"""

    fact: str
    fact_type: str
    source_type: str
    source_url: str
    quote: str | None = None
    source_name: str | None = None
    value_json: dict | None = None
    published_at: datetime | None = None
    confidence: int = 85
    confidence_reason: str | None = None

    def validate(self) -> None:
        """落库前校验：必填字段与 fact_type 合法性（fail fast，防脏数据进 core.evidence）。"""
        if not self.fact or not self.fact.strip():
            raise ValueError("EvidenceIn.fact 不能为空")
        if not self.source_url or not self.source_url.strip():
            raise ValueError(f"证据「{self.fact[:30]}…」缺少 source_url")
        if self.fact_type not in ALLOWED_FACT_TYPES:
            raise ValueError(
                f"证据「{self.fact[:30]}…」fact_type={self.fact_type} 不在 "
                f"{ALLOWED_FACT_TYPES}"
            )
        if not 0 <= self.confidence <= 100:
            raise ValueError(f"confidence={self.confidence} 越界（0-100）")


class SourceAdapter(ABC):
    """数据源适配器抽象。"""

    #: 源名（注册键，与 __init__._SOURCE_MODULES 一致）
    name: str = ""
    #: core.evidence.source_type（cninfo / tianyancha / akshare / …）
    source_type: str = ""

    @abstractmethod
    def collect(self, object_row: dict, params: dict) -> list[EvidenceIn]:
        """采集一个对象的证据。

        参数：
        - object_row: core.object 行（display_name / natural_key=USCC / display_meta）
        - params: 任务 input 里的源参数（stock_code / max_items / case_path …）

        返回 EvidenceIn 列表（可为空 = 该源无数据）；网络/接口错误抛异常
        （由 collect_evidence 任务捕获并落 task_step.failed，不静默吞掉）。
        """


# 适配器注册表（get_source 触发模块导入后从各模块的 @register_source 填充）
SOURCES: dict[str, SourceAdapter] = {}


def register_source(name: str):
    def deco(adapter: SourceAdapter):
        adapter.name = name
        SOURCES[name] = adapter
        return adapter
    return deco
