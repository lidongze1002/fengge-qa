from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class Settings:
    root: Path
    data_dir: Path
    clips_dir: Path
    raw_dir: Path
    audio_dir: Path
    asr_dir: Path
    structured_dir: Path
    dataset_dir: Path
    logs_dir: Path
    db_path: Path
    manifest_path: Path
    up_mid: str
    browser: str
    cookie: str
    cookie_file: Path
    openai_api_key: str
    openai_base_url: str
    llm_model: str
    embedding_model: str
    embedding_backend: str
    local_embedding_model: str
    whisper_model: str
    whisper_compute_type: str
    download_delay: tuple[float, float]
    trial_size: int
    dedupe_threshold: float
    verify_threshold: float
    max_duration: float | None


def _default_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_settings(
    root: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Settings:
    env = os.environ if env is None else env
    root = Path(root) if root is not None else _default_root()
    data_dir = root / "data"

    return Settings(
        root=root,
        data_dir=data_dir,
        clips_dir=data_dir / "clips",
        raw_dir=data_dir / "raw",
        audio_dir=data_dir / "audio",
        asr_dir=data_dir / "asr",
        structured_dir=data_dir / "structured",
        dataset_dir=root / "dataset",
        logs_dir=root / "logs",
        db_path=data_dir / "state.db",
        manifest_path=data_dir / "manifest.jsonl",
        up_mid=env.get("UP_MID", "433004026"),
        browser=env.get("BILI_BROWSER", "edge"),
        cookie=env.get("BILI_COOKIE", ""),
        cookie_file=Path(env.get("BILI_COOKIE_FILE", str(root / "cookies.txt"))),
        openai_api_key=env.get("OPEN_API_KEY", ""),
        openai_base_url=env.get("OPENAI_BASE_URL", ""),
        llm_model=env.get("LLM_MODEL", "gpt-4o-mini"),
        embedding_model=env.get("EMBEDDING_MODEL", "text-embedding-3-small"),
        embedding_backend=env.get("EMBEDDING_BACKEND", "local"),
        local_embedding_model=env.get("LOCAL_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"),
        whisper_model=env.get("WHISPER_MODEL", "large-v3"),
        whisper_compute_type=env.get("WHISPER_COMPUTE_TYPE", "int8_float16"),
        download_delay=(3.0, 6.0),
        trial_size=int(env.get("TRIAL_SIZE", "300")),
        dedupe_threshold=float(env.get("DEDUPE_THRESHOLD", "0.92")),
        verify_threshold=float(env.get("VERIFY_THRESHOLD", "0.62")),
        max_duration=_optional_float(env.get("MAX_DURATION", "180")),
    )


def _optional_float(value: str | None) -> float | None:
    if value is None or value.strip() in ("", "0", "none", "None"):
        return None
    return float(value)
