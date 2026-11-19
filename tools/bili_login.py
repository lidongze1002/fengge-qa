"""B 站扫码登录：生成二维码图片并轮询，成功后写 cookies.txt。

用法：
    python tools/bili_login.py [--out cookies.txt]

二维码会写到 .qr/bili_login.png，用浏览器预览它，手机 B 站 App 扫码确认即可。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from http.cookiejar import Cookie, LWPCookieJar
from pathlib import Path
from urllib.parse import urlparse

import qrcode
import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
}
GEN_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"


def make_qr(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = qrcode.make(url)
    img.save(path)


def write_netscape(cookies: dict[str, str], path: Path) -> None:
    lines = ["# Netscape HTTP Cookie File", ""]
    for name, value in cookies.items():
        if not value:
            continue
        lines.append(
            "\t".join([".bilibili.com", "TRUE", "/", "TRUE", "2000000000", name, value])
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="cookies.txt")
    parser.add_argument("--png", default=".qr/bili_login.png")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args(argv)

    session = requests.Session()
    session.headers.update(HEADERS)

    gen = session.get(GEN_URL, timeout=20).json()
    if gen.get("code") != 0:
        print(f"生成二维码失败：{gen}", file=sys.stderr)
        return 1
    url = gen["data"]["url"]
    key = gen["data"]["qrcode_key"]

    png = Path(args.png)
    make_qr(url, png)
    print(f"QR: {png.resolve()}")
    print(f"key: {key}", flush=True)

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        try:
            resp = session.get(POLL_URL, params={"qrcode_key": key}, timeout=20)
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            print(f"poll error: {exc}", flush=True)
            time.sleep(2)
            continue

        code = payload.get("data", {}).get("code")
        if code == 0:
            jar = session.cookies
            cookies = {c.name: c.value for c in jar}
            if not cookies.get("SESSDATA"):
                for raw in resp.headers.get("set-cookie", "").split(","):
                    if "SESSDATA=" in raw:
                        cookies["SESSDATA"] = raw.split("SESSDATA=")[1].split(";")[0]
            out = Path(args.out)
            write_netscape(cookies, out)
            print(f"LOGIN_OK {out.resolve()} cookies={sorted(cookies)}", flush=True)
            return 0
        if code == 86038:
            print("二维码已过期，请重跑", flush=True)
            return 2
        if code == 86090:
            print("已扫码，等待手机确认", flush=True)
        time.sleep(2)

    print("超时未确认", flush=True)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
