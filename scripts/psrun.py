#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""psrun.py —— 在本机 Photoshop 里跑 ps-repair 配方（recipes/*.jsx）或任意 jsx。

macOS 用 osascript（AppleEvent do javascript）；Windows 用 PowerShell 的 COM 自动化
（Photoshop.Application -> DoJavaScriptFile），Photoshop 没开时自动启动。两边跑同一份拼好的 jsx。

用法：
  python3 scripts/psrun.py <配方名> --args '<json>' [--timeout 900] [--app "Adobe Photoshop 2026"]
  python3 scripts/psrun.py <配方名> --args-file <参数.json>       同上，参数从文件读
  python3 scripts/psrun.py --jsx <file.jsx> [--args '<json>']   任意脚本；没定义 run(args) 时整段 eval，
                                                               最后一个表达式的值放在 data.value
  python3 scripts/psrun.py --list                                列出配方与用途（不碰 PS）
  python3 scripts/psrun.py <配方名> --check                      只做语法检查（需要 node，不碰 PS）
  python3 scripts/psrun.py --poll <结果文件> [--timeout 600]      继续等待一次超时运行的结果

stdout 只打印一个 JSON：{"ok","recipe","data","error","elapsed_ms","history"}；失败时退出码非 0。
警告（Higgsfield MCP 锁、排队等待等）只写 stderr。

超时：AppleEvent（Windows 上是 COM 调用）等 --ae-timeout 秒（默认 120）。超时后脚本仍在 PS 里跑，
runner 转为轮询结果文件，直到出现或到 --timeout（默认 900，从启动算起）。
Windows 上 --app 可写 "Adobe Photoshop 2026" 之类的安装目录名，或 Photoshop.exe 的完整路径。
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

IS_WIN = sys.platform == "win32"
if IS_WIN:
    import msvcrt
else:
    import fcntl

ROOT = str(Path(__file__).resolve().parent.parent)
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
def _win_running_paths():
    """正在运行的 Photoshop.exe 的完整路径（小写、正斜杠归一）。"""
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
           "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
           "Get-Process -Name Photoshop -ErrorAction SilentlyContinue | ForEach-Object { $_.Path }"]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    return {os.path.normcase(os.path.normpath(ln.strip())) for ln in out.splitlines() if ln.strip()}


def _win_exe_of(app):
    """--app 既可以是 Photoshop.exe 路径，也可以是安装目录名（Adobe Photoshop 2026）。"""
    if app.lower().endswith(".exe") and os.path.isfile(app):
        return os.path.normpath(app)
    for base in _win_program_dirs():
        cand = os.path.join(base, "Adobe", app, "Photoshop.exe")
        if os.path.isfile(cand):
            return cand
    return None


def _win_program_dirs():
    return [d for d in {os.environ.get("ProgramW6432"), os.environ.get("ProgramFiles")} if d]


def find_app_win(explicit=None):
    if explicit:
        return _win_exe_of(explicit)
    exes = []
    for base in _win_program_dirs():
        exes += glob.glob(os.path.join(base, "Adobe", "Adobe Photoshop*", "Photoshop.exe"))
    if not exes:
        return None
    running = _win_running_paths()

    def score(p):
        name = os.path.basename(os.path.dirname(p))
        m = re.search(r"(\d{4})", name)
        return (os.path.normcase(os.path.normpath(p)) in running, "Beta" not in name, int(m.group(1)) if m else 0)

    return max(exes, key=score)


def app_running_win(exe):
    return os.path.normcase(os.path.normpath(exe)) in _win_running_paths()


def find_app(explicit=None):
    if IS_WIN:
        return find_app_win(explicit)
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
    if IS_WIN:
        return app_running_win(app)
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


def _try_lock(fd):
    if IS_WIN:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)  # 拿不到锁抛 OSError
    else:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def release_lock(fd):
    if IS_WIN:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


def acquire_lock(deadline):
    fd = os.open(LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o600)
    warned = False
    while True:
        try:
            _try_lock(fd)
            return fd
        except (OSError,) if IS_WIN else (BlockingIOError,):
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
        with open(jsx, encoding="utf-8-sig") as f:
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
        p = subprocess.run([node, "--check", path], capture_output=True, text=True, encoding="utf-8", errors="replace")
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


