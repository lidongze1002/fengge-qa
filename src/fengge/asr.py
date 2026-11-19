from __future__ import annotations

from pathlib import Path
from typing import Any

PROMPT = (
    "以下是峰哥直播连麦的语音，B友提问，峰哥回答。"
    "常见词：峰哥、B友、连麦、老哥、牛马、躺平、搞钱、上岸、"
    "直播间、刷礼物、东北、深圳。"
    "口语词如 嗯、啊、那个、就是说 可以保留。"
)

FILLER_CHARS = set("嗯啊哦呃诶欸唉哎噢喔呀哈嘛额")

REPEAT_LIMIT = 3


def build_extract_audio_cmd(src: Path, dst: Path) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "flac",
        str(dst),
    ]


def build_initial_prompt() -> str:
    return PROMPT


def _is_filler(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and all(ch in FILLER_CHARS for ch in stripped)


def normalize_segments(raw: list[dict[str, Any]], min_chars: int = 1) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for seg in raw:
        text = (seg.get("text") or "").strip()
        if not text or len(text) < min_chars or _is_filler(text):
            continue
        cleaned.append(
            {"start": float(seg.get("start") or 0.0), "end": float(seg.get("end") or 0.0), "text": text}
        )

    result: list[dict[str, Any]] = []
    i = 0
    while i < len(cleaned):
        j = i + 1
        while j < len(cleaned) and cleaned[j]["text"] == cleaned[i]["text"]:
            j += 1
        run = j - i
        if run < REPEAT_LIMIT:
            result.extend(cleaned[i:j])
        i = j
    return result


def join_text(segments: list[dict[str, Any]]) -> str:
    return "".join((s.get("text") or "").strip() for s in segments)


class Transcriber:
    """faster-whisper 封装；构造时就确定实际可用设备。"""

    def __init__(
        self,
        model_size: str,
        compute_type: str,
        device: str = "cuda",
        logger: Any = None,
    ):
        self.requested_device = device
        self.compute_type = compute_type
        self.model_size = model_size
        self._logger = logger
        self.device = device
        try:
            self._model = self._build(device, compute_type)
        except Exception as exc:  # noqa: BLE001
            if device != "cuda":
                raise
            self._cuda_error = str(exc)
            self._fallback()
        else:
            self._cuda_error = ""

    def _build(self, device: str, compute_type: str):
        from . import dllpaths

        dllpaths.register()
        import faster_whisper

        return faster_whisper.WhisperModel(
            self.model_size, device=device, compute_type=compute_type
        )

    def _fallback(self) -> None:
        if self._logger:
            self._logger.warning(
                "CUDA unavailable (%s), falling back to CPU int8",
                getattr(self, "_cuda_error", "unknown"),
            )
        self.device = "cpu"
        self.compute_type = "int8"
        self._model = self._build("cpu", "int8")

    def transcribe(self, audio: Path) -> dict[str, Any]:
        try:
            segments_iter, info = self._model.transcribe(
                str(audio),
                language="zh",
                vad_filter=True,
                condition_on_previous_text=False,
                initial_prompt=build_initial_prompt(),
            )
        except Exception:
            if self.device == "cuda":
                self._fallback()
                segments_iter, info = self._model.transcribe(
                    str(audio),
                    language="zh",
                    vad_filter=True,
                    condition_on_previous_text=False,
                    initial_prompt=build_initial_prompt(),
                )
            else:
                raise

        raw = [
            {"start": float(s.start), "end": float(s.end), "text": s.text}
            for s in segments_iter
        ]
        segments = normalize_segments(raw)
        return {
            "segments": segments,
            "text": join_text(segments),
            "duration": float(getattr(info, "duration", 0.0) or 0.0),
            "lang_prob": float(getattr(info, "language_probability", 0.0) or 0.0),
        }
