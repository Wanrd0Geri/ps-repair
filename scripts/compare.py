#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compare.py —— 验收用的 ffmpeg 封装（只用标准库；本机没有 PIL/ImageMagick）。

子命令（结果都以 JSON 打印到 stdout）：
  tiles        <图> --grid 3x2 --out <目录>              切成 列x行 块，原尺寸，文件名 tile_r<行>_c<列>.png
  zoom         <图> --rect l,t,r,b --scale 4 [--grid 10] --out <文件>
                                                          裁切 + 最近邻放大；--grid N 每 N 个原图像素画一条线，
                                                          上边/左边标原图坐标（用于读坐标、定选区）
  hstack       <前> <后> --out <文件> [--rect l,t,r,b] [--scale 2]   前后对比并排（可先裁同一区域）
  psnr_outside <前> <后> --rect l,t,r,b [--rect ...]     修改区（可多个矩形）之外的 PSNR；期望 inf
  diffbox      <前> <后>                                  变化像素的外接框（没有变化时为 null）

坐标一律是原图像素，左上角原点，right/bottom 不含。
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

def find_tool(name):
    """按顺序找：PATH（Windows 上 which 会补 .exe）→ 环境变量 FFMPEG_DIR → macOS 常见位置。找不到返回裸名，运行时报错。"""
    hit = shutil.which(name)
    if hit:
        return hit
    dirs = [os.environ.get("FFMPEG_DIR", ""), "/opt/homebrew/bin", "/usr/local/bin"]
    for d in dirs:
        if not d:
            continue
        for fn in (name + ".exe", name):
            cand = os.path.join(d, fn)
            if os.path.isfile(cand):
                return cand
    return name


FFMPEG = find_tool("ffmpeg")
FFPROBE = find_tool("ffprobe")


