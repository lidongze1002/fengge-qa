from __future__ import annotations

import math

import pytest

from fengge.filter import cosine, dedupe, filter_item, filter_video, sanitize_items


def good_item(**kw):
    base = {
        "is_qa": True,
        "question_verbatim": "峰哥我该考研吗",
        "abstract_question": "要不要继续读研",
        "question_type": "学历与教育",
        "answer_summary": "x",
        "quality": 4,
    }
    base.update(kw)
    return base


LONG_TEXT = "这是一段足够长的转写文本内容用来测试过滤规则是否按顺序生效再多写几个字凑长度"


def test_filter_video_rules():
    assert len(LONG_TEXT) >= 30
    assert filter_video("太短", 30.0, 0.9) == "too_short_transcript"
    assert filter_video(LONG_TEXT, 10.0, 0.9) == "too_short_video"
    assert filter_video(LONG_TEXT, 30.0, 0.3) == "low_lang_prob"
    assert filter_video(LONG_TEXT, 30.0, 0.9) is None


def test_filter_item_rejects_non_qa():
    assert filter_item(good_item(is_qa=False), 30.0) == "not_qa"


def test_filter_item_rejects_low_quality():
    assert filter_item(good_item(quality=2), 30.0) == "low_quality"


def test_filter_item_rejects_same_as_verbatim():
    item = good_item(abstract_question="峰哥我该考研吗")
    assert filter_item(item, 30.0) == "no_abstract"


def test_filter_item_rejects_long_video_below_4():
    assert filter_item(good_item(quality=3), 400.0) == "long_low_quality"
    assert filter_item(good_item(quality=4), 400.0) is None


def test_filter_item_passes():
    assert filter_item(good_item(), 30.0) is None


def test_cosine_basic():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)


def test_dedupe_keeps_higher_quality():
    recs = [
        {"id": "a", "abstract_question": "要不要读研", "quality": 3},
        {"id": "b", "abstract_question": "该不该考研", "quality": 5},
        {"id": "c", "abstract_question": "怎么找对象", "quality": 4},
    ]
    vecs = {
        "要不要读研": [1.0, 0.0],
        "该不该考研": [0.99, 0.14],
        "怎么找对象": [-0.9, 0.1],
    }
    kept, dropped = dedupe(recs, embed=lambda texts: [vecs[t] for t in texts])
    assert [r["id"] for r in kept] == ["b", "c"]
    assert dropped[0]["id"] == "a"
    assert dropped[0]["reject_reason"] == "duplicate"


def _item_with_trim(start, end, quality=4):
    item = good_item(quality=quality)
    item["trim"] = {"start": start, "end": end}
    return item


def test_sanitize_items_clamps_to_duration_and_orders():
    items = [
        _item_with_trim(0.0, 10.0),
        _item_with_trim(8.0, 18.0),
        _item_with_trim(25.0, 40.0),
    ]
    out = sanitize_items(items, 30.0)
    assert [o["trim"] for o in out] == [
        {"start": 0.0, "end": 10.0},
        {"start": 10.0, "end": 18.0},
        {"start": 25.0, "end": 30.0},
    ]


def test_sanitize_items_drops_inverted_and_empty():
    items = [
        _item_with_trim(20.0, 19.0),
        _item_with_trim(5.0, 5.0),
        _item_with_trim(1.0, 4.0),
    ]
    out = sanitize_items(items, 30.0)
    assert len(out) == 1
    assert out[0]["trim"] == {"start": 1.0, "end": 4.0}


def test_sanitize_items_accepts_trim_as_pair():
    item = good_item()
    item["trim"] = [1.0, 4.0]
    out = sanitize_items([item], 30.0)
    assert out[0]["trim"] == {"start": 1.0, "end": 4.0}


def test_sanitize_items_coerces_unknown_question_type():
    item = good_item(question_type="职业选择")
    item["trim"] = {"start": 1.0, "end": 4.0}
    out = sanitize_items([item], 30.0)
    assert out[0]["question_type"] == "其他"


def test_sanitize_items_defaults_missing_is_qa_to_true():
    item = good_item()
    item.pop("is_qa")
    item["trim"] = {"start": 1.0, "end": 4.0}
    out = sanitize_items([item], 30.0)
    assert out[0]["is_qa"] is True


def test_sanitize_items_sorts_out_of_order_items():
    items = [_item_with_trim(12.0, 18.0), _item_with_trim(0.0, 6.0)]
    out = sanitize_items(items, 30.0)
    assert [o["trim"]["start"] for o in out] == [0.0, 12.0]
