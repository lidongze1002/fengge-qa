from __future__ import annotations

import subprocess
from typing import Any, Callable


def _run(
    cmd: list[str], runner: Callable[..., subprocess.CompletedProcess]
) -> subprocess.CompletedProcess:
    return runner(cmd, capture_output=True, text=True, encoding="utf-8")


def check_ffmpeg(
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> tuple[bool, str]:
    try:
        result = _run(["ffmpeg", "-version"], runner)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"ffmpeg 不可用：{exc}"
    if result.returncode != 0:
        return False, f"ffmpeg 返回码 {result.returncode}"
    first = (result.stdout or "").splitlines()[0] if result.stdout else ""
    return True, first or "ffmpeg ok"


def check_ytdlp(
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> tuple[bool, str]:
    try:
        result = _run(["yt-dlp", "--version"], runner)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"yt-dlp 不可用：{exc}"
    if result.returncode != 0:
        return False, f"yt-dlp 返回码 {result.returncode}: {(result.stderr or '')[:120]}"
    return True, (result.stdout or "").strip() or "yt-dlp ok"


def check_gpu() -> tuple[bool, str]:
    try:
        import ctranslate2
    except ImportError as exc:
        return False, f"ctranslate2 未安装：{exc}"

    try:
        count = ctranslate2.get_cuda_device_count()
    except Exception as exc:  # noqa: BLE001
        return False, f"无法探测 CUDA 设备：{str(exc)[:160]}"
    if count == 0:
        return False, "没有可用的 CUDA 设备，ASR 将走 CPU int8（慢一个数量级）"

    try:
        types = ctranslate2.get_supported_compute_types("cuda")
    except Exception as exc:  # noqa: BLE001
        return False, f"CUDA 设备存在但 compute type 探测失败：{str(exc)[:160]}"
    if "int8_float16" not in types:
        return False, f"CUDA 可用但不支持 int8_float16：{sorted(types)}"
    return True, f"CUDA 可用（{count} 个设备，支持 int8_float16）"


def run_all() -> list[dict[str, Any]]:
    checks = (
        ("ffmpeg", check_ffmpeg()),
        ("yt-dlp", check_ytdlp()),
        ("gpu", check_gpu()),
    )
    return [{"name": name, "ok": ok, "detail": detail} for name, (ok, detail) in checks]


def print_report() -> bool:
    items = run_all()
    all_ok = True
    for item in items:
        mark = "OK  " if item["ok"] else "WARN"
        if not item["ok"]:
            all_ok = False
        print(f"[{mark}] {item['name']}: {item['detail']}")
    return all_ok
