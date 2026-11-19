"""重建一个修好的 PSD：加脖子、补鞋子、把头发盖到脸上。

走 PSD 而不是层目录，是因为 image2live2d 的左右拆分（眼睛/手臂/腿）只在
「从 PSD 读」的路径上做；层目录模式一层就是一块，会丢掉 L/R 独立绑定。

脖子：原画里下巴直接压在衬衫领上，没有脖子。要造出脖子，只能把整体缩小一点
（腾出画面空间），再把头部往上、身体往下拉开，中间那段填皮肤。

脖子涂在 topwear 里而不是做成独立 neck 零件：image2live2d 的
normalize_neck_zorder() 会主动把 neck 压到衣服后面，独立零件永远露不出来。
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageFilter
from psd_tools import PSDImage

TASK = Path(
    r"D:\fengge-rag\live2d-build\live2d-ai-generator-main\workspace\20261118-213223-313287"
)
PSD = TASK / "decompose" / "layers.psd"
CLEAN = TASK / "preprocess" / "clean.png"
OUT = Path(r"D:\fengge-rag\live2d-build\fix-out")
OUT.mkdir(parents=True, exist_ok=True)

SCALE = 0.85      # 整体缩小，给脖子腾出上下空间
HEAD_SCALE = 0.90 # 头部再缩一圈（以下巴为轴心，不影响脖子长度）
HEAD_UP = 0      # 头部（脸/五官/头发/耳朵）上移
BODY_DOWN = 50    # 身体（西装/手臂/腿/鞋）下移

HEAD_PARTS = {"face", "mouth", "nose", "eyewhite", "irides", "eyebrow", "eyelash",
              "front hair", "ears"}
BODY_PARTS = {"topwear", "handwear", "legwear"}

ORDER = [
    "legwear",
    "shoe_l",
    "shoe_r",
    "handwear",
    "topwear",
    "ears",
    "face",
    "mouth",
    "nose",
    "eyewhite",
    "irides",
    "eyebrow",
    "eyelash",
    "front hair",
]


def scaled(img: Image.Image, xy: tuple[int, int], dx: int = 0, dy: int = 0):
    w = max(1, round(img.size[0] * SCALE))
    h = max(1, round(img.size[1] * SCALE))
    return img.resize((w, h), Image.LANCZOS), (
        round(xy[0] * SCALE + dx),
        round(xy[1] * SCALE + dy),
    )


def main() -> int:
    psd = PSDImage.open(PSD)
    canvas = psd.size
    layers = {}
    for layer in psd:
        img = layer.topil()
        if img is None:
            continue
        layers[layer.name] = (img.convert("RGBA"), (layer.bbox[0], layer.bbox[1]))

    cw, ch = canvas
    # 缩小后居中：x 方向水平和原来一样居中，y 方向顶部留白由 shrink 自然产生
    base_dx = round((cw - cw * SCALE) / 2)
    base_dy = round((ch - ch * SCALE) / 2)

    moved = {}
    for name, (img, xy) in layers.items():
        dx, dy = base_dx, base_dy
        if name in HEAD_PARTS:
            dy -= HEAD_UP
        elif name in BODY_PARTS:
            dy += BODY_DOWN
        moved[name] = scaled(img, xy, dx, dy)

    # ---- 头部再缩一圈：以下巴为轴心等比缩小，脖子长度不受影响
    if HEAD_SCALE != 1.0:
        fimg, (fx0, fy0) = moved["face"]
        a = fimg.split()[-1]
        fw0, fh0 = fimg.size
        chin0 = fy0 + fh0 - 1
        for y in range(fh0 - 1, -1, -1):
            if max(a.getpixel((x, y)) for x in range(0, fw0, 3)) > 40:
                chin0 = fy0 + y
                break
        pivot_x = round(512 * SCALE + base_dx)
        pivot_y = chin0
        for name in HEAD_PARTS:
            if name not in moved:
                continue
            img, xy = moved[name]
            nw = max(1, round(img.size[0] * HEAD_SCALE))
            nh = max(1, round(img.size[1] * HEAD_SCALE))
            img2 = img.resize((nw, nh), Image.LANCZOS)
            nx = round(pivot_x + (xy[0] - pivot_x) * HEAD_SCALE)
            ny = round(pivot_y + (xy[1] - pivot_y) * HEAD_SCALE)
            moved[name] = (img2, (nx, ny))

    topwear, (twx, twy) = moved["topwear"]
    face, (fx, fy) = moved["face"]

    # ---- 下巴底边 / 领口顶部（缩放 + 偏移后的坐标）
    alpha = face.split()[-1]
    fw, fh = face.size
    chin_local = 0
    for y in range(fh - 1, -1, -1):
        if max(alpha.getpixel((x, y)) for x in range(0, fw, 3)) > 40:
            chin_local = y
            break
    chin_y = fy + chin_local

    tw_px = topwear.load()
    # 领口 V 的顶部：topwear 中线附近第一行不透明
    collar_top = twy
    for y in range(topwear.size[1]):
        row = [tw_px[x, y][3] for x in range(topwear.size[0] // 3, 2 * topwear.size[0] // 3, 3)]
        if max(row) > 40:
            collar_top = twy + y
            break
    print(f"chin={chin_y} collar_top={collar_top} gap={collar_top - chin_y}")

    # ---- 脖子：从下巴往上藏一截，往下穿到领口里
    NECK_TOP = chin_y - 96
    NECK_BOT = collar_top + 34
    cx = round(512 * SCALE + base_dx)
    half_top, half_bot = 29, 54

    mask = Image.new("L", canvas, 0)
    mp = mask.load()
    falpha = face.split()[-1]
    fw2, fh2 = face.size
    mouth_img = layers.get("mouth", (None, (0, 0)))
    malpha = mouth_img[0].split()[-1] if mouth_img[0] is not None else None
    mimg, mxy = (scaled(mouth_img[0], mouth_img[1], base_dx, base_dy - HEAD_UP)
                 if malpha else (None, (0, 0)))
    mw2, mh2 = (malpha.size if malpha else (0, 0))

    def head_half(y: int) -> int:
        """脸 + 胡子在这一行的半宽并集。脖子不能比它宽，否则会从腮帮子边上探出来。"""
        spans = []
        row = y - fy
        if 0 <= row < fh2:
            xs = [x for x in range(0, fw2, 2) if falpha.getpixel((x, row)) > 40]
            if xs:
                spans.append((fy, max(xs) - min(xs)))
        if malpha is not None and mimg is not None:
            row_m = y - mxy[1]
            if 0 <= row_m < mh2:
                xs = [x for x in range(0, mw2, 2) if malpha.getpixel((x, row_m)) > 40]
                if xs:
                    spans.append((mxy[1], max(xs) - min(xs)))
        if not spans:
            return 0
        return max(s for _, s in spans) // 2

    def jaw_half(y: int) -> int:
        return head_half(y)

    # 头部轮廓（脸+胡子+耳朵），脖子只画在它外面 —— 这样"头顶住脖子"是构造保证的，
    # 不会在腮帮子旁边露出方角
    head_sil = Image.new("L", canvas, 0)
    for name in ("face", "mouth", "ears"):
        if name not in layers:
            continue
        img, xy = moved[name]
        a = img.split()[-1].point(lambda v: 255 if v > 40 else 0)
        head_sil.paste(255, (int(xy[0]), int(xy[1])), a)

    for y in range(NECK_TOP, NECK_BOT):
        t = (y - NECK_TOP) / max(1, NECK_BOT - NECK_TOP)
        half = 40 if t < 0.75 else round(40 + 6 * (t - 0.75) / 0.25)
        for x in range(cx - half, cx + half):
            if head_sil.getpixel((x, y)):
                continue                       # 被头挡住的部分不画
            edge = min(x - (cx - half), (cx + half) - 1 - x)
            a_side = min(255, int(255 * edge / 8)) if edge < 8 else 255
            sx, sy = x - twx, y - twy
            if not (0 <= sy < topwear.size[1] and 0 <= sx < topwear.size[0]):
                mp[x, y] = a_side                  # 西装没画到这里
                continue
            r, g, b, a = tw_px[sx, sy]
            if a < 200:
                mp[x, y] = a_side                  # 透明
            elif abs(r - 163) < 24 and abs(g - 157) < 24 and abs(b - 153) < 26:
                mp[x, y] = a_side                  # 领口那块灰洞
    mask = mask.filter(ImageFilter.MinFilter(3))
    mp = mask.load()
    box = mask.getbbox()
    print("neck mask", box)
    if not box:
        print("no neck mask", file=sys.stderr)
        return 1

    skin = face.getpixel((min(fw - 1, 60), fh // 2))[:3]
    patch = Image.new("RGBA", canvas, skin + (0,))
    pp = patch.load()
    span = max(1, box[3] - box[1])
    for y in range(canvas[1]):
        k = (y - box[1]) / span
        shade = 0.66 + 0.34 * min(1.0, k / 0.62)   # 下巴往下慢慢提亮
        col = tuple(min(255, int(c * shade)) for c in skin) + (255,)
        for x in range(canvas[0]):
            if mp[x, y]:
                pp[x, y] = col
    patch.putalpha(mask)

    body = Image.new("RGBA", canvas, (0, 0, 0, 0))
    body.alpha_composite(topwear, (twx, twy))
    body.alpha_composite(patch, (0, 0))
    bb = body.getbbox()
    moved["topwear"] = (body.crop(bb), bb[:2])

    # ---- 鞋子：从原图腿部下方切出来，按左右拆（跟着身体一起缩放/下移）
    clean = Image.open(CLEAN).convert("RGBA")
    legwear, (lx, ly) = layers["legwear"]
    clean_scale = clean.size[0] / cw
    band_top = int((ly + legwear.size[1]) * clean_scale) - 2
    band = clean.crop((0, band_top, clean.size[0], clean.size[1]))
    band = band.resize((cw, max(1, round(band.size[1] / clean_scale))), Image.LANCZOS)
    alpha_b = band.split()[-1].point(lambda v: 255 if v > 120 else 0)
    band.putalpha(alpha_b)
    cols = [0] * band.size[0]
    bp = alpha_b.load()
    for y in range(band.size[1]):
        for x in range(band.size[0]):
            if bp[x, y]:
                cols[x] += 1
    xs = [x for x, c in enumerate(cols) if c]
    x0, x1 = min(xs), max(xs)
    mid = (x0 + x1) // 2
    gap = min(range(mid - 30, mid + 30), key=lambda x: cols[x])
    shoe_y = round(band_top / clean_scale) + BODY_DOWN

    def shoe(a: int, b: int):
        piece = band.crop((a, 0, b, band.size[1]))
        bb2 = piece.getbbox()
        return piece.crop(bb2), (a + bb2[0], shoe_y + bb2[1])

    shoe_l, shoe_l_xy = shoe(x0, gap)
    shoe_r, shoe_r_xy = shoe(gap, x1 + 1)

    placed = dict(moved)
    placed["shoe_l"] = scaled(shoe_l, (shoe_l_xy[0] - 0, shoe_l_xy[1] - BODY_DOWN),
                              base_dx, base_dy + BODY_DOWN)
    placed["shoe_r"] = scaled(shoe_r, (shoe_r_xy[0] - 0, shoe_r_xy[1] - BODY_DOWN),
                              base_dx, base_dy + BODY_DOWN)
    print("shoes", placed["shoe_l"][1], placed["shoe_r"][1])

    out = PSDImage.new("RGBA", canvas)
    for name in ORDER:
        img, xy = placed[name]
        out.create_pixel_layer(img, name=name, top=int(xy[1]), left=int(xy[0]))
    dst = OUT / "layers_fixed.psd"
    out.save(dst)
    print("wrote", dst, dst.stat().st_size // 1024, "KB")

    comp = Image.new("RGBA", canvas, (245, 245, 248, 255))
    for name in ORDER:
        img, xy = placed[name]
        comp.alpha_composite(img, (int(xy[0]), int(xy[1])))
    shots = Path(r"D:\fengge-rag\live2d-build\shots")
    comp.convert("RGB").save(shots / "psd-composite.jpg", quality=88)
    top = max(0, chin_y - 120)
    comp.crop((cx - 150, top, cx + 150, top + 210)).resize((600, 420), Image.LANCZOS).convert(
        "RGB"
    ).save(shots / "psd-neck-zoom.jpg", quality=92)
    return 0


if __name__ == "__main__":
    sys.exit(main())
