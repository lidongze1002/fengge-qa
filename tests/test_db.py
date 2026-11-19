from __future__ import annotations

import pytest

from fengge.db import Database
from fengge.models import ClipMeta


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "state.db")
    d.init_schema()
    return d


def meta(bvid="BV1", title="t"):
    return ClipMeta(bvid=bvid, aid=1, title=title, duration=30.0, pubdate=100, cover_url="u")


def test_upsert_is_idempotent_and_keeps_state(db):
    assert db.upsert_clip(meta()) is True
    db.set_state("BV1", "downloaded")
    assert db.upsert_clip(meta(title="新标题")) is False
    row = db.get("BV1")
    assert row["state"] == "downloaded"
    assert row["title"] == "新标题"
    assert row["attempts"] == 0


def test_fail_increments_and_caps(db):
    db.upsert_clip(meta())
    db.set_state("BV1", "downloaded")
    assert db.fail("BV1", "boom") == "downloaded"
    assert db.get("BV1")["attempts"] == 1
    db.fail("BV1", "boom")
    assert db.fail("BV1", "boom") == "failed"
    assert db.get("BV1")["state"] == "failed"


def test_next_batch_only_returns_requested_state_ordered_by_pubdate_desc(db):
    for i, bv in enumerate(["BV1", "BV2", "BV3"]):
        db.upsert_clip(ClipMeta(bv, i, "t", 30.0, 100 + i, "u"))
    db.set_state("BV2", "downloaded")
    db.set_state("BV3", "downloaded")
    rows = db.next_batch("downloaded", 10)
    assert [r["bvid"] for r in rows] == ["BV3", "BV2"]


def test_set_state_writes_fields_and_timestamp(db):
    db.upsert_clip(meta())
    db.set_state("BV1", "downloaded", raw_path="data/raw/BV1.mp4", cover_path="c.jpg")
    row = db.get("BV1")
    assert row["raw_path"] == "data/raw/BV1.mp4"
    assert row["cover_path"] == "c.jpg"
    assert row["updated_at"] is not None


def test_counts_groups_by_state(db):
    for i, bv in enumerate(["BV1", "BV2"]):
        db.upsert_clip(ClipMeta(bv, i, "t", 30.0, 100, "u"))
    db.set_state("BV2", "downloaded")
    assert db.counts() == {"discovered": 1, "downloaded": 1}


def test_next_batch_accepts_multiple_states(db):
    for i, bv in enumerate(["BV1", "BV2", "BV3"]):
        db.upsert_clip(ClipMeta(bv, i, "t", 30.0, 100 + i, "u"))
    db.set_state("BV1", "archived")
    db.set_state("BV2", "asr_done")
    db.set_state("BV3", "accepted")
    rows = db.next_batch(["archived", "asr_done"], 10)
    assert [r["bvid"] for r in rows] == ["BV2", "BV1"]


def test_next_batch_skip_clipped_frees_the_limit_window(db):
    # 已归档的 rejected 会留在原状态，不能被反复选中占满窗口
    for i, bv in enumerate(["BV1", "BV2", "BV3"]):
        db.upsert_clip(ClipMeta(bv, i, "t", 30.0, 200 + i, "u"))
    for bv in ("BV1", "BV2"):
        db.set_state(bv, "rejected", clip_path=f"clips/{bv}.mp4", raw_path="raw.mp4")
    db.set_state("BV3", "asr_done", raw_path="raw.mp4")
    assert [r["bvid"] for r in db.next_batch(["asr_done", "rejected"], 10)] == [
        "BV3",
        "BV2",
        "BV1",
    ]
    assert [r["bvid"] for r in db.next_batch(
        ["asr_done", "rejected"], 10, skip_clipped=True
    )] == ["BV3"]


def test_upsert_fills_aid_but_never_blanks_it(db):
    db.upsert_clip(ClipMeta("BV1", 0, "t", 30.0, 100, "u"))
    db.upsert_clip(ClipMeta("BV1", 777, "t", 30.0, 100, "u"))
    assert db.get("BV1")["aid"] == 777
    db.upsert_clip(ClipMeta("BV1", 0, "t", 30.0, 100, "u"))
    assert db.get("BV1")["aid"] == 777


def test_next_batch_honours_max_duration(db):
    db.upsert_clip(ClipMeta("BV_short", 1, "t", 60.0, 100, "u"))
    db.upsert_clip(ClipMeta("BV_long", 2, "t", 900.0, 101, "u"))
    rows = db.next_batch("discovered", 10, max_duration=180.0)
    assert [r["bvid"] for r in rows] == ["BV_short"]
    assert len(db.next_batch("discovered", 10, max_duration=None)) == 2


def test_reopen_keeps_data(db, tmp_path):
    db.upsert_clip(meta())
    db.set_state("BV1", "accepted")
    again = Database(tmp_path / "state.db")
    again.init_schema()
    assert again.get("BV1")["state"] == "accepted"
