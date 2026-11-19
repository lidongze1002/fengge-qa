from __future__ import annotations

from fengge.envcheck import check_ffmpeg, check_ytdlp, run_all


def test_check_ffmpeg_ok():
    def r(cmd, **kw):
        return type("R", (), {"returncode": 0, "stdout": "ffmpeg version 7", "stderr": ""})()

    ok, detail = check_ffmpeg(runner=r)
    assert ok is True and "7" in detail


def test_check_ffmpeg_missing():
    def r(cmd, **kw):
        raise FileNotFoundError()

    ok, detail = check_ffmpeg(runner=r)
    assert ok is False and "ffmpeg" in detail


def test_check_ytdlp_missing():
    def r(cmd, **kw):
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": "not found"})()

    ok, _ = check_ytdlp(runner=r)
    assert ok is False


def test_run_all_returns_named_items(monkeypatch):
    import fengge.envcheck as ec

    monkeypatch.setattr(ec, "check_ffmpeg", lambda **kw: (True, "ok"))
    monkeypatch.setattr(ec, "check_ytdlp", lambda **kw: (True, "ok"))
    monkeypatch.setattr(ec, "check_gpu", lambda: (False, "cpu fallback"))
    items = ec.run_all()
    assert {i["name"] for i in items} == {"ffmpeg", "yt-dlp", "gpu"}
    assert next(i for i in items if i["name"] == "gpu")["ok"] is False
