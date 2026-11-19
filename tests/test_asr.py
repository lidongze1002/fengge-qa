from __future__ import annotations

from pathlib import Path

from fengge.asr import (
    build_extract_audio_cmd,
    build_initial_prompt,
    join_text,
    normalize_segments,
)


def test_extract_audio_cmd_is_16k_mono():
    cmd = build_extract_audio_cmd(Path("a.mp4"), Path("a.flac"))
    assert cmd[0] == "ffmpeg"
    assert "-vn" in cmd
    assert cmd[cmd.index("-ar") + 1] == "16000"
    assert cmd[cmd.index("-ac") + 1] == "1"
    assert Path(cmd[-1]) == Path("a.flac")


def test_initial_prompt_contains_domain_words():
    p = build_initial_prompt()
    for w in ("峰哥", "B友", "连麦", "老哥", "牛马"):
        assert w in p


def test_normalize_drops_short_and_empty():
    raw = [
        {"start": 0.0, "end": 1.0, "text": "嗯"},
        {"start": 1.0, "end": 2.0, "text": "   "},
        {"start": 2.0, "end": 4.0, "text": "你说得对"},
    ]
    out = normalize_segments(raw)
    assert [s["text"] for s in out] == ["你说得对"]


def test_normalize_collapses_repeated_hallucination():
    raw = [{"start": i, "end": i + 1, "text": "谢谢观看"} for i in range(5)]
    assert normalize_segments(raw) == []


def test_normalize_keeps_two_repeats():
    raw = [
        {"start": 0, "end": 1, "text": "对"},
        {"start": 1, "end": 2, "text": "对"},
        {"start": 2, "end": 3, "text": "我跟你讲"},
    ]
    assert len(normalize_segments(raw)) == 3


def test_join_text_strips_and_joins():
    segs = [
        {"start": 0, "end": 1, "text": " 你好 "},
        {"start": 1, "end": 2, "text": "世界"},
    ]
    assert join_text(segs) == "你好世界"


def test_transcriber_falls_back_when_cuda_build_fails(monkeypatch):
    import fengge.asr as a

    seen = []
    dummy = object()

    def fake_build(self, device, compute_type):
        seen.append(device)
        if device == "cuda":
            raise RuntimeError("libcudnn not found")
        return dummy

    monkeypatch.setattr(a.Transcriber, "_build", fake_build)
    t = a.Transcriber("large-v3", "int8_float16", device="cuda")
    assert t.device == "cpu"
    assert t.compute_type == "int8"
    assert seen == ["cuda", "cpu"]
