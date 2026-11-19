from __future__ import annotations

from pathlib import Path

from fengge.transcode import build_transcode_cmd, verify_archive


def test_cmd_scales_to_720_and_copies_audio():
    cmd = build_transcode_cmd(Path("raw/a.mp4"), Path("clips/a.mp4"))
    assert cmd[0] == "ffmpeg"
    assert "-y" in cmd
    vf = cmd[cmd.index("-vf") + 1]
    assert "720" in vf
    assert "libx264" in cmd and "aac" in cmd
    assert Path(cmd[-1]) == Path("clips/a.mp4")


def test_verify_archive_accepts_within_tolerance(tmp_path):
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    a.write_bytes(b"x")
    b.write_bytes(b"y")
    durs = {a: 30.0, b: 30.4}
    assert verify_archive(a, b, prober=lambda p, **kw: durs[p]) is True


def test_verify_archive_rejects_drift(tmp_path):
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    a.write_bytes(b"x")
    b.write_bytes(b"y")
    durs = {a: 30.0, b: 5.0}
    assert verify_archive(a, b, prober=lambda p, **kw: durs[p]) is False


def test_verify_archive_rejects_missing_dest(tmp_path):
    a = tmp_path / "a.mp4"
    a.write_bytes(b"x")
    assert verify_archive(a, tmp_path / "nope.mp4", prober=lambda p, **kw: 30.0) is False
