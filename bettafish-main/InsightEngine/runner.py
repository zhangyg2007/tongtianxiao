"""InsightEngine 纯执行体（去 Streamlit，设计文档 §3.2）。

run_research 是无 UI 依赖的深度研究执行函数：
- 进度通过 on_progress 回调上报（结构化事件 dict，供 Streamlit 驱动、
  RQ worker 处理器、后续 /api/v1 SSE 统一消费）；
- 取消通过 should_stop 回调在段落边界检查，命中时抛 ResearchCanceled；
- 引擎包本身零依赖 Streamlit/Flask，只有 SingleEngineApp 驱动文件与
  backend.worker 处理器引用本模块。

事件 schema（p0-8 SSE 直接复用）：
    {"type": "stage",                 "stage": str, "progress": int, "message": str}
    {"type": "structure_done",        "progress": int, "paragraphs": [str, ...]}
    {"type": "paragraph_start",       "index": int, "total": int, "title": str, "progress": int, "message": str}
    {"type": "paragraph_search_done", "index": int, "total": int, "progress": int}
    {"type": "paragraph_done",        "index": int, "total": int, "title": str, "progress": int}
    {"type": "complete",              "progress": 100, "result": dict}
"""

from datetime import datetime
from typing import Any, Callable, Dict, Optional

from loguru import logger

from .agent import DeepSearchAgent
from .utils.config import Settings

ProgressCallback = Callable[[Dict[str, Any]], None]
StopCheck = Callable[[], bool]

# 与 ReportEngine 输入扫描目录（check_input_files）保持一致，
# 报告落这里才能被下游报告引擎发现
DEFAULT_OUTPUT_DIR = "insight_engine_streamlit_reports"


class ResearchCanceled(Exception):
    """用户取消研究（should_stop 回调命中时抛出）。"""


def _noop_progress(event: Dict[str, Any]) -> None:
    pass


def _default_config() -> Settings:
    """默认配置：从环境变量/.env 构建，输出目录固定到 ReportEngine 扫描目录。"""
    return Settings(OUTPUT_DIR=DEFAULT_OUTPUT_DIR)


def run_research(
    query: str,
    config: Optional[Settings] = None,
    on_progress: Optional[ProgressCallback] = None,
    should_stop: Optional[StopCheck] = None,
    save_report: bool = True,
) -> Dict[str, Any]:
    """执行一次完整的深度研究（无 UI 依赖）。

    Args:
        query: 研究查询
        config: InsightEngine Settings；缺省时从环境变量构建
        on_progress: 进度回调，入参为事件 dict（见模块 docstring）
        should_stop: 取消检查回调，段落边界调用；返回 True 时抛 ResearchCanceled
        save_report: 是否保存报告/状态文件

    Returns:
        结果 dict：{query, report_title, report, report_path, state_path,
                   paragraphs: [...], search_count, search_history: [...],
                   started_at, finished_at}
    """
    if not query or not query.strip():
        raise ValueError("研究查询不能为空")

    started_at = datetime.now().isoformat()
    emit = on_progress or _noop_progress
    config = config or _default_config()

    logger.info(f"runner 开始深度研究: {query}")

    emit({"type": "stage", "stage": "init", "progress": 5, "message": "正在初始化Agent..."})
    agent = DeepSearchAgent(config)

    emit({"type": "stage", "stage": "structure", "progress": 10, "message": "正在生成报告结构..."})
    agent._generate_report_structure(query)
    emit({"type": "stage", "stage": "structure", "progress": 20, "message": "报告结构已生成"})
    emit({
        "type": "structure_done",
        "progress": 20,
        "paragraphs": [p.title for p in agent.state.paragraphs],
    })

    total = len(agent.state.paragraphs)
    for i in range(total):
        if should_stop is not None and should_stop():
            logger.warning(f"研究已取消（段落 {i + 1}/{total} 边界）")
            raise ResearchCanceled(f"研究在段落 {i + 1}/{total} 前被取消")

        paragraph = agent.state.paragraphs[i]
        emit({
            "type": "paragraph_start",
            "index": i,
            "total": total,
            "title": paragraph.title,
            "progress": int(20 + i / total * 60),
            "message": f"正在处理段落 {i + 1}/{total}: {paragraph.title}",
        })

        agent._initial_search_and_summary(i)
        emit({
            "type": "paragraph_search_done",
            "index": i,
            "total": total,
            "progress": int(20 + (i + 0.5) / total * 60),
        })

        agent._reflection_loop(i)
        agent.state.paragraphs[i].research.mark_completed()
        emit({
            "type": "paragraph_done",
            "index": i,
            "total": total,
            "title": paragraph.title,
            "progress": int(20 + (i + 1) / total * 60),
        })

    emit({"type": "stage", "stage": "final_report", "progress": 90, "message": "正在生成最终报告..."})
    final_report = agent._generate_final_report()

    report_path: Optional[str] = None
    state_path: Optional[str] = None
    if save_report:
        emit({"type": "stage", "stage": "save", "progress": 95, "message": "正在保存报告..."})
        report_path, state_path = agent._save_report(final_report)

    result = _build_result(agent, query, final_report, report_path, state_path, started_at)
    emit({"type": "complete", "progress": 100, "result": result})
    logger.info(f"runner 深度研究完成: {query}")
    return result


def _build_result(
    agent: DeepSearchAgent,
    query: str,
    final_report: str,
    report_path: Optional[str],
    state_path: Optional[str],
    started_at: str,
) -> Dict[str, Any]:
    """把 agent.state 汇总为可序列化的结果 dict（供前端/任务结果消费）。"""
    paragraphs = []
    searches = []
    for i, p in enumerate(agent.state.paragraphs):
        paragraphs.append({
            "index": i,
            "title": p.title,
            "content": p.content,
            "latest_summary": p.research.latest_summary,
            "search_count": p.research.get_search_count(),
            "reflection_iteration": p.research.reflection_iteration,
            "is_completed": p.research.is_completed,
        })
        searches.extend(p.research.search_history)

    return {
        "query": query,
        "report_title": agent.state.report_title,
        "report": final_report,
        "report_path": report_path,
        "state_path": state_path,
        "paragraphs": paragraphs,
        "search_count": len(searches),
        "search_history": [s.to_dict() for s in searches],
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(),
    }
