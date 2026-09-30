#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_tests.py —— macOS（osascript）与 Windows（COM）通用：在 Photoshop 里新建 800×600 合成文档，依次跑配方并断言，最后关闭不保存。

断言：结果 ok、产出图层（“修_”前缀）、蒙版存在、修改区外像素不变（导出前后 PSNR=inf）、修改区内确有变化。
不跑 generative_fill（扣积分），只对它做语法检查。
用法：python3 -X utf8 tests/run_tests.py [--keep] [--skip-tier2] [--skip-timeout] [--syntax-only]
  --syntax-only 只跑配方语法检查和 psrun 用法报错两项，不碰 PS（PS 关着也能跑；没有 node 时语法检查记为跳过）。
退出码：有 FAIL 时为 1。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent)
IS_WIN = sys.platform == "win32"
PSRUN = os.path.join(ROOT, "scripts", "psrun.py")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import compare  # noqa: E402

W, H = 800, 600
PREFIX = "修_"


def ps(recipe=None, args=None, jsx=None, timeout=300, extra=None):
    cmd = [sys.executable, PSRUN] + ([recipe] if recipe else ["--jsx", jsx])
    cmd += ["--args", json.dumps(args or {}, ensure_ascii=False), "--timeout", str(timeout)] + (extra or [])
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        res = json.loads(p.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        res = {"ok": False, "error": "psrun 输出无法解析：%s %s" % (p.stdout[-300:], p.stderr[-300:])}
    res["_rc"] = p.returncode
    return res


def grow(rect, m):
    return [max(0, rect[0] - m), max(0, rect[1] - m), min(W, rect[2] + m), min(H, rect[3] + m)]


def near(a, b, tol=1):
    return a is not None and b is not None and all(abs(x - y) <= tol for x, y in zip(a, b))


class Fail(Exception):
    pass


def check(cond, msg):
    if not cond:
        raise Fail(msg)


class Suite:
    def __init__(self, keep):
        self.rows, self.doc, self.keep = [], None, keep
        self.tmp = tempfile.mkdtemp(prefix="psrepair-test-")
        self.n, self.last = 0, None
        self.ids = {}

    # ---------- 基础 ----------
    def call(self, recipe, args=None, **kw):
        a = dict(args or {})
        if self.doc is not None and "doc_id" not in a:
            a["doc_id"] = self.doc
        return ps(recipe, a, **kw)

    def ok(self, recipe, args=None, **kw):
        r = self.call(recipe, args, **kw)
        check(r.get("ok"), "%s 失败：%s" % (recipe, r.get("error")))
        return r["data"]

    def expect_error(self, recipe, args, code):
        r = self.call(recipe, args)
        check(not r.get("ok") and code in (r.get("error") or ""), "%s 应报 %s，实际：%s" % (recipe, code, r.get("error") or "ok"))
        check(r["_rc"] != 0, "失败时退出码应非 0")

    def export(self):
        self.n += 1
        path = os.path.join(self.tmp, "step%02d.png" % self.n)
        self.ok("export_png", {"path": path})
        return path

    def case(self, name, tier, fn):
        t0 = time.time()
        try:
            detail = fn() or ""
            status = "PASS"
        except Fail as e:
            status, detail = "FAIL", str(e)
        except Exception as e:  # noqa: BLE001
            status, detail = "FAIL", "异常：%s" % e
            traceback.print_exc()
        if status == "FAIL":
            self.last = None  # 失败的用例可能留下半截状态，下一个用例重新导出“修改前”
        self.rows.append((name, tier, status, int((time.time() - t0) * 1000), detail))
        print("  %-26s %-4s %-4s %s" % (name, tier, status, detail[:110]), flush=True)

    # 像素类/调整类通用断言：新“修_”图层 + 蒙版 + 区外不变 + 区内有变化
    def base(self):
        if self.last is None:
            self.last = self.export()
        return self.last

    def pixel_case(self, recipe, args, region, margin=2, expect_change=True, key=None):
        before = self.base()
        d = self.ok(recipe, args)
        check(d.get("name", "").startswith(PREFIX), "图层名应以“修_”开头：%s" % d.get("name"))
        check(d.get("has_mask") is True, "应带蒙版")
        after = self.export()
        allowed = grow(region, margin)
        out = compare.psnr_outside(before, after, [allowed])
        check(out["identical_outside"], "修改区外有变化 PSNR=%s（允许区 %s）" % (out["psnr"], allowed))
        db = compare.diffbox(before, after)
        if expect_change:
            check(db["changed"], "修改区内没有变化")
        self.last = after
        if key:
            self.ids[key] = d["id"]
        return "layer=%s bbox=%s" % (d["id"], db["bbox"])

    # ---------- 用例 ----------
    def run(self, skip_tier2, skip_timeout, syntax_only=False):
        print("临时目录：%s" % self.tmp)
        self.case("syntax_check(all)", "-", self.t_syntax)
        self.case("psrun_usage_errors", "-", self.t_usage)
        if syntax_only:
            return
        pre = ps("inspect", {})
        pre_docs = [d["id"] for d in (pre.get("data") or {}).get("documents", [])] if pre.get("ok") else []
        made = ps(jsx=os.path.join(ROOT, "tests", "make_test_doc.jsx"))
        if not made.get("ok"):
            self.rows.append(("make_test_doc", "-", "FAIL", 0, str(made.get("error"))))
            return
        self.doc = made["data"]["id"]
        self.bg = made["data"]["layers"][-1]["id"]
        print("测试文档 doc_id=%s（用户已开文档：%s）" % (self.doc, pre_docs or "无"))
        try:
            self.tier1()
            if not skip_tier2:
                self.tier2()
            if not skip_timeout:
                self.case("psrun_ae_timeout_poll", "-", self.t_timeout)
        finally:
            r = ps("close_doc", {"doc_id": self.doc})
            print("关闭测试文档：%s" % ("ok" if r.get("ok") else r.get("error")))
            post = ps("inspect", {})
            post_docs = [d["id"] for d in (post.get("data") or {}).get("documents", [])] if post.get("ok") else []
            self.rows.append(("user_docs_untouched", "-", "PASS" if set(pre_docs) <= set(post_docs) else "FAIL", 0,
                              "测试前已开文档 %s 仍在" % pre_docs))

    def tier1(self):
        c = self.case
        c("inspect", 1, self.t_inspect)
        c("export_png", 1, self.t_export)
        c("select_rect", 1, lambda: self.sel("select_rect", {"rect": [350, 150, 390, 190]}, [350, 150, 390, 190], 0))
        c("select_polygon", 1, lambda: self.sel("select_polygon", {"points": [[100, 300], [200, 300], [150, 380]]}, [100, 300, 200, 380], 1))
        c("select_modify", 1, self.t_modify)
        c("selection_save_channel", 1, self.t_save_channel)
        c("selection_load_channel", 1, lambda: self.sel("selection_load_channel", {"name": "测试通道"}, [500, 300, 640, 440], 0))
        c("select_sky", 1, self.t_sky)
        c("select_color_range", 1, self.t_color_range)
        c("select_subject", 1, self.t_subject)
        c("content_aware_fill", 1, lambda: self.pixel_case("content_aware_fill", {
            "selection": {"rect": [346, 146, 394, 194]}, "expand_px": 2, "label": "白框", "layer_id": self.bg},
            [346, 146, 394, 194], margin=3, key="caf"))
        c("fill_layer_solid", 1, lambda: self.pixel_case("fill_layer_solid", {
            "rgb": [20, 30, 90], "selection": {"rect": [600, 40, 760, 120]}, "blend": "multiply", "opacity": 50,
            "feather_px": 3, "label": "压暗"}, [600, 40, 760, 120], margin=12, key="solid"))
        c("adj_curves", 1, lambda: self.pixel_case("adj_curves", {
            "points": [[128, 170]], "selection": {"rect": [20, 20, 120, 120]}}, [20, 20, 120, 120], key="curves"))
        c("adj_levels", 1, lambda: self.pixel_case("adj_levels", {
            "output_black": 40, "gamma": 1.2, "selection": {"rect": [130, 20, 230, 120]}}, [130, 20, 230, 120]))
        c("adj_color_balance", 1, lambda: self.pixel_case("adj_color_balance", {
            "midtones": [30, 0, -30], "selection": {"rect": [240, 20, 340, 120]}}, [240, 20, 340, 120]))
        c("adj_hue_sat", 1, lambda: self.pixel_case("adj_hue_sat", {
            "hue": 30, "saturation": -30, "selection": {"rect": [420, 20, 520, 120]}}, [420, 20, 520, 120]))
        c("adj_hue_sat(colorize)", 1, lambda: self.pixel_case("adj_hue_sat", {
            "colorize": True, "hue": 200, "saturation": 40, "selection": {"rect": [310, 450, 430, 590]}}, [310, 450, 430, 590]))
        c("adj_brightness_contrast", 1, lambda: self.pixel_case("adj_brightness_contrast", {
            "brightness": 40, "contrast": 20, "selection": {"rect": [20, 130, 120, 230]}}, [20, 130, 120, 230]))
        c("filter_smart_blur", 1, lambda: self.pixel_case("filter_smart_blur", {
            "radius": 4, "threshold": 40, "selection": {"rect": [20, 300, 120, 400]}, "layer_id": self.bg,
            "expand_px": 2, "feather_px": 2}, [20, 300, 120, 400], margin=10))
        c("filter_surface_blur", 1, lambda: self.pixel_case("filter_surface_blur", {
            "radius": 6, "threshold": 30, "selection": {"rect": [130, 300, 230, 400]}, "layer_id": self.bg},
            [130, 300, 230, 400]))
        c("filter_gaussian_blur", 1, lambda: self.pixel_case("filter_gaussian_blur", {
            "radius": 3, "selection": {"polygon": [[240, 300], [340, 300], [290, 400]]}, "layer_id": self.bg},
            [240, 300, 340, 400]))
        c("filter_add_noise", 1, lambda: self.pixel_case("filter_add_noise", {
            "amount": 8, "selection": {"rect": [350, 300, 450, 400]}, "layer_id": self.bg}, [350, 300, 450, 400]))
        c("filter_high_pass", 1, lambda: self.pixel_case("filter_high_pass", {
            "radius": 3, "selection": {"rect": [490, 290, 650, 450]}, "layer_id": self.bg},
            [490, 290, 650, 450], key="hp"))
        c("mask_from_selection", 1, self.t_mask_from_selection)
        c("mask_set", 1, self.t_mask_set)
        c("layer_ops", 1, self.t_layer_ops)
        c("place_image", 1, self.t_place)
        c("duplicate_doc+close_doc", 1, self.t_dup_close)
        c("save_copy_psd", 1, self.t_save_psd)

    def tier2(self):
        c = self.case
        c("filter_lens_blur", 2, lambda: self.pixel_case("filter_lens_blur", {
            "radius": 12, "selection": {"rect": [660, 300, 780, 420]}, "layer_id": self.bg},
            [660, 300, 780, 420]))
        c("fill_layer_gradient", 2, lambda: self.pixel_case("fill_layer_gradient", {
            "from_rgb": [235, 238, 245], "from_opacity": 0, "to_opacity": 80, "angle": 90,
            "selection": {"rect": [0, 130, 800, 250]}, "label": "雾"}, [0, 130, 800, 250]))
        c("adj_selective_color", 2, lambda: self.pixel_case("adj_selective_color", {
            "colors": {"reds": [60, 0, 0, 0]}, "selection": {"rect": [520, 320, 620, 420]}}, [520, 320, 620, 420]))
        c("adj_photo_filter", 2, lambda: self.pixel_case("adj_photo_filter", {
            "density": 60, "selection": {"rect": [120, 450, 300, 590]}}, [120, 450, 300, 590]))
        c("camera_raw", 2, lambda: self.pixel_case("camera_raw", {
            "dehaze": 40, "clarity": 30, "exposure": 0.4, "selection": {"rect": [0, 450, 110, 590]},
            "layer_id": self.bg}, [0, 450, 110, 590]))

    # ---------- 具体用例 ----------
    def t_syntax(self):
        names = [f[:-4] for f in sorted(os.listdir(os.path.join(ROOT, "recipes"))) if f.endswith(".jsx") and not f.startswith("_")]
        bad = []
        for n in names:
            r = ps(n, {}, extra=["--check"])
            if not r.get("ok"):
                bad.append("%s: %s" % (n, r.get("error")))
            elif not (r.get("data") or {}).get("checked"):
                return "没有 node，跳过（%d 个配方）" % len(names)
        check(not bad, "; ".join(bad))
        return "%d 个配方语法通过（含 generative_fill，未运行）" % len(names)

    def t_usage(self):
        r = ps("no_such_recipe", {})
        check(not r["ok"] and r["_rc"] == 2 and "USAGE" in r["error"], "未知配方应返回 USAGE 且退出码 2")
        p = subprocess.run([sys.executable, PSRUN, "inspect", "--args", "{bad"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        check(p.returncode == 2 and json.loads(p.stdout)["ok"] is False, "坏 JSON 应返回退出码 2")
        return "未知配方/坏参数 → ok=false，退出码 2"

    def t_inspect(self):
        d = self.ok("inspect", {})
        doc = d["document"]
        check(doc["id"] == self.doc and doc["width"] == W and doc["height"] == H, "文档信息不符")
        check(doc["layer_count"] == 1 and doc["layers"][0]["is_background"], "应只有背景层")
        check(doc["trial"] is True, "测试文档应识别为试做文档")
        return "layers=%d profile=%s" % (doc["layer_count"], doc["profile"])

    def t_export(self):
        self.last = self.export()
        check(compare.size_of(self.last) == (W, H), "导出尺寸不对")
        self.expect_error("export_png", {"path": self.last}, "OUTPUT_EXISTS")
        return "800x600，已存在路径拒绝覆盖"

    def sel(self, recipe, args, expect, tol):
        d = self.ok(recipe, args)
        check(near(d["bounds"], expect, tol), "选区 %s，期望 %s" % (d["bounds"], expect))
        return "bounds=%s" % d["bounds"]

    def t_modify(self):
        self.ok("select_rect", {"rect": [100, 100, 200, 200]})
        d = self.ok("select_modify", {"op": "expand", "px": 5})
        check(near(d["bounds"], [95, 95, 205, 205], 1), "expand 后 %s" % d["bounds"])
        d = self.ok("select_modify", {"op": "contract", "px": 5})
        check(near(d["bounds"], [100, 100, 200, 200], 1), "contract 后 %s" % d["bounds"])
        d = self.ok("select_modify", {"ops": [{"op": "smooth", "px": 2}, {"op": "feather", "px": 2}]})
        check(d["bounds"][0] < 100 and d["bounds"][2] > 200, "feather 后软边应外延：%s" % d["bounds"])
        d = self.ok("select_modify", {"op": "invert"})
        check(d["bounds"] == [0, 0, W, H], "invert 后 %s" % d["bounds"])
        d = self.ok("select_modify", {"op": "deselect"})
        check(d["bounds"] is None, "deselect 后应无选区")
        self.expect_error("select_modify", {"op": "expand", "px": 3}, "NO_SELECTION")
        return "expand/contract/feather/invert/deselect"

    def t_save_channel(self):
        self.ok("select_rect", {"rect": [500, 300, 640, 440]})
        d = self.ok("selection_save_channel", {"name": "测试通道"})
        check(d["channel"] == "测试通道", "通道名不符")
        self.expect_error("selection_save_channel", {"name": "测试通道"}, "CHANNEL_EXISTS")
        self.ok("selection_save_channel", {"name": "测试通道", "overwrite": True})
        insp = self.ok("inspect", {})["document"]
        check(any(ch["name"] == "测试通道" for ch in insp["alpha_channels"]), "inspect 看不到通道")
        self.ok("select_modify", {"op": "deselect"})
        return "新建/重名报错/覆盖"

    def t_sky(self):
        d = self.ok("select_sky", {})
        check(d["found"] and d["bounds"][1] == 0 and d["bounds"][3] <= 350, "天空选区 %s" % d["bounds"])
        return "bounds=%s" % d["bounds"]

    def t_color_range(self):
        d = self.ok("select_color_range", {"sample_rgb": [200, 40, 40], "fuzziness": 40})
        check(near(d["bounds"], [500, 300, 640, 440], 2), "红方块 %s" % d["bounds"])
        d2 = self.ok("select_color_range", {"sample_rgb": [[230, 200, 40], [220, 190, 50]], "fuzziness": 30})
        check(near(d2["bounds"], [140, 360, 260, 480], 3), "黄圆 %s" % d2["bounds"])
        d3 = self.ok("select_color_range", {"preset": "highlights"})
        check(d3["found"], "高光预设没有选中任何像素")
        self.ok("select_rect", {"rect": [480, 280, 560, 460]})
        d4 = self.ok("select_color_range", {"sample_rgb": [200, 40, 40], "fuzziness": 40, "within_selection": True})
        check(near(d4["bounds"], [500, 300, 560, 440], 2), "within_selection 应只在左半边：%s" % d4["bounds"])
        self.ok("select_modify", {"op": "deselect"})
        return "红=%s 黄=%s 高光=%s 选区内=%s" % (d["bounds"], d2["bounds"], d3["bounds"], d4["bounds"])

    def t_subject(self):
        d = self.ok("select_subject", {})
        check(d["found"], "没识别到主体")
        self.ok("select_modify", {"op": "deselect"})
        return "bounds=%s" % d["bounds"]

    def t_mask_from_selection(self):
        before = self.base()
        d = self.ok("mask_from_selection", {"layer_id": self.ids["caf"], "selection": {"rect": [300, 100, 440, 240]}, "replace": True})
        check(d["has_mask"] and near(d["bounds"], [300, 100, 440, 240], 1), "新蒙版范围 %s" % d["bounds"])
        self.expect_error("mask_from_selection", {"layer_id": self.ids["caf"], "selection": {"rect": [0, 0, 10, 10]}}, "MASK_EXISTS")
        self.expect_error("mask_from_selection", {"layer_id": self.bg, "selection": {"rect": [0, 0, 10, 10]}}, "PROTECTED_LAYER")
        after = self.export()
        out = compare.psnr_outside(before, after, [[0, 0, 1, 1]])
        check(out["identical_outside"], "副本在填充区外与原图相同，重建更大的蒙版不应改变合成（PSNR=%s）" % out["psnr"])
        self.last = after
        return "重建蒙版 + MASK_EXISTS + PROTECTED_LAYER"

    def t_mask_set(self):
        lid = self.ids["solid"]
        base = self.base()
        d = self.ok("mask_set", {"layer_id": lid, "feather_px": 6})
        check(d["mask"]["feather"] == 6, "羽化读回 %s" % d["mask"])
        d = self.ok("mask_set", {"layer_id": lid, "density": 50})
        check(d["mask"]["density"] == 50, "浓度读回 %s" % d["mask"])
        d = self.ok("mask_set", {"layer_id": lid, "density": 100, "feather_px": 3})
        check(d["mask"]["density"] == 100 and d["mask"]["feather"] == 3, "同时设两个属性读回 %s" % d["mask"])
        d = self.ok("mask_set", {"layer_id": lid, "enabled": False})
        check(d["mask"]["enabled"] is False, "停用读回 %s" % d["mask"])
        off = self.export()
        check(compare.diffbox(base, off)["changed"], "停用蒙版后合成应变化")
        self.ok("mask_set", {"layer_id": lid, "enabled": True})
        self.ok("mask_set", {"layer_id": lid, "invert": True})
        self.ok("mask_set", {"layer_id": lid, "invert": True})
        back = self.export()
        check(not compare.diffbox(base, back)["changed"], "恢复原属性、两次反相后合成应与之前逐位相同")
        self.expect_error("mask_set", {"layer_id": self.bg, "density": 50}, "PROTECTED_LAYER")
        self.last = back
        return "feather/density/enabled/invert 读回一致，可逆"

    def t_layer_ops(self):
        lid = self.ids["curves"]
        base = self.base()
        d = self.ok("layer_ops", {"ops": [
            {"op": "rename", "layer_id": lid, "name": "曲线改名"},
            {"op": "opacity", "layer_id": lid, "value": 30},
            {"op": "blend", "layer_id": lid, "mode": "screen"},
            {"op": "visible", "layer_id": lid, "value": False}]})["results"]
        # 不透明度按 0-255 存，30% 读回 30.2
        check(d[0]["name"] == "修_曲线改名" and abs(d[1]["opacity"] - 30) < 0.5 and d[2]["blend"] == "screen" and d[3]["visible"] is False,
              "rename/opacity/blend/visible 读回不符：%s" % [(x["name"], x["opacity"], x["blend"], x["visible"]) for x in d])
        hidden = self.export()
        db = compare.diffbox(base, hidden)
        check(db["changed"] and near(db["bbox"], [20, 20, 120, 120], 1), "隐藏曲线层只应影响其蒙版区：%s" % db["bbox"])
        self.ok("layer_ops", {"ops": [{"op": "visible", "layer_id": lid, "value": True},
                                      {"op": "opacity", "layer_id": lid, "value": 100},
                                      {"op": "blend", "layer_id": lid, "mode": "normal"}]})
        restored = self.export()
        check(not compare.diffbox(base, restored)["changed"], "恢复后合成应与之前逐位相同")
        self.ok("layer_ops", {"op": "move", "layer_id": lid, "to": "top"})
        top = self.ok("inspect", {})["document"]["layers"][0]["id"]
        check(top == lid, "move top 后顶层是 %s" % top)
        self.ok("layer_ops", {"op": "move", "layer_id": lid, "to": "below", "ref_layer_id": self.ids["hp"]})
        self.ok("layer_ops", {"op": "move", "layer_id": lid, "to": "bottom"})
        layers = self.ok("inspect", {})["document"]["layers"]
        check(layers[-2]["id"] == lid, "move bottom 后应在背景层正上方")
        self.ok("layer_ops", {"op": "select", "layer_id": self.bg})
        self.expect_error("layer_ops", {"op": "delete", "layer_id": self.bg}, "PROTECTED_LAYER")
        self.expect_error("layer_ops", {"op": "rename", "layer_id": self.bg, "name": "x"}, "PROTECTED_LAYER")
        d = self.ok("layer_ops", {"op": "delete", "layer_id": self.ids["hp"]})["results"][0]
        check(d.get("deleted"), "删除返回不符")
        ids = [l["id"] for l in self.ok("inspect", {})["document"]["layers"]]
        check(self.ids["hp"] not in ids, "删除后图层仍在")
        self.last = self.export()
        return "rename/opacity/blend/visible/move/select/delete + 保护"

    def t_place(self):
        patch = os.path.join(self.tmp, "patch120x80.png")
        compare.run_ff(["-f", "lavfi", "-i", "testsrc2=size=120x80:rate=1", "-frames:v", "1", patch])
        before = self.base()
        d = self.ok("place_image", {"path": patch, "x": 640, "y": 480, "label": "补丁"})
        check(d["kind"] == "smartobject" and d["corners"] == [640, 480, 760, 560] and d["has_mask"], "1:1 放置 %s" % d.get("corners"))
        after = self.export()
        out = compare.psnr_outside(before, after, [[640, 480, 760, 560]])
        check(out["identical_outside"], "放置区外有变化 PSNR=%s" % out["psnr"])
        d2 = self.ok("place_image", {"path": patch, "x": 10, "y": 500, "width": 60, "selection": {"rect": [10, 500, 50, 530]}})
        check(d2["corners"] == [10, 500, 70, 540] and near(d2["bounds"], [10, 500, 50, 530], 0), "缩放放置 %s / %s" % (d2["corners"], d2["bounds"]))
        after2 = self.export()
        out2 = compare.psnr_outside(after, after2, [[10, 500, 50, 530]])
        check(out2["identical_outside"], "带选区蒙版的放置在蒙版外有变化")
        self.expect_error("place_image", {"path": "/nonexistent/x.png", "x": 0, "y": 0}, "FILE_NOT_FOUND")
        self.last = after2
        return "1:1 corners=%s；缩放 corners=%s" % (d["corners"], d2["corners"])

    def t_dup_close(self):
        d = self.ok("duplicate_doc", {})
        dup = d["id"]
        try:
            check(d["name"].startswith("试做_") and d["layer_count"] > 1, "副本 %s" % d)
        finally:
            r = ps("close_doc", {"doc_id": dup})
        check(r["ok"], "关闭副本失败：%s" % r.get("error"))
        r0 = ps("close_doc", {})  # 不经 self.call：它会自动补上测试文档的 doc_id
        check(not r0["ok"] and "BAD_ARG" in r0["error"], "不给 doc_id 应拒绝：%s" % r0.get("error"))
        g = ps(jsx=os.path.join(ROOT, "tests", "make_test_doc.jsx"), args={"name": "psrepair_guard_test"})
        check(g["ok"], "建保护测试文档失败")
        gid = g["data"]["id"]
        r1 = ps("close_doc", {"doc_id": gid})
        r2 = ps("close_doc", {"doc_id": gid, "force": True})
        check(not r1["ok"] and "PROTECTED_DOC" in r1["error"], "非试做文档不带 force 应拒绝关闭")
        check(r2["ok"], "force 关闭失败")
        return "副本 %s 已关闭；非试做文档需 force" % dup

    def t_save_psd(self):
        path = os.path.join(self.tmp, "copy.psd")
        d = self.ok("save_copy_psd", {"path": path})
        check(os.path.getsize(path) > 10000 and d["layer_count"] > 1, "PSD 太小或图层数不对")
        self.expect_error("save_copy_psd", {"path": path}, "OUTPUT_EXISTS")
        insp = self.ok("inspect", {})["document"]
        check(insp["path"] is None, "另存副本后文档不应指向新文件")
        return "%d 字节，%d 层" % (os.path.getsize(path), d["layer_count"])

    def t_timeout(self):
        src = os.path.join(self.tmp, "sleep.jsx")
        with open(src, "w", encoding="utf-8") as f:
            f.write("function run(args) { $.sleep(14000); return { slept: true }; }\n")
        t0 = time.time()
        r = ps(jsx=src, timeout=60, extra=["--ae-timeout", "10"])
        check(r["ok"] and r["data"].get("slept"), "超时轮询没拿到结果：%s" % r.get("error"))
        return "%s 10 s 超时后轮询到结果（共 %.1f s）" % ("COM 调用" if IS_WIN else "AppleEvent", time.time() - t0)

    # ---------- 汇总 ----------
    def report(self):
        print("\n%-3s %-26s %-4s %-5s %7s  %s" % ("#", "用例", "tier", "结果", "ms", "说明"))
        for i, (name, tier, st, ms, det) in enumerate(self.rows, 1):
            print("%-3d %-26s %-4s %-5s %7d  %s" % (i, name, tier, st, ms, det[:120]))
        fails = [r for r in self.rows if r[2] == "FAIL"]
        print("\n总计 %d 项：PASS %d，FAIL %d" % (len(self.rows), len(self.rows) - len(fails), len(fails)))
        if not fails and not self.keep:
            shutil.rmtree(self.tmp, ignore_errors=True)
        else:
            print("中间文件保留在 %s" % self.tmp)
        return 1 if fails else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="保留导出的中间 PNG")
    ap.add_argument("--skip-tier2", action="store_true")
    ap.add_argument("--skip-timeout", action="store_true", help="跳过 14 秒的 -1712 轮询测试")
    ap.add_argument("--syntax-only", action="store_true", help="只跑语法检查和用法报错两项，不碰 PS")
    ns = ap.parse_args()
    s = Suite(ns.keep)
    try:
        s.run(ns.skip_tier2, ns.skip_timeout, ns.syntax_only)
    except KeyboardInterrupt:
        print("中断")
    sys.exit(s.report())


if __name__ == "__main__":
    main()
