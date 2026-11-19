from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Callable

from . import asr as asr_mod
from . import download as download_mod
from . import transcode as transcode_mod
from .config import Settings
from .db import Database
from .filter import filter_item, filter_video, sanitize_items
from .models import ClipMeta

log = logging.getLogger("fengge")

STAGES = ("download", "asr", "archive", "structure")

RATE_LIMIT_STRIKES = 3


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RateLimited(RuntimeError):
    """连续多次 403/412：整批停机，避免把全部条目刷成 failed。"""


class NetworkDown(RuntimeError):
    """连续多次网络错误：整批停机，等网络恢复再续跑。"""


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        db: Database | None = None,
        transcriber: Any = None,
        llm: Any = None,
    ):
        self.settings = settings
        self.db = db or Database(settings.db_path)
        self.db.init_schema()
        self._transcriber = transcriber
        self._llm = llm

    # --- lazily built dependencies -------------------------------------
    @property
    def transcriber(self) -> Any:
        if self._transcriber is None:
            self._transcriber = asr_mod.Transcriber(
                self.settings.whisper_model,
                self.settings.whisper_compute_type,
                device="cuda",
                logger=log,
            )
        return self._transcriber

    @property
    def llm(self) -> Any:
        if self._llm is None:
            from .structure import LLMClient

            self._llm = LLMClient(
                self.settings.openai_api_key,
                self.settings.llm_model,
                self.settings.openai_base_url,
            )
        return self._llm

    # --- injectable steps ----------------------------------------------
    def _download_one(self, meta: ClipMeta) -> dict[str, str]:
        return download_mod.download_one(meta, self.settings)

    def _extract_audio(self, src: Path, dst: Path) -> None:
        dst.parent.mkdir(parents=True, exist_ok=True)
        cmd = asr_mod.build_extract_audio_cmd(src, dst)
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg extract failed: {(result.stderr or '')[:200]}")

    def _archive_one(self, row: dict[str, Any]) -> bool:
        src = Path(row["raw_path"])
        dst = Path(self.settings.clips_dir) / f"{row['bvid']}.mp4"
        return transcode_mod.archive(src, dst)

    # --- stages --------------------------------------------------------
    def _download_stage(self, limit: int | None) -> dict[str, int]:
        rows = self.db.next_batch(
            "discovered", limit or 10_000, self.settings.max_duration
        )
        processed = failed = 0
        strikes: list[download_mod.DownloadError] = []
        for row in rows:
            meta = ClipMeta(
                bvid=row["bvid"],
                aid=row["aid"] or 0,
                title=row["title"] or "",
                duration=row["duration"] or 0.0,
                pubdate=row["pubdate"] or 0,
                cover_url=row["cover_url"] or "",
            )
            try:
                out = self._download_one(meta)
            except download_mod.DownloadError as exc:
                failed += 1
                strikes.append(exc)
                if exc.status == "forbidden":
                    # 403/412 是账号或网络层面的问题，不该记到视频头上
                    self.db.set_meta(row["bvid"], last_error=str(exc))
                elif exc.status == "network":
                    self.db.set_meta(row["bvid"], last_error=str(exc))
                else:
                    self.db.fail(row["bvid"], str(exc))
                if download_mod.is_rate_limited(strikes):
                    raise RateLimited(
                        f"{RATE_LIMIT_STRIKES} consecutive blocks; stopping batch. "
                        f"Last error: {exc}"
                    ) from exc
                if download_mod.is_network_down(strikes):
                    raise NetworkDown(
                        f"{RATE_LIMIT_STRIKES} consecutive network errors; "
                        f"stopping batch. Last error: {exc}"
                    ) from exc
                continue
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self.db.fail(row["bvid"], str(exc))
                continue
            strikes.clear()
            self.db.set_state(
                row["bvid"],
                "downloaded",
                raw_path=out["raw_path"],
                cover_path=out["cover_path"],
            )
            processed += 1
            log.info("[download] %s ok (%s/%s)", row["bvid"], processed, len(rows))
        log.info("[download] done processed=%s failed=%s", processed, failed)
        return {"processed": processed, "failed": failed}

    def _asr_stage(self, limit: int | None) -> dict[str, int]:
        rows = self.db.next_batch(
            "downloaded", limit or 10_000, self.settings.max_duration
        )
        if not rows:
            return {"processed": 0, "failed": 0}
        transcriber = self.transcriber  # 配置问题在循环外炸掉，不记到每条视频头上
        processed = failed = 0
        for row in rows:
            bvid = row["bvid"]
            try:
                raw = Path(row["raw_path"] or "")
                if not raw.is_file():
                    raise FileNotFoundError(f"raw missing: {raw}")
                audio = Path(self.settings.audio_dir) / f"{bvid}.flac"
                audio.parent.mkdir(parents=True, exist_ok=True)
                self._extract_audio(raw, audio)
                try:
                    result = transcriber.transcribe(audio)
                finally:
                    audio.unlink(missing_ok=True)
                asr_path = Path(self.settings.asr_dir) / f"{bvid}.json"
                asr_path.parent.mkdir(parents=True, exist_ok=True)
                asr_path.write_text(
                    json.dumps(result, ensure_ascii=False), encoding="utf-8"
                )
                reason = filter_video(
                    result.get("text", ""),
                    float(result.get("duration") or row["duration"] or 0.0),
                    float(result.get("lang_prob") or 0.0),
                )
                if reason:
                    self.db.set_state(bvid, "rejected", reject_reason=reason)
                else:
                    self.db.set_state(
                        bvid,
                        "asr_done",
                        asr_path=str(asr_path),
                        asr_chars=len(result.get("text", "")),
                        asr_lang_prob=float(result.get("lang_prob") or 0.0),
                    )
                processed += 1
                log.info(
                    "[asr] %s done chars=%s (%s/%s)",
                    bvid,
                    len(result.get("text", "")),
                    processed,
                    len(rows),
                )
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self.db.fail(bvid, str(exc))
                log.warning("[asr] %s failed: %s", bvid, exc)
        log.info("[asr] done processed=%s failed=%s", processed, failed)
        return {"processed": processed, "failed": failed}

    def _archive_stage(self, limit: int | None) -> dict[str, int]:
        rows = [
            r
            for r in self.db.next_batch(
                ["asr_done", "rejected"],
                limit or 10_000,
                self.settings.max_duration,
                skip_clipped=True,
            )
            if not r["clip_path"] and r["raw_path"]
        ]
        processed = failed = 0
        for row in rows:
            bvid = row["bvid"]
            try:
                if not Path(row["raw_path"]).is_file():
                    raise FileNotFoundError(f"raw missing for {bvid}")
                if not self._archive_one(row):
                    raise RuntimeError(f"archive verification failed for {bvid}")
                clip = Path(self.settings.clips_dir) / f"{bvid}.mp4"
                if row["state"] == "rejected":
                    # 内容不用，但片子要留住；状态保持 rejected，避免被 structure 重新捡起
                    self.db.set_meta(
                        bvid, clip_path=str(clip), archived_at=_now_iso()
                    )
                else:
                    self.db.set_state(bvid, "archived", clip_path=str(clip))
                Path(row["raw_path"]).unlink(missing_ok=True)
                if row["audio_path"]:
                    Path(row["audio_path"]).unlink(missing_ok=True)
                processed += 1
                log.info("[archive] %s ok (%s/%s)", bvid, processed, len(rows))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self.db.fail(bvid, str(exc))
                log.warning("[archive] %s failed: %s", bvid, exc)
        log.info("[archive] done processed=%s failed=%s", processed, failed)
        return {"processed": processed, "failed": failed}

    def _structure_stage(self, limit: int | None) -> dict[str, int]:
        rows = self.db.next_batch(
            "archived", limit or 10_000, self.settings.max_duration
        )
        if not rows:
            return {"processed": 0, "failed": 0}
        llm = self.llm  # 缺 key / 模型名写错时整批停，不要逐条 failed
        processed = failed = 0
        for row in rows:
            bvid = row["bvid"]
            try:
                asr_path = Path(row["asr_path"] or "")
                payload = json.loads(asr_path.read_text(encoding="utf-8"))
                duration = float(payload.get("duration") or row["duration"] or 0.0)
                items = sanitize_items(
                    llm.structure(
                        row["title"] or "",
                        payload.get("segments") or [],
                        duration,
                    ),
                    duration,
                )
                out_path = Path(self.settings.structured_dir) / f"{bvid}.json"
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(
                    json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8"
                )
                accepted = [
                    it for it in items if filter_item(it, duration) is None
                ]
                if accepted:
                    best = max(int(it.get("quality") or 0) for it in accepted)
                    self.db.set_state(
                        bvid, "accepted", quality=best, structured_path=str(out_path)
                    )
                else:
                    reason = "no_qa"
                    if items:
                        reason = filter_item(items[0], duration) or "no_qa"
                    self.db.set_state(
                        bvid, "rejected", reject_reason=reason, structured_path=str(out_path)
                    )
                processed += 1
                log.info(
                    "[structure] %s -> %s (%s/%s)",
                    bvid,
                    "accepted" if accepted else "rejected",
                    processed,
                    len(rows),
                )
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self.db.fail(bvid, str(exc))
                log.warning("[structure] %s failed: %s", bvid, exc)
        log.info("[structure] done processed=%s failed=%s", processed, failed)
        return {"processed": processed, "failed": failed}

    def run(self, stage: str, limit: int | None = None) -> dict[str, int]:
        stages: dict[str, Callable[[int | None], dict[str, int]]] = {
            "download": self._download_stage,
            "asr": self._asr_stage,
            "archive": self._archive_stage,
            "structure": self._structure_stage,
        }
        if stage not in stages:
            raise ValueError(f"unknown stage: {stage}")
        return stages[stage](limit)

    def run_all(self, limit: int | None = None) -> dict[str, dict[str, int]]:
        return {stage: self.run(stage, limit) for stage in STAGES}
