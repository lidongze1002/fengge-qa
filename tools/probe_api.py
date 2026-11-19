import json
import time

from fengge.config import load_settings
from fengge.discover import ARC_URL, _mixin_key, _new_session, sign_params

s = load_settings()
sess = _new_session(s)
spi = sess.get("https://api.bilibili.com/x/frontend/finger/spi", timeout=20).json()
sess.cookies.set("buvid3", spi["data"]["b_3"], domain=".bilibili.com")
sess.cookies.set("buvid4", spi["data"]["b_4"], domain=".bilibili.com")
sess.headers.update(
    {
        "Referer": "https://space.bilibili.com/433004026/video",
        "Origin": "https://space.bilibili.com",
    }
)

mixin = _mixin_key(sess)
params = {
    "mid": "433004026",
    "ps": "2",
    "pn": "1",
    "order": "pubdate",
    "platform": "web",
    "web_location": "1550101",
    "dm_img_list": "[]",
    "dm_img_str": "V2ViR0wgMS4wIChPcGVuR0wgRVMgMi4wIENocm9taXVtKQ",
    "dm_cover_img_str": "QU5HTEUgKEludGVsLCBJbnRlbChSKSBVSEQgR3JhcGhpY3MgNjMwIERpcmVjdDNEMTEp",
    "dm_img_inter": json.dumps({"ds": [], "wh": [0, 0, 0], "of": [0, 0, 0]}, separators=(",", ":")),
}
signed = sign_params(params, mixin, int(time.time()))
r = sess.get(ARC_URL, params=signed, timeout=20)
print("wbi+dm status", r.status_code, r.headers.get("content-type"))
try:
    d = r.json()
    print("code", d.get("code"), d.get("message"))
    if d.get("code") == 0:
        print("title", d["data"]["list"]["vlist"][0]["title"])
except Exception as exc:  # noqa: BLE001
    print("not json", exc)

v = sess.get(
    "https://api.bilibili.com/x/web-interface/view",
    params={"bvid": "BV1QR446eEMm"},
    timeout=20,
)
print("view status", v.status_code)
try:
    vd = v.json()
    print("view code", vd.get("code"), (vd.get("data") or {}).get("title"))
except Exception as exc:  # noqa: BLE001
    print("view not json", exc)
