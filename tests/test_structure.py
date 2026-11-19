from __future__ import annotations

import json

import pytest

from fengge.structure import (
    QUESTION_TYPES,
    build_messages,
    parse_llm_response,
    qa_json_schema,
    structure_clip,
)


def test_twelve_controlled_types():
    assert len(QUESTION_TYPES) == 12
    assert QUESTION_TYPES[0] == "职业发展"
    assert QUESTION_TYPES[-1] == "其他"


def test_schema_restricts_question_type_to_enum():
    schema = qa_json_schema()
    item = schema["schema"]["properties"]["items"]["items"]
    assert item["properties"]["question_type"]["enum"] == list(QUESTION_TYPES)
    assert item["properties"]["quality"]["minimum"] == 1
    assert item["properties"]["quality"]["maximum"] == 5


def test_messages_include_timestamps_and_duration():
    segs = [{"start": 2.4, "end": 5.1, "text": "峰哥"}]
    msgs = build_messages("标题", segs, 30.0)
    assert msgs[0]["role"] == "system"
    assert "峰哥" in msgs[1]["content"] and "2.4" in msgs[1]["content"]
    assert "30" in msgs[1]["content"]
    for t in QUESTION_TYPES:
        assert t in msgs[1]["content"]


def test_parse_response_returns_items():
    body = {"items": [{"question_type": "职业发展"}]}
    assert (
        parse_llm_response(json.dumps(body, ensure_ascii=False))[0]["question_type"]
        == "职业发展"
    )


def test_parse_response_rejects_bad_json():
    with pytest.raises(ValueError):
        parse_llm_response("不是 json")


def test_parse_response_tolerates_markdown_fence():
    body = {"items": []}
    assert parse_llm_response("```json\n" + json.dumps(body) + "\n```") == []


def test_parse_response_drops_non_dict_items():
    body = {"items": [["not", "a", "dict"], {"question_type": "其他"}]}
    assert parse_llm_response(json.dumps(body)) == [{"question_type": "其他"}]


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]


class _Completions:
    def __init__(self):
        self.formats = []

    def create(self, model, messages, response_format, temperature):
        self.formats.append(response_format["type"])
        if response_format["type"] == "json_schema":
            raise RuntimeError("response_format json_schema is not supported")
        return _Resp(json.dumps({"items": [{"question_type": "其他"}]}))


class _Client:
    def __init__(self):
        self.chat = type("C", (), {"completions": _Completions()})()


def test_structure_clip_falls_back_to_json_object():
    client = _Client()
    items = structure_clip(client, "deepseek-chat", "t", [], 30.0)
    assert items[0]["question_type"] == "其他"
    assert client.chat.completions.formats == ["json_schema", "json_object"]
