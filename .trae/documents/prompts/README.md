# Prompt 模板库 · 装配说明

本目录是「多 Agent 协作 Prompt 工程方案」的模板实现，配套主文档
[../多Agent协作Prompt工程方案.md](../多Agent协作Prompt工程方案.md)。

> 现状：仅设计产物，尚未接入运行时。接入时建议复制到 `bettafish-main/backend/agents/prompts/`
> （见主文档 §9.3），本目录保留为可评审的源版本。

## 1. 文件清单

| 文件 | 层 | 作用 |
|---|---|---|
| `l0_constitution.j2` | L0 | 全局铁律，代码内固化，任何层不得覆盖 |
| `l1_orchestrator.j2` | L1 | 调度者：任务规划 → TaskPlan |
| `l1_collector.j2` | L1 | 采集员：唯一接触原始网页的角色 |
| `l1_verifier.j2` | L1 | 核验员：去重、来源、完整性、主体一致性 |
| `l1_analyst.j2` | L1 | 分析师：单维度结论，置信度由证据聚合 |
| `l1_arbiter.j2` | L1 | 仲裁者：按固定优先级裁决冲突 |
| `l1_writer.j2` | L1 | 写作：只重组证据与分析，逐句带角标 |
| `l1_reviewer.j2` | L1 | 审核：只报问题不改稿，blocker 即 reject |
| `l2_task.j2` | L2 | 本次任务参数（按 role 分支） |
| `l3_evidence.j2` | L3 | 证据注入：nonce 包裹 + 三级压缩 + 注入隔离 |

## 2. 装配顺序（不可调换）

```text
system_prompt = L0 + "\n\n" + L1_<role>
user_prompt   = L2(role=...) + "\n\n" + L3(evidence=..., analyses=...)
```

为什么顺序不可调换：

1. **L0 在最前**——模型对开头的约束遵守率最高；把铁律放在证据之后等于把裁判权交给外部内容。
2. **L3 在最后且之后不再接指令**——若证据后面还有指令，注入内容可以伪装成"系统后续要求"。
3. **L2 在 L3 之前**——任务参数属于可信输入，必须与不可信证据物理分离。

`L0` 与 `L1` 只拼一次（同一任务内复用，可命中前缀缓存）；`L2` 每阶段可不同；
`L3` 每次调用都不同。

## 3. 渲染示例（Python）

```python
import hashlib
import secrets

from jinja2 import Environment, FileSystemLoader, StrictUndefined

PROMPT_DIR = "backend/agents/prompts"
env = Environment(
    loader=FileSystemLoader(PROMPT_DIR),
    undefined=StrictUndefined,      # 缺变量必须报错，不允许静默渲染成空
    autoescape=False,               # 提示词不是 HTML，转义在下面显式做
    trim_blocks=True,
    lstrip_blocks=True,
)


def sanitize_untrusted(text: str, nonce: str) -> str:
    """L3 证据正文消毒：破坏伪标签 + 防闭合逃逸。必须在渲染前调用。"""
    if not text:
        return ""
    if nonce in text:               # 证据里出现 nonce → 无法安全包裹，整条丢弃
        return ""
    text = text.replace("<", "＜").replace(">", "＞")
    # 额外破坏常见的伪标签与分隔符
    for bad in ("```", "###", "[INST]", "<<SYS>>", "</s>"):
        text = text.replace(bad, "［已屏蔽］")
    return text


def build_prompts(role: str, task: dict, obj: dict, params: dict, evidence: list[dict],
                  analyses: list[dict], level: str = "full") -> tuple[str, str]:
    nonce = secrets.token_hex(4)
    safe_evidence = []
    for ev in evidence:
        raw_quote = ev.get("quote") or ""
        clean = sanitize_untrusted(raw_quote, nonce)
        if raw_quote and not clean:      # quote 含 nonce，无法安全包裹，整条丢弃
            continue
        safe_evidence.append({**ev, "quote": clean})
    max_items = {"full": 15, "digest": 60, "index": 200}[level]

    system_prompt = (
        env.get_template("l0_constitution.j2").render()
        + "\n\n"
        + env.get_template(f"l1_{role}.j2").render()
    )
    user_prompt = env.get_template("l2_task.j2").render(
        role=role, task=task, object=obj, params=params
    ) + "\n\n" + env.get_template("l3_evidence.j2").render(
        nonce=nonce, level=level, evidence=safe_evidence,
        analyses=analyses, max_items=max_items
    )
    return system_prompt, user_prompt


