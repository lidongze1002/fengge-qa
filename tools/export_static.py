"""导出纯静态站点（GitHub Pages / Cloudflare Pages 可直接托管）。

产出 dist/：
    index.html          前端（检索在浏览器里跑，不需要服务器）
    data/clips.json     瘦身后的问答数据
    thumbs/<bvid>.jpg   缩略图（240px，按需加载）
    vendor/live2d/      看板娘（只带 fengge 模型 + 渲染库）

视频不打包：每条记录用 trim.start 生成 B 站时间戳链接，点了跳原视频。
这样 19 GB 视频不用托管，也没有二次分发的问题。

用法：
    python tools/export_static.py [--dist dist] [--thumb-width 240]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def build_clips(dataset: Path) -> list[dict]:
    rows = []
    seen: set[str] = set()
    with dataset.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            rid = d.get("id") or ""
            if not rid or rid in seen:
                continue
            seen.add(rid)
            trim = d.get("trim") or {}
            start = float(trim.get("start") or 0)
            end = float(trim.get("end") or 0)
            bvid = d.get("source_bvid") or ""
            rows.append(
                {
                    "id": rid,
                    "b": bvid,
                    "t": round(start, 1),
                    "e": round(end, 1),
                    "q": (d.get("abstract_question") or d.get("question_verbatim") or "").strip(),
                    "qv": (d.get("question_verbatim") or "").strip(),
                    "a": (d.get("answer_summary") or "").strip(),
                    "quote": (d.get("quote") or "").strip(),
                    "tags": (d.get("tags") or [])[:6],
                    "title": (d.get("title") or "").strip(),
                    "type": d.get("question_type") or "",
                }
            )
    return rows


def pick_cover(record_id: str, bvid: str, clips_dir: Path) -> Path | None:
    for name in (f"{record_id}.jpg", f"{bvid}.jpg"):
        p = clips_dir / name
        if p.is_file():
            return p
    return None


def write_thumbs(rows: list[dict], clips_dir: Path, out_dir: Path, width: int) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    made = 0
    missing = 0
    for r in rows:
        dst = out_dir / f"{r['id']}.jpg"
        if dst.is_file():
            continue
        src = pick_cover(r["id"], r["b"], clips_dir)
        if src is None:
            missing += 1
            continue
        try:
            im = Image.open(src).convert("RGB")
            if im.width > width:
                im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
            im.save(dst, quality=72, optimize=True)
            made += 1
        except Exception:  # noqa: BLE001
            missing += 1
    print(f"thumbs: {made} new, {len(rows) - missing} total, {missing} without cover")
    return missing


def copy_vendor(dist: Path) -> None:
    src_models = ROOT / "web" / "vendor" / "live2d" / "models" / "fengge"
    src_libs = ROOT / "web" / "vendor" / "live2d" / "cubism"
    dst = dist / "vendor" / "live2d"
    if not src_models.is_dir():
        print("warn: fengge 模型不存在，跳过看板娘")
        return
    shutil.copytree(src_models, dst / "models" / "fengge", dirs_exist_ok=True)
    if src_libs.is_dir():
        shutil.copytree(src_libs, dst / "cubism", dirs_exist_ok=True)
    print(f"vendor: {sum(1 for _ in dst.rglob('*') if _.is_file())} files")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", default=str(ROOT / "dist"))
    ap.add_argument("--thumb-width", type=int, default=240)
    ap.add_argument("--dataset", default=str(ROOT / "dataset" / "clips.jsonl"))
    args = ap.parse_args()

    dist = Path(args.dist)
    dataset = Path(args.dataset)
    if not dataset.is_file():
        print(f"dataset not found: {dataset}", file=sys.stderr)
        return 1

    rows = build_clips(dataset)
    if not rows:
        print("no records", file=sys.stderr)
        return 1

    (dist / "data").mkdir(parents=True, exist_ok=True)
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    (dist / "data" / "clips.json").write_text(payload, encoding="utf-8")
    print(f"clips: {len(rows)} records, {len(payload) / 1024 / 1024:.2f} MB")

    write_thumbs(rows, ROOT / "data" / "clips", dist / "thumbs", args.thumb_width)
    copy_vendor(dist)

    page = ROOT / "web" / "static" / "index.html"
    if not page.is_file():
        print(f"missing page template: {page}", file=sys.stderr)
        return 1
    shutil.copy2(page, dist / "index.html")
    (dist / ".nojekyll").write_text("", encoding="utf-8")

    total = sum(p.stat().st_size for p in dist.rglob("*") if p.is_file())
    print(f"dist: {dist}  {total / 1024 / 1024:.1f} MB")
    print("预览：cd dist && python -m http.server 8080")
    return 0


if __name__ == "__main__":
    sys.exit(main())
