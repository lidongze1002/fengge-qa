from __future__ import annotations

import sys
from pathlib import Path

import pytest

from fengge.download import (
    DownloadError,
    build_download_cmd,
    cover_path,
    download_one,
    find_output,
    is_valid_video,
    strip_cover_query,
)


def meta():
    from fengge.models import ClipMeta

    return ClipMeta(
        "BV1QR446eEMm", 1, "t", 30.0, 1, "http://i0.hdslb.com/a.jpg@100w.jpg"
    )


def runner_ok(raw_dir: Path, size: int = 20000, stderr: str = ""):
    def run(cmd, **kw):
        raw_dir.mkdir(parents=True, exist_ok=True)
        (raw_dir / "BV1QR446eEMm.mp4").write_bytes(b"0" * size)
        return type("R", (), {"returncode": 0 if size else 1, "stdout": "", "stderr": stderr})()

    return run


def test_cmd_prefers_mp4_and_sets_output():
    cmd = build_download_cmd(meta(), Path("raw/BV1QR446eEMm.mp4"), "edge", "")
    assert cmd[0] == sys.executable and cmd[1:3] == ["-m", "yt_dlp"]
    assert "-o" in cmd and cmd[cmd.index("-o") + 1].endswith("BV1QR446eEMm.%(ext)s")
    assert "bv*[height<=1080]+ba/b" in cmd
    assert cmd[-1] == "https://www.bilibili.com/video/BV1QR446eEMm"


def test_cmd_uses_cookie_string_when_no_browser():
    cmd = build_download_cmd(meta(), Path("raw/x.mp4"), "", "SESSDATA=abc")
    assert "--add-header" in cmd
    assert "Cookie:SESSDATA=abc" in cmd


def test_download_one_reports_network_error(tmp_path):
    from fengge.config import load_settings

    s = load_settings(root=tmp_path, env={})

    def runner(cmd, **kw):
        return type(
            "R",
            (),
            {
                "returncode": 1,
                "stdout": "",
                "stderr": "ERROR: Unable to download webpage: <urlopen error [WinError 10054]",
            },
        )()

    with pytest.raises(DownloadError) as e:
        download_one(
            meta(),
            s,
            runner=runner,
            sleeper=lambda _: None,
            fetcher=lambda url: b"jpg",
            prober=lambda p: 30.0,
        )
    assert e.value.status == "network"


def test_is_network_down_needs_three_consecutive():
    from fengge.download import is_network_down

    err = DownloadError("x", status="network")
    assert is_network_down([err, err]) is False
    assert is_network_down([err, err, err]) is True
    assert is_network_down([err, DownloadError("y", status="forbidden"), err]) is False


def test_cmd_prefers_cookie_file_over_browser(tmp_path):
    ck = tmp_path / "cookies.txt"
    ck.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    cmd = build_download_cmd(meta(), Path("raw/x.mp4"), "edge", "", ck)
    assert "--cookies" in cmd
    assert cmd[cmd.index("--cookies") + 1] == str(ck)
    assert "--cookies-from-browser" not in cmd


def test_is_valid_video_rejects_tiny_files(tmp_path):
    p = tmp_path / "a.mp4"
    p.write_bytes(b"0" * 100)
    assert is_valid_video(p) is False
    p.write_bytes(b"0" * 20000)
    assert is_valid_video(p) is True
    assert is_valid_video(tmp_path / "missing.mp4") is False


def test_find_output_prefers_mp4_then_other_extensions(tmp_path):
    (tmp_path / "BV1.flv").write_bytes(b"x")
    assert find_output(tmp_path, "BV1").name == "BV1.flv"
    (tmp_path / "BV1.mp4").write_bytes(b"x")
    assert find_output(tmp_path, "BV1").name == "BV1.mp4"
    assert find_output(tmp_path, "nope") is None


def test_strip_cover_query_removes_at_suffix():
    assert strip_cover_query("http://i0.hdslb.com/a.jpg@100w.jpg") == "http://i0.hdslb.com/a.jpg"


def test_download_one_fails_on_zero_byte_output(tmp_path):
    from fengge.config import load_settings

    s = load_settings(root=tmp_path, env={})

    def runner(cmd, **kw):
        s.raw_dir.mkdir(parents=True, exist_ok=True)
        (s.raw_dir / "BV1QR446eEMm.mp4").write_bytes(b"")
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    with pytest.raises(DownloadError) as e:
        download_one(
            meta(),
            s,
            runner=runner,
            sleeper=lambda _: None,
            fetcher=lambda url: b"jpg",
        )
    assert e.value.status == "invalid_file"


def test_download_one_reports_403(tmp_path):
    from fengge.config import load_settings

    s = load_settings(root=tmp_path, env={})

    def runner(cmd, **kw):
        return type(
            "R", (), {"returncode": 1, "stdout": "", "stderr": "ERROR: HTTP Error 403: Forbidden"}
        )()

    with pytest.raises(DownloadError) as e:
        download_one(
            meta(), s, runner=runner, sleeper=lambda _: None, fetcher=lambda url: b"jpg"
        )
    assert e.value.status == "forbidden"


def test_download_one_writes_cover_and_returns_paths(tmp_path):
    from fengge.config import load_settings

    s = load_settings(root=tmp_path, env={})
    out = download_one(
        meta(),
        s,
        runner=runner_ok(s.raw_dir),
        sleeper=lambda _: None,
        fetcher=lambda url: b"jpgbytes",
        prober=lambda p: 30.0,
    )
    assert Path(out["raw_path"]).exists()
    assert Path(out["cover_path"]).read_bytes() == b"jpgbytes"
    assert cover_path(s.clips_dir, "BV1QR446eEMm").name == "BV1QR446eEMm.jpg"


def test_download_one_rejects_unreadable_duration(tmp_path):
    from fengge.config import load_settings

    s = load_settings(root=tmp_path, env={})
    with pytest.raises(DownloadError) as e:
        download_one(
            meta(),
            s,
            runner=runner_ok(s.raw_dir),
            sleeper=lambda _: None,
            fetcher=lambda url: b"jpg",
            prober=lambda p: 0.0,
        )
    assert e.value.status == "invalid_file"


def test_download_one_keeps_going_when_cover_fails(tmp_path, caplog):
    from fengge.config import load_settings

    s = load_settings(root=tmp_path, env={})

    def boom(url):
        raise RuntimeError("cdn down")

    with caplog.at_level("WARNING"):
        out = download_one(
            meta(),
            s,
            runner=runner_ok(s.raw_dir),
            sleeper=lambda _: None,
            fetcher=boom,
            prober=lambda p: 30.0,
        )
    assert Path(out["raw_path"]).exists()
    assert out["cover_path"] == ""
    assert any("cover" in r.message.lower() for r in caplog.records)