def prompt_fingerprint(role: str, system_prompt: str, user_prompt: str) -> tuple[str, str]:
    """返回 (prompt_version, prompt_sha256)，必须与 agent_run 一起落库。"""
    full = system_prompt + "\x00" + user_prompt
    sha = hashlib.sha256(full.encode("utf-8")).hexdigest()
    return f"l0@1.0.0|{role}@1.0.0|{sha[:12]}", sha
```

## 4. 变量契约

| 变量 | 层 | 类型 | 说明 |
|---|---|---|---|
| `role` | L2 | enum | 七个角色之一，决定 L2 的分支 |
| `task` | L2 | object | `task_id / product_line / task_type / requested_by / created_at` |
| `object` | L2 | object | `object_id / object_type / display_name / natural_key / display_meta` |
| `params` | L2 | object | 任务参数，按角色取子集（见下表） |
| `nonce` | L3 | string | 8 位随机十六进制，每次调用重生成 |
| `level` | L3 | enum | `full / digest / index` |
| `evidence` | L3 | array | Evidence 数组（`quote` 已消毒） |
| `analyses` | L3 | array | 已仲裁结论，可为空 |
| `max_items` | L3 | int | 本批上限：15 / 60 / 200 |

`params` 按角色必填项：

| role | 必填 params |
|---|---|
| orchestrator | `dimension_catalog`、`allowed_source_types` |
| collector | `collection_requests`、`existing_content_hashes`、`tool_call_budget`、`source_grade_rules` |
| verifier | `allowed_domains`、`object_identifiers`、`existing_content_hashes` |
| analyst | `dimension`（含 `dimension/fact_types/weight`）、`rubric` |
| arbiter | `conflict_report`、`priority` |
| writer | `chapter_spec`、`compliance_note`、`scorecard`（investment_dd） |
| reviewer | `review_scope`、`deterministic_findings` |

## 5. 三条不可妥协的实现要求

1. **`StrictUndefined`**：变量缺失必须抛异常。提示词静默少一段字段，会让模型自由发挥，
   这是幻觉的主要入口之一。
2. **nonce 每次重新生成**，且 `sanitize_untrusted` 必须在渲染前执行。仅靠模板里的
   声明文字防不住注入，物理隔离（破坏伪标签、防止闭合）才是有效防线。
3. **落库最终全文**：只存 `prompt_version` 无法复现——模板 + 数据才等于最终 prompt。
   `agent_run.prompt_text` 必须保存渲染后的 `user_prompt` 全文（或对象存储引用）。

## 6. 版本化

- 语义版本：`l0@1.0.0`、`l1_analyst@1.0.0`，每个 `.j2` 文件头注释里维护。
- 内容指纹：`sha256(渲染后全文)`，进 `agent_run.prompt_sha256`。
- 变更纪律：任何 L0/L1 修改都要走 golden set 回归（主文档 §8），指标不下降才合入。
- L3 模板修改需额外跑注入回归用例（含 5 条已知注入样本）。

## 7. 本地自测

```bash
# 渲染快照（不调用 LLM），确认无未定义变量、无空段
python -m backend.agents.prompt_snapshot --role analyst --case golden/case_01.json

# 与上一次快照 diff，评审提示词改动
python -m backend.agents.prompt_snapshot --role analyst --diff
```

（命令为设计建议，尚未实现；接入时按主文档 §9.2 的「必须新写」清单实现。）

## 8. 常见错误

| 错误 | 后果 |
|---|---|
| 把 L3 拼到 L0 之前 | 证据里的伪指令优先级高于铁律，注入直接生效 |
| 用字符串替换拼 L2 而不是模板 | 用户输入里的 `{` 会破坏 JSON 参数段 |
| `quote` 未消毒直接注入 | 网页里的 `</EVIDENCE_BLOCK>` 可提前闭合证据块 |
| 证据超限直接截断到 `max_items` 而不告知 | 模型以为"就这么多"，把缺失写成"不存在" |
| 只保存 prompt_version 不保存全文 | 历史结果无法复现 |
