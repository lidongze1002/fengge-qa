from __future__ import annotations

from dataclasses import dataclass

QUESTION_TYPES: tuple[str, ...] = (
    "职业发展",
    "搞钱赚钱",
    "情感两性",
    "婚姻家庭",
    "人际关系",
    "城市与去留",
    "学历与教育",
    "自我认同",
    "身心健康",
    "社会议题",
    "生活方式",
    "其他",
)


@dataclass(frozen=True)
class ClipMeta:
    bvid: str
    aid: int
    title: str
    duration: float
    pubdate: int
    cover_url: str
