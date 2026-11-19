from __future__ import annotations

import json

import pytest

from fengge.db import Database
from fengge.models import ClipMeta
from fengge.pipeline import Pipeline, RateLimited

ASR_TEXT = "峰哥我想问一下我这个情况到底该不该去考研你帮我看看行不行啊你说说"
ASR_BODY = {
    "segments": [{"start": 0.0, "end": 9.0, "text": ASR_TEXT}],
    "text": ASR_TEXT,
    "duration": 30.0,
    "lang_prob": 0.99,
}


class FakeTranscriber:
    device = "cpu"

    def transcribe(self, audio):
        return ASR_BODY


class FakeLLM:
    def structure(self, title, segments, duration):
        return [
            {
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
                "trim": {"start": 0.0, "end": 3.0},
            }
        ]


@pytest.fixture
def pipe(tmp_path):
    from fengge.config import load_settings

    s = load_settings(root=tmp_path, env={})
    db = Database(s.db_path)
    db.init_schema()
    db.upsert_clip(ClipMeta("BV1", 1, "t", 30.0, 100, ""))
    return Pipeline(s, db=db, transcriber=FakeTranscriber(), llm=FakeLLM()), db


def write_asr(settings, bvid="BV1"):
    settings.asr_dir.mkdir(parents=True, exist_ok=True)
    (settings.asr_dir / f"{bvid}.json").write_text(
        json.dumps(ASR_BODY, ensure_ascii=False), encoding="utf-8"
    )


def test_structure_stage_moves_state_and_writes_file(pipe):
    p, db = pipe
    write_asr(p.settings)
    db.set_state(
        "BV1",
        "archived",
        asr_chars=100,
        asr_path=str(p.settings.asr_dir / "BV1.json"),
        clip_path="data/clips/BV1.mp4",
    )
    p.run("structure", limit=10)
    assert db.get("BV1")["state"] in ("accepted", "rejected")
    assert (p.settings.structured_dir / "BV1.json").exists()


def test_structure_stage_skips_already_done(pipe):
    p, db = pipe
    write_asr(p.settings)
    db.set_state("BV1", "accepted")
    before = db.get("BV1")["updated_at"]
    p.run("structure", limit=10)
    assert db.get("BV1")["updated_at"] == before


def test_failure_increments_attempts(pipe):
    p, db = pipe
    write_asr(p.settings)
    db.set_state(
        "BV1",
        "archived",
        asr_path=str(p.settings.asr_dir / "BV1.json"),
        clip_path="data/clips/BV1.mp4",
    )

    def boom(*a, **kw):
        raise RuntimeError("llm down")

    p.llm.structure = boom
    p.run("structure", limit=1)
    assert db.get("BV1")["attempts"] == 1
    assert db.get("BV1")["state"] == "archived"


def test_rate_limit_stops_batch(pipe):
    p, db = pipe
    for i, bv in enumerate(["BV2", "BV3"]):
        db.upsert_clip(ClipMeta(bv, i + 2, "t", 30.0, 100 + i, ""))
    from fengge.download import DownloadError

    p._download_one = lambda meta: (_ for _ in ()).throw(
        DownloadError("403", status="forbidden")
    )
    with pytest.raises(RateLimited):
        p.run("download", limit=5)
    for bv in ["BV1", "BV2", "BV3"]:
        assert db.get(bv)["state"] == "discovered"
        assert db.get(bv)["attempts"] == 0
        assert db.get(bv)["last_error"]


def test_archive_stage_archives_rejected_rows_but_keeps_state(pipe):
    p, db = pipe
    raw = p.settings.raw_dir / "BV1.mp4"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(b"video")
    db.set_state(
        "BV1", "rejected", raw_path=str(raw), reject_reason="too_short_transcript"
    )
    p._archive_one = lambda row: True
    p.run("archive", limit=1)
    row = db.get("BV1")
    assert row["state"] == "rejected"
    assert row["reject_reason"] == "too_short_transcript"
    assert row["clip_path"].endswith("BV1.mp4")
    assert not raw.exists()


def test_structure_stage_aborts_when_llm_cannot_be_built(pipe, monkeypatch):
    p, db = pipe
    write_asr(p.settings)
    db.set_state(
        "BV1",
        "archived",
        asr_path=str(p.settings.asr_dir / "BV1.json"),
        clip_path="data/clips/BV1.mp4",
    )

    def boom(_self):
        raise RuntimeError("missing OPEN_API_KEY")

    monkeypatch.setattr(type(p), "llm", property(boom))
    with pytest.raises(RuntimeError):
        p.run("structure", limit=1)
    row = db.get("BV1")
    assert row["state"] == "archived"
    assert row["attempts"] == 0


def test_asr_stage_writes_transcript_and_advances(pipe):
    p, db = pipe
    raw = p.settings.raw_dir / "BV1.mp4"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(b"video")
    db.set_state("BV1", "downloaded", raw_path=str(raw))
    p._extract_audio = lambda src, dst: dst.write_bytes(b"audio")
    p.run("asr", limit=1)
    row = db.get("BV1")
    assert row["state"] == "asr_done"
    assert (p.settings.asr_dir / "BV1.json").exists()
    assert row["asr_chars"] > 0


def test_asr_stage_rejects_short_transcript(pipe):
    p, db = pipe
    raw = p.settings.raw_dir / "BV1.mp4"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(b"video")
    db.set_state("BV1", "downloaded", raw_path=str(raw))
    p._extract_audio = lambda src, dst: dst.write_bytes(b"audio")
    p.transcriber.transcribe = lambda audio: {
        "segments": [{"start": 0.0, "end": 1.0, "text": "很短"}],
        "text": "很短",
        "duration": 30.0,
        "lang_prob": 0.99,
    }
    p.run("asr", limit=1)
    assert db.get("BV1")["state"] == "rejected"
    assert db.get("BV1")["reject_reason"] == "too_short_transcript"


def test_archive_stage_sets_clip_and_drops_raw(pipe):
    p, db = pipe
    raw = p.settings.raw_dir / "BV1.mp4"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(b"video")
    db.set_state("BV1", "asr_done", raw_path=str(raw), asr_path="data/asr/BV1.json")
    p._archive_one = lambda row: True
    p.run("archive", limit=1)
    row = db.get("BV1")
    assert row["state"] == "archived"
    assert row["clip_path"].endswith("BV1.mp4")
    assert not raw.exists()
