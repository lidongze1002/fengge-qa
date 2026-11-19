from pathlib import Path

from fengge.config import load_settings


def test_load_settings_builds_paths_under_root(tmp_path):
    s = load_settings(root=tmp_path, env={"OPEN_API_KEY": "sk-test"})
    assert s.root == tmp_path
    assert s.data_dir == tmp_path / "data"
    assert s.clips_dir == tmp_path / "data" / "clips"
    assert s.db_path == tmp_path / "data" / "state.db"
    assert s.dataset_dir == tmp_path / "dataset"


def test_load_settings_defaults(tmp_path):
    s = load_settings(root=tmp_path, env={})
    assert s.up_mid == "433004026"
    assert s.llm_model == "gpt-4o-mini"
    assert s.embedding_model == "text-embedding-3-small"
    assert s.whisper_model == "large-v3"
    assert s.whisper_compute_type == "int8_float16"
    assert s.download_delay == (3.0, 6.0)
    assert s.trial_size == 300


def test_load_settings_reads_env_overrides(tmp_path):
    s = load_settings(
        root=tmp_path,
        env={"BILI_BROWSER": "chrome", "TRIAL_SIZE": "50", "LLM_MODEL": "gpt-4.1-mini"},
    )
    assert s.browser == "chrome"
    assert s.trial_size == 50
    assert s.llm_model == "gpt-4.1-mini"


def test_settings_dirs_are_derived_not_hardcoded(tmp_path):
    s = load_settings(root=tmp_path, env={})
    for d in (
        s.data_dir,
        s.clips_dir,
        s.raw_dir,
        s.audio_dir,
        s.asr_dir,
        s.structured_dir,
        s.dataset_dir,
    ):
        assert str(d).startswith(str(tmp_path))