# Windows：PowerShell 里通过 COM（Photoshop.Application）调 DoJavaScriptFile。
# 注册表里 Photoshop.Application 只指向最后安装的那个版本（这里是 Beta），所以本脚本先自己确保目标 exe 在跑，
# 再连 COM 并核对 $app.Path；对不上就报错，不往错误的实例里发脚本。
# 文件只含 ASCII（Windows PowerShell 5.1 读无 BOM 的 .ps1 会按 ANSI 解码）。
WIN_DRIVER = r"""
param([string]$Exe, [string]$Loader, [int]$WaitSec)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
function Fail($m) { [Console]::Error.WriteLine($m); exit 1 }
function ChainHr($e) {
  $codes = @()
  while ($e) { $codes += [uint32]($e.HResult -band 0xFFFFFFFF); $e = $e.InnerException }
  return $codes
}
$wantDir = [IO.Path]::GetFullPath([IO.Path]::GetDirectoryName($Exe)).TrimEnd('\')
$deadline = (Get-Date).AddSeconds($WaitSec)
$app = $null
$last = 'Photoshop process not found'
while (-not $app) {
  $alive = @(Get-Process -Name Photoshop -ErrorAction SilentlyContinue | Where-Object { $_.Path -and ([IO.Path]::GetFullPath($_.Path) -ieq [IO.Path]::GetFullPath($Exe)) })
  if ($alive.Count -gt 0) {
    try {
      $cand = New-Object -ComObject Photoshop.Application
      $got = [IO.Path]::GetFullPath([string]$cand.Path).TrimEnd('\')
      if ($got -ieq $wantDir) { $app = $cand; break }
      Fail ("COM_MISMATCH: COM connected to " + $got + " but target is " + $wantDir + " (another Photoshop instance is running; close it or pass --app)")
    } catch { $last = $_.Exception.Message }
  }
  if ((Get-Date) -gt $deadline) { Fail ("COM_UNAVAILABLE: " + $last) }
  Start-Sleep -Milliseconds 1000
}
while ($true) {
  try {
    $r = $app.DoJavaScriptFile($Loader)
    [Console]::Out.Write([string]$r)
    exit 0
  } catch {
    $hr = ChainHr $_.Exception
    $busy = ($hr -contains [uint32]2147549185) -or ($hr -contains [uint32]2147549450)   # 0x80010001 CALL_REJECTED / 0x8001010A RETRYLATER
    if ($busy -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 1500; continue }
    Fail ("COM_CALL_FAILED: " + $_.Exception.Message)
  }
}
"""

WIN_MARK = "__PSRUN_JSERR__"


def win_loader(script_path):
    """极小的引导脚本：evalFile 跑拼好的脚本，语法错误变成返回值而不是 Photoshop 弹窗。"""
    return ('try { $.evalFile(new File(%s)); } catch (e) { "%s" + String(e) + " @line " + (e.line || 0); }\n'
            % (js_literal(script_path.replace("\\", "/")), WIN_MARK))


