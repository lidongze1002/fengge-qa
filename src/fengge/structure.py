from __future__ import annotations

import json
from typing import Any

from .models import QUESTION_TYPES

QUESTION_TYPES = QUESTION_TYPES  # re-export for callers that import from structure

SYSTEM_PROMPT = """你是视频问答标注员。给定一个短视频的标题和带时间戳的逐句转写，抽取出其中的问答对。

规则：
1. 只有当视频里确实有人提出问题、并且有人给出回答时才产出 item；纯段子、纯情绪输出、连麦互骂但没有问答的，返回空数组。
2. 一条视频里可能有多组问答，全部产出，按时间顺序排列。
3. question_verbatim 忠实于原话，保留口语和脏话。
4. abstract_question 是核心字段：去掉人名、平台名、具体地名、脏话、具体时间，把问题改写成一句任何人都会问的通用问题。
   例：「峰哥，我98年的在深圳送外卖还有救吗」→「二十多岁做体力工作还有没有出路」。
5. answer_summary 用 2-3 句复述峰哥的核心观点，不要加自己的判断。
6. quote 挑一句最出圈、最有峰哥味道的原话；没有就留空串。
7. quality 1-5：5 是观点清晰且完整回答，3 是答了但很散，1 是几乎没回答。
8. trim 给出这组问答的首尾秒数，必须是转写里出现过的区间，同一视频的多组 trim 不能重叠。
9. question_type 只能从给定的枚举里选一个。
"""


def _item_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "is_qa": {"type": "boolean"},
            "question_verbatim": {"type": "string"},
            "abstract_question": {"type": "string"},
            "question_type": {"type": "string", "enum": list(QUESTION_TYPES)},
            "answer_summary": {"type": "string"},
            "key_claims": {"type": "array", "items": {"type": "string"}},
            "quote": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "emotion": {"type": "string"},
            "quality": {"type": "integer", "minimum": 1, "maximum": 5},
            "reject_reason": {"type": ["string", "null"]},
            "trim": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                },
                "required": ["start", "end"],
                "additionalProperties": False,
            },
        },
        "required": [
            "is_qa",
            "question_verbatim",
            "abstract_question",
            "question_type",
            "answer_summary",
            "key_claims",
            "quote",
            "tags",
            "emotion",
            "quality",
            "reject_reason",
            "trim",
        ],
        "additionalProperties": False,
    }


def qa_json_schema() -> dict[str, Any]:
    return {
        "name": "qa_items",
        "schema": {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": _item_schema()},
            },
            "required": ["items"],
            "additionalProperties": False,
        },
    }


def build_messages(
    title: str, segments: list[dict[str, Any]], duration: float
) -> list[dict[str, str]]:
    lines = [f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments]
    user = (
        f"标题：{title}\n"
        f"总时长：{duration:.1f} 秒\n"
        f"逐句转写：\n" + "\n".join(lines) + "\n\n"
        "question_type 必须严格取以下之一（逐字照抄，不要自创）：\n"
        + "、".join(QUESTION_TYPES)
        + "\ntrim 必须是 {\"start\": 秒, \"end\": 秒} 对象。\n"
        "只输出 JSON：{\"items\": [...]}。"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def parse_llm_response(content: str) -> list[dict[str, Any]]:
    text = (content or "").strip()
    if text.startswith("```"):
        body = text.split("```")[1]
        if body.startswith("json"):
            body = body[4:]
        text = body.strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned invalid JSON: {text[:200]}") from exc
    if not isinstance(payload, dict) or "items" not in payload:
        raise ValueError(f"LLM response missing 'items': {text[:200]}")
    items = payload["items"]
    if not isinstance(items, list):
        raise ValueError("LLM response 'items' is not a list")
    return [item for item in items if isinstance(item, dict)]


def structure_clip(
    client: Any,
    model: str,
    title: str,
    segments: list[dict[str, Any]],
    duration: float,
) -> list[dict[str, Any]]:
    messages = build_messages(title, segments, duration)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_schema", "json_schema": qa_json_schema()},
            temperature=0.2,
        )
    except Exception as exc:  # noqa: BLE001
        if "response_format" not in str(exc) and "json_schema" not in str(exc):
            raise
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.2,
        )
    return parse_llm_response(resp.choices[0].message.content or "")


class LLMClient:
    """Pipeline 只需要 .structure(title, segments, duration)。"""

    def __init__(self, api_key: str, model: str, base_url: str = "", timeout: float = 180.0):
        from openai import OpenAI

        kwargs: dict[str, Any] = {"api_key": api_key, "timeout": timeout, "max_retries": 3}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self.model = model

    def structure(
        self, title: str, segments: list[dict[str, Any]], duration: float
    ) -> list[dict[str, Any]]:
        return structure_clip(self._client, self.model, title, segments, duration)

    def complete(self, system: str, user: str, max_tokens: int = 400) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""
