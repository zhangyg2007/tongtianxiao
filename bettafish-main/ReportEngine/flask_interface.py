"""
Report Engine Flask接口。

该模块为前端/CLI提供统一HTTP/SSE入口，负责：
1. 初始化 ReportAgent；
2. 任务经 RQ 队列异步执行（执行体见 ReportEngine/tasks.py），
   状态与事件持久化在 Redis（task_store），多任务并发不再受限；
3. 提供模板列表、输入文件检查等周边能力。

去单例改造（设计文档 §3.1）：原 `current_task` 全局单例 + 内存事件队列
已删除，任务状态统一走 Redis，SSE 改为 XREAD BLOCK 消费事件流。
"""

import os
import json
import time
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify, Response, send_file, stream_with_context
from typing import Dict, Any, List, Optional
from loguru import logger
from .agent import ReportAgent, create_agent
from .nodes import ChapterJsonParseError
from .utils.config import settings
from . import task_store


# 创建Blueprint
report_bp = Blueprint('report_engine', __name__)

# 全局变量
report_agent = None


def _get_report_agent() -> ReportAgent:
    """惰性获取/创建 ReportAgent（Flask 启动时初始化，worker 进程内兜底）。"""
    global report_agent
    if report_agent is None:
        report_agent = create_agent()
        logger.info("Report Engine初始化成功")
    return report_agent


# ====== SSE 常量 ======
STREAM_HEARTBEAT_INTERVAL = 15  # 心跳间隔秒（XREAD BLOCK 超时）
STREAM_IDLE_TIMEOUT = 120  # 终态后最长保活时间，避免孤儿SSE阻塞
STREAM_TERMINAL_STATUSES = {"completed", "error", "cancelled"}

def _get_task(task_id: str) -> Optional['ReportTask']:
    """
    统一的任务查找方法：从 Redis task_store 读取。

    参数:
        task_id: 任务ID。

    返回:
        ReportTask | None: 命中时返回任务实例，否则为None。
    """
    return ReportTask.from_redis(task_id)


def _latest_task() -> Optional['ReportTask']:
    """最近创建的一个任务（供 /status 展示）。"""
    ids = task_store.latest_task_ids(1)
    return ReportTask.from_redis(ids[0]) if ids else None


