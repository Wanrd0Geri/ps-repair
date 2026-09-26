#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""psrun.py —— 用 osascript 在本机 Photoshop 里跑 ps-repair 配方（recipes/*.jsx）或任意 jsx。

用法：
  python3 scripts/psrun.py <配方名> --args '<json>' [--timeout 900] [--app "Adobe Photoshop 2026"]
  python3 scripts/psrun.py --jsx <file.jsx> [--args '<json>']   任意脚本；没定义 run(args) 时整段 eval，
                                                               最后一个表达式的值放在 data.value
  python3 scripts/psrun.py --list                                列出配方与用途（不碰 PS）
  python3 scripts/psrun.py <配方名> --check                      只做语法检查（需要 node，不碰 PS）
  python3 scripts/psrun.py --poll <结果文件> [--timeout 600]      继续等待一次超时运行的结果

stdout 只打印一个 JSON：{"ok","recipe","data","error","elapsed_ms","history"}；失败时退出码非 0。
警告（Higgsfield MCP 锁、排队等待等）只写 stderr。

超时：AppleEvent 等 --ae-timeout 秒（默认 120）。超时报 -1712 时脚本仍在 PS 里跑，
runner 转为轮询结果文件，直到出现或到 --timeout（默认 900，从启动算起）。
"""
import argparse
import fcntl
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECIPES = os.path.join(ROOT, "recipes")
LIB = os.path.join(RECIPES, "_lib.jsx")
LOCK_PATH = os.path.join(tempfile.gettempdir(), "ps-repair-psrun.lock")
MCP_DIR = os.environ.get("ADOBE_MCP_CONFIG_DIR") or os.path.expanduser("~/.higgsfield-adobe")
MCP_LOCK = os.path.join(MCP_DIR, "photoshop.lock")
MCP_FRESH_SECONDS = 600


def eprint(*a):
    print(*a, file=sys.stderr, flush=True)


def emit(res, code=None):
    """打印唯一的 JSON（固定 6 个字段）并退出。"""
    shaped = {
        "ok": bool(res.get("ok")),
        "recipe": res.get("recipe"),
        "data": res.get("data"),
        "error": res.get("error"),
        "elapsed_ms": int(res.get("elapsed_ms") or 0),
        "history": res.get("history") or [],
    }
    print(json.dumps(shaped, ensure_ascii=False))
    sys.exit(code if code is not None else (0 if shaped["ok"] else 1))


# ---------- Photoshop 应用 ----------
def find_app(explicit=None):
    if explicit:
        return explicit
    bundles = glob.glob("/Applications/Adobe Photoshop */Adobe Photoshop *.app")
    names = sorted({os.path.basename(b)[:-4] for b in bundles})
    if not names:
        return None
    running = subprocess.run(["/bin/ps", "-axo", "command"], capture_output=True, text=True).stdout

    def score(n):
        m = re.search(r"(\d{4})", n)
        return ("/%s.app/Contents/MacOS/" % n in running, "Beta" not in n, int(m.group(1)) if m else 0)

    return max(names, key=score)


def app_running(app):
    out = subprocess.run(["/bin/ps", "-axo", "command"], capture_output=True, text=True).stdout
    return ("/%s.app/Contents/MacOS/" % app) in out


# ---------- 锁 ----------
def check_mcp_lock():
    if not os.path.exists(MCP_LOCK):
        return
    age = time.time() - os.path.getmtime(MCP_LOCK)
    if age < MCP_FRESH_SECONDS:
        eprint("警告：Higgsfield MCP 锁 %s 是 %d 秒前建的，MCP 可能正在驱动 Photoshop；"
               "两边不要同时操作（PS 会排队，但多步流程可能交错）。" % (MCP_LOCK, age))
    else:
        eprint("警告：存在陈旧的 Higgsfield MCP 锁 %s（%d 分钟前）。它表示 MCP 上次调用结果未知，"
               "MCP 会拒绝新调用；确认 PS 里没有脚本在跑之后再手动删除，本工具不会删它。" % (MCP_LOCK, age // 60))


def acquire_lock(deadline):
    fd = os.open(LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o600)
    warned = False
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            if not warned:
                eprint("另一个 psrun 正在驱动 Photoshop，排队等待……")
                warned = True
            if time.time() > deadline:
                os.close(fd)
                return None
            time.sleep(0.5)


# ---------- 拼脚本 ----------
def js_literal(obj):
    return json.dumps(obj, ensure_ascii=True)


def load_body(recipe=None, jsx=None):
    if jsx:
        with open(jsx, encoding="utf-8") as f:
            src = f.read()
        if re.search(r"\bfunction\s+run\s*\(", src):
            return src
        # 任意脚本：整段 eval，最后一个表达式的值放进 data.value
        return ("var __SRC__ = %s;\nfunction run(args) { var __v = eval(__SRC__); "
                "return { value: (__v === undefined ? null : __v) }; }\n" % js_literal(src))
    if not re.match(r"^[a-z0-9][a-z0-9_]*$", recipe or ""):
        raise ValueError("配方名只能是小写字母、数字、下划线：%r" % recipe)
    path = os.path.join(RECIPES, recipe + ".jsx")
    if not os.path.exists(path):
        raise ValueError("没有这个配方：%s（用 --list 查看）" % recipe)
    with open(path, encoding="utf-8") as f:
        return f.read()


def compose(body, args, result_path, recipe_label, body_name):
    with open(LIB, encoding="utf-8") as f:
        lib = f.read()
    header = ("(function () {\nvar __ARGS__ = %s;\nvar __RESULT_PATH__ = %s;\nvar __RECIPE__ = %s;\n"
              % (js_literal(args), js_literal(result_path), js_literal(recipe_label)))
    parts = [(header, "<header>"), (lib + "\n", "_lib.jsx"), (body + "\n", body_name),
             ("return __main();\n})();\n", "<footer>")]
    segments, line = [], 1
    for text, name in parts:
        n = text.count("\n")
        segments.append((line, line + n - 1, name))
        line += n
    return "".join(t for t, _ in parts), segments


def map_lines(msg, segments):
    """把错误里的行号（@line N / Line: N）换算成 文件:行。"""
    def where(n):
        for start, end, name in segments:
            if start <= n <= end:
                return "%s:%d" % (name, n - start + 1)
        return "?"

    def rep(m):
        return "%s (%s)" % (m.group(0), where(int(m.group(1))))

    msg = re.sub(r"@line (\d+)", rep, msg or "")
    return re.sub(r"Line: (\d+)", rep, msg)


def list_recipes():
    out = []
    for p in sorted(glob.glob(os.path.join(RECIPES, "*.jsx"))):
        name = os.path.basename(p)[:-4]
        if name.startswith("_"):
            continue
        purpose, status = "", ""
        with open(p, encoding="utf-8") as f:
            for ln in f:
                if not ln.startswith("//"):
                    break
                if "用途：" in ln and not purpose:
                    purpose = ln.split("用途：", 1)[1].strip()
                if "验证：" in ln and not status:
                    status = ln.split("验证：", 1)[1].strip()
        out.append({"name": name, "purpose": purpose, "status": status})
    return out


def syntax_check(script):
    node = shutil.which("node")
    if not node:
        return None, "没有 node，跳过语法检查"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(script)
        path = f.name
    try:
        p = subprocess.run([node, "--check", path], capture_output=True, text=True)
        return p.returncode == 0, p.stderr.strip()
    finally:
        os.unlink(path)


# ---------- 运行 ----------
def read_result(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return None


def poll_result(path, deadline, interval=2.0):
    while time.time() < deadline:
        res = read_result(path)
        if res is not None:
            return res
        time.sleep(interval)
    return read_result(path)


def run_script(app, script, result_path, timeout, ae_timeout, segments, label):
    t0 = time.time()
    deadline = t0 + timeout
    ae = int(max(10, min(ae_timeout, timeout)))
    cmd = ["/usr/bin/osascript",
           "-e", "on run argv",
           "-e", "with timeout of %d seconds" % ae,
           "-e", 'tell application "%s" to do javascript (item 1 of argv)' % app,
           "-e", "end timeout",
           "-e", "end run", script]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=ae + 30)
        rc, out, err = p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        rc, out, err = None, "", "osascript 子进程超时"
    res = read_result(result_path)
    if res is None and rc == 0 and out.startswith("{"):
        try:
            res = json.loads(out)
        except ValueError:
            res = None
    if res is None and (rc is None or "-1712" in err):
        eprint("AppleEvent 超时（-1712），脚本仍在 Photoshop 里运行；轮询结果文件 %s，最长到 --timeout……" % result_path)
        res = poll_result(result_path, deadline)
        if res is None:
            return {"ok": False, "recipe": label, "data": None,
                    "error": "TIMEOUT: %d 秒内没有结果；脚本可能仍在 PS 里运行，结果未知——不要盲目重试有副作用的配方，"
                             "先 inspect 文档；也可用 --poll %s 继续等待" % (timeout, result_path),
                    "elapsed_ms": int((time.time() - t0) * 1000), "history": [], "keep_run_dir": True}
    if res is None:
        return {"ok": False, "recipe": label, "data": None,
                "error": "OSASCRIPT_ERROR: " + map_lines(err or out or ("退出码 %s" % rc), segments),
                "elapsed_ms": int((time.time() - t0) * 1000), "history": []}
    if res.get("error"):
        res["error"] = map_lines(res["error"], segments)
    return res


def main():
    ap = argparse.ArgumentParser(description="在 Photoshop 里跑 ps-repair 配方")
    ap.add_argument("recipe", nargs="?", help="配方名（recipes/<名>.jsx）")
    ap.add_argument("--args", default="{}", help="JSON 参数")
    ap.add_argument("--jsx", help="跑任意 jsx 文件")
    ap.add_argument("--timeout", type=float, default=900, help="总等待秒数（默认 900）")
    ap.add_argument("--ae-timeout", type=float, default=120, help="AppleEvent 等待秒数，超时后改轮询（默认 120）")
    ap.add_argument("--app", help='应用名，如 "Adobe Photoshop 2026"；默认自动找')
    ap.add_argument("--list", action="store_true", help="列出配方")
    ap.add_argument("--check", action="store_true", help="只做语法检查（node），不碰 PS")
    ap.add_argument("--poll", help="等待某个结果文件")
    ap.add_argument("--keep-script", action="store_true", help="保留拼好的脚本（调试用）")
    ns = ap.parse_args()

    if ns.list:
        print(json.dumps(list_recipes(), ensure_ascii=False, indent=1))
        return
    if ns.poll:
        t0 = time.time()
        res = poll_result(ns.poll, t0 + ns.timeout)
        if res is None:
            emit({"ok": False, "recipe": None, "error": "TIMEOUT: 结果文件仍未出现 " + ns.poll,
                  "elapsed_ms": int((time.time() - t0) * 1000)})
        emit(res)

    label = ("jsx:" + os.path.basename(ns.jsx)) if ns.jsx else ns.recipe
    if not label:
        emit({"ok": False, "recipe": None, "error": "USAGE: 需要配方名或 --jsx"}, 2)
    try:
        args = json.loads(ns.args)
        if not isinstance(args, dict):
            raise ValueError("--args 必须是 JSON 对象")
        body = load_body(ns.recipe, ns.jsx)
    except (ValueError, OSError) as e:
        emit({"ok": False, "recipe": label, "error": "USAGE: %s" % e}, 2)

    run_dir = tempfile.mkdtemp(prefix="psrun-")
    result_path = os.path.join(run_dir, "result.json")
    body_name = os.path.basename(ns.jsx) if ns.jsx else ns.recipe + ".jsx"
    script, segments = compose(body, args, result_path, label, body_name)

    if ns.check:
        ok, msg = syntax_check(script)
        shutil.rmtree(run_dir, ignore_errors=True)
        emit({"ok": ok is not False, "recipe": label, "data": {"checked": ok is not None, "note": msg or None},
              "error": None if ok is not False else "SYNTAX: " + map_lines(msg, segments)})

    app = find_app(ns.app)
    if not app:
        emit({"ok": False, "recipe": label, "error": "PS_NOT_FOUND: /Applications 下没找到 Adobe Photoshop"}, 2)
    if not app_running(app):
        emit({"ok": False, "recipe": label, "error": "PS_NOT_RUNNING: %s 没在运行，请先打开" % app}, 2)

    t0 = time.time()
    check_mcp_lock()
    fd = acquire_lock(t0 + ns.timeout)
    if fd is None:
        emit({"ok": False, "recipe": label, "error": "BUSY: 等待其他 psrun 超时"})
    try:
        with open(os.path.join(run_dir, "script.jsx"), "w", encoding="utf-8") as f:
            f.write(script)
        remaining = max(10.0, ns.timeout - (time.time() - t0))
        res = run_script(app, script, result_path, remaining, ns.ae_timeout, segments, label)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    if res.get("ok") and not ns.keep_script:
        shutil.rmtree(run_dir, ignore_errors=True)
    elif not res.get("ok") and not res.get("keep_run_dir"):
        res["error"] = "%s [拼好的脚本：%s]" % (res.get("error"), os.path.join(run_dir, "script.jsx"))
    emit(res)


if __name__ == "__main__":
    main()
