"""证据后校验（定制化设计方案 §8.1.4 第 2 条——产品可信度的关键，纯函数）。

对报告正文做两类校验：
1. 引用校验：抽取所有 E{evidence_id} 角标，校验证据存在且归属报告主体；
2. 数字回查：抽取引用所在句中的数字（金额/比例/次数/日期），
   回查对应证据 quote（原文片段）是否包含该数字；
   不包含 → 该引用 checked=False，标红降级为「待核实」。

生成报告时事实句由 evidence 组装，天然通过；
该机制主要拦截后续 LLM 生成 / 人工编辑引入的数字漂移。
"""

import re

# 引用角标：E12 / E123
CITATION_RE = re.compile(r"\bE(\d+)\b")

# 数字 token：连续数字，可含千分位/小数点/日期连字符（2024-03-12、1,000.50）
NUMBER_TOKEN_RE = re.compile(r"\d[\d,，.\-]*")

# 校验时忽略的短数字（如"E12"角标自身、章节号）
MIN_TOKEN_LEN = 2


def _normalize(s: str) -> str:
    """去千分位分隔符与空白，便于子串匹配。"""
    return re.sub(r"[,，\s]", "", s)


def extract_citations(text: str) -> list[int]:
    """按出现顺序抽取去重后的 evidence_id 列表。"""
    seen: list[int] = []
    for m in CITATION_RE.finditer(text):
        eid = int(m.group(1))
        if eid not in seen:
            seen.append(eid)
    return seen


def extract_numbers(text: str) -> list[str]:
    """抽取数字 token（归一化后），过滤引用角标自身。"""
    tokens = []
    for m in NUMBER_TOKEN_RE.finditer(text):
        raw = m.group(0)
        # 跳过 E+数字 的角标本身
        start = m.start()
        if start > 0 and text[start - 1] in "Ee":
            continue
        norm = _normalize(raw).strip(".-")
        if len(norm) >= MIN_TOKEN_LEN and norm not in tokens:
            tokens.append(norm)
    return tokens


def numbers_missing_in_quote(fact_text: str, quote: str | None) -> list[str]:
    """事实句中的数字哪些未出现在原文片段里。"""
    if not quote:
        # 无 quote 的证据：数字一律视为待核实
        return extract_numbers(fact_text)
    quote_norm = _normalize(quote)
    return [n for n in extract_numbers(fact_text) if n not in quote_norm]


def verify_report(
    blocks: list[dict],
    evidence_by_id: dict[int, dict],
    object_id: int,
) -> dict:
    """对报告块做引用校验 + 数字回查。

    blocks: [{seq, content_md, ...}]（heading 块自动跳过）
    evidence_by_id: {evidence_id: evidence_row}

    返回：
    {
      "citations": {str(evidence_id): {"checked": bool, "block_seqs": [...]}},
      "issues": [{"type", "block_seq", "evidence_id", "detail"}],
      "passed": int, "failed": int,
    }
    """
    citations: dict[str, dict] = {}
    issues: list[dict] = []
    for block in blocks:
        if block.get("block_type") == "heading":
            continue
        content = block.get("content_md") or ""
        # 句级校验：引用与数字须在同一行才互相关联，
        # 避免多证据合并在一个块时数字张冠李戴
        for line in content.splitlines():
            line_citations = extract_citations(line)
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
                        "type": "missing_evidence",
                        "block_seq": block["seq"],
                        "evidence_id": eid,
                        "detail": f"E{eid} 引用的证据不存在",
                    })
                    continue
                if ev.get("object_id") != object_id:
                    entry["checked"] = False
                    issues.append({
                        "type": "object_mismatch",
                        "block_seq": block["seq"],
                        "evidence_id": eid,
                        "detail": f"E{eid} 归属对象 {ev.get('object_id')}，"
                                  f"与报告主体 {object_id} 不一致",
                    })
                    continue
                missing = numbers_missing_in_quote(line, ev.get("quote"))
                if missing:
                    entry["checked"] = False
                    issues.append({
                        "type": "number_mismatch",
                        "block_seq": block["seq"],
                        "evidence_id": eid,
                        "detail": f"E{eid} 所在句数字 {missing} 未见于原文片段，"
                                  "降级为待核实",
                    })
    passed = sum(1 for c in citations.values() if c["checked"])
    return {
        "citations": citations,
        "issues": issues,
        "passed": passed,
        "failed": len(citations) - passed,
    }
