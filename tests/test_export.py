from __future__ import annotations

import json

from fengge.export import (
    build_report,
    to_record,
    trim_segments,
    write_jsonl,
    write_review_sample,
)
from fengge.models import ClipMeta

SEGS = [
    {"start": 0.0, "end": 2.0, "text": "开场"},
    {"start": 2.0, "end": 5.0, "text": "峰哥我该考研吗"},
    {"start": 5.0, "end": 9.0, "text": "你先看专业"},
    {"start": 9.0, "end": 12.0, "text": "结尾"},
]


def meta():
    return ClipMeta("BV1", 1, "标题", 30.0, 1793862075, "u")


def item(quality=4):
    return {
        "is_qa": True,
        "question_verbatim": "峰哥我该考研吗",
        "abstract_question": "要不要继续读研",
        "question_type": "学历与教育",
        "answer_summary": "看专业",
        "key_claims": ["看专业"],
        "quote": "先看专业",
        "tags": ["考研"],
        "emotion": "劝退",
        "quality": quality,
        "trim": {"start": 2.0, "end": 9.0},
    }


def test_trim_segments_keeps_overlap_only():
    out = trim_segments(SEGS, 2.0, 9.0)
    assert [s["text"] for s in out] == ["峰哥我该考研吗", "你先看专业"]


def test_to_record_id_has_page_suffix():
    r = to_record("BV1", meta(), item(), SEGS, 1)
    assert r["id"] == "BV1_p1"
    assert r["source_bvid"] == "BV1"
    assert r["source_url"].endswith("BV1")
    assert r["clip_path"].endswith("BV1.mp4")
    assert r["transcript"] == "峰哥我该考研吗你先看专业"


def test_to_record_page_two():
    r = to_record("BV1", meta(), item(), SEGS, 2)
    assert r["id"] == "BV1_p2"


def test_to_record_keeps_source_aid_for_comments():
    assert to_record("BV1", meta(), item(), SEGS, 1)["source_aid"] == 1


def test_write_jsonl_is_utf8_and_counts(tmp_path):
    p = tmp_path / "clips.jsonl"
    assert write_jsonl(p, [{"a": "峰哥"}]) == 1
    raw = p.read_text(encoding="utf-8")
    assert "峰哥" in raw and "\\u5cf0" not in raw
    assert json.loads(raw.strip())["a"] == "峰哥"


def test_report_mentions_counts_and_reasons():
    recs = [{"id": "a"}, {"id": "b"}]
    rejected = [
        {"reject_reason": "no_qa"},
        {"reject_reason": "no_qa"},
        {"reject_reason": "duplicate"},
    ]
    text = build_report(recs, rejected, {"discovered": 3, "accepted": 1})
    assert "2" in text and "no_qa" in text and "discovered" in text


def test_write_review_sample_is_deterministic_and_capped(tmp_path):
    recs = [
        {
            "id": f"BV{i}_p1",
            "title": "t",
            "abstract_question": "q",
            "trim": {"start": 0.0, "end": 1.0},
            "source_url": "u",
        }
        for i in range(100)
    ]
    p = tmp_path / "review_sample.csv"
    assert write_review_sample(recs, p, n=10) == 10
    first = p.read_text(encoding="utf-8")
    assert len(first.strip().splitlines()) == 11
    write_review_sample(recs, p, n=10)
    assert p.read_text(encoding="utf-8") == first
