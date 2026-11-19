from __future__ import annotations

import hashlib
import json
import logging
import random
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

from .config import Settings
from .models import ClipMeta

MIXIN_TAB = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
)

NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
ARC_URL = "https://api.bilibili.com/x/space/wbi/arc/search"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def wbi_mixin_key(img_key: str, sub_key: str) -> str:
    raw = img_key + sub_key
    return "".join(raw[i] for i in MIXIN_TAB)[:32]


def sign_params(params: dict[str, Any], mixin: str, ts: int) -> dict[str, Any]:
    signed: dict[str, Any] = {k: str(v) for k, v in params.items()}
    signed["wts"] = ts
    query = urlencode(sorted((k, str(v)) for k, v in signed.items()))
    signed["w_rid"] = hashlib.md5((query + mixin).encode()).hexdigest()
    return signed


def parse_api_page(payload: dict[str, Any]) -> list[ClipMeta]:
    if payload.get("code") != 0:
        raise RuntimeError(
            f"bilibili api error {payload.get('code')}: {payload.get('message')}"
        )
    metas: list[ClipMeta] = []
    # 接口偶发把 data 返回成 list（风控/降级响应），直接 .get 会抛
    # "'list' object has no attribute 'get'" 把整轮发现打挂
    data = payload.get("data")
    listing = data.get("list") if isinstance(data, dict) else None
    if not isinstance(listing, dict):
        return metas
    for item in listing.get("vlist") or []:
        if not isinstance(item, dict):
            continue
        bvid = item.get("bvid") or ""
        if not bvid:
            continue
        metas.append(
            ClipMeta(
                bvid=bvid,
                aid=int(item.get("aid") or 0),
                title=(item.get("title") or "").strip(),
                duration=float(item.get("duration") or 0.0),
                pubdate=int(item.get("created") or 0),
                cover_url=item.get("pic") or "",
            )
        )
    return metas


def build_space_cmd(mid: str, browser: str, cookie_file: Path | None = None) -> list[str]:
    url = f"https://space.bilibili.com/{mid}/video"
    cmd = [sys.executable, "-m", "yt_dlp", "--flat-playlist", "-J"]
    if cookie_file is not None and Path(cookie_file).is_file():
        cmd += ["--cookies", str(cookie_file)]
    else:
        cmd += ["--cookies-from-browser", browser]
    cmd += ["--", url]
    return cmd


def parse_space_json(payload: dict[str, Any]) -> list[ClipMeta]:
    metas: list[ClipMeta] = []
    for entry in payload.get("entries") or []:
        bvid = entry.get("id") or ""
        if not bvid:
            continue
        thumbs = entry.get("thumbnails") or []
        cover = ""
        if thumbs:
            cover = thumbs[0].get("url") or ""
        metas.append(
            ClipMeta(
                bvid=bvid,
                aid=int(entry.get("aid") or 0),
                title=(entry.get("title") or "").strip(),
                duration=float(entry.get("duration") or 0.0),
                pubdate=int(entry.get("timestamp") or 0),
                cover_url=cover,
            )
        )
    return metas


def write_manifest(metas: list[ClipMeta], path: Path) -> int:
    seen: set[str] = set()
    unique: list[ClipMeta] = []
    for meta in metas:
        if meta.bvid in seen:
            continue
        seen.add(meta.bvid)
        unique.append(meta)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for meta in unique:
            fh.write(json.dumps(asdict(meta), ensure_ascii=False) + "\n")
    return len(unique)


def read_manifest(path: Path) -> list[ClipMeta]:
    metas: list[ClipMeta] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            metas.append(ClipMeta(**json.loads(line)))
    return metas


