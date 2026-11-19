from __future__ import annotations

import math
from typing import Any, Callable, Iterable

from .models import QUESTION_TYPES

REJECT_REASONS: tuple[str, ...] = (
    "too_short_transcript",
    "too_short_video",
    "low_lang_prob",
    "no_qa",
    "not_qa",
    "low_quality",
    "no_abstract",
    "long_low_quality",
    "duplicate",
    "no_clip",
)

MIN_TRANSCRIPT_CHARS = 30
MIN_VIDEO_SECONDS = 15.0
MIN_LANG_PROB = 0.6
LONG_VIDEO_SECONDS = 300.0


def filter_video(text: str, duration: float, lang_prob: float) -> str | None:
    if len((text or "").strip()) < MIN_TRANSCRIPT_CHARS:
        return "too_short_transcript"
    if duration < MIN_VIDEO_SECONDS:
        return "too_short_video"
    if lang_prob < MIN_LANG_PROB:
        return "low_lang_prob"
    return None


def filter_item(item: dict[str, Any], duration: float) -> str | None:
    if not item.get("is_qa"):
        return "not_qa"
    if int(item.get("quality") or 0) < 3:
        return "low_quality"
    abstract = (item.get("abstract_question") or "").strip()
    verbatim = (item.get("question_verbatim") or "").strip()
    if not abstract or abstract == verbatim:
        return "no_abstract"
    if duration > LONG_VIDEO_SECONDS and int(item.get("quality") or 0) < 4:
        return "long_low_quality"
    return None


def _coerce_trim(trim: Any) -> tuple[float, float] | None:
    if isinstance(trim, dict):
        raw = (trim.get("start"), trim.get("end"))
    elif isinstance(trim, (list, tuple)) and len(trim) == 2:
        raw = (trim[0], trim[1])
    else:
        return None
    try:
        return float(raw[0]), float(raw[1])
    except (TypeError, ValueError):
        return None


def sanitize_items(
    items: list[dict[str, Any]], duration: float
) -> list[dict[str, Any]]:
    """把 LLM 给的 trim 夹到视频范围内，丢掉非法区间，并消除重叠。

    同时兜住 json_object 模式下模型不守 schema 的两处：trim 返回成数组、
    question_type 自创词表外的值。
    """
    prepared: list[tuple[dict[str, Any], float, float]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        parsed = _coerce_trim(item.get("trim"))
        if parsed is None:
            continue
        start = max(0.0, min(parsed[0], duration))
        end = max(0.0, min(parsed[1], duration))
        if end <= start:
            continue
        question_type = item.get("question_type")
        if question_type not in QUESTION_TYPES:
            question_type = "其他"
        is_qa = item.get("is_qa")
        if is_qa is None:
            is_qa = True  # json_object 模式下模型常省略该字段；既然产出了 item 就视为问答
        prepared.append(
            ({**item, "question_type": question_type, "is_qa": bool(is_qa)}, start, end)
        )
    prepared.sort(key=lambda row: (row[1], row[2]))

    out: list[dict[str, Any]] = []
    previous_end = 0.0
    for item, start, end in prepared:
        start = max(start, previous_end)
        if end <= start:
            continue
        out.append({**item, "trim": {"start": start, "end": end}})
        previous_end = end
    return out


def cosine(a: Iterable[float], b: Iterable[float]) -> float:
    va, vb = list(a), list(b)
    if len(va) != len(vb):
        raise ValueError("vector length mismatch")
    dot = sum(x * y for x, y in zip(va, vb))
    na = math.sqrt(sum(x * x for x in va))
    nb = math.sqrt(sum(y * y for y in vb))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def dedupe(
    records: list[dict[str, Any]],
    embed: Callable[[list[str]], list[list[float]]],
    threshold: float = 0.92,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not records:
        return [], []
    ordered = sorted(
        records, key=lambda r: (-int(r.get("quality") or 0), r.get("id") or "")
    )
    texts = [(r.get("abstract_question") or "").strip() for r in ordered]
    vectors = embed(texts)

    kept: list[dict[str, Any]] = []
    kept_vectors: list[list[float]] = []
    dropped: list[dict[str, Any]] = []
    for record, vector in zip(ordered, vectors):
        duplicate_of = None
        for prev, prev_vec in zip(kept, kept_vectors):
            if cosine(vector, prev_vec) > threshold:
                duplicate_of = prev["id"]
                break
        if duplicate_of is None:
            kept.append(record)
            kept_vectors.append(vector)
        else:
            dropped.append({**record, "reject_reason": "duplicate", "duplicate_of": duplicate_of})
    return kept, dropped
