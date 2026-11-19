from __future__ import annotations

import json
import re
from typing import Any

EXPAND_SYSTEM = """你把用户的口语提问改写成 3 条「通用人生问题」，用来做检索。

要求：
1. 去掉具体人名、地名、公司名、平台名、数字、时间、职业细节和情绪词。
2. 三条要覆盖不同的说法：一条最贴原意，一条更宽，一条换个角度。
3. 每条不超过 30 字，不要解释。
4. 只输出 JSON：{"questions": ["...", "...", "..."]}

例：
输入：峰哥我在深圳送外卖25岁还有救吗
输出：{"questions": ["二十多岁做体力工作还有没有出路", "没有学历的年轻人怎么改变现状", "送外卖这类工作能长期干吗"]}
"""

ABSTRACT_SYSTEM = EXPAND_SYSTEM  # 兼容旧名字


def _clean(text: str, limit: int = 60) -> str:
    text = re.sub(r"[\r\n]+", " ", (text or "").strip().strip("。\"'“”"))
    return text if len(text) <= limit else ""


def expand_query(llm: Any, question: str) -> list[str]:
    """把提问改写成 1~3 条通用问题；失败时退回原文。"""
    question = (question or "").strip()
    if not question:
        return []
    try:
        content = llm.complete(EXPAND_SYSTEM, question)
    except Exception:  # noqa: BLE001
        return [question]

    payload: Any = None
    try:
        raw = (content or "").strip().strip("`")
        payload = json.loads(raw.removeprefix("json"))
    except Exception:  # noqa: BLE001
        payload = None

    variants: list[str] = []
    if isinstance(payload, dict):
        for item in payload.get("questions") or []:
            cleaned = _clean(str(item))
            if cleaned and cleaned not in variants:
                variants.append(cleaned)
    if not variants:
        cleaned = _clean(content or "")
        if cleaned:
            variants = [cleaned]
    if not variants:
        return [question]

    variants = variants[:3]
    if question not in variants:
        variants.append(question)
    return variants


def abstract_query(llm: Any, question: str) -> str:
    """只要一条改写结果时用这个。"""
    variants = expand_query(llm, question)
    return variants[0] if variants else question


RERANK_SYSTEM = """判断候选片段是否真的回答了用户的问题。

用户问题：{question}

候选片段：
{candidates}

只输出 JSON：{{"id": "最匹配的候选 id 或空串", "verdict": "answers|partial|no", "reason": "一句话"}}
- answers：这段直接回答了问题
- partial：只沾到边，能给一点启发但没正面回答
- no：答非所问，宁可说 no 也不要硬凑
"""


def _client(llm: Any) -> Any:
    return llm


def _format_candidates(hits: list[Any]) -> str:
    lines = []
    for hit in hits:
        r = hit.record
        lines.append(
            f'- id={r.get("id")} | 问：{r.get("abstract_question")} | 答：'
            f'{(r.get("answer_summary") or "")[:80]}'
        )
    return "\n".join(lines)


def rerank(llm: Any, question: str, hits: list[Any]) -> dict[str, Any] | None:
    """让模型判断候选里有没有真正回答提问的；失败返回 None（退回纯向量判断）。"""
    if not hits:
        return None
    prompt = RERANK_SYSTEM.format(
        question=question, candidates=_format_candidates(hits)
    )
    try:
        content = llm.complete("你是一个严格的检索评审，只输出 JSON。", prompt)
        payload = json.loads((content or "").strip().strip("`").removeprefix("json"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None
    verdict = payload.get("verdict")
    if verdict not in ("answers", "partial", "no"):
        return None
    return {
        "id": str(payload.get("id") or ""),
        "verdict": verdict,
        "reason": str(payload.get("reason") or "")[:120],
    }
