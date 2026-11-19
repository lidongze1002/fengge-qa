"""分批扩语料：下载 → 转写 → 归档，断点续跑，遇到网络/风控自动等待重试。"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=True)
except ImportError:  # pragma: no cover
    pass

FFMPEG_BIN = (
    Path(os.environ["LOCALAPPDATA"])
    / "Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
)
for candidate in FFMPEG_BIN.glob("ffmpeg-*/bin"):
    os.environ["PATH"] = str(candidate) + os.pathsep + os.environ.get("PATH", "")

from fengge.config import load_settings  # noqa: E402
from fengge.pipeline import NetworkDown, Pipeline, RateLimited  # noqa: E402

CHUNK = 120
MAX_ROUNDS = 40
WAIT_ON_LIMIT = 600

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(ROOT / "logs" / "expand.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("expand")


def main() -> int:
    settings = load_settings()
    log.info(
        "max_duration=%s records=%s",
        settings.max_duration,
        settings.manifest_path.exists(),
    )
    pipeline = Pipeline(settings)
    rounds = 0
    while rounds < MAX_ROUNDS:
        rounds += 1
        counts = pipeline.db.counts()
        todo = counts.get("discovered", 0)
        log.info("round %s | discovered=%s downloaded=%s asr_done=%s archived=%s",
                 rounds, todo, counts.get("downloaded", 0),
                 counts.get("asr_done", 0), counts.get("archived", 0))
        if todo == 0 and counts.get("downloaded", 0) == 0:
            break
        try:
            for stage in ("download", "asr", "archive"):
                result = pipeline.run(stage, limit=CHUNK)
                log.info("%s -> %s", stage, result)
        except (NetworkDown, RateLimited) as exc:
            log.warning("paused: %s (sleep %ss)", exc, WAIT_ON_LIMIT)
            time.sleep(WAIT_ON_LIMIT)
            continue
    log.info("expand finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