def launch_win(exe):
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([exe], cwd=os.path.dirname(exe), close_fds=True, creationflags=flags,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_script_win(exe, run_dir, result_path, timeout, ae_timeout, segments, label, launched):
    t0 = time.time()
    deadline = t0 + timeout
    ae = int(max(10, min(ae_timeout, timeout)))
    wait = 240 if launched else 30
    driver = os.path.join(run_dir, "driver.ps1")
    loader = os.path.join(run_dir, "loader.jsx")
    with open(driver, "w", encoding="ascii") as f:
        f.write(WIN_DRIVER)
    with open(loader, "w", encoding="ascii") as f:
        f.write(win_loader(os.path.join(run_dir, "script.jsx")))
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", driver,
           exe, loader, str(wait)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=ae + wait + 20 if launched else ae + 20, stdin=subprocess.DEVNULL)
        rc, out, err = p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        rc, out, err = None, "", "powershell 子进程超时"
    res = read_result(result_path)
    if res is None and rc == 0 and out.startswith("{"):
        try:
            res = json.loads(out)
        except ValueError:
            res = None
    if res is None and rc is None:
        eprint("COM 调用超过 %d 秒仍未返回，脚本可能仍在 Photoshop 里运行；轮询结果文件 %s，最长到 --timeout……" % (ae, result_path))
        res = poll_result(result_path, deadline)
        if res is None:
            return {"ok": False, "recipe": label, "data": None,
                    "error": "TIMEOUT: %d 秒内没有结果；脚本可能仍在 PS 里运行，结果未知——不要盲目重试有副作用的配方，"
                             "先 inspect 文档；也可用 --poll %s 继续等待" % (timeout, result_path),
                    "elapsed_ms": int((time.time() - t0) * 1000), "history": [], "keep_run_dir": True}
    if res is None:
        if out.startswith(WIN_MARK):
            msg = "JS_ERROR: " + out[len(WIN_MARK):]
        else:
            msg = "COM_ERROR: " + (err or out or ("退出码 %s" % rc))
        return {"ok": False, "recipe": label, "data": None, "error": map_lines(msg, segments),
                "elapsed_ms": int((time.time() - t0) * 1000), "history": []}
    if res.get("error"):
        res["error"] = map_lines(res["error"], segments)
    return res


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
    if IS_WIN:  # 中文输出不受控制台代码页影响
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.reconfigure(encoding="utf-8")
            except (AttributeError, ValueError):
                pass
    ap = argparse.ArgumentParser(description="在 Photoshop 里跑 ps-repair 配方")
    ap.add_argument("recipe", nargs="?", help="配方名（recipes/<名>.jsx）")
    ap.add_argument("--args", default="{}", help="JSON 参数")
    ap.add_argument("--args-file", help="从 UTF-8 文件读 JSON 参数（Windows PowerShell 5.1 会吃掉 --args 里的双引号时用）")
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
        if ns.args_file:
            with open(ns.args_file, encoding="utf-8-sig") as f:
                args = json.load(f)
        else:
            args = json.loads(ns.args)
        if not isinstance(args, dict):
            raise ValueError("--args 必须是 JSON 对象")
        body = load_body(ns.recipe, ns.jsx)
    except (ValueError, OSError) as e:
        emit({"ok": False, "recipe": label, "error": "USAGE: %s" % e}, 2)

    run_dir = tempfile.mkdtemp(prefix="psrun-")
    result_path = os.path.join(run_dir, "result.json")
    body_name = os.path.basename(ns.jsx) if ns.jsx else ns.recipe + ".jsx"
    # Windows：结果路径用正斜杠写进 jsx，免得反斜杠在 ExtendScript 字符串里出岔子
    script, segments = compose(body, args, result_path.replace("\\", "/") if IS_WIN else result_path, label, body_name)

    if ns.check:
        ok, msg = syntax_check(script)
        shutil.rmtree(run_dir, ignore_errors=True)
        emit({"ok": ok is not False, "recipe": label, "data": {"checked": ok is not None, "note": msg or None},
              "error": None if ok is not False else "SYNTAX: " + map_lines(msg, segments)})

    app = find_app(ns.app)
    launched = False
    if not app:
        where = ("Program Files\\Adobe 下没找到 Adobe Photoshop（--app 也可直接给 Photoshop.exe 路径）" if IS_WIN
                 else "/Applications 下没找到 Adobe Photoshop")
        emit({"ok": False, "recipe": label, "error": "PS_NOT_FOUND: " + where}, 2)
    if not app_running(app):
        if not IS_WIN:
            emit({"ok": False, "recipe": label, "error": "PS_NOT_RUNNING: %s 没在运行，请先打开" % app}, 2)
        eprint("Photoshop 没在运行，正在启动 %s ……" % app)
        launch_win(app)
        launched = True

    t0 = time.time()
    check_mcp_lock()
    fd = acquire_lock(t0 + ns.timeout)
    if fd is None:
        emit({"ok": False, "recipe": label, "error": "BUSY: 等待其他 psrun 超时"})
    try:
        # Windows 上 jsx 带 BOM：ExtendScript 读无 BOM 文件会按系统代码页解码，中文会坏
        with open(os.path.join(run_dir, "script.jsx"), "w", encoding="utf-8-sig" if IS_WIN else "utf-8") as f:
            f.write(script)
        remaining = max(10.0, ns.timeout - (time.time() - t0))
        if IS_WIN:
            res = run_script_win(app, run_dir, result_path, remaining, ns.ae_timeout, segments, label, launched)
        else:
            res = run_script(app, script, result_path, remaining, ns.ae_timeout, segments, label)
    finally:
        release_lock(fd)
    if res.get("ok") and not ns.keep_script:
        shutil.rmtree(run_dir, ignore_errors=True)
    elif not res.get("ok") and not res.get("keep_run_dir"):
        res["error"] = "%s [拼好的脚本：%s]" % (res.get("error"), os.path.join(run_dir, "script.jsx"))
    emit(res)


if __name__ == "__main__":
    main()
