from __future__ import annotations

import json
from types import SimpleNamespace

from fengge.query import abstract_query, rerank


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def complete(self, system, user, max_tokens=400):
        self.calls.append((system, user))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def hit(id_, question, answer="答"):
    return SimpleNamespace(
        record={"id": id_, "abstract_question": question, "answer_summary": answer}
    )


def test_abstract_query_returns_model_text():
    llm = FakeLLM("二十多岁做体力工作还有没有出路")
    assert abstract_query(llm, "峰哥我在深圳送外卖25岁还有救吗") == "二十多岁做体力工作还有没有出路"


def test_abstract_query_strips_punctuation_and_newlines():
    llm = FakeLLM("  父母催婚该怎么应对。\n  ")
    assert abstract_query(llm, "我妈天天催婚") == "父母催婚该怎么应对"


def test_abstract_query_falls_back_on_error():
    llm = FakeLLM(RuntimeError("boom"))
    assert abstract_query(llm, "  原问题  ") == "原问题"


def test_abstract_query_falls_back_when_too_long():
    llm = FakeLLM("很" * 80)
    assert abstract_query(llm, "原问题") == "原问题"


def test_rerank_parses_json():
    llm = FakeLLM(json.dumps({"id": "a", "verdict": "answers", "reason": "直接回答"}))
    out = rerank(llm, "要不要读研", [hit("a", "要不要读研"), hit("b", "怎么找对象")])
    assert out["id"] == "a"
    assert out["verdict"] == "answers"


def test_rerank_handles_fenced_json():
    llm = FakeLLM('```json\n{"id": "b", "verdict": "partial"}\n```')
    assert rerank(llm, "q", [hit("b", "x")])["verdict"] == "partial"


def test_rerank_returns_none_on_bad_payload():
    assert rerank(FakeLLM("不是json"), "q", [hit("a", "x")]) is None
    assert rerank(FakeLLM(json.dumps({"verdict": "maybe"})), "q", [hit("a", "x")]) is None
    assert rerank(FakeLLM(RuntimeError("x")), "q", [hit("a", "x")]) is None


def test_rerank_returns_none_without_hits():
    llm = FakeLLM("{}")
    assert rerank(llm, "q", []) is None
    assert llm.calls == []