def _as_int(value, default: int = 0) -> int:
    """把 Redis 读出的字符串安全转成 int。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _format_sse(event: Dict[str, Any]) -> str:
    """
    按SSE协议格式化消息。

    输出形如 `id:/event:/data:` 的三段文本，供浏览器端直接消费。

    参数:
        event: 事件payload，至少包含 id/type。

    返回:
        str: SSE协议要求的字符串。
    """
    payload = json.dumps(event, ensure_ascii=False)
    event_id = event.get('id', 0)
    event_type = event.get('type', 'message')
    return f"id: {event_id}\nevent: {event_type}\ndata: {payload}\n\n"


def _safe_filename_segment(value: str, fallback: str = "report") -> str:
    """
    生成可用于文件名的安全片段，保留字母数字与常见分隔符。

    参数:
        value: 原始字符串。
        fallback: 兜底文本，当value为空或清洗后为空时使用。
    """
    sanitized = "".join(c for c in str(value) if c.isalnum() or c in (" ", "-", "_")).strip()
    sanitized = sanitized.replace(" ", "_")
    return sanitized or fallback


def initialize_report_engine():
    """
    初始化Report Engine。

    单例化 ReportAgent，方便 API 启动后直接接收任务。

    返回:
        bool: 初始化成功返回True，异常时返回False。
    """
    global report_agent
    try:
        report_agent = create_agent()
        logger.info("Report Engine初始化成功")

        # 检测 PDF 生成依赖（Pango）
        try:
            from .utils.dependency_check import log_dependency_status
            log_dependency_status()
        except Exception as dep_err:
            logger.warning(f"依赖检测失败: {dep_err}")

        return True
    except Exception as e:
        logger.exception(f"Report Engine初始化失败: {str(e)}")
        return False


class ReportTask:
    """
    报告生成任务（Redis 持久化，见 task_store）。

    写侧（worker 进程）通过属性赋值 / update_status 写穿到 Redis；
    读侧（Flask 路由）每次属性访问都取 Redis 最新值。
    事件通过 Redis Stream 追加，事件 id 即 Stream 条目 id。
    """

    # 落 Redis Hash 的字段（created_at/updated_at 存 isoformat 字符串）
    _FIELDS = (
        'query', 'custom_template', 'status', 'progress', 'error_message',
        'html_content',
        'report_file_path', 'report_file_relative_path', 'report_file_name',
        'state_file_path', 'state_file_relative_path',
        'ir_file_path', 'ir_file_relative_path',
        'markdown_file_path', 'markdown_file_relative_path', 'markdown_file_name',
        'created_at', 'updated_at',
    )

    def __init__(self, task_id: str, query: str = '', custom_template: str = ''):
        """
        绑定任务；Redis 中不存在该任务时创建初始记录。

        Args:
            task_id: 任务唯一ID
            query: 最终需要生成的报告主题
            custom_template: 可选的自定义Markdown模板
        """
        self.task_id = task_id
        if not task_store.exists(task_id):
            now = datetime.now().isoformat()
            task_store.create_task(task_id, {
                'query': query,
                'custom_template': custom_template,
                'status': 'pending',
                'progress': 0,
                'error_message': '',
                'created_at': now,
                'updated_at': now,
            })

    @classmethod
    def from_redis(cls, task_id: str) -> Optional['ReportTask']:
        """从 Redis 构建；任务不存在返回 None。"""
        if not task_store.exists(task_id):
            return None
        return cls(task_id)

    def __getattr__(self, name: str):
        # 仅常规属性未命中时才会进入这里；读一律取 Redis 最新值
        if name.startswith('_') or name not in ReportTask._FIELDS:
            raise AttributeError(name)
        fields = task_store.get_fields(object.__getattribute__(self, 'task_id')) or {}
        return fields.get(name, '')

    def __setattr__(self, name: str, value):
        if name.startswith('_') or name == 'task_id':
            object.__setattr__(self, name, value)
            return
        if name in ReportTask._FIELDS:
            task_store.set_fields(object.__getattribute__(self, 'task_id'),
                                  {name: str(value)})
            return
        object.__setattr__(self, name, value)

    def update_status(self, status: str, progress: int = None, error_message: str = ""):
        """
        更新任务状态并广播事件。

        参数:
            status: 任务阶段（pending/running/completed/error/cancelled）。
            progress: 可选的进度百分比。
            error_message: 出错时的人类可读说明。
        """
        mapping = {'status': status, 'updated_at': datetime.now().isoformat()}
        if progress is not None:
            mapping['progress'] = progress
        if error_message:
            mapping['error_message'] = error_message
        task_store.set_fields(self.task_id, mapping)
        # 推送状态变更事件，方便前端实时刷新
        info = self.to_dict()
        self.publish_event(
            'status',
            {
                'status': status,
                'progress': info['progress'],
                'error_message': info['error_message'],
                'hint': error_message or '',
                'task': info,
            }
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，方便直接返回给JSON API。"""
        f = task_store.get_fields(self.task_id) or {}
        return {
            'task_id': self.task_id,
            'query': f.get('query', ''),
            'status': f.get('status', 'pending'),
            'progress': _as_int(f.get('progress', 0)),
            'error_message': f.get('error_message', ''),
            'created_at': f.get('created_at', ''),
            'updated_at': f.get('updated_at', ''),
            'has_result': bool(f.get('html_content')),
            'report_file_ready': bool(f.get('report_file_path')),
            'report_file_name': f.get('report_file_name', ''),
            'report_file_path': f.get('report_file_relative_path') or f.get('report_file_path', ''),
            'state_file_ready': bool(f.get('state_file_path')),
            'state_file_path': f.get('state_file_relative_path') or f.get('state_file_path', ''),
            'ir_file_ready': bool(f.get('ir_file_path')),
            'ir_file_path': f.get('ir_file_relative_path') or f.get('ir_file_path', ''),
            'markdown_file_ready': bool(f.get('markdown_file_path')),
            'markdown_file_name': f.get('markdown_file_name', ''),
            'markdown_file_path': f.get('markdown_file_relative_path') or f.get('markdown_file_path', ''),
        }

    def publish_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        将事件追加到 Redis Stream（SSE 消费方按 Last-Event-ID 续读）。

        参数:
            event_type: SSE中的event名称。
            payload: 实际业务数据。
        """
        task_store.publish_event(self.task_id, event_type, payload)

    def history_since(self, last_event_id: Optional[str]) -> List[Dict[str, Any]]:
        """
        根据Last-Event-ID补发历史事件，确保断线重连无遗漏。

        参数:
            last_event_id: SSE客户端记录的最后一个事件ID（Stream 条目 id）。

        返回:
            list[dict]: 从 last_event_id 之后的事件列表。
        """
        return task_store.read_events(self.task_id, after_id=last_event_id)


def check_engines_ready() -> Dict[str, Any]:
    """
    检查三个子引擎是否都有新文件。

    调用 ReportAgent 的基准检测逻辑，并附带论坛日志存在性，
    是 /status、/generate 的前置校验。
    """
    directories = {
        'insight': 'insight_engine_streamlit_reports',
        'media': 'media_engine_streamlit_reports',
        'query': 'query_engine_streamlit_reports'
    }

    forum_log_path = 'logs/forum.log'

    try:
        agent = _get_report_agent()
    except Exception as e:
        return {
            'ready': False,
            'error': f'Report Engine初始化失败: {e}'
        }

    return agent.check_input_files(
        directories['insight'],
        directories['media'],
        directories['query'],
        forum_log_path
    )


def run_report_generation(task: ReportTask, query: str, custom_template: str = ""):
    """
    在 worker 进程中运行报告生成。

    包括：检查输入→加载文档→调用ReportAgent→持久化输出→
    推送阶段性事件。出现错误会自动推送并写状态。

    参数:
        task: 本次任务对象（状态持久化在 Redis）。
        query: 报告主题。
        custom_template: 可选的自定义模板字符串。
    """
    try:
        # 在局部闭包内封装推送逻辑，便于传递给ReportAgent
        def stream_handler(event_type: str, payload: Dict[str, Any]):
            """所有阶段事件都通过同一个接口分发，保证日志一致。"""
            task.publish_event(event_type, payload)
            # 如果事件包含进度信息，同步更新任务进度
            if event_type == 'progress' and 'progress' in payload:
                task.update_status("running", payload['progress'])

        task.update_status("running", 5)
        task.publish_event('stage', {'message': '任务已启动，正在检查输入文件', 'stage': 'prepare'})

        # 检查输入文件
        check_result = check_engines_ready()
        if not check_result['ready']:
            task.update_status("error", 0, f"输入文件未准备就绪: {check_result.get('missing_files', [])}")
            return

        if task.status == 'cancelled':
            logger.info(f"[task {task.task_id}] 任务已取消，停止执行")
            return

        task.publish_event('stage', {
            'message': '输入文件检查通过，准备载入内容',
            'stage': 'io_ready',
            'files': check_result.get('latest_files', {})
        })

        # 加载输入文件
        agent = _get_report_agent()
        content = agent.load_input_files(check_result['latest_files'])
        task.publish_event('stage', {'message': '源数据加载完成，启动生成流程', 'stage': 'data_loaded'})

        # 生成报告（附带兜底重试，缓解瞬时网络抖动）
        for attempt in range(1, 3):
            try:
                task.publish_event('stage', {
                    'message': f'正在调用ReportAgent生成报告（第{attempt}次尝试）',
                    'stage': 'agent_running',
                    'attempt': attempt
                })
                generation_result = agent.generate_report(
                    query=query,
                    reports=content['reports'],
                    forum_logs=content['forum_logs'],
                    custom_template=custom_template,
                    save_report=True,
                    stream_handler=stream_handler,
                    report_id=task.task_id
                )
                break
            except ChapterJsonParseError as err:
                hint_message = "尝试将Report Engine的API更换为算力更强、上下文更长的LLM"
                task.publish_event('warning', {
                    'message': hint_message,
                    'stage': 'agent_running',
                    'attempt': attempt,
                    'reason': 'chapter_json_parse',
                    'error': str(err),
                    'task': task.to_dict(),
                })
                # 旧逻辑：在JSON解析失败后重启Report Engine
                # backoff = min(5 * attempt, 15)
                # task.publish_event('stage', {
                #     'message': f'{backoff} 秒后重试生成任务',
                #     'stage': 'retry_wait',
                #     'wait_seconds': backoff
                # })
                # time.sleep(backoff)
                raise ChapterJsonParseError(hint_message) from err
            except Exception as err:
                # 将错误即时推送至前端，方便观察重试策略
                task.publish_event('warning', {
                    'message': f'ReportAgent执行失败: {str(err)}',
                    'stage': 'agent_running',
                    'attempt': attempt
                })
                if attempt == 2:
                    raise
                # 简单的指数退避，防止频繁触发限流（单位秒）
                backoff = min(5 * attempt, 15)
                task.publish_event('stage', {
                    'message': f'{backoff} 秒后重试生成任务',
                    'stage': 'retry_wait',
                    'wait_seconds': backoff
                })
                time.sleep(backoff)

        if isinstance(generation_result, dict):
            html_report = generation_result.get('html_content', '')
        else:
            html_report = generation_result

        if task.status == 'cancelled':
            logger.info(f"[task {task.task_id}] 任务在持久化前被取消，丢弃结果")
            return

        task.publish_event('stage', {'message': '报告生成完毕，准备持久化', 'stage': 'persist'})

        # 保存结果
        task.html_content = html_report
        if isinstance(generation_result, dict):
            task.report_file_path = generation_result.get('report_filepath', '')
            task.report_file_relative_path = generation_result.get('report_relative_path', '')
            task.report_file_name = generation_result.get('report_filename', '')
            task.state_file_path = generation_result.get('state_filepath', '')
            task.state_file_relative_path = generation_result.get('state_relative_path', '')
            task.ir_file_path = generation_result.get('ir_filepath', '')
            task.ir_file_relative_path = generation_result.get('ir_relative_path', '')
        task.publish_event('html_ready', {
            'message': 'HTML渲染完成，可刷新预览',
            'report_file': task.report_file_relative_path or task.report_file_path,
            'state_file': task.state_file_relative_path or task.state_file_path,
            'task': task.to_dict(),
        })
        task.update_status("completed", 100)
        task.publish_event('completed', {
            'message': '任务完成',
            'duration_seconds': (datetime.now() - datetime.fromisoformat(task.created_at)).total_seconds(),
            'report_file': task.report_file_relative_path or task.report_file_path,
            'task': task.to_dict(),
        })

    except Exception as e:
        logger.exception(f"报告生成过程中发生错误: {str(e)}")
        task.update_status("error", 0, str(e))
        task.publish_event('error', {
            'message': str(e),
            'stage': 'failed',
            'task': task.to_dict(),
        })


@report_bp.route('/status', methods=['GET'])
def get_status():
    """
    获取Report Engine状态，包括引擎就绪情况与当前任务信息。

    返回:
        Response: JSON结构包含initialized/engines_ready/当前任务等。
    """
    try:
        engines_status = check_engines_ready()

        return jsonify({
            'success': True,
            'initialized': report_agent is not None,
            'engines_ready': engines_status['ready'],
            'files_found': engines_status.get('files_found', []),
            'missing_files': engines_status.get('missing_files', []),
            'current_task': (lambda t: t.to_dict() if t else None)(_latest_task()),
        })
    except Exception as e:
        logger.exception(f"获取Report Engine状态失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/generate', methods=['POST'])
def generate_report():
    """
    开始生成报告。

    负责排队、创建后台线程、清空日志并返回SSE地址。

    请求体:
        query: 报告主题（可选）。
        custom_template: 自定义模板字符串（可选）。

    返回:
        Response: JSON，包含 task_id 与 SSE stream url。
    """
    try:
        # 去单例改造后允许多任务并发，由 RQ worker 逐个执行
        # 获取请求参数
        data = request.get_json() or {}
        if not isinstance(data, dict):
            logger.warning("generate_report 接收到非对象JSON负载，已忽略原始内容")
            data = {}
        query = data.get('query', '智能舆情分析报告')
        custom_template = data.get('custom_template', '')

        # 清空日志文件
        clear_report_log()

        # 检查Report Engine是否初始化（惰性兜底）
        try:
            _get_report_agent()
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Report Engine未初始化: {e}'
            }), 500

        # 检查输入文件是否准备就绪
        engines_status = check_engines_ready()
        if not engines_status['ready']:
            return jsonify({
                'success': False,
                'error': '输入文件未准备就绪',
                'missing_files': engines_status.get('missing_files', [])
            }), 400

        # 创建新任务（time_ns 避免同秒并发撞 id）
        task_id = f"report_{time.time_ns()}"
        task = ReportTask(task_id, query, custom_template)

        # 通过主动推送pending事件告知前端任务已经排队
        info = task.to_dict()
        task.publish_event(
            'status',
            {
                'status': info['status'],
                'progress': info['progress'],
                'message': '任务已排队，等待 worker 执行',
                'task': info,
            }
        )

        # 入 RQ 'pr' 队列，由 worker 进程异步执行
        try:
            from .tasks import enqueue_report_job
            enqueue_report_job(task_id, query, custom_template)
        except Exception as e:
            task.update_status("error", 0, f"任务入队失败: {e}")
            logger.exception(f"报告任务入队失败: {e}")
            return jsonify({
                'success': False,
                'error': f'任务入队失败: {e}'
            }), 500

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': '报告生成已启动',
            'task': task.to_dict(),
            'stream_url': f"/api/report/stream/{task_id}"
        })

    except Exception as e:
        logger.exception(f"开始生成报告失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/progress/<task_id>', methods=['GET'])
def get_progress(task_id: str):
    """
    获取报告生成进度，若任务被清理则返回一个完成态兜底。

    参数:
        task_id: 任务唯一标识。

    返回:
        Response: JSON包含任务当前状态。
    """
    try:
        task = _get_task(task_id)
        if not task:
            # 如果任务不存在，可能是历史记录已被清理，回传一个完成态兜底
            return jsonify({
                'success': True,
                'task': {
                    'task_id': task_id,
                    'status': 'completed',
                    'progress': 100,
                    'error_message': '',
                    'has_result': True,
                    'report_file_ready': False,
                    'report_file_name': '',
                    'report_file_path': '',
                    'state_file_ready': False,
                    'state_file_path': ''
                }
            })

        return jsonify({
            'success': True,
            'task': task.to_dict()
        })

    except Exception as e:
        logger.exception(f"获取报告生成进度失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/stream/<task_id>', methods=['GET'])
def stream_task(task_id: str):
    """
    基于SSE的实时推送接口。

    - 自动补发Last-Event-ID之后的历史事件；
    - 周期性发送心跳以防代理中断；
    - 任务结束后自动注销监听。

    参数:
        task_id: 任务唯一标识。

    返回:
        Response: `text/event-stream` 类型响应。
    """
    task = _get_task(task_id)
    if not task:
        return jsonify({'success': False, 'error': '任务不存在'}), 404

    # 事件 id 即 Redis Stream 条目 id（形如 "1728483945000-3"），
    # 浏览器断线重连时原样带回；旧版整型 id 无法映射，退回全量补发
    last_event_id = request.headers.get('Last-Event-ID') or None

    def client_disconnected() -> bool:
        """
        尽早探测客户端是否已经断开，避免继续写入触发BrokenPipe。

        eventlet 在 Windows 上会在关闭连接时抛出 ConnectionAbortedError，
        提前退出生成器可以缩减无意义的日志。
        """
        try:
            env_input = request.environ.get('wsgi.input')
            return bool(getattr(env_input, 'closed', False))
        except Exception:
            return False

    def event_generator():
        """
        SSE事件生成器（消费 Redis Stream）。

        - 先按 Last-Event-ID 补发历史事件；
        - XREAD BLOCK 持续监听新事件，超时则发心跳；
        - 终态后事件流消费完自动收口。
        """
        last_id = last_event_id
        last_data_ts = time.time()
        try:
            # 断线重连场景下，先补发历史事件，保证界面状态一致
            for event in task.history_since(last_id):
                yield _format_sse(event)
                if event.get('type') != 'heartbeat':
                    last_data_ts = time.time()
                last_id = event.get('id') or last_id
                if event.get('type') in ("completed", "error", "cancelled"):
                    return

            while True:
                if client_disconnected():
                    logger.info(f"SSE客户端已断开，停止推送: {task_id}")
                    break

                events = []
                try:
                    events = task_store.read_events(
                        task_id,
                        after_id=last_id,
                        block_ms=STREAM_HEARTBEAT_INTERVAL * 1000,
                    )
                except Exception as exc:
                    logger.exception(f"SSE读取事件流失败（task {task_id}）: {exc}")
                    break

                if not events:
                    # 超时无新事件：发心跳；任务已终态且事件消费完则收口
                    status = task.status
                    if status in STREAM_TERMINAL_STATUSES:
                        logger.info(f"任务 {task_id} 已结束且无新事件，SSE自动收口")
                        break
                    heartbeat = {
                        'id': f"hb-{int(time.time() * 1000)}",
                        'type': 'heartbeat',
                        'task_id': task_id,
                        'timestamp': datetime.utcnow().isoformat() + 'Z',
                        'payload': {'status': status}
                    }
                    events = [heartbeat]

                for event in events:
                    try:
                        yield _format_sse(event)
                        if event.get('type') != 'heartbeat':
                            last_data_ts = time.time()
                    except GeneratorExit:
                        logger.info(f"SSE生成器关闭，停止任务 {task_id} 推送")
                        return
                    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as exc:
                        logger.warning(f"SSE连接被客户端中断（task {task_id}）: {exc}")
                        return
                    except Exception as exc:
                        logger.exception(f"SSE推送失败（task {task_id}）: {exc}")
                        return

                    if event.get('type') in ("completed", "error", "cancelled"):
                        return

                    if event.get('id'):
                        last_id = event['id']

                # 终态下最多保活一段时间，防止前端早已结束但后台循环未退出
                if task.status in STREAM_TERMINAL_STATUSES:
                    idle_for = time.time() - last_data_ts
                    if idle_for > STREAM_IDLE_TIMEOUT:
                        logger.info(f"任务 {task_id} 已终态且空闲 {int(idle_for)}s，主动关闭SSE")
                        break
        except GeneratorExit:
            logger.info(f"SSE生成器关闭，停止任务 {task_id} 推送")

    response = Response(
        stream_with_context(event_generator()),
        mimetype='text/event-stream'
    )
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response


@report_bp.route('/result/<task_id>', methods=['GET'])
def get_result(task_id: str):
    """
    获取报告生成结果。

    参数:
        task_id: 任务ID。

    返回:
        Response: JSON，包含HTML预览与文件路径。
    """
    try:
        task = _get_task(task_id)
        if not task:
            return jsonify({
                'success': False,
                'error': '任务不存在'
            }), 404

        if task.status != "completed":
            return jsonify({
                'success': False,
                'error': '报告尚未完成',
                'task': task.to_dict()
            }), 400

        return Response(
            task.html_content,
            mimetype='text/html'
        )

    except Exception as e:
        logger.exception(f"获取报告生成结果失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/result/<task_id>/json', methods=['GET'])
def get_result_json(task_id: str):
    """获取报告生成结果（JSON格式）"""
    try:
        task = _get_task(task_id)
        if not task:
            return jsonify({
                'success': False,
                'error': '任务不存在'
            }), 404

        if task.status != "completed":
            return jsonify({
                'success': False,
                'error': '报告尚未完成',
                'task': task.to_dict()
            }), 400

        return jsonify({
            'success': True,
            'task': task.to_dict(),
            'html_content': task.html_content
        })

    except Exception as e:
        logger.exception(f"获取报告生成结果失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/download/<task_id>', methods=['GET'])
def download_report(task_id: str):
    """
    下载已生成的报告HTML文件。

    参数:
        task_id: 任务ID。

    返回:
        Response: HTML文件的附件下载响应。
    """
    try:
        task = _get_task(task_id)
        if not task:
            return jsonify({
                'success': False,
                'error': '任务不存在'
            }), 404

        if task.status != "completed" or not task.report_file_path:
            return jsonify({
                'success': False,
                'error': '报告尚未完成或尚未保存'
            }), 400

        if not os.path.exists(task.report_file_path):
            return jsonify({
                'success': False,
                'error': '报告文件不存在或已被删除'
            }), 404

        download_name = task.report_file_name or os.path.basename(task.report_file_path)
        return send_file(
            task.report_file_path,
            mimetype='text/html',
            as_attachment=True,
            download_name=download_name
        )

    except Exception as e:
        logger.exception(f"下载报告失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/cancel/<task_id>', methods=['POST'])
def cancel_task(task_id: str):
    """
    取消报告生成任务。

    参数:
        task_id: 需要被取消的任务ID。

    返回:
        Response: JSON，包含取消结果或错误信息。
    """
    try:
        task = _get_task(task_id)
        if not task:
            return jsonify({
                'success': False,
                'error': '任务不存在'
            }), 404

        if task.status not in ('running', 'pending'):
            return jsonify({
                'success': False,
                'error': '任务不存在或无法取消'
            }), 404

        task.update_status("cancelled", 0, "用户取消任务")
        task.publish_event('cancelled', {
            'message': '任务被用户主动终止',
            'task': task.to_dict(),
        })

        # 尽力取消 RQ 侧尚未开始执行的 job；执行中的由
        # run_report_generation 在阶段边界检测 cancelled 后自行退出
        try:
            import rq
            queue = rq.Queue('pr', connection=task_store.get_redis())
            job = queue.fetch_job(f"report_{task_id}")
            if job is not None:
                job.cancel()
        except Exception:
            logger.warning(f"RQ 侧取消失败（task {task_id}），已仅标记 Redis 状态")

        return jsonify({
            'success': True,
            'message': '任务已取消'
        })

    except Exception as e:
        logger.exception(f"取消报告生成任务失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@report_bp.route('/templates', methods=['GET'])
def get_templates():
    """
    获取可用模板列表，便于前端展示可选Markdown骨架。

    返回:
        Response: JSON，列出模板名称/描述/大小。
    """
    try:
        _get_report_agent()  # 确保引擎可用（幂等）

        template_dir = settings.TEMPLATE_DIR
        templates = []

        if os.path.exists(template_dir):
            for filename in os.listdir(template_dir):
                if filename.endswith('.md'):
                    template_path = os.path.join(template_dir, filename)
                    try:
                        with open(template_path, 'r', encoding='utf-8') as f:
                            content = f.read()

                        templates.append({
                            'name': filename.replace('.md', ''),
                            'filename': filename,
                            'description': content.split('\n')[0] if content else '无描述',
                            'size': len(content)
                        })
                    except Exception as e:
                        logger.exception(f"读取模板失败 {filename}: {str(e)}")

        return jsonify({
            'success': True,
            'templates': templates,
            'template_dir': template_dir
        })

    except Exception as e:
        logger.exception(f"获取可用模板列表失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# 错误处理
@report_bp.errorhandler(404)
def not_found(error):
    """404兜底处理：保证接口统一返回JSON结构"""
    logger.exception(f"API端点不存在: {str(error)}")
    return jsonify({
        'success': False,
        'error': 'API端点不存在'
    }), 404


@report_bp.errorhandler(500)
def internal_error(error):
    """500兜底处理：捕获未被主动捕获的异常"""
    logger.exception(f"服务器内部错误: {str(error)}")
    return jsonify({
        'success': False,
        'error': '服务器内部错误'
    }), 500


def clear_report_log():
    """
    清空report.log文件，方便新任务只查看本次运行日志。

    返回:
        None
    """
    try:
        log_file = settings.LOG_FILE

        # 【修复】使用truncate而非重新打开，避免与logger的文件句柄冲突
        # 追加模式打开，然后truncate，保持文件句柄有效
        with open(log_file, 'r+', encoding='utf-8') as f:
            f.truncate(0)  # 清空文件内容但不关闭文件
            f.flush()      # 立即刷新

        logger.info(f"已清空日志文件: {log_file}")
    except FileNotFoundError:
        # 文件不存在，创建空文件
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write('')
            logger.info(f"创建日志文件: {log_file}")
        except Exception as e:
            logger.exception(f"创建日志文件失败: {str(e)}")
    except Exception as e:
        logger.exception(f"清空日志文件失败: {str(e)}")


@report_bp.route('/log', methods=['GET'])
def get_report_log():
    """
    获取report.log内容，并按行去除空白返回。

    【修复】优化大文件读取，添加错误处理和文件锁

    返回:
        Response: JSON，包含最新日志行数组。
    """
    try:
        log_file = settings.LOG_FILE

        if not os.path.exists(log_file):
            return jsonify({
                'success': True,
                'log_lines': []
            })

        # 【修复】检查文件大小，避免读取过大文件导致内存问题
        file_size = os.path.getsize(log_file)
        max_size = 10 * 1024 * 1024  # 10MB限制

        if file_size > max_size:
            # 文件过大，只读取最后10MB
            with open(log_file, 'rb') as f:
                f.seek(-max_size, 2)  # 从文件末尾往前10MB
                # 跳过可能不完整的第一行
                f.readline()
                content = f.read().decode('utf-8', errors='replace')
            lines = content.splitlines()
            logger.warning(f"日志文件过大 ({file_size} bytes)，仅返回最后 {max_size} bytes")
        else:
            # 正常大小，完整读取
            with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()

        # 清理行尾的换行符和空行
        log_lines = [line.rstrip('\n\r') for line in lines if line.strip()]

        return jsonify({
            'success': True,
            'log_lines': log_lines
        })

    except PermissionError as e:
        logger.error(f"读取日志权限不足: {str(e)}")
        return jsonify({
            'success': False,
            'error': '读取日志权限不足'
        }), 403
    except UnicodeDecodeError as e:
        logger.error(f"日志文件编码错误: {str(e)}")
        return jsonify({
            'success': False,
            'error': '日志文件编码错误'
        }), 500
    except Exception as e:
        logger.exception(f"读取日志失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'读取日志失败: {str(e)}'
        }), 500


@report_bp.route('/log/clear', methods=['POST'])
def clear_log():
    """
    手动清空日志，提供REST入口供前端一键重置。

    返回:
        Response: JSON，标记是否清理成功。
    """
    try:
        clear_report_log()
        return jsonify({
            'success': True,
            'message': '日志已清空'
        })
    except Exception as e:
        logger.exception(f"清空日志失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'清空日志失败: {str(e)}'
        }), 500


@report_bp.route('/export/md/<task_id>', methods=['GET'])
def export_markdown(task_id: str):
    """
    导出报告为 Markdown 格式。

    基于已保存的 Document IR 调用 MarkdownRenderer，生成文件并返回下载。
    """
    try:
        task = _get_task(task_id)
        if not task:
            return jsonify({
                'success': False,
                'error': '任务不存在'
            }), 404

        if task.status != 'completed':
            return jsonify({
                'success': False,
                'error': f'任务未完成，当前状态: {task.status}'
            }), 400

        if not task.ir_file_path or not os.path.exists(task.ir_file_path):
            return jsonify({
                'success': False,
                'error': 'IR文件不存在，无法生成Markdown'
            }), 404

        with open(task.ir_file_path, 'r', encoding='utf-8') as f:
            document_ir = json.load(f)

        from .renderers import MarkdownRenderer
        renderer = MarkdownRenderer()
        # 传入 ir_file_path，修复后的图表会自动保存到 IR 文件
        markdown_text = renderer.render(document_ir, ir_file_path=task.ir_file_path)

        metadata = document_ir.get('metadata') if isinstance(document_ir, dict) else {}
        topic = (metadata or {}).get('topic') or (metadata or {}).get('title') or (metadata or {}).get('query') or task.query
        safe_topic = _safe_filename_segment(topic or 'report')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"report_{safe_topic}_{timestamp}.md"

        output_dir = Path(settings.OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / filename
        md_path.write_text(markdown_text, encoding='utf-8')

        task.markdown_file_path = str(md_path.resolve())
        task.markdown_file_relative_path = os.path.relpath(task.markdown_file_path, os.getcwd())
        task.markdown_file_name = filename

        logger.info(f"导出Markdown完成: {md_path}")

        return send_file(
            task.markdown_file_path,
            mimetype='text/markdown',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.exception(f"导出Markdown失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'导出Markdown失败: {str(e)}'
        }), 500


@report_bp.route('/export/pdf/<task_id>', methods=['GET'])
def export_pdf(task_id: str):
    """
    导出报告为PDF格式。

    从IR JSON文件生成优化的PDF，支持自动布局调整。

    参数:
        task_id: 任务ID

    查询参数:
        optimize: 是否启用布局优化（默认true）

    返回:
        Response: PDF文件流或错误信息
    """
    try:
        # 检测 Pango 依赖
        from .utils.dependency_check import check_pango_available
        pango_available, pango_message = check_pango_available()
        if not pango_available:
            return jsonify({
                'success': False,
                'error': 'PDF 导出功能不可用：缺少系统依赖',
                'details': '请查看根目录 README.md “源码启动”的第二步（PDF 导出依赖）了解安装方法',
                'help_url': 'https://github.com/666ghj/BettaFish#2-安装-pdf-导出所需系统依赖可选',
                'system_message': pango_message
            }), 503

        # 获取任务信息
        task = _get_task(task_id)
        if not task:
            return jsonify({
                'success': False,
                'error': '任务不存在'
            }), 404

        # 检查任务是否完成
        if task.status != 'completed':
            return jsonify({
                'success': False,
                'error': f'任务未完成，当前状态: {task.status}'
            }), 400

        # 获取IR文件路径
        if not task.ir_file_path or not os.path.exists(task.ir_file_path):
            return jsonify({
                'success': False,
                'error': 'IR文件不存在'
            }), 404

        # 读取IR数据
        with open(task.ir_file_path, 'r', encoding='utf-8') as f:
            document_ir = json.load(f)

        # 检查是否启用布局优化
        optimize = request.args.get('optimize', 'true').lower() == 'true'

        # 创建PDF渲染器并生成PDF
        from .renderers import PDFRenderer
        renderer = PDFRenderer()

        logger.info(f"开始导出PDF，任务ID: {task_id}，布局优化: {optimize}")

        # 生成PDF字节流
        pdf_bytes = renderer.render_to_bytes(document_ir, optimize_layout=optimize)

        # 确定下载文件名
        topic = document_ir.get('metadata', {}).get('topic', 'report')
        pdf_filename = f"report_{topic}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        # 返回PDF文件
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{pdf_filename}"',
                'Content-Type': 'application/pdf'
            }
        )

    except Exception as e:
        logger.exception(f"导出PDF失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'导出PDF失败: {str(e)}'
        }), 500


@report_bp.route('/export/pdf-from-ir', methods=['POST'])
def export_pdf_from_ir():
    """
    从IR JSON直接导出PDF（不需要任务ID）。

    适用于前端直接传递IR数据的场景。

    请求体:
        {
            "document_ir": {...},  // Document IR JSON
            "optimize": true       // 是否启用布局优化（可选）
        }

    返回:
        Response: PDF文件流或错误信息
    """
    try:
        # 检测 Pango 依赖
        from .utils.dependency_check import check_pango_available
        pango_available, pango_message = check_pango_available()
        if not pango_available:
            return jsonify({
                'success': False,
                'error': 'PDF 导出功能不可用：缺少系统依赖',
                'details': '请查看根目录 README.md “源码启动”的第二步（PDF 导出依赖）了解安装方法',
                'help_url': 'https://github.com/666ghj/BettaFish#2-安装-pdf-导出所需系统依赖可选',
                'system_message': pango_message
            }), 503

        data = request.get_json() or {}
        if not isinstance(data, dict):
            logger.warning("export_pdf_from_ir 请求体不是JSON对象")
            return jsonify({
                'success': False,
                'error': '请求体必须是JSON对象'
            }), 400

        if not data or 'document_ir' not in data:
            return jsonify({
                'success': False,
                'error': '缺少document_ir参数'
            }), 400

        document_ir = data['document_ir']
        optimize = data.get('optimize', True)

        # 创建PDF渲染器并生成PDF
        from .renderers import PDFRenderer
        renderer = PDFRenderer()

        logger.info(f"从IR直接导出PDF，布局优化: {optimize}")

        # 生成PDF字节流
        pdf_bytes = renderer.render_to_bytes(document_ir, optimize_layout=optimize)

        # 确定下载文件名
        topic = document_ir.get('metadata', {}).get('topic', 'report')
        pdf_filename = f"report_{topic}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        # 返回PDF文件
        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{pdf_filename}"',
                'Content-Type': 'application/pdf'
            }
        )

    except Exception as e:
        logger.exception(f"从IR导出PDF失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'导出PDF失败: {str(e)}'
        }), 500
