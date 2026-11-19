from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .models import ClipMeta

STATES: tuple[str, ...] = (
    "discovered",
    "downloaded",
    "asr_done",
    "archived",
    "accepted",
    "rejected",
    "failed",
)

_COLUMNS: tuple[str, ...] = (
    "bvid",
    "aid",
    "title",
    "duration",
    "pubdate",
    "cover_url",
    "state",
    "attempts",
    "last_error",
    "raw_path",
    "audio_path",
    "clip_path",
    "cover_path",
    "asr_path",
    "structured_path",
    "asr_chars",
    "asr_lang_prob",
    "quality",
    "reject_reason",
    "created_at",
    "updated_at",
    "archived_at",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS clips (
    bvid TEXT PRIMARY KEY,
    aid INTEGER,
    title TEXT,
    duration REAL,
    pubdate INTEGER,
    cover_url TEXT,
    state TEXT NOT NULL DEFAULT 'discovered',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    raw_path TEXT,
    audio_path TEXT,
    clip_path TEXT,
    cover_path TEXT,
    asr_path TEXT,
    structured_path TEXT,
    asr_chars INTEGER,
    asr_lang_prob REAL,
    quality INTEGER,
    reject_reason TEXT,
    created_at TEXT,
    updated_at TEXT,
    archived_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_clips_state ON clips(state, pubdate DESC);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self._conn.close()

    def init_schema(self) -> None:
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def upsert_clip(self, meta: ClipMeta) -> bool:
        exists = self._conn.execute(
            "SELECT 1 FROM clips WHERE bvid = ?", (meta.bvid,)
        ).fetchone()
        if exists:
            self._conn.execute(
                "UPDATE clips SET title = ?, duration = ?, pubdate = ?, cover_url = ?,"
                " aid = COALESCE(NULLIF(?, 0), aid)"
                " WHERE bvid = ?",
                (meta.title, meta.duration, meta.pubdate, meta.cover_url, meta.aid, meta.bvid),
            )
            self._conn.commit()
            return False
        now = _now()
        self._conn.execute(
            "INSERT INTO clips (bvid, aid, title, duration, pubdate, cover_url,"
            " state, attempts, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 'discovered', 0, ?, ?)",
            (
                meta.bvid,
                meta.aid,
                meta.title,
                meta.duration,
                meta.pubdate,
                meta.cover_url,
                now,
                now,
            ),
        )
        self._conn.commit()
        return True

    def get(self, bvid: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM clips WHERE bvid = ?", (bvid,)).fetchone()
        return dict(row) if row else None

    def set_state(self, bvid: str, state: str, **fields: Any) -> None:
        if state not in STATES:
            raise ValueError(f"unknown state: {state}")
        unknown = set(fields) - set(_COLUMNS)
        if unknown:
            raise ValueError(f"unknown columns: {sorted(unknown)}")
        updates = {"state": state, "updated_at": _now(), **fields}
        clause = ", ".join(f"{name} = ?" for name in updates)
        self._conn.execute(
            f"UPDATE clips SET {clause} WHERE bvid = ?",
            (*updates.values(), bvid),
        )
        self._conn.commit()

    def fail(self, bvid: str, error: str, max_attempts: int = 3) -> str:
        row = self.get(bvid)
        if row is None:
            raise KeyError(bvid)
        attempts = (row["attempts"] or 0) + 1
        state = "failed" if attempts >= max_attempts else row["state"]
        self._conn.execute(
            "UPDATE clips SET attempts = ?, last_error = ?, state = ?, updated_at = ?"
            " WHERE bvid = ?",
            (attempts, error, state, _now(), bvid),
        )
        self._conn.commit()
        return state

    def next_batch(
        self,
        state: str | Sequence[str],
        limit: int,
        max_duration: float | None = None,
        skip_clipped: bool = False,
    ) -> list[dict[str, Any]]:
        states = (state,) if isinstance(state, str) else tuple(state)
        placeholders = ", ".join("?" for _ in states)
        sql = f"SELECT * FROM clips WHERE state IN ({placeholders})"
        params: tuple[Any, ...] = (*states,)
        if max_duration is not None:
            sql += " AND duration <= ?"
            params += (max_duration,)
        if skip_clipped:
            # archive 阶段会把「已归档的 rejected」留在原状态，靠 clip_path 标记做过。
            # 不在这里过滤掉，它们会一直占满 LIMIT 窗口，把后面真正待处理的
            # asr_done 挤出去（实测每轮只处理 7~24 条，队列越积越长）。
            sql += " AND (clip_path IS NULL OR clip_path = '')"
        sql += " ORDER BY pubdate DESC, bvid LIMIT ?"
        params += (limit,)
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def counts(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT state, COUNT(*) AS n FROM clips GROUP BY state"
        ).fetchall()
        return {r["state"]: r["n"] for r in rows}

    def set_meta(self, bvid: str, **fields: Any) -> None:
        """更新元信息列但不触碰状态机（供 pipeline 回写路径等使用）。"""
        unknown = set(fields) - set(_COLUMNS)
        if unknown:
            raise ValueError(f"unknown columns: {sorted(unknown)}")
        if not fields:
            return
        fields = {**fields, "updated_at": _now()}
        clause = ", ".join(f"{name} = ?" for name in fields)
        self._conn.execute(
            f"UPDATE clips SET {clause} WHERE bvid = ?",
            (*fields.values(), bvid),
        )
        self._conn.commit()
