"""数据源适配层（改造模块清单 §7 步骤②）。

所有采集器（巨潮 / AkShare / 天眼查 / 离线案例文件）输出统一的
EvidenceIn，由 collect_evidence 任务落 core.evidence——报告流水线
（backend/dd/pipeline.py）只认 core.evidence，不感知数据源差异。

适配器按需懒加载（akshare 等重依赖只在真正使用时 import）。
"""

import importlib

from .base import EvidenceIn, SourceAdapter, register_source  # noqa: F401

# 源名 → 模块相对路径（get_source 时才 import，避免拉起重依赖）
_SOURCE_MODULES = {
    "juchao": ".juchao",
    "akshare": ".akshare_src",
    "tianyancha": ".tianyancha",
    "case_file": ".case_file",
}

# 源名 → 中文说明（collect_evidence 任务阶段展示用）
SOURCE_LABELS = {
    "juchao": "巨潮资讯网公告",
    "akshare": "AkShare 财务数据",
    "tianyancha": "天眼查工商信息",
    "case_file": "离线案例文件",
}


def get_source(name: str) -> SourceAdapter:
    """按名取适配器实例（触发模块导入与注册）。"""
    if name not in _SOURCE_MODULES:
        raise KeyError(
            f"未知数据源「{name}」，可选：{sorted(_SOURCE_MODULES)}"
        )
    module = importlib.import_module(_SOURCE_MODULES[name], __name__)
    return module.ADAPTER


def list_sources() -> list[str]:
    return sorted(_SOURCE_MODULES)
