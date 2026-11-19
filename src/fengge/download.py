from __future__ import annotations

import logging
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from . import transcode
from .config import Settings
from .models import ClipMeta

VIDEO_EXTS = (".mp4", ".flv", ".mkv", ".mov", ".webm", ".ts")
MIN_VIDEO_BYTES = 10240
MIN_VIDEO_SECONDS = 1.0

log = logging.getLogger("fengge")


class DownloadError(Exception):
    def __init__(self, message: str, status: str = "other", stderr: str = ""):
        super().__init__(message)
        self.status = status
        self.stderr = stderr


def build_download_cmd(
    meta: ClipMeta,
    out_path: Path,
    browser: str,
    cookie: str,
    cookie_file: Path | None = None,
) -> list[str]:
    url = f"https://www.bilibili.com/video/{meta.bvid}"
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "-f",
        "bv*[height<=1080]+ba/b",
        "--merge-output-format",
        "mp4",
        "--no-playlist",
        "--retries",
        "3",
    ]
    if cookie_file is not None and Path(cookie_file).is_file():
        cmd += ["--cookies", str(cookie_file)]
    elif browser:
        cmd += ["--cookies-from-browser", browser]
    elif cookie:
        cmd += ["--add-header", f"Cookie:{cookie}"]
    cmd += ["-o", str(out_path.with_suffix(".%(ext)s")), url]
    return cmd


def find_output(raw_dir: Path, bvid: str) -> Path | None:
    if not raw_dir.exists():
        return None
    for ext in VIDEO_EXTS:
        candidate = raw_dir / f"{bvid}{ext}"
        if candidate.exists():
            return candidate
    return None


def is_valid_video(path: Path, min_bytes: int = MIN_VIDEO_BYTES) -> bool:
    try:
        return path.is_file() and path.stat().st_size >= min_bytes
    except OSError:
        return False


def cover_path(clips_dir: Path, bvid: str) -> Path:
    return Path(clips_dir) / f"{bvid}.jpg"


def strip_cover_query(url: str) -> str:
    return url.split("@", 1)[0]


def _fetch_bytes(url: str) -> bytes:
    import requests

    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    return resp.content


def download_cover(
    url: str, dest: Path, fetcher: Callable[[str], bytes] | None = None
) -> bool:
    if not url:
        return False
    fetcher = fetcher or _fetch_bytes
    try:
        data = fetcher(strip_cover_query(url))
    except Exception:
        return False
    if not data:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True


def download_one(
    meta: ClipMeta,
    settings: Settings,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    sleeper: Callable[[float], None] = time.sleep,
    fetcher: Callable[[str], bytes] | None = None,
    prober: Callable[[Path], float] = transcode.probe_duration,
) -> dict[str, str]:
    raw_dir = Path(settings.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / f"{meta.bvid}.mp4"

    found = find_output(raw_dir, meta.bvid)
    if found is not None and is_valid_video(found):
        result_path = found
    else:
        if found is not None:
            found.unlink(missing_ok=True)
        cmd = build_download_cmd(
            meta, target, settings.browser, settings.cookie, settings.cookie_file
        )
        result = runner(cmd, capture_output=True, text=True, encoding="utf-8")
        stderr = (result.stderr or "")
        if result.returncode != 0:
            if "403" in stderr or "412" in stderr:
                raise DownloadError(
                    f"blocked by bilibili: {stderr[:200]}", status="forbidden", stderr=stderr
                )
            if _looks_like_network_error(stderr):
                raise DownloadError(
                    f"network error: {stderr[:200]}", status="network", stderr=stderr
                )
            raise DownloadError(
                f"yt-dlp failed ({result.returncode}): {stderr[:200]}",
                status="other",
                stderr=stderr,
            )
        result_path = find_output(raw_dir, meta.bvid)
        if result_path is None or not is_valid_video(result_path):
            raise DownloadError(
                f"downloaded file unusable for {meta.bvid}", status="invalid_file", stderr=stderr
            )

    duration = prober(result_path)
    if duration < MIN_VIDEO_SECONDS:
        raise DownloadError(
            f"downloaded file has no readable duration ({duration:.2f}s) for {meta.bvid}",
            status="invalid_file",
        )

    cover = cover_path(settings.clips_dir, meta.bvid)
    cover_ok = download_cover(meta.cover_url, cover, fetcher=fetcher)
    if not cover_ok:
        log.warning("cover download failed for %s (%s)", meta.bvid, meta.cover_url)
        cover_value = ""
    else:
        cover_value = str(cover)

    sleeper(random.uniform(*settings.download_delay))
    return {"raw_path": str(result_path), "cover_path": cover_value}


def is_rate_limited(errors: list[DownloadError]) -> bool:
    return len(errors) >= 3 and all(e.status == "forbidden" for e in errors[-3:])


NETWORK_MARKERS = (
    "failed to resolve",
    "getaddrinfo",
    "connection reset",
    "connection aborted",
    "connection refused",
    "timed out",
    "timeout",
    "temporary failure",
    "unable to connect",
    "unable to download",
    "urlopen error",
    "winerror",
    "network is unreachable",
    "remote end closed",
    "ssl",
)


def _looks_like_network_error(stderr: str) -> bool:
    lowered = (stderr or "").lower()
    return any(marker in lowered for marker in NETWORK_MARKERS)


def is_network_down(errors: list[DownloadError]) -> bool:
    return len(errors) >= 3 and all(e.status == "network" for e in errors[-3:])
