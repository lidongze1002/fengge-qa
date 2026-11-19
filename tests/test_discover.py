from __future__ import annotations

import hashlib
import json
import sys

from fengge.discover import (
    build_space_cmd,
    fetch_video_meta,
    parse_api_page,
    parse_space_json,
    sign_params,
    wbi_mixin_key,
    write_manifest,
)
from fengge.models import ClipMeta


def test_build_space_cmd_uses_browser_cookies():
    cmd = build_space_cmd("433004026", "edge")
    assert cmd[0] == sys.executable and cmd[1:3] == ["-m", "yt_dlp"]
    assert "--flat-playlist" in cmd
    assert "--cookies-from-browser" in cmd
    assert cmd[cmd.index("--cookies-from-browser") + 1] == "edge"
    assert cmd[-1] == "https://space.bilibili.com/433004026/video"


def test_build_space_cmd_prefers_cookie_file(tmp_path):
    ck = tmp_path / "cookies.txt"
    ck.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    cmd = build_space_cmd("433004026", "edge", ck)
    assert "--cookies" in cmd
    assert cmd[cmd.index("--cookies") + 1] == str(ck)
    assert "--cookies-from-browser" not in cmd


def test_wbi_mixin_key_is_deterministic_and_32_chars():
    img = "7cd084941338484aae1ad9425b84077c"
    sub = "4932caff0ff746eab6f01bf08b70ac45"
    key = wbi_mixin_key(img, sub)
    assert len(key) == 32
    assert key == wbi_mixin_key(img, sub)
    assert key != img[:32]


def test_sign_params_adds_wts_and_w_rid():
    mixin = "ea1db124af3c7062474693fa704f4ff8"
    params = {"mid": "433004026", "ps": "50", "pn": "1"}
    signed = sign_params(params, mixin, ts=1700000000)
    assert signed["wts"] == 1700000000
    assert len(signed["w_rid"]) == 32
    expected = hashlib.md5(
        ("mid=433004026&pn=1&ps=50&wts=1700000000" + mixin).encode()
    ).hexdigest()
    assert signed["w_rid"] == expected


def test_parse_api_page_maps_vlist():
    payload = {
        "code": 0,
        "data": {
            "page": {"pn": 1, "ps": 2, "count": 5},
            "list": {
                "vlist": [
                    {
                        "bvid": "BV1",
                        "aid": 111,
                        "title": "峰哥问答",
                        "duration": 30,
                        "created": 1793862075,
                        "pic": "http://x/c.jpg",
                    },
                    {"bvid": "", "title": "坏条目"},
                ]
            },
        },
    }
    metas = parse_api_page(payload)
    assert len(metas) == 1
    assert metas[0].bvid == "BV1"
    assert metas[0].aid == 111
    assert metas[0].title == "峰哥问答"
    assert metas[0].duration == 30.0
    assert metas[0].pubdate == 1793862075
    assert metas[0].cover_url == "http://x/c.jpg"


def test_parse_api_page_raises_on_error_code():
    import pytest

    with pytest.raises(RuntimeError):
        parse_api_page({"code": -412, "message": "blocked"})


def test_parse_api_page_tolerates_list_shaped_data():
    # 风控时接口会把 data 降级成 list，不能让 .get 把整轮发现打挂
    assert parse_api_page({"code": 0, "data": []}) == []
    assert parse_api_page({"code": 0, "data": {"list": []}}) == []
    assert parse_api_page({"code": 0, "data": {"list": {"vlist": ["x"]}}}) == []
    assert parse_api_page({"code": 0}) == []


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _Session:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return _Resp(self.payloads.pop(0))


def test_fetch_video_meta_maps_view_payload():
    payload = {
        "code": 0,
        "data": {
            "aid": 117562532760165,
            "title": "峰哥，年轻人做什么工作最好？",
            "duration": 30,
            "pubdate": 1793862075,
            "pic": "http://x/p.jpg",
        },
    }
    meta = fetch_video_meta(_Session([payload]), "BV1QR446eEMm", sleeper=lambda _: None)
    assert meta.bvid == "BV1QR446eEMm"
    assert meta.aid == 117562532760165
    assert meta.title == "峰哥，年轻人做什么工作最好？"
    assert meta.duration == 30.0
    assert meta.pubdate == 1793862075
    assert meta.cover_url == "http://x/p.jpg"


def test_fetch_video_meta_retries_on_rate_limit():
    payloads = [
        {"code": -799, "message": "frequent"},
        {"code": 0, "data": {"title": "t", "duration": 12, "pubdate": 5}},
    ]
    slept = []
    meta = fetch_video_meta(
        _Session(payloads), "BV1", sleeper=slept.append, retries=2
    )
    assert meta.title == "t"
    assert slept == [5]


def test_fetch_video_meta_gives_up_after_retries():
    meta = fetch_video_meta(
        _Session([{"code": -799}, {"code": -799}]),
        "BV1",
        sleeper=lambda _: None,
        retries=2,
    )
    assert meta is None


def test_parse_space_json_maps_entries():
    payload = {
        "entries": [
            {
                "id": "BV1",
                "title": " 峰哥 问答 ",
                "duration": 30,
                "timestamp": 1793862075,
                "thumbnails": [{"url": "http://x/cover.jpg"}],
            },
            {"id": "BV2", "title": "无封面", "duration": 61, "timestamp": 1793777218},
        ]
    }
    metas = parse_space_json(payload)
    assert len(metas) == 2
    assert metas[0].bvid == "BV1"
    assert metas[0].title == "峰哥 问答"
    assert metas[0].duration == 30.0
    assert metas[0].pubdate == 1793862075
    assert metas[0].cover_url == "http://x/cover.jpg"
    assert metas[1].cover_url == ""


def test_parse_space_json_skips_bad_entries():
    payload = {"entries": [{"title": "没有 id"}, {"id": "", "title": "空 id"}]}
    assert parse_space_json(payload) == []


def test_write_manifest_dedupes_by_bvid(tmp_path):
    metas = [
        ClipMeta("BV1", 1, "a", 30.0, 2, ""),
        ClipMeta("BV1", 1, "a", 30.0, 2, ""),
    ]
    path = tmp_path / "manifest.jsonl"
    assert write_manifest(metas, path) == 1
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["bvid"] == "BV1"
