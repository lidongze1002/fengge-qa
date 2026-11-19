"""下载 live2d-widget 运行时与官方免费模型，落到 web/vendor/live2d/。"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(r"D:\fengge-rag\web\vendor\live2d")
MODELS = ["haru", "shizuku", "koharu"]
WIDGET = (
    "https://cdn.jsdelivr.net/npm/live2d-widget@3.1.4/lib/L2Dwidget.min.js"
)
UA = {"User-Agent": "Mozilla/5.0"}


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def walk(nodes, prefix=""):
    for node in nodes:
        name = f"{prefix}{node['name']}"
        if node.get("type") == "file":
            yield name
        else:
            yield from walk(node.get("files") or [], f"{name}/")


def download_tree(package: str, dest: Path) -> tuple[int, int]:
    meta = json.loads(get(f"https://data.jsdelivr.com/v1/packages/npm/{package}"))
    version = meta.get("tags", {}).get("latest") or meta["versions"][0]["version"]
    tree = json.loads(
        get(f"https://data.jsdelivr.com/v1/packages/npm/{package}@{version}")
    )
    total = 0
    for rel in walk(tree["files"]):
        if rel.endswith(".map"):
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://cdn.jsdelivr.net/npm/{package}@{version}/{rel}"
        data = get(url)
        target.write_bytes(data)
        total += len(data)
    return sum(1 for _ in dest.rglob("*") if _.is_file()), total


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)

    widget = ROOT / "L2Dwidget.min.js"
    widget.write_bytes(get(WIDGET))
    print(f"widget {widget.stat().st_size / 1024:.0f} KB")

    for name in MODELS:
        dest = ROOT / "models" / name
        try:
            files, size = download_tree(f"live2d-widget-model-{name}", dest)
            print(f"{name}: {files} files, {size / 1024 / 1024:.1f} MB")
        except Exception as exc:  # noqa: BLE001
            print(f"{name} FAILED {exc}", file=sys.stderr)

    for path in sorted((ROOT / "models").rglob("*.model.json")):
        print("model:", path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