def run_ff(args, check=True):
    p = subprocess.run([FFMPEG, "-hide_banner", "-nostats", "-y"] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        raise RuntimeError("ffmpeg 失败：%s" % p.stderr.strip()[-600:])
    return p.stderr


def size_of(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0:s=x", path],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout.strip()
    w, h = out.split("x")[:2]
    return int(w), int(h)


def parse_rect(s):
    if isinstance(s, (list, tuple)):
        v = [int(round(float(x))) for x in s]
    else:
        v = [int(round(float(x))) for x in re.split(r"[,\s]+", s.strip()) if x]
    if len(v) != 4 or v[2] <= v[0] or v[3] <= v[1]:
        raise ValueError("rect 需要 l,t,r,b 且 r>l、b>t：%r" % (s,))
    return v


def clamp_rect(r, w, h):
    l, t, rr, b = max(0, r[0]), max(0, r[1]), min(w, r[2]), min(h, r[3])
    if rr <= l or b <= t:
        raise ValueError("rect 完全在图外：%r（图 %dx%d）" % (r, w, h))
    return [l, t, rr, b]


# ---------- tiles ----------
def tiles(img, grid, out_dir):
    cols, rows = [int(x) for x in grid.lower().split("x")]
    w, h = size_of(img)
    os.makedirs(out_dir, exist_ok=True)
    items = []
    for r in range(rows):
        for c in range(cols):
            l, rr = w * c // cols, w * (c + 1) // cols
            t, b = h * r // rows, h * (r + 1) // rows
            out = os.path.join(out_dir, "tile_r%d_c%d.png" % (r, c))
            run_ff(["-i", img, "-vf", "crop=%d:%d:%d:%d" % (rr - l, b - t, l, t), "-frames:v", "1", out])
            items.append({"path": out, "rect": [l, t, rr, b]})
    return {"image": img, "size": [w, h], "grid": [cols, rows], "tiles": items}


# ---------- zoom（含坐标标注：ffmpeg 没有 drawtext，用 3x5 点阵数字自己画） ----------
FONT = {"0": ["111", "101", "101", "101", "111"], "1": ["010", "110", "010", "010", "111"],
        "2": ["111", "001", "111", "100", "111"], "3": ["111", "001", "111", "001", "111"],
        "4": ["101", "101", "111", "001", "001"], "5": ["111", "100", "111", "001", "111"],
        "6": ["111", "100", "111", "101", "111"], "7": ["111", "001", "001", "001", "001"],
        "8": ["111", "101", "111", "101", "111"], "9": ["111", "101", "111", "001", "111"],
        "-": ["000", "000", "111", "000", "000"]}
DOT = 2  # 每个点阵像素画成 2x2


def draw_text(buf, W, H, x, y, text, rgba=(200, 0, 0, 255)):
    for i, ch in enumerate(text):
        glyph = FONT.get(ch)
        if not glyph:
            continue
        ox = x + i * 4 * DOT
        for gy, row in enumerate(glyph):
            for gx, bit in enumerate(row):
                if bit != "1":
                    continue
                for dy in range(DOT):
                    for dx in range(DOT):
                        px, py = ox + gx * DOT + dx, y + gy * DOT + dy
                        if 0 <= px < W and 0 <= py < H:
                            o = (py * W + px) * 4
                            buf[o:o + 4] = bytes(rgba)


def zoom(img, rect, scale, grid, out):
    w, h = size_of(img)
    l, t, r, b = clamp_rect(parse_rect(rect), w, h)
    cw, ch, s = r - l, b - t, int(scale)
    ZW, ZH = cw * s, ch * s
    vf = "crop=%d:%d:%d:%d,scale=%d:%d:flags=neighbor,format=rgba" % (cw, ch, l, t, ZW, ZH)
    if not grid:
        run_ff(["-i", img, "-vf", vf, "-frames:v", "1", out])
        return {"out": out, "rect": [l, t, r, b], "scale": s, "size": [ZW, ZH]}
    g = int(grid)
    TOP, LEFT = 14, 6 * 4 * DOT  # 标注边距
    W, H = ZW + LEFT, ZH + TOP
    # 网格线：在放大图上画（原图每 g 像素一条，从能被 g 整除的坐标开始）
    lines = []
    xs = list(range(((l + g - 1) // g) * g, r, g))
    ys = list(range(((t + g - 1) // g) * g, b, g))
    for gx in xs:
        lines.append("drawbox=x=%d:y=0:w=1:h=%d:color=red@0.55:t=fill" % ((gx - l) * s, ZH))
    for gy in ys:
        lines.append("drawbox=x=0:y=%d:w=%d:h=1:color=red@0.55:t=fill" % ((gy - t) * s, ZW))
    labels = bytearray(W * H * 4)
    step = max(1, int(math.ceil(28.0 / (g * s))))  # 标签太挤时隔几条标一次
    for i, gx in enumerate(xs):
        if i % step == 0:
            draw_text(labels, W, H, LEFT + (gx - l) * s + 2, 2, str(gx))
    for i, gy in enumerate(ys):
        if i % step == 0:
            draw_text(labels, W, H, 1, TOP + (gy - t) * s + 2, str(gy))
    with tempfile.TemporaryDirectory() as td:
        raw = os.path.join(td, "labels.rgba")
        with open(raw, "wb") as f:
            f.write(labels)
        chain = ",".join([vf] + lines + ["pad=%d:%d:%d:%d:color=white" % (W, H, LEFT, TOP)])
        run_ff(["-i", img, "-f", "rawvideo", "-pix_fmt", "rgba", "-s", "%dx%d" % (W, H), "-i", raw,
                "-filter_complex", "[0:v]%s[z];[z][1:v]overlay=0:0:format=auto" % chain,
                "-frames:v", "1", out])
    return {"out": out, "rect": [l, t, r, b], "scale": s, "grid": g, "size": [W, H],
            "note": "标注边距：上 %dpx、左 %dpx；原图坐标 = rect 左上 + (放大图坐标 - 边距) / scale" % (TOP, LEFT)}


# ---------- hstack ----------
def hstack(a, b, out, rect=None, scale=1):
    wa, ha = size_of(a)
    wb, hb = size_of(b)
    pre = []
    if rect:
        l, t, r, bb = clamp_rect(parse_rect(rect), min(wa, wb), min(ha, hb))
        pre.append("crop=%d:%d:%d:%d" % (r - l, bb - t, l, t))
    if int(scale) != 1:
        pre.append("scale=iw*%d:ih*%d:flags=neighbor" % (int(scale), int(scale)))
    pre.append("format=rgb24")
    chain = ",".join(pre)
    fc = ("[0:v]%s,pad=iw+6:ih:0:0:color=white[a];[1:v]%s[b];[a][b]hstack=inputs=2" % (chain, chain))
    run_ff(["-i", a, "-i", b, "-filter_complex", fc, "-frames:v", "1", out])
    return {"out": out, "before": a, "after": b, "rect": rect and parse_rect(rect), "scale": int(scale)}


# ---------- 像素比较 ----------
def _masked_chain(rects):
    boxes = ["drawbox=x=%d:y=%d:w=%d:h=%d:color=black:t=fill" % (r[0], r[1], r[2] - r[0], r[3] - r[1]) for r in rects]
    return ",".join(["format=rgba"] + boxes)


def psnr_outside(a, b, rects):
    rects = [parse_rect(r) for r in rects]
    if size_of(a) != size_of(b):
        raise ValueError("两张图尺寸不同：%s vs %s" % (size_of(a), size_of(b)))
    chain = _masked_chain(rects)
    err = run_ff(["-i", a, "-i", b, "-lavfi", "[0:v]%s[x];[1:v]%s[y];[x][y]psnr" % (chain, chain), "-f", "null", "-"])
    m = re.search(r"average:(\S+)", err)
    if not m:
        raise RuntimeError("没读到 PSNR：" + err[-400:])
    val = m.group(1)
    psnr = float("inf") if val == "inf" else float(val)
    return {"psnr": "inf" if math.isinf(psnr) else round(psnr, 3), "identical_outside": math.isinf(psnr),
            "rects": rects}


def diffbox(a, b):
    if size_of(a) != size_of(b):
        raise ValueError("两张图尺寸不同")
    lut = "if(gt(val\\,0)\\,255\\,0)"
    fc = ("[0:v]format=rgb24[x];[1:v]format=rgb24[y];[x][y]blend=all_mode=difference,"
          "lutrgb=r=%s:g=%s:b=%s,format=gray,bbox=min_val=1" % (lut, lut, lut))
    err = run_ff(["-i", a, "-i", b, "-filter_complex", fc, "-f", "null", "-"])
    m = re.search(r"x1:(\d+) x2:(\d+) y1:(\d+) y2:(\d+)", err)
    if not m:
        return {"changed": False, "bbox": None}
    x1, x2, y1, y2 = [int(v) for v in m.groups()]
    return {"changed": True, "bbox": [x1, y1, x2 + 1, y2 + 1]}


def main():
    ap = argparse.ArgumentParser(description="ps-repair 验收用 ffmpeg 封装")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("tiles"); p.add_argument("img"); p.add_argument("--grid", default="3x2"); p.add_argument("--out", required=True)
    p = sub.add_parser("zoom"); p.add_argument("img"); p.add_argument("--rect", required=True)
    p.add_argument("--scale", type=int, default=4); p.add_argument("--grid", type=int, default=0); p.add_argument("--out", required=True)
    p = sub.add_parser("hstack"); p.add_argument("before"); p.add_argument("after"); p.add_argument("--out", required=True)
    p.add_argument("--rect"); p.add_argument("--scale", type=int, default=1)
    p = sub.add_parser("psnr_outside"); p.add_argument("before"); p.add_argument("after")
    p.add_argument("--rect", action="append", required=True)
    p = sub.add_parser("diffbox"); p.add_argument("before"); p.add_argument("after")
    ns = ap.parse_args()
    try:
        if ns.cmd == "tiles":
            res = tiles(ns.img, ns.grid, ns.out)
        elif ns.cmd == "zoom":
            res = zoom(ns.img, ns.rect, ns.scale, ns.grid, ns.out)
        elif ns.cmd == "hstack":
            res = hstack(ns.before, ns.after, ns.out, ns.rect, ns.scale)
        elif ns.cmd == "psnr_outside":
            res = psnr_outside(ns.before, ns.after, ns.rect)
        else:
            res = diffbox(ns.before, ns.after)
        print(json.dumps(dict(ok=True, **res), ensure_ascii=False))
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)
    except OSError as e:  # 含 FileNotFoundError：没装 ffmpeg/ffprobe，或输出目录写不进
        msg = str(e)
        if getattr(e, "filename", None) in (FFMPEG, FFPROBE):
            msg = "找不到或无法运行 %s：装好后加进 PATH，或设环境变量 FFMPEG_DIR 指向其所在目录" % e.filename
        print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
