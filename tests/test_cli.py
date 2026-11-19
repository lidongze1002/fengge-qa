from __future__ import annotations

import json

import pytest

from fengge.cli import produce_dataset
from fengge.db import Database
from fengge.models import ClipMeta

ASR = {
    "segments": [
        {"start": 0.0, "end": 3.0, "text": "峰哥我该考研吗"},
        {"start": 3.0, "end": 9.0, "text": "你先看专业再决定"},
    ],
    "text": "峰哥我该考研吗你先看专业再决定",
    "duration": 30.0,
    "lang_prob": 0.99,
}

ITEM = {
    "is_qa": True,
    "question_verbatim": "峰哥我该考研吗",
    "abstract_question": "要不要继续读研",
    "question_type": "学历与教育",
    "answer_summary": "看专业",
    "key_claims": [],
    "quote": "",
    "tags": [],
    "emotion": "劝退",
    "quality": 4,
    "trim": {"start": 0.0, "end": 9.0},
}


@pytest.fixture
def dataset_env(tmp_path):
    from fengge.config import load_settings

    s = load_settings(root=tmp_path, env={})
    db = Database(s.db_path)
    db.init_schema()
    db.upsert_clip(ClipMeta("BV1", 1, "标题", 30.0, 1793862075, ""))
    s.asr_dir.mkdir(parents=True, exist_ok=True)
    (s.asr_dir / "BV1.json").write_text(json.dumps(ASR, ensure_ascii=False), encoding="utf-8")
    s.structured_dir.mkdir(parents=True, exist_ok=True)
    (s.structured_dir / "BV1.json").write_text(
        json.dumps({"items": [ITEM]}, ensure_ascii=False), encoding="utf-8"
    )
    db.set_state(
        "BV1",
        "accepted",
        asr_path=str(s.asr_dir / "BV1.json"),
        structured_path=str(s.structured_dir / "BV1.json"),
        clip_path="data/clips/BV1.mp4",
    )
    return s, db


def test_produce_dataset_writes_jsonl_report_and_review(dataset_env):
    s, db = dataset_env
    stats = produce_dataset(s, db, embed=lambda texts: [[1.0, 0.0] for _ in texts])
    assert stats["records"] == 1
    lines = (s.dataset_dir / "clips.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["id"] == "BV1_p1"
    assert (s.dataset_dir / "report.md").exists()
    assert (s.dataset_dir / "review_sample.csv").exists()


def test_produce_dataset_records_rejections(dataset_env):
    s, db = dataset_env
    db.upsert_clip(ClipMeta("BV2", 2, "t", 10.0, 1, ""))
    db.set_state("BV2", "rejected", reject_reason="too_short_video")
    stats = produce_dataset(s, db, embed=lambda texts: [[1.0, 0.0] for _ in texts])
    assert stats["rejected"] == 1
    rejected = (s.dataset_dir / "rejected.jsonl").read_text(encoding="utf-8")
    assert "too_short_video" in rejected


def test_parser_accepts_limit_after_subcommand():
    from fengge.cli import _build_parser

    args = _build_parser().parse_args(["run", "--limit", "300"])
    assert args.command == "run"
    assert args.limit == 300
    assert _build_parser().parse_args(["discover", "--force"]).force is True


def test_produce_dataset_dedupes_near_duplicates(dataset_env):
    s, db = dataset_env
    db.upsert_clip(ClipMeta("BV2", 2, "标题2", 30.0, 1793862076, ""))
    (s.asr_dir / "BV2.json").write_text(json.dumps(ASR, ensure_ascii=False), encoding="utf-8")
    (s.structured_dir / "BV2.json").write_text(
        json.dumps({"items": [ITEM]}, ensure_ascii=False), encoding="utf-8"
    )
    db.set_state(
        "BV2",
        "accepted",
        asr_path=str(s.asr_dir / "BV2.json"),
        structured_path=str(s.structured_dir / "BV2.json"),
        clip_path="data/clips/BV2.mp4",
    )
    vectors = {"要不要继续读研": [1.0, 0.0]}
    stats = produce_dataset(s, db, embed=lambda texts: [vectors[t] for t in texts])
    assert stats["records"] == 1
    assert stats["rejected"] == 1
    rejected = (s.dataset_dir / "rejected.jsonl").read_text(encoding="utf-8")
    assert "duplicate" in rejected
