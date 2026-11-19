from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

SCALE_FILTER = "scale='if(gte(iw,ih),-2,720)':'if(gte(iw,ih),720,-2)'"


def build_transcode_cmd(src: Path, dst: Path) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-vf",
        SCALE_FILTER,
        "-c:v",
        "libx264",
        "-crf",
        "26",
        "-preset",
        "veryfast",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        str(dst),
    ]


def probe_duration(
    path: Path, runner: Callable[..., subprocess.CompletedProcess] = subprocess.run
) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "csv=p=0",
        str(path),
    ]
    try:
        result = runner(cmd, capture_output=True, text=True, encoding="utf-8")
    except (OSError, subprocess.SubprocessError):
        return 0.0
    if result.returncode != 0:
        return 0.0
    try:
        return float((result.stdout or "").strip())
    except ValueError:
        return 0.0


def verify_archive(
    src: Path,
    dst: Path,
    tol: float = 0.5,
    prober: Callable[..., float] = probe_duration,
) -> bool:
    if not Path(dst).is_file() or Path(dst).stat().st_size == 0:
        return False
    if not Path(src).is_file():
        return False
    src_dur = prober(src)
    dst_dur = prober(dst)
    if src_dur <= 0 or dst_dur <= 0:
        return False
    return abs(src_dur - dst_dur) <= tol


def archive(
    src: Path,
    dst: Path,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    prober: Callable[..., float] = probe_duration,
) -> bool:
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    cmd = build_transcode_cmd(src, dst)
    try:
        result = runner(cmd, capture_output=True, text=True, encoding="utf-8")
    except (OSError, subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        return False
    return verify_archive(src, dst, prober=prober)