def _load_cookie_file(session: Any, path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        _, _, _, _, _, name, value = parts[:7]
        session.cookies.set(name, value, domain=".bilibili.com")


def _new_session(settings: Settings) -> Any:
    import requests

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Referer": "https://space.bilibili.com/"})
    _load_cookie_file(session, settings.cookie_file)
    return session


def _mixin_key(session: Any) -> str:
    payload = session.get(NAV_URL, timeout=20).json()
    wbi = (payload.get("data") or {}).get("wbi_img") or {}
    img = Path(wbi.get("img_url") or "").stem
    sub = Path(wbi.get("sub_url") or "").stem
    if not img or not sub:
        raise RuntimeError(f"cannot obtain wbi keys: {payload.get('code')}")
    return wbi_mixin_key(img, sub)


def discover_via_api(
    settings: Settings,
    session: Any = None,
    sleeper: Callable[[float], None] = time.sleep,
    page_size: int = 50,
    max_pages: int | None = None,
) -> list[ClipMeta]:
    session = session or _new_session(settings)
    mixin = _mixin_key(session)
    metas: list[ClipMeta] = []
    page_number = 1
    while True:
        if max_pages is not None and page_number > max_pages:
            break
        params = {
            "mid": settings.up_mid,
            "ps": page_size,
            "pn": page_number,
            "order": "pubdate",
            "platform": "web",
        }
        signed = sign_params(params, mixin, int(time.time()))
        attempt = 0
        while True:
            resp = session.get(ARC_URL, params=signed, timeout=20)
            try:
                page = parse_api_page(resp.json())
                break
            except RuntimeError as exc:
                attempt += 1
                if attempt >= 3:
                    raise
                wait = 30 * attempt
                logging.getLogger("fengge").warning(
                    "api blocked (%s); waiting %ss", exc, wait
                )
                sleeper(wait)
                sign_ts = int(time.time())
                signed = sign_params(params, mixin, sign_ts)
        metas.extend(page)
        logging.getLogger("fengge").info(
            "page %s: +%s (total %s)", page_number, len(page), len(metas)
        )
        if len(page) < page_size:
            break
        page_number += 1
        sleeper(2.0)
    return metas


def discover(
    settings: Settings,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> list[ClipMeta]:
    """先拿 bvid 列表，再逐条补元信息。

    space 接口对部分 IP 直接 412，而 yt-dlp 的 flat 模式只给 bvid，
    所以主路径是「yt-dlp 拿 id + view 接口补标题/时长/封面」。
    """
    try:
        metas = discover_via_api(settings)
        if metas and any(m.title for m in metas):
            write_manifest(metas, settings.manifest_path)
            return metas
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("fengge").warning(
            "space api failed (%s); using yt-dlp ids + view api", exc
        )

    cmd = build_space_cmd(settings.up_mid, settings.browser, settings.cookie_file)
    result = runner(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp space crawl failed: {(result.stderr or '')[:300]}")
    metas = parse_space_json(json.loads(result.stdout))
    write_manifest(metas, settings.manifest_path)
    enrich_manifest(settings)
    return read_manifest(settings.manifest_path)


VIEW_URL = "https://api.bilibili.com/x/web-interface/view"


def fetch_video_meta(
    session: Any,
    bvid: str,
    retries: int = 3,
    sleeper: Callable[[float], None] = time.sleep,
) -> ClipMeta | None:
    for attempt in range(retries):
        try:
            payload = session.get(VIEW_URL, params={"bvid": bvid}, timeout=20).json()
        except ValueError:
            payload = {"code": -1}
        if payload.get("code") == 0:
            data = payload.get("data") or {}
            return ClipMeta(
                bvid=bvid,
                aid=int(data.get("aid") or 0),
                title=(data.get("title") or "").strip(),
                duration=float(data.get("duration") or 0.0),
                pubdate=int(data.get("pubdate") or 0),
                cover_url=data.get("pic") or "",
            )
        if payload.get("code") in (-799, -412, -509):
            sleeper(5 * (attempt + 1))
            continue
        return None
    return None


def enrich_manifest(
    settings: Settings,
    limit: int | None = None,
    session: Any = None,
    sleeper: Callable[[float], None] = time.sleep,
    progress_every: int = 50,
) -> int:
    metas = read_manifest(settings.manifest_path)
    by_bvid = {m.bvid: m for m in metas}
    todo = [m for m in metas if not m.title]
    if limit is not None:
        todo = todo[:limit]
    if not todo:
        return 0

    session = session or _new_session(settings)
    updated = 0
    for index, meta in enumerate(todo, 1):
        fresh = fetch_video_meta(session, meta.bvid, sleeper=sleeper)
        if fresh is not None:
            by_bvid[meta.bvid] = fresh
            updated += 1
        if index % progress_every == 0:
            write_manifest(list(by_bvid.values()), settings.manifest_path)
            logging.getLogger("fengge").info(
                "enriched %s/%s (updated %s)", index, len(todo), updated
            )
        sleeper(random.uniform(0.8, 1.5))
    write_manifest(list(by_bvid.values()), settings.manifest_path)
    return updated
