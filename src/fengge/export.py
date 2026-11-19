from __future__ import annotations

import csv
import json
import random
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .filter import filter_item, sanitize_items
from .models import ClipMeta

AUTHOR = "卡秃噜皮君"


def trim_segments(
    segments: list[dict[str, Any]], start: float, end: float
) -> list[dict[str, Any]]:
    picked = [
        s for s in segments if float(s["end"]) > start and float(s["start"]) < end
    ]
    if not picked:
        return []
    out = [dict(s) for s in picked]
    out[0]["start"] = max(float(out[0]["start"]), start)
    out[-1]["end"] = min(float(out[-1]["end"]), end)
    return out


def to_record(
    bvid: str,
    meta: ClipMeta,
    item: dict[str, Any],
    segments: list[dict[str, Any]],
    index: int,
) -> dict[str, Any]:
    trim = item.get("trim") or {}
    start = float(trim.get("start") or 0.0)
    end = float(trim.get("end") or 0.0)
    picked = trim_segments(segments, start, end)
    transcript = "".join((s.get("text") or "").strip() for s in picked)
    try:
        pubdate = datetime.fromtimestamp(meta.pubdate).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        pubdate = ""
    return {
        "id": f"{bvid}_p{index}",
        "source_bvid": bvid,
        "source_aid": meta.aid,
        "source_url": f"https://www.bilibili.com/video/{bvid}",
        "author": "卡秃噜皮君",        "title": meta.title,
        "duration": meta.duration,
        "pubdate": pubdate,
        "clip_path": f"data/clips/{bvid}.mp4",
        "cover_path": f"data/clips/{bvid}.jpg",
        "trim": {"start": start, "end": end},
        "transcript": transcript,
        "segments": picked,
        "question_verbatim": item.get("question_verbatim", ""),
        "abstract_question": item.get("abstract_question", ""),
        "question_type": item.get("question_type", "其他"),
        "answer_summary": item.get("answer_summary", ""),
        "key_claims": item.get("key_claims", []),
        "quote": item.get("quote", ""),
        "tags": item.get("tags", []),
        "emotion": item.get("emotion", ""),
        "quality": int(item.get("quality") or 0),
    }


def records_from_rows(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """把 accepted / rejected 的库行展开成导出的问答记录。

    导出与检索验证共用这一个入口，保证两边看到的是同一份语料、同一套编号。
    """
    records: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for row in rows:
        bvid = row["bvid"]
        if row["state"] == "rejected":
            rejected.append({"id": bvid, "reject_reason": row["reject_reason"] or "unknown"})
            continue

        try:
            structured = json.loads(Path(row["structured_path"]).read_text(encoding="utf-8"))
            asr_payload = json.loads(Path(row["asr_path"]).read_text(encoding="utf-8"))
        except (OSError, TypeError, json.JSONDecodeError) as exc:
            rejected.append({"id": bvid, "reject_reason": "no_clip", "error": str(exc)})
            continue

        meta = ClipMeta(
            bvid=bvid,
            aid=row["aid"] or 0,
            title=row["title"] or "",
            duration=row["duration"] or 0.0,
            pubdate=row["pubdate"] or 0,
            cover_url=row["cover_url"] or "",
        )
        duration = float(asr_payload.get("duration") or row["duration"] or 0.0)
        segments = asr_payload.get("segments") or []
        index = 0
        for item in sanitize_items(structured.get("items") or [], duration):
            reason = filter_item(item, duration)
            if reason:
                rejected.append(
                    {"id": bvid, "reject_reason": reason, "reason": reason}
                )
                continue
            index += 1
            records.append(to_record(bvid, meta, item, segments, index))
    return records, rejected


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def _markdown_table(title: str, pairs: list[tuple[str, Any]]) -> str:
    lines = [f"### {title}", "", "| 项 | 数量 |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in pairs]
    lines.append("")
    return "\n".join(lines)


def build_report(
    records: list[dict[str, Any]],
    rejected: list[dict[str, Any]],
    counts: dict[str, int],
    disk_root: Path | None = None,
) -> str:
    parts = ["# 数据集报告", ""]
    parts.append(_markdown_table("状态分布", sorted(counts.items())))
    parts.append(_markdown_table(
        "拒绝原因分布",
        sorted(Counter(r.get("reject_reason") or "unknown" for r in rejected).items(),
               key=lambda kv: (-kv[1], kv[0])),
    ))
    parts.append(_markdown_table(
        "话题分布",
        sorted(Counter(r.get("question_type") or "其他" for r in records).items(),
               key=lambda kv: (-kv[1], kv[0])),
    ))

    durations = sorted(float(r.get("duration") or 0.0) for r in records)
    median = durations[len(durations) // 2] if durations else 0.0
    parts.append("### 概览")
    parts.append("")
    parts.append(f"- 可用问答：{len(records)}")
    parts.append(f"- 被拒条目：{len(rejected)}")
    parts.append(f"- 时长中位数：{median:.1f} 秒")
    if disk_root is not None:
        usage = shutil.disk_usage(str(disk_root))
        parts.append(
            f"- 磁盘剩余：{usage.free / (1024 ** 3):.1f} GB / "
            f"共 {usage.total / (1024 ** 3):.1f} GB"
        )
    parts.append("")
    return "\n".join(parts)


REVIEW_COLUMNS = (
    "id",
    "title",
    "abstract_question",
    "trim_start",
    "trim_end",
    "source_url",
    "verdict",
)


def write_review_sample(
    records: list[dict[str, Any]], path: Path, n: int = 50, seed: int = 42
) -> int:
    if not records:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        return 0
    sample = random.Random(seed).sample(records, min(n, len(records)))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for row in sample:
            trim = row.get("trim") or {}
            writer.writerow(
                {
                    "id": row.get("id", ""),
                    "title": row.get("title", ""),
                    "abstract_question": row.get("abstract_question", ""),
                    "trim_start": trim.get("start", ""),
                    "trim_end": trim.get("end", ""),
                    "source_url": row.get("source_url", ""),
                    "verdict": "",
                }
            )
    return len(sample)
