"""investment_dd 任务处理器：评分 → 组装 12 章 → 证据后校验 → 落 PG。

P0 定位：确定性流水线（无 LLM）。报告事实全部来自 core.evidence，
评分卡按 template.py 的规则评估，后校验走 verify.py。
P1 接入真实数据源与 LLM 章节写作后，评分/校验/落库环节原样复用。

input: {}（对象取自 core.task.object_id，任务须挂对象发起）
产出：core.artifact + core.artifact_block + core.artifact_citation（含 checked）
"""

from ..worker import evidence as evidence_store
from ..worker import store
from ..worker.jobs import TaskContext, register
from ..worker.objects import (
    get_object,
    register_artifact,
    write_artifact_blocks,
    write_citation,
)
from .report import build_blocks, build_scorecard
from .template import TEMPLATE_CODE
from .verify import verify_report


@register("investment_dd")
def investment_dd(ctx: TaskContext, input: dict) -> dict:
    """投资尽调报告（P0：确定性流水线，事实全部来自 core.evidence）。"""
    task = store.get_task(ctx.task_id)
    object_id = (task or {}).get("object_id")
    if not object_id:
        raise ValueError("investment_dd 必须挂载 object_id 发起（先注册对象）")

    with ctx.step("load_evidence"):
        ctx.set_stage("加载对象与证据", 10)
        object_row = get_object(object_id)
        if object_row is None:
            raise ValueError(f"对象 {object_id} 不存在")
        rows = evidence_store.list_evidence(object_id=object_id, limit=500)

    with ctx.step("scorecard"):
        ctx.set_stage("评分卡三态判定", 30)
        card = build_scorecard(rows)

    with ctx.step("compose_report"):
        ctx.set_stage("组装 12 章报告", 50)
        blocks = build_blocks(object_row, rows, card, verify_result=None)

    with ctx.step("verify_evidence"):
        ctx.set_stage("证据后校验（引用 + 数字回查）", 70)
        evidence_by_id = {r["evidence_id"]: r for r in rows}
        verify_result = verify_report(blocks, evidence_by_id, object_id)
        # 后校验结果并入第 12 章附录后重算一次块
        blocks = build_blocks(object_row, rows, card, verify_result)

    with ctx.step("persist_artifact"):
        ctx.set_stage("落库产物与句级引用", 90)
        artifact_id = register_artifact(
            task_id=ctx.task_id,
            object_id=object_id,
            artifact_type="report_md",
            template_code=TEMPLATE_CODE,
            title=f"{object_row['display_name']} 投资尽调报告（{TEMPLATE_CODE}）",
        )
        block_ids = write_artifact_blocks(artifact_id, blocks)
        # 句级引用绑定：正文 E{id} 角标 ↔ evidence（checked = 后校验是否通过）
        for eid_str, info in verify_result["citations"].items():
            for seq in info["block_seqs"]:
                write_citation(
                    artifact_id=artifact_id,
                    block_id=block_ids[seq - 1],
                    marker=f"E{eid_str}",
                    evidence_id=int(eid_str),
                    checked=info["checked"],
                )

    ctx.set_stage("完成", 100)
    return {
        "artifact_id": artifact_id,
        "template_code": TEMPLATE_CODE,
        "scorecard": {
            "score": card.score,
            "coverage": round(card.coverage, 4),
            "verdict": card.verdict,
            "verdict_label": card.verdict_label,
            "dimensions": [
                {"key": d.key, "name": d.name, "weight": d.weight,
                 "status": d.status, "score": d.score}
                for d in card.dimensions
            ],
        },
        "verify": {
            "citations": len(verify_result["citations"]),
            "passed": verify_result["passed"],
            "failed": verify_result["failed"],
        },
        "evidence_count": len(rows),
    }
