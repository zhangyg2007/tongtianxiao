#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多 Agent 提示词链路 · 离线案例 runner。

用途：
  1. 加载 .trae/documents/cases/*.json；
  2. 用 Jinja2 StrictUndefined 渲染 .trae/documents/prompts/ 下的 L0/L1/L2/L3 模板；
  3. 输出渲染结果、三档压缩选择与 token 估算；
  4. 运行代码层后校验（schema / evidence_id / quote 一致性 / 数字回查 / 绝对化词 /
     注入检测 / 缺失维度 / 时效 / 实体对齐 / 压缩截断）；
  5. 用 golden 的 sample_answer_md 做期望结果评分；
  6. 可选：配置 API 后跑真实调用并保存 trace。

设计约束：
  - 不调用业务代码，不写数据库；
  - 缺少 jinja2 时明确报错退出，不自动安装；
  - 缺少 jsonschema 时降级为内置最小校验，并在报告中标注；
  - 缺少 core.evidence_raw 时，真实案例 quote 只能标 partial（runner 会如实报告）。

示例：
  python .trae/documents/cases/run_case.py
  python .trae/documents/cases/run_case.py --case adv_05_prompt_injection --levels
  python .trae/documents/cases/run_case.py --case real_002372_weixing --role analyst --all-roles
  python .trae/documents/cases/run_case.py --case adv_06_oversize_evidence --dump-prompts .tmp/prompts
  python .trae/documents/cases/run_case.py --case real_002372_weixing --api --out trace.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

CASES_DIR = Path(__file__).resolve().parent
DOCS_DIR = CASES_DIR.parent
PROMPTS_DIR = DOCS_DIR / "prompts"
SCHEMA_PATH = CASES_DIR / "evidence.schema.json"
REPO_ROOT = CASES_DIR.parents[2]
VERIFY_PY = REPO_ROOT / "bettafish-main" / "backend" / "dd" / "verify.py"

ROLE_LEVEL_MAX_ITEMS = {"full": 15, "digest": 60, "index": 200}
LEVEL_CHAR_BUDGET = {"full": 12000, "digest": 30000}
ROLES = ["orchestrator", "collector", "verifier", "analyst", "arbiter", "writer", "reviewer"]

ABSOLUTE_WORDS = [
    "绝对", "必然", "从未", "毫无", "百分之百", "确保",
    "完全不存在", "一定不会",
]

INJECTION_MARKERS = [
    "忽略以上", "忽略上述", "ignore previous", "ignore all previous",
    "系统提示词", "system prompt", "</EVIDENCE_BLOCK>", "[INST]", "<<SYS>>",
    "你现在是", "标记为低风险",
]

META_MARKERS = (
    "本批", "截断", "索引级", "元数据", "数据缺失", "证据覆盖",
    "渲染", "评分", "合规声明", "本案例为人为构造",
)

USCC_RE = re.compile(r"(?<![0-9A-Z])[0-9A-HJ-NPQRTUWXY]{18}(?![0-9A-Z])")

# 一条事实句通常以“（依据 E12,E13）”收尾；按角标组切句，避免同一行多组引用时
# 数字被错误地拿去和所有被引证据比对。
CITE_GROUP_RE = re.compile(r"（依据\s*E\d+(?:\s*[,，、]\s*E\d+)*\s*）")

# must_not_include 采用子串匹配；若短语前面是“不得/不能/禁止”等否定词，
# 说明报告是在禁止该说法，不应判为幻觉。
NEGATION_RE = re.compile(r"(不得|不能|不应|不可|禁止|严禁|并非|而非|避免|不等于|不要)")

try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    HAS_JINJA = True
except ImportError:  # pragma: no cover
    HAS_JINJA = False

try:
    import jsonschema
    from jsonschema import FormatChecker
    HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover
    HAS_JSONSCHEMA = False


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def norm_text(s: str | None) -> str:
    """去空白，用于 quote 与原文的连续性比对。"""
    return re.sub(r"[\s\u3000]+", "", s or "")


def estimate_tokens(text: str) -> int:
    """CJK 约 1.4 字符/token，其余约 4 字符/token；误差约 ±15%。"""
    cjk = len(re.findall(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]", text or ""))
    other = max(0, len(text or "") - cjk)
    return int(math.ceil(cjk / 1.4 + other / 4))


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def months_between(older: datetime, newer: datetime) -> int:
    return (newer.year - older.year) * 12 + (newer.month - older.month) + (
        1 if newer.day >= older.day else 0
    )


def sanitize_untrusted(text: str, nonce: str) -> str:
    """与 prompts/README.md 的参考实现保持一致。"""
    if not text:
        return ""
    if nonce and nonce in text:
        return ""
    text = text.replace("<", "＜").replace(">", "＞")
    for bad in ("```", "###", "[INST]", "<<SYS>>", "</s>"):
        text = text.replace(bad, "［已屏蔽］")
    return text


def choose_level(evidence: list[dict]) -> tuple[str, int, int]:
    """按条数与 quote 总字符数选择 full/digest/index。"""
    n = len(evidence)
    chars = sum(len(ev.get("quote") or "") for ev in evidence)
    if n > ROLE_LEVEL_MAX_ITEMS["digest"] or chars > LEVEL_CHAR_BUDGET["digest"]:
        return "index", n, chars
    if n > ROLE_LEVEL_MAX_ITEMS["full"] or chars > LEVEL_CHAR_BUDGET["full"]:
        return "digest", n, chars
    return "full", n, chars


def load_verify_module():
    """优先复用 backend/dd/verify.py；失败则返回本地等价实现。"""
    if VERIFY_PY.exists():
        try:
            spec = importlib.util.spec_from_file_location("bf_dd_verify", str(VERIFY_PY))
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            return mod, f"imported:{VERIFY_PY}"
        except Exception as exc:  # noqa: BLE001
            pass
    return _LocalVerify(), "local_fallback"


class _LocalVerify:
    CITATION_RE = re.compile(r"\bE(\d+)\b")
    NUMBER_TOKEN_RE = re.compile(r"\d[\d,，.\-]*")
    MIN_TOKEN_LEN = 2

    @staticmethod
    def _normalize(s: str) -> str:
        return re.sub(r"[,，\s]", "", s)

    def extract_citations(self, text: str) -> list[int]:
        seen: list[int] = []
        for m in self.CITATION_RE.finditer(text):
            eid = int(m.group(1))
            if eid not in seen:
                seen.append(eid)
        return seen

    def extract_numbers(self, text: str) -> list[str]:
        tokens = []
        for m in self.NUMBER_TOKEN_RE.finditer(text):
            raw = m.group(0)
            start = m.start()
            if start > 0 and text[start - 1] in "Ee":
                continue
            norm = self._normalize(raw).strip(".-")
            if len(norm) >= self.MIN_TOKEN_LEN and norm not in tokens:
                tokens.append(norm)
        return tokens

    def numbers_missing_in_quote(self, fact_text: str, quote: str | None) -> list[str]:
        if not quote:
            return self.extract_numbers(fact_text)
        quote_norm = self._normalize(quote)
        return [n for n in self.extract_numbers(fact_text) if n not in quote_norm]

    def verify_report(self, blocks, evidence_by_id, object_id):
        citations: dict[str, dict] = {}
        issues: list[dict] = []
        for block in blocks:
            if block.get("block_type") == "heading":
                continue
            content = block.get("content_md") or ""
            for line in content.splitlines():
                line_citations = self.extract_citations(line)
                if not line_citations:
                    continue
                for eid in line_citations:
                    entry = citations.setdefault(
                        str(eid), {"checked": True, "block_seqs": []}
                    )
                    entry["block_seqs"].append(block["seq"])
                    ev = evidence_by_id.get(eid)
                    if ev is None:
                        entry["checked"] = False
                        issues.append({
                            "type": "missing_evidence", "block_seq": block["seq"],
                            "evidence_id": eid, "detail": f"E{eid} 引用的证据不存在",
                        })
                        continue
                    if ev.get("object_id") != object_id:
                        entry["checked"] = False
                        issues.append({
                            "type": "object_mismatch", "block_seq": block["seq"],
                            "evidence_id": eid,
                            "detail": f"E{eid} 归属对象 {ev.get('object_id')} 与 {object_id} 不一致",
                        })
                        continue
                    missing = self.numbers_missing_in_quote(line, ev.get("quote"))
                    if missing:
                        entry["checked"] = False
                        issues.append({
                            "type": "number_mismatch", "block_seq": block["seq"],
                            "evidence_id": eid,
                            "detail": f"E{eid} 所在句数字 {missing} 未见于原文片段",
                        })
        passed = sum(1 for c in citations.values() if c["checked"])
        return {
            "citations": citations,
            "issues": issues,
            "passed": passed,
            "failed": len(citations) - passed,
        }


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------

def build_env():
    if not HAS_JINJA:
        raise SystemExit(
            "缺少依赖 jinja2，无法渲染提示词。请先安装（本脚本不会自动安装）：\n"
            "  python -m pip install jinja2\n"
            "如只需查看案例 JSON，可直接打开 .trae/documents/cases/README.md。"
        )
    return Environment(
        loader=FileSystemLoader(str(PROMPTS_DIR)),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )


def build_prompts(env, case: dict, role: str, level: str, nonce: str | None = None):
    nonce = nonce or secrets.token_hex(4)
    safe_evidence = []
    dropped = []
    for ev in case.get("evidence", []):
        raw_quote = ev.get("quote") or ""
        clean = sanitize_untrusted(raw_quote, nonce)
        if raw_quote and not clean:
            dropped.append(ev.get("evidence_id"))
            continue
        safe_evidence.append({**ev, "quote": clean})

    max_items = ROLE_LEVEL_MAX_ITEMS[level]
    system_prompt = (
        env.get_template("l0_constitution.j2").render()
        + "\n\n"
        + env.get_template(f"l1_{role}.j2").render()
    )
    l2 = env.get_template("l2_task.j2").render(
        role=role,
        task=case.get("task", {}),
        object=case.get("object", {}),
        params=case.get("params", {}),
    )
    l3 = env.get_template("l3_evidence.j2").render(
        nonce=nonce,
        level=level,
        evidence=safe_evidence,
        analyses=case.get("analyses", []),
        max_items=max_items,
    )
    user_prompt = l2 + "\n\n" + l3
    return {
        "nonce": nonce,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "l2": l2,
        "l3": l3,
        "safe_evidence": safe_evidence,
        "dropped": dropped,
    }


def prompt_fingerprint(role: str, system_prompt: str, user_prompt: str):
    full = system_prompt + "\x00" + user_prompt
    sha = hashlib.sha256(full.encode("utf-8")).hexdigest()
    return f"l0@1.0.0|{role}@1.0.0|{sha[:12]}", sha


# ---------------------------------------------------------------------------
# 结果收集
# ---------------------------------------------------------------------------

class Report:
    def __init__(self, case_id: str, role: str, level: str):
        self.case_id = case_id
        self.role = role
        self.level = level
        self.checks: list[dict] = []
        self.metrics: dict = {}

    def add(self, name: str, status: str, detail: str = ""):
        self.checks.append({"name": name, "status": status, "detail": detail})

    def fail(self, name: str, detail: str = ""):
        self.add(name, "fail", detail)

    def warn(self, name: str, detail: str = ""):
        self.add(name, "warn", detail)

    def ok(self, name: str, detail: str = ""):
        self.add(name, "pass", detail)

    def info(self, name: str, detail: str = ""):
        self.add(name, "info", detail)

    def counts(self):
        c = {"pass": 0, "fail": 0, "warn": 0, "info": 0}
        for chk in self.checks:
            c[chk["status"]] = c.get(chk["status"], 0) + 1
        return c

    def verdict(self):
        return "FAIL" if self.counts()["fail"] else "PASS"

    def to_dict(self):
        return {
            "case_id": self.case_id,
            "role": self.role,
            "level": self.level,
            "verdict": self.verdict(),
            "counts": self.counts(),
            "metrics": self.metrics,
            "checks": self.checks,
        }


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------

def validate_schema(case: dict, schema: dict, report: Report):
    evidence = case.get("evidence", [])
    if HAS_JSONSCHEMA:
        validator = jsonschema.Draft202012Validator(
            schema, format_checker=FormatChecker()
        )
        errors = []
        for ev in evidence:
            for err in sorted(validator.iter_errors(ev), key=lambda e: list(e.path)):
                errors.append(f"{ev.get('evidence_id', '?')}: {err.message}")
        if errors:
            report.fail("schema", "; ".join(errors[:6]) + (
                f"（共 {len(errors)} 处）" if len(errors) > 6 else ""
            ))
        else:
            report.ok("schema", f"{len(evidence)}/{len(evidence)} 条通过 jsonschema")
        return
    # 最小校验
    errors = []
    required = schema.get("required", [])
    props = schema.get("properties", {})
    for ev in evidence:
        eid = ev.get("evidence_id", "?")
        for key in required:
            if key not in ev:
                errors.append(f"{eid}: 缺少 {key}")
        quote = ev.get("quote") or ""
        if not (10 <= len(quote) <= 1000):
            errors.append(f"{eid}: quote 长度 {len(quote)} 越界")
        fact = ev.get("fact") or ""
        if not (8 <= len(fact) <= 300):
            errors.append(f"{eid}: fact 长度 {len(fact)} 越界")
        if not str(ev.get("source_url", "")).startswith(("http://", "https://")):
            errors.append(f"{eid}: source_url 非 http(s)")
        if ev.get("fact_type") not in props["fact_type"]["enum"]:
            errors.append(f"{eid}: fact_type 非法")
        if ev.get("source_type") not in props["source_type"]["enum"]:
            errors.append(f"{eid}: source_type 非法")
        if ev.get("confidence") is not None and not (0 <= ev["confidence"] <= 100):
            errors.append(f"{eid}: confidence 越界")
    if errors:
        report.fail("schema", "; ".join(errors[:6]))
    else:
        report.warn(
            "schema",
            f"未安装 jsonschema，已用内置最小校验（{len(evidence)} 条）；"
            "安装后可得完整 draft 2020-12 校验：python -m pip install jsonschema",
        )


def check_ids(case: dict, report: Report):
    evidence = case.get("evidence", [])
    ids = [ev.get("evidence_id") for ev in evidence]
    bad = [i for i in ids if not re.fullmatch(r"E[0-9]{1,9}", str(i or ""))]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if bad:
        report.fail("evidence_id_format", f"非法编号：{bad[:8]}")
    if dup:
        report.fail("evidence_id_unique", f"重复编号：{dup}")
    if not bad and not dup:
        report.ok("evidence_id", f"{len(ids)} 个编号唯一且格式合法")


def check_quote(case: dict, report: Report):
    source_texts = case.get("source_texts") or {}
    evidence = case.get("evidence", [])
    if not source_texts:
        report.warn(
            "quote_consistency",
            "案例未提供 source_texts，quote 无法做连续性二级校验；"
            "真实案例因 core.evidence_raw 未落地只能标 partial",
        )
        report.metrics["quote_verifiable_rate"] = None
        return
    ok, bad = [], []
    for ev in evidence:
        eid = ev.get("evidence_id")
        src = source_texts.get(ev.get("source_url"))
        if not src:
            bad.append(f"{eid}:source_texts 缺 URL")
        elif norm_text(ev.get("quote")) in norm_text(src):
            ok.append(eid)
        else:
            bad.append(f"{eid}:quote 不在原文中")
    rate = len(ok) / len(evidence) if evidence else 0.0
    report.metrics["quote_verifiable_rate"] = round(rate, 4)
    if bad:
        report.fail("quote_consistency", f"{len(bad)} 条不一致：{bad[:6]}")
    else:
        report.ok("quote_consistency", f"{len(ok)}/{len(evidence)} 条可在 source_texts 中连续命中")


def iter_claim_blocks(answer: str) -> list[dict]:
    """把 markdown 答案拆成“一条事实句”级别的块，供 verify_report 做数字回查。

    标题与元信息行（本批/截断/数据缺失等）标为 heading，跳过回查；
    其余按“（依据 E..）”角标组切分，确保每个数字只与它所属的引用比对。
    """
    blocks: list[dict] = []
    seq = 0
    for raw_line in (answer or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        seq += 1
        if line.startswith("#") or any(m in line for m in META_MARKERS):
            blocks.append({"seq": seq, "content_md": line, "block_type": "heading"})
            continue
        last = 0
        claims = []
        for m in CITE_GROUP_RE.finditer(line):
            seg = line[last:m.end()].strip(" 。；;，,")
            if seg:
                claims.append(seg)
            last = m.end()
        tail = line[last:].strip(" 。；;，,")
        if tail:
            claims.append(tail)
        if not claims:
            claims = [line]
        for part in claims:
            seq += 1
            blocks.append({"seq": seq, "content_md": part, "block_type": "paragraph"})
    return blocks


def check_numbers_and_citations(case: dict, answer: str, report: Report):
    verify, source = load_verify_module()
    evidence = case.get("evidence", [])
    object_id = case.get("object", {}).get("object_id")
    ev_by_id = {int(str(ev["evidence_id"])[1:]): ev for ev in evidence}
    blocks = iter_claim_blocks(answer)
    result = verify.verify_report(blocks, ev_by_id, object_id)

    issues = result["issues"]
    number_issues = [i for i in issues if i["type"] == "number_mismatch"]
    missing_ev = [i for i in issues if i["type"] == "missing_evidence"]
    object_mismatch = [i for i in issues if i["type"] == "object_mismatch"]

    if number_issues:
        detail = "; ".join(i["detail"] for i in number_issues[:5])
        report.fail("number_backcheck", detail)
    else:
        report.ok(
            "number_backcheck",
            f"{result['passed']}/{len(result['citations'])} 个引用通过数字回查（{source}）",
        )
    if missing_ev:
        report.fail("citation_exists", "; ".join(i["detail"] for i in missing_ev[:5]))
    else:
        report.ok("citation_exists", "答案中的 evidence_id 均存在")
    if object_mismatch:
        report.fail("citation_object", "; ".join(i["detail"] for i in object_mismatch[:5]))

    # 引用合规（段落级）：有数字但整段无 citation 视为未标注
    numeric_paras, uncited = 0, []
    for line in (answer or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or any(m in s for m in META_MARKERS):
            continue
        if re.search(r"\d[\d,，.\-]{1,}", s):
            numeric_paras += 1
            if not re.search(r"\bE\d+\b", s):
                uncited.append(s[:40])
    compliance = 1.0 if numeric_paras == 0 else 1 - len(uncited) / numeric_paras
    report.metrics["citation_compliance"] = round(compliance, 4)
    if uncited:
        report.fail(
            "citation_compliance",
            f"{len(uncited)}/{numeric_paras} 个含数字段落无引用：" + "; ".join(uncited[:3]),
        )
    else:
        report.ok("citation_compliance", f"{numeric_paras} 个含数字段落均带引用")


def check_absolute_words(answer: str, report: Report):
    hits = []
    for word in ABSOLUTE_WORDS:
        if word in (answer or ""):
            hits.append(word)
    if hits:
        report.warn("absolute_words", f"出现绝对化表述：{hits}（需人工确认是否越界）")
    else:
        report.ok("absolute_words", "未发现绝对化表述")


def check_injection(case: dict, rendered: dict, report: Report):
    gate = case.get("gate_expectations", {})
    expected_ids = set(gate.get("injection_evidence_ids") or [])
    hits: dict[str, list[str]] = {}
    for ev in case.get("evidence", []):
        text = (ev.get("fact") or "") + "\n" + (ev.get("quote") or "")
        found = [m for m in INJECTION_MARKERS if m.lower() in text.lower()]
        if found:
            hits[ev.get("evidence_id")] = found
    detected = set(hits)
    unmarked = [
        eid for eid in detected
        if not next(
            (ev for ev in case["evidence"] if ev.get("evidence_id") == eid), {}
        ).get("injection_suspected")
    ]
    if expected_ids and not expected_ids.issubset(detected):
        report.fail(
            "injection_detect",
            f"预期注入证据 {sorted(expected_ids)} 未全部检出，实际 {sorted(detected)}",
        )
    elif detected:
        report.ok("injection_detect", f"检出 {sorted(detected)}：{hits}")
    else:
        report.ok("injection_detect", "未发现注入特征")

    if unmarked:
        report.warn("injection_flag", f"{unmarked} 含注入特征但 injection_suspected 未置 true")

    # 消毒与夹层完整性：模板正文里会先出现一次开标签字样，实际开/闭各一次
    sanitized_bad = [
        ev.get("evidence_id") for ev in rendered["safe_evidence"]
        if "<" in (ev.get("quote") or "") or ">" in (ev.get("quote") or "")
    ]
    l3 = rendered["l3"]
    open_tags = l3.count('<EVIDENCE_BLOCK nonce="')
    close_tags = l3.count('</EVIDENCE_BLOCK nonce="')
    bare_close = l3.count("</EVIDENCE_BLOCK>")
    if sanitized_bad:
        report.fail("sanitize", f"{sanitized_bad} 消毒后仍含尖括号")
    elif expected_ids:
        if "＜/EVIDENCE_BLOCK＞" in l3:
            report.ok("sanitize", "注入证据的伪闭合标签已被替换为全角")
        else:
            report.warn("sanitize", "未在 L3 中观察到被替换的伪闭合标签")
    else:
        report.ok("sanitize", "证据正文已消毒")

    if open_tags != 2 or close_tags != 1 or bare_close:
        report.fail(
            "evidence_block",
            f"L3 证据块标签异常：open={open_tags} close={close_tags} bare_close={bare_close}"
            "（模板说明 1 次 + 实际开 1 次；闭合应仅 1 次且必须带 nonce）",
        )
    else:
        report.ok("evidence_block", "L3 证据块夹层完整，闭合标签均带 nonce")


def check_dimensions(case: dict, report: Report):
    dims = case.get("dimensions") or []
    evidence = case.get("evidence", [])
    covered, missing = [], []
    for dim in dims:
        types = set(dim.get("fact_types") or [])
        if any(ev.get("fact_type") in types for ev in evidence):
            covered.append(dim.get("dimension"))
        else:
            missing.append(dim.get("dimension"))
    rate = len(covered) / len(dims) if dims else 0.0
    report.metrics["coverage"] = round(rate, 4)
    report.metrics["covered_dimensions"] = covered
    report.metrics["missing_dimensions"] = missing

    expected_missing = set(
        (case.get("gate_expectations") or {}).get("empty_dimensions") or []
    )
    if expected_missing:
        if set(missing) == expected_missing:
            report.ok(
                "dimension_coverage",
                f"{len(covered)}/{len(dims)} 覆盖；缺失维度与预期一致：{sorted(missing)}",
            )
        else:
            report.fail(
                "dimension_coverage",
                f"缺失维度 {sorted(missing)} 与预期 {sorted(expected_missing)} 不一致",
            )
    else:
        detail = f"{len(covered)}/{len(dims)} 覆盖"
        if missing:
            detail += f"；缺失：{missing}"
        report.ok("dimension_coverage", detail)


def check_stale(case: dict, report: Report):
    gate = case.get("gate_expectations", {})
    expected = set(gate.get("stale_evidence_ids") or [])
    threshold = int((case.get("params") or {}).get("stale_after_months", 24))
    created = parse_dt((case.get("task") or {}).get("created_at"))
    stale = []
    if created:
        for ev in case.get("evidence", []):
            published = parse_dt(ev.get("published_at"))
            if not published:
                continue
            age = months_between(published, created)
            if age > threshold:
                stale.append(ev.get("evidence_id"))
    if expected:
        if set(stale) >= expected:
            report.ok(
                "stale_evidence",
                f"{sorted(expected)} 已识别为超过 {threshold} 个月的历史证据",
            )
        else:
            report.fail(
                "stale_evidence",
                f"预期过期证据 {sorted(expected)}，实际识别 {stale}",
            )
    else:
        if stale:
            report.warn("stale_evidence", f"存在超过 {threshold} 个月的证据：{stale}")
        else:
            report.ok("stale_evidence", f"无超过 {threshold} 个月的证据")


def check_entity(case: dict, report: Report):
    gate = case.get("gate_expectations", {})
    expected_rejected = set(gate.get("rejected_evidence_ids") or [])
    target = str((case.get("object", {}).get("natural_key") or {}).get("uscc") or "")
    mismatch = []
    for ev in case.get("evidence", []):
        text = " ".join([
            ev.get("fact") or "",
            ev.get("quote") or "",
            (case.get("source_texts") or {}).get(ev.get("source_url"), ""),
        ])
        found = {m.group(0) for m in USCC_RE.finditer(text)}
        found = {f for f in found if not target or f != target}
        if found:
            mismatch.append((ev.get("evidence_id"), sorted(found)))
    mismatch_ids = {eid for eid, _ in mismatch}

    if expected_rejected:
        status_ok = all(
            next((ev for ev in case["evidence"] if ev.get("evidence_id") == eid), {})
            .get("verify_status") == "rejected"
            for eid in expected_rejected
        )
        if status_ok:
            report.ok(
                "entity_alignment",
                f"{sorted(expected_rejected)} 已标 rejected；"
                f"检出其他主体 USCC：{mismatch or '无'}",
            )
        else:
            report.fail(
                "entity_alignment",
                f"预期拒绝 {sorted(expected_rejected)} 中存在未标 rejected 的证据",
            )
    elif mismatch:
        report.warn(
            "entity_alignment",
            f"证据中出现非标的主体 USCC（可能是关联方，需人工确认）：{mismatch[:5]}",
        )
    else:
        report.ok("entity_alignment", "未发现其他主体 USCC")

    expected_review = set(gate.get("needs_review_evidence_ids") or [])
    if expected_review:
        bad = [
            eid for eid in expected_review
            if next((ev for ev in case["evidence"] if ev.get("evidence_id") == eid), {})
            .get("verify_status") != "needs_review"
        ]
        if bad:
            report.fail("needs_review", f"{bad} 未标 needs_review")
        else:
            report.ok("needs_review", f"{sorted(expected_review)} 已标 needs_review")


def check_compression(case: dict, env, role: str, level: str, report: Report):
    gate = case.get("gate_expectations", {})
    expected_level = gate.get("expected_auto_level")
    evidence = case.get("evidence", [])
    if expected_level and expected_level != level:
        report.fail(
            "compression_choice",
            f"自动选择 {level}，与预期 {expected_level} 不一致",
        )
    else:
        report.ok("compression_choice", f"自动选择 {level}（{len(evidence)} 条证据）")

    expected_levels = gate.get("expected_levels") or {}
    seen = {}
    for lv in ("full", "digest", "index"):
        rendered = build_prompts(env, case, role, lv, nonce="deadbeef")
        l3 = rendered["l3"]
        items = len(re.findall(r"(?m)^\[E\d+\]", l3))
        truncated = "本批已截断" in l3
        has_quote = bool(re.search(r"(?m)^quote: ", l3))
        seen[lv] = {"items": items, "truncated": truncated, "has_quote": has_quote}
        exp = expected_levels.get(lv)
        if exp:
            cap = int(exp.get("max_items"))
            expected_items = min(len(evidence), cap)
            expected_trunc = len(evidence) > cap
            if items != expected_items or truncated != expected_trunc:
                report.fail(
                    f"compression_{lv}",
                    f"渲染 items={items} truncated={truncated}，"
                    f"预期 items={expected_items} truncated={expected_trunc}（cap={cap}）",
                )
    report.metrics["levels"] = seen
    if not expected_levels:
        report.info("compression_levels", json.dumps(seen, ensure_ascii=False))


def check_arbiter(case: dict, report: Report):
    conflict = (case.get("params") or {}).get("conflict_report") or {}
    if not conflict:
        return
    gate = case.get("gate_expectations", {})
    expected = gate.get("expected_arbiter_conflict_id")
    cid = conflict.get("conflict_id")
    ev_ids = set(ev.get("evidence_id") for ev in case.get("evidence", []))
    missing = [eid for eid in conflict.get("evidence_ids", []) if eid not in ev_ids]
    analyses = case.get("analyses") or []
    conclusions = {a.get("conclusion") for a in analyses}
    ok = (
        (not expected or cid == expected)
        and not missing
        and len(analyses) >= 2
        and len(conclusions) >= 2
    )
    if ok:
        report.ok(
            "arbiter_trigger",
            f"冲突 {cid} 已登记，关联证据齐全，{len(analyses)} 条分析结论不一致",
        )
    else:
        report.fail(
            "arbiter_trigger",
            f"冲突登记不完整：cid={cid} expected={expected} missing={missing} "
            f"analyses={len(analyses)} distinct_conclusions={len(conclusions)}",
        )


def find_violations(text: str, phrases: list[str]) -> list[str]:
    """返回确实出现的禁止结论（排除“不得写成 X”这类否定语境）。"""
    hits = []
    for phrase in phrases:
        start = 0
        while True:
            idx = text.find(phrase, start)
            if idx < 0:
                break
            window = text[max(0, idx - 24):idx]
            if not NEGATION_RE.search(window):
                hits.append(phrase)
                break
            start = idx + 1
    return hits


def check_golden(case: dict, answer: str, report: Report):
    golden = case.get("golden") or {}
    must_include = golden.get("must_include") or []
    must_not = golden.get("must_not_include") or []
    include_hits = [x for x in must_include if x in answer]
    include_miss = [x for x in must_include if x not in answer]
    not_hits = find_violations(answer, must_not)

    if include_miss:
        report.fail(
            "golden_must_include",
            f"{len(include_hits)}/{len(must_include)} 命中；缺失：{include_miss[:6]}",
        )
    else:
        report.ok("golden_must_include", f"{len(include_hits)}/{len(must_include)} 全部命中")

    if not_hits:
        report.fail("golden_must_not_include", f"出现禁止结论：{not_hits[:6]}")
    else:
        report.ok("golden_must_not_include", f"{len(must_not)} 条禁止结论均未出现")

    sentences = [s for s in re.split(r"[。；！？\n]", answer) if s.strip()]
    hallucination_rate = len(not_hits) / max(1, len(sentences))
    fact_accuracy = len(include_hits) / len(must_include) if must_include else 1.0
    report.metrics["fact_accuracy"] = round(fact_accuracy, 4)
    report.metrics["hallucination_rate"] = round(hallucination_rate, 4)

    scoring = golden.get("scoring") or {}
    checks = [
        ("fact_accuracy", fact_accuracy, scoring.get("fact_accuracy_target")),
        ("citation_compliance", report.metrics.get("citation_compliance"),
         scoring.get("citation_compliance_target")),
        ("coverage", report.metrics.get("coverage"), scoring.get("coverage_target")),
        ("hallucination_rate", hallucination_rate, scoring.get("hallucination_rate_target")),
    ]
    for name, actual, target in checks:
        if actual is None or target is None:
            continue
        if name == "hallucination_rate":
            ok = actual <= target
        else:
            ok = actual + 0.01 >= target
        if not ok:
            report.fail(
                f"target_{name}",
                f"实际 {actual:.4f} 未达目标 {target}",
            )


def check_bad_sample(case: dict, report: Report):
    golden = case.get("golden") or {}
    bad = golden.get("bad_sample_md")
    if not bad:
        return
    verify, _ = load_verify_module()
    evidence = case.get("evidence", [])
    object_id = case.get("object", {}).get("object_id")
    ev_by_id = {int(str(ev["evidence_id"])[1:]): ev for ev in evidence}
    res = verify.verify_report(iter_claim_blocks(bad), ev_by_id, object_id)
    number_issues = [i for i in res["issues"] if i["type"] == "number_mismatch"]
    expected_tokens = golden.get("bad_sample_must_fail") or []
    caught = any(
        any(
            re.sub(r"[,，\s]", "", tok) in re.sub(r"[,，\s]", "", i["detail"])
            for tok in expected_tokens
        )
        for i in number_issues
    ) if expected_tokens else bool(number_issues)
    if caught:
        report.ok(
            "bad_sample_gate",
            f"坏样例被数字回查拦截：{number_issues[0]['detail'] if number_issues else ''}",
        )
    else:
        report.fail(
            "bad_sample_gate",
            f"坏样例未被拦截（预期出现 {expected_tokens}）：issues={res['issues'][:3]}",
        )


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def load_case(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def find_cases(selector: str | None) -> list[Path]:
    files = sorted(
        p for p in CASES_DIR.glob("*.json")
        if p.name != "evidence.schema.json"
    )
    if not selector:
        return files
    sel = selector.lower()
    matched = [
        p for p in files
        if sel in p.stem.lower() or sel == (json.loads(
            p.read_text(encoding="utf-8")
        ).get("case_id", "").lower())
    ]
    if not matched:
        raise SystemExit(f"未找到案例：{selector}（可用：{[p.stem for p in files]}）")
    return matched


def run_one(case: dict, args, env) -> tuple[Report, dict]:
    evidence = case.get("evidence", [])
    auto_level, n, chars = choose_level(evidence)
    report = Report(case.get("case_id", "?"), args.role, auto_level)
    report.metrics["evidence_count"] = n
    report.metrics["total_quote_chars"] = chars
    report.metrics["auto_level_reason"] = (
        f"n={n}, quote_chars={chars}; "
        f"full≤15条/{LEVEL_CHAR_BUDGET['full']}字符，"
        f"digest≤60条/{LEVEL_CHAR_BUDGET['digest']}字符，其余 index"
    )

    try:
        rendered = build_prompts(env, case, args.role, auto_level)
        report.ok("template_render", f"L0/L1 + L2/L3 渲染成功（nonce={rendered['nonce']}）")
    except Exception as exc:  # noqa: BLE001
        report.fail("template_render", f"{type(exc).__name__}: {exc}")
        return report, {}

    report.metrics["tokens"] = {
        "system": estimate_tokens(rendered["system_prompt"]),
        "user": estimate_tokens(rendered["user_prompt"]),
        "l2": estimate_tokens(rendered["l2"]),
        "l3": estimate_tokens(rendered["l3"]),
        "note": "CJK/1.4 + 非CJK/4，误差约 ±15%",
    }
    version, sha = prompt_fingerprint(args.role, rendered["system_prompt"], rendered["user_prompt"])
    report.metrics["prompt_version"] = version
    report.metrics["prompt_sha256"] = sha
    if rendered["dropped"]:
        report.warn("nonce_drop", f"以下证据含 nonce 被整条丢弃：{rendered['dropped']}")

    check_ids(case, report)
    validate_schema(case, load_schema(), report)
    check_quote(case, report)
    check_injection(case, rendered, report)
    check_dimensions(case, report)
    check_stale(case, report)
    check_entity(case, report)
    check_compression(case, env, args.role, auto_level, report)
    check_arbiter(case, report)

    answer = rendered.get("answer")
    if args.answer:
        answer = Path(args.answer).read_text(encoding="utf-8")
    elif not answer:
        answer = (case.get("golden") or {}).get("sample_answer_md", "")
    if not answer:
        report.warn("golden_answer", "案例未提供 sample_answer_md，跳过 golden 评分")
    else:
        check_numbers_and_citations(case, answer, report)
        check_absolute_words(answer, report)
        check_golden(case, answer, report)
        check_bad_sample(case, report)

    # 可选：真实 API 调用
    if args.api:
        api_cfg = {
            "key": os.environ.get("BF_API_KEY") or os.environ.get("OPENAI_API_KEY"),
            "base": os.environ.get("BF_API_BASE", "https://api.openai.com/v1"),
            "model": os.environ.get("BF_MODEL", "gpt-4o-mini"),
        }
        if not api_cfg["key"]:
            report.warn(
                "api_call",
                "未配置 BF_API_KEY / OPENAI_API_KEY，已跳过真实调用；"
                "模板装配与离线校验结果仍然有效",
            )
        else:
            try:
                content, trace = call_api(
                    rendered["system_prompt"], rendered["user_prompt"], api_cfg
                )
                report.ok("api_call", f"{api_cfg['model']} 返回 {len(content)} 字符")
                report.metrics["api_trace"] = trace
                check_numbers_and_citations(case, content, report)
                check_absolute_words(content, report)
                check_golden(case, content, report)
            except Exception as exc:  # noqa: BLE001
                report.warn("api_call", f"调用失败，已保留离线结果：{type(exc).__name__}: {exc}")

    # 记录三档渲染产物大小
    report.metrics["level_sizes"] = {}
    for lv in ("full", "digest", "index"):
        r = build_prompts(env, case, args.role, lv, nonce="deadbeef")
        report.metrics["level_sizes"][lv] = {
            "l3_chars": len(r["l3"]),
            "l3_tokens": estimate_tokens(r["l3"]),
        }

    return report, rendered


def call_api(system_prompt: str, user_prompt: str, cfg: dict) -> tuple[str, dict]:
    url = cfg["base"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['key']}",
        },
        method="POST",
    )
    start = time.time()
    with urllib.request.urlopen(req, timeout=180) as resp:  # noqa: S310
        body = json.loads(resp.read().decode("utf-8"))
    latency_ms = int((time.time() - start) * 1000)
    content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
    trace = {
        "url": url,
        "model": cfg["model"],
        "latency_ms": latency_ms,
        "usage": body.get("usage"),
        "response_id": body.get("id"),
        "finish_reason": body.get("choices", [{}])[0].get("finish_reason"),
        "output_chars": len(content),
    }
    return content, trace


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def print_report(report: Report, args):
    c = report.counts()
    print("")
    print(f"=== {report.case_id} · role={report.role} · level={report.level} ===")
    tokens = report.metrics.get("tokens") or {}
    if tokens:
        print(
            f"[tokens] system≈{tokens['system']} user≈{tokens['user']} "
            f"(L2≈{tokens['l2']}, L3≈{tokens['l3']})"
        )
    print(
        f"[evidence] {report.metrics.get('evidence_count')} 条，"
        f"quote≈{report.metrics.get('total_quote_chars')} 字符；"
        f"覆盖 {len(report.metrics.get('covered_dimensions') or [])}"
        f"/{len(report.metrics.get('covered_dimensions') or []) + len(report.metrics.get('missing_dimensions') or [])}"
    )
    for chk in report.checks:
        mark = {"pass": "PASS", "fail": "FAIL", "warn": "WARN", "info": "INFO"}[chk["status"]]
        line = f"[{mark}] {chk['name']}"
        if chk["detail"]:
            line += f": {chk['detail']}"
        print(line)
    print(
        f"VERDICT: {report.verdict()} "
        f"(pass={c['pass']} fail={c['fail']} warn={c['warn']} info={c['info']})"
    )


def main():
    parser = argparse.ArgumentParser(description="多 Agent 提示词离线案例 runner")
    parser.add_argument("--case", help="案例 id 或文件名片段；缺省跑全部")
    parser.add_argument("--role", default="analyst", choices=ROLES, help="渲染角色，默认 analyst")
    parser.add_argument("--all-roles", action="store_true", help="依次渲染全部 7 个角色")
    parser.add_argument("--levels", action="store_true", help="额外打印 full/digest/index 三档大小")
    parser.add_argument("--answer", help="用指定 markdown 文件替代 sample_answer_md 做评分")
    parser.add_argument("--dump-prompts", help="把渲染后的 system/user prompt 写入目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON 报告")
    parser.add_argument("--out", help="把 JSON 报告写入文件")
    parser.add_argument("--api", action="store_true", help="配置 API 后跑真实调用")
    args = parser.parse_args()

    env = build_env()
    cases = find_cases(args.case)
    reports = []

    for path in cases:
        case = load_case(path)
        roles = ROLES if args.all_roles else [args.role]
        for role in roles:
            args_role = role
            args.role = args_role
            report, rendered = run_one(case, args, env)
            reports.append(report)
            if not args.json:
                print_report(report, args)
            if args.dump_prompts:
                out_dir = Path(args.dump_prompts) / case.get("case_id", path.stem)
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / f"{role}.system.txt").write_text(
                    rendered.get("system_prompt", ""), encoding="utf-8"
                )
                (out_dir / f"{role}.user.txt").write_text(
                    rendered.get("user_prompt", ""), encoding="utf-8"
                )
                print(f"[dump] {out_dir}\\{role}.system.txt / {role}.user.txt")
            if args.levels and not args.json:
                print("[level sizes] " + json.dumps(
                    report.metrics.get("level_sizes", {}), ensure_ascii=False
                ))

    payload = [r.to_dict() for r in reports]
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[out] {args.out}")

    failed = sum(1 for r in reports if r.verdict() == "FAIL")
    if not args.json:
        print("")
        print(f"总结：{len(reports)} 次运行，FAIL {failed} 次。")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
