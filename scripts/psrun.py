#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""psrun.py —— 在本机 Photoshop 里跑 ps-repair 配方（recipes/*.jsx）或任意 jsx。

macOS 用 osascript（AppleEvent do javascript）；Windows 用 PowerShell 的 COM 自动化（从运行对象表取正在运行的
目标 Photoshop -> DoJavaScriptFile，不经注册表新建实例），Photoshop 没开时自动启动。两边跑同一份拼好的 jsx。

用法：
  python3 scripts/psrun.py <配方名> --args '<json>' [--timeout 900] [--app "Adobe Photoshop 2026"]
  python3 scripts/psrun.py <配方名> --args-file <参数.json>       同上，参数从文件读
  python3 scripts/psrun.py --jsx <file.jsx> [--args '<json>']   任意脚本；没定义 run(args) 时整段 eval，
                                                               最后一个表达式的值放在 data.value
  python3 scripts/psrun.py --ping                                探活：PS 能否马上响应（等 15 秒、总共 30 秒），附系统盘剩余空间
  python3 scripts/psrun.py --list                                列出配方与用途（不碰 PS）
  python3 scripts/psrun.py <配方名> --check                      只做语法检查（node）和 ES3 写法扫描，不碰 PS
  python3 scripts/psrun.py --poll <结果文件> [--timeout 600]      继续等待一次超时运行的结果

stdout 只打印一个 JSON：{"ok","recipe","data","error","error_code","error_number","elapsed_ms","history","warnings"}；
失败时退出码非 0。error_code 是错误文本里的稳定代码（如 LAYER_EXISTS），error_number 是 PS 原生错误号。
警告（Higgsfield MCP 锁、系统盘空间低、ES3 写法等）同时写 stderr 和 warnings。

超时：AppleEvent（Windows 上是 COM 调用）等 --ae-timeout 秒（默认 120）。超时后脚本仍在 PS 里跑，
runner 转为轮询结果文件，直到出现或到 --timeout（默认 900，从启动算起）。--ping 默认 15 / 30 秒。
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
# 系统盘（PS 默认暂存盘）剩余低于这个数就警告。Adobe 官方页面：系统盘至少留 20 GB；暂存盘满的排障建议腾出 100 GB。
DISK_WARN_GB = 20
WARNINGS = []


def eprint(*a):
    print(*a, file=sys.stderr, flush=True)


def warn(msg):
    """警告写 stderr，同时进结果 JSON 的 warnings。"""
    eprint("警告：" + msg)
    WARNINGS.append(msg)


LEAD_CODE_RE = re.compile(r"\s*([A-Z][A-Z0-9_]{2,}):\s*")
LOCAL_PREFIX_RE = re.compile(r"\s*(?:[^\x00-\x7f]+|[A-Z][a-z]+)\s*:\s*")  # PS 本地化前缀：「错误:」「Error:」
WRAPPER_CODES = ("COM_ERROR", "JS_ERROR", "OSASCRIPT_ERROR")


def _lead_code(s):
    """开头的 CODE:（允许前面有一个本地化前缀）；返回 (代码, 后文) 或 (None, s)。只认开头，说明文字里的 URL: 之类不算。"""
    m = LEAD_CODE_RE.match(s)
    if not m:
        p = LOCAL_PREFIX_RE.match(s)
        m = LEAD_CODE_RE.match(s, p.end()) if p else None
    return (m.group(1), s[m.end():]) if m else (None, s)


def error_code(err):
    """错误文本开头的稳定代码；COM_ERROR 这类外壳紧跟着还有更具体的代码时取里面那个。"""
    code, rest = _lead_code(err or "")
    if code in WRAPPER_CODES:
        inner, _ = _lead_code(rest)
        return inner or code
    return code


def emit(res, code=None):
    """打印唯一的 JSON（固定 9 个字段）并退出。"""
    err = res.get("error")
    shaped = {
        "ok": bool(res.get("ok")),
        "recipe": res.get("recipe"),
        "data": res.get("data"),
        "error": err,
        "error_code": res.get("error_code") or (error_code(err) if err else None),
        "error_number": res.get("error_number"),
        "elapsed_ms": int(res.get("elapsed_ms") or 0),
        "history": res.get("history") or [],
        "warnings": WARNINGS + [w for w in (res.get("warnings") or []) if w not in WARNINGS],
    }
    print(json.dumps(shaped, ensure_ascii=False))
    sys.exit(code if code is not None else (0 if shaped["ok"] else 1))


# ---------- 系统盘（暂存盘）----------
SCRATCH_RECOVERY = ("暂存盘满时 PS 会弹窗卡住，脚本只表现为超时（PS 错误号 -25010）。Adobe 的处理办法：系统盘至少留 20 GB，"
                    "排障时腾出 100 GB；Windows 关掉 PS 后删掉 C 盘里以 Photoshop Temp 开头的文件，macOS 清理 Macintosh HD；"
                    "然后重启 PS。在 PS 设置里把暂存盘改到了别的盘的话，以那块盘为准。")


def disk_status():
    """系统盘剩余空间（PS 默认把暂存盘放在系统盘；用户改过暂存盘的话这里看不出来）。"""
    root = (os.environ.get("SystemDrive", "C:") + "\\") if IS_WIN else "/"
    try:
        u = shutil.disk_usage(root)
    except OSError:
        return None
    return {"path": root, "free_gb": round(u.free / 1024 ** 3, 1), "total_gb": round(u.total / 1024 ** 3, 1),
            "low": u.free < DISK_WARN_GB * 1024 ** 3}  # 按字节判断，不按四舍五入后的显示值


def scratch_note(disk):
    return "系统盘 %s 只剩 %.1f GB。%s" % (disk["path"], disk["free_gb"], SCRATCH_RECOVERY)


# ---------- ES3 写法扫描 ----------
# ExtendScript 是 ES3，node --check 认 ES6，拦不住下面这些写法（任何一处都会让整段脚本在 PS 里解析失败或报未定义）。
ES3_RULES = [
    (re.compile(r"=>"), "箭头函数 =>"),
    (re.compile(r"`"), "模板字符串（反引号）"),
    (re.compile(r"\b(?:let|const|class)\s+[A-Za-z_$]"), "let / const / class"),
    (re.compile(r"\.\.\.\s*[A-Za-z_$\[(]"), "展开运算符 ..."),
    (re.compile(r"\bfor\s*\(\s*(?:var\s+)?[A-Za-z_$][\w$]*\s+of\b"), "for...of"),
    (re.compile(r"\.(?:forEach|map|filter|reduce|some|every|find|findIndex|includes|trim|startsWith|endsWith|repeat)\s*\("),
     "ES5+ 数组/字符串方法（ExtendScript 没有）"),
    (re.compile(r"\bJSON\s*\."), "JSON 对象（ExtendScript 没有，用 _lib 的 __json）"),
    (re.compile(r"\bObject\s*\.\s*(?:keys|assign|entries|values|create|freeze|defineProperty)\b"), "ES5+ Object 方法"),
    (re.compile(r"\bArray\s*\.\s*(?:isArray|from|of)\b"), "ES5+ Array 方法"),
    (re.compile(r"\bfunction\b[^(]*\([^)]*="), "参数默认值"),
    (re.compile(r"\{\s*[A-Za-z_$][\w$]*(?:\s*,\s*[A-Za-z_$][\w$]*)*\s*\}"), "对象简写 { a, b }"),
    (re.compile(r"\{[^{}]*:[^{}]*,\s*[A-Za-z_$][\w$]*\s*\}"), "对象简写 { a: 1, b }"),
]
NOT_SHORTHAND = {"return", "break", "continue", "debugger"}
REGEX_BEFORE = set("(,=:[!&|?{};+-*/%<>~^")
REGEX_KEYWORDS = ("", "return", "typeof", "throw", "case", "delete", "void", "in", "instanceof", "new", "else", "do")


def _strip_js(src):
    """注释换成空格；字符串、正则字面量只留两端的引号/斜杠、中间换成空格（保留换行和长度），只留代码给 ES3 扫描。
    留着两端是为了让后面的 / 知道前面是个值（是除号不是正则）。已知局限：`if (x) /re/.test(s)` 这种
    条件括号后直接跟正则的写法会被当成除号，可能误报；本仓库没有这种写法。"""
    out, i, n = [], 0, len(src)

    def blank(s):
        return re.sub(r"[^\n]", " ", s)

    def hollow(s):  # 字面量：保留首尾字符
        return s if len(s) < 2 else s[0] + blank(s[1:-1]) + s[-1]

    def last_code():
        k = len(out) - 1
        while k >= 0 and out[k].isspace():
            k -= 1
        if k < 0:
            return ""
        j = k
        while j >= 0 and (out[j].isalnum() or out[j] in "_$"):
            j -= 1
        return "".join(out[j + 1:k + 1]) if j < k else out[k]

    def tail2():  # 跳过空白（注释已变成空白）后的最后两个代码字符
        k = len(out) - 1
        while k >= 0 and out[k].isspace():
            k -= 1
        return "".join(out[max(0, k - 1):k + 1])

    def is_regex_start():
        """这个 / 是正则开头还是除号：前面是运算符（含除号）、左括号、语句开头或 return/throw 这类关键字时是正则；
        前面是值（标识符、数字、字面量、右括号、a++ / a--）时是除号。正则字面量输出成 "…" 占位，所以它后面的 / 是除号。"""
        lc = last_code()
        if lc in REGEX_KEYWORDS:
            return True
        if tail2() in ("++", "--"):
            return False
        return lc[-1:] in REGEX_BEFORE

    while i < n:
        c, nx = src[i], src[i + 1] if i + 1 < n else ""
        lit = True
        if c == "/" and nx == "/":
            j, lit = src.find("\n", i), False
            j = n if j < 0 else j
        elif c == "/" and nx == "*":
            j, lit = src.find("*/", i + 2), False
            j = n if j < 0 else j + 2
        elif c in "'\"":
            j = i + 1
            while j < n and src[j] != c and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            j = min(j + 1, n)
        elif c == "/" and is_regex_start():
            j, in_class = i + 1, False
            while j < n and src[j] != "\n":
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "[":
                    in_class = True
                elif src[j] == "]":
                    in_class = False
                elif src[j] == "/" and not in_class:
                    break
                j += 1
            j += 1
            while j < n and src[j].isalpha():
                j += 1
            lit = "re"
        else:
            out.append(c)
            i += 1
            continue
        if lit == "re":  # 正则字面量占位成 "…"（同长度），和除号的 / 区分开
            s = src[i:j]
            out.extend('"' + blank(s[1:-1]) + '"' if len(s) >= 2 else blank(s))
        else:
            out.extend(hollow(src[i:j]) if lit else blank(src[i:j]))
        i = j
    return "".join(out)


def es3_lint(src, name):
    """返回 ["文件:行 规则：片段", ...]；空列表表示没发现 ES3 之外的写法。"""
    code = _strip_js(src)
    lines = src.split("\n")
    hits = []
    for rx, what in ES3_RULES:
        for m in rx.finditer(code):
            if what == "对象简写 { a, b }" and set(re.findall(r"[A-Za-z_$][\w$]*", m.group(0))) <= NOT_SHORTHAND:
                continue
            ln = code.count("\n", 0, m.start()) + 1
            hits.append("%s:%d %s：%s" % (name, ln, what, lines[ln - 1].strip()[:80]))
    return sorted(set(hits), key=lambda h: int(h.split(" ", 1)[0].rsplit(":", 1)[1]))


# ---------- Photoshop 应用 ----------
def _win_running_paths():
    """正在运行的 Photoshop.exe 的完整路径（小写、正斜杠归一）；查询超时返回 None（不知道，别当成没在跑）。"""
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
           "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
           "Get-Process -Name Photoshop -ErrorAction SilentlyContinue | ForEach-Object { $_.Path }"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15).stdout
    except subprocess.TimeoutExpired:
        return None
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
    # Beta 只在显式 --app 时用：默认候选里排除，哪怕只有 Beta 在跑
    exes = [p for p in exes if "Beta" not in os.path.basename(os.path.dirname(p))]
    if not exes:
        return None
    running = _win_running_paths() or set()

    def score(p):
        m = re.search(r"(\d{4})", os.path.basename(os.path.dirname(p)))
        return (os.path.normcase(os.path.normpath(p)) in running, int(m.group(1)) if m else 0)

    return max(exes, key=score)


def app_running_win(exe):
    paths = _win_running_paths()
    return None if paths is None else os.path.normcase(os.path.normpath(exe)) in paths


def find_app(explicit=None):
    if IS_WIN:
        return find_app_win(explicit)
    if explicit:
        return explicit
    bundles = glob.glob("/Applications/Adobe Photoshop */Adobe Photoshop *.app")
    names = sorted({os.path.basename(b)[:-4] for b in bundles if "Beta" not in os.path.basename(b)})  # Beta 只在显式 --app 时用
    if not names:
        return None
    running = _mac_ps() or ""

    def score(n):
        m = re.search(r"(\d{4})", n)
        return ("/%s.app/Contents/MacOS/" % n in running, int(m.group(1)) if m else 0)

    return max(names, key=score)


def _mac_ps():
    try:
        return subprocess.run(["/bin/ps", "-axo", "command"], capture_output=True, text=True, timeout=10).stdout
    except subprocess.TimeoutExpired:
        return None


def app_running(app):
    """True / False；进程列表查不到时返回 None，调用方不能据此启动 PS。"""
    if IS_WIN:
        return app_running_win(app)
    out = _mac_ps()
    return None if out is None else ("/%s.app/Contents/MacOS/" % app) in out


# ---------- 锁 ----------
def check_mcp_lock():
    if not os.path.exists(MCP_LOCK):
        return
    age = time.time() - os.path.getmtime(MCP_LOCK)
    if age < MCP_FRESH_SECONDS:
        warn("MCP_LOCK: Higgsfield MCP 锁 %s 是 %d 秒前建的，MCP 可能正在驱动 Photoshop；"
             "两边不要同时操作（PS 会排队，但多步流程可能交错）。" % (MCP_LOCK, age))
    else:
        warn("MCP_LOCK_STALE: 存在陈旧的 Higgsfield MCP 锁 %s（%d 分钟前）。它表示 MCP 上次调用结果未知，"
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
    """返回 (要拼进脚本的正文, 原始源码)；原始源码给 ES3 扫描用（任意脚本被包进字符串后扫不到）。"""
    if jsx:
        with open(jsx, encoding="utf-8-sig") as f:
            src = f.read()
        if re.search(r"\bfunction\s+run\s*\(", src):
            return src, src
        # 任意脚本：整段 eval，最后一个表达式的值放进 data.value
        return ("var __SRC__ = %s;\nfunction run(args) { var __v = eval(__SRC__); "
                "return { value: (__v === undefined ? null : __v) }; }\n" % js_literal(src)), src
    if not re.match(r"^[a-z0-9][a-z0-9_]*$", recipe or ""):
        raise ValueError("配方名只能是小写字母、数字、下划线：%r" % recipe)
    path = os.path.join(RECIPES, recipe + ".jsx")
    if not os.path.exists(path):
        raise ValueError("没有这个配方：%s（用 --list 查看）" % recipe)
    with open(path, encoding="utf-8") as f:
        src = f.read()
    return src, src


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
        time.sleep(max(0.0, min(interval, deadline - time.time())))  # 最后一次不睡过截止时间
    return read_result(path)


# Windows：PowerShell 里拿到正在运行的目标 Photoshop 的 COM 对象，调 DoJavaScriptFile。
# 不用 New-Object -ComObject Photoshop.Application：注册表里这个入口只指向最后安装的版本（本机是 Beta 28.0），
# 正式版运行时登记的是另一个 CLSID，New-Object 连不上它，反而会按注册表拉起 Beta（2026-10-10 实测，正式版随后退出，
# 见 known-failures K8）。所以只在运行对象表（ROT）里找已经在跑、Path 等于目标目录的实例，绝不新建进程。
# 文件只含 ASCII（Windows PowerShell 5.1 读无 BOM 的 .ps1 会按 ANSI 解码）。
WIN_DRIVER = r"""
param([string]$Exe, [string]$Loader, [int]$WaitSec)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
function Fail($m) { [Console]::Error.WriteLine($m); exit 1 }
function ChainHr($e) {
  # HResult is a signed Int32; [uint32] on a negative value throws, so mask through Int64 (gives 0x80010001 = 2147549185)
  $codes = @()
  while ($e) { $codes += ([int64]$e.HResult -band 4294967295); $e = $e.InnerException }
  return $codes
}
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
public static class PsRot {
  [DllImport("ole32.dll")] static extern int GetRunningObjectTable(int r, out IRunningObjectTable rot);
  [DllImport("ole32.dll")] static extern int CreateBindCtx(int r, out IBindCtx ctx);
  // ROT entries registered by class ("!{CLSID}"): returns [clsid, object] pairs. Never starts a process.
  public static List<object[]> Entries() {
    var list = new List<object[]>();
    IRunningObjectTable rot;
    if (GetRunningObjectTable(0, out rot) != 0) return list;
    IEnumMoniker e; rot.EnumRunning(out e);
    IBindCtx ctx; CreateBindCtx(0, out ctx);
    IMoniker[] m = new IMoniker[1];
    while (e.Next(1, m, IntPtr.Zero) == 0) {
      string n = null;
      try { m[0].GetDisplayName(ctx, null, out n); } catch { continue; }
      if (n == null || !n.StartsWith("!{")) continue;
      object o;
      if (rot.GetObject(m[0], out o) == 0 && o != null) list.Add(new object[] { n.Substring(1), o });
    }
    return list;
  }
}
'@
function FindPs($wantDir) {
  $r = @{ app = $null; others = @(); err = $null }
  foreach ($ent in [PsRot]::Entries()) {
    $name = (Get-ItemProperty ('Registry::HKEY_CLASSES_ROOT\CLSID\' + $ent[0]) -ErrorAction SilentlyContinue).'(default)'
    if ($name -and $name -notmatch 'Photoshop') { continue }   # other programs (e.g. PowerPoint): leave alone
    try { $p = [string]$ent[1].Path } catch { $r.err = $_.Exception.Message; continue }
    if (-not $p) { continue }
    $got = [IO.Path]::GetFullPath($p).TrimEnd('\')
    if ($got -ieq $wantDir) { $r.app = $ent[1]; return $r }
    $r.others += $got
  }
  return $r
}
$wantDir = [IO.Path]::GetFullPath([IO.Path]::GetDirectoryName($Exe)).TrimEnd('\')
$deadline = (Get-Date).AddSeconds($WaitSec)
$app = $null
$last = 'COM_UNAVAILABLE: Photoshop process not found'
while (-not $app) {
  $alive = @(Get-Process -Name Photoshop -ErrorAction SilentlyContinue | Where-Object { $_.Path -and ([IO.Path]::GetFullPath($_.Path) -ieq [IO.Path]::GetFullPath($Exe)) })
  if ($alive.Count -gt 0) {
    try {
      $f = FindPs $wantDir
      if ($f.app) { $app = $f.app; break }
      if ($f.others.Count -gt 0) { $last = 'COM_MISMATCH: only other Photoshop instances are registered: ' + ($f.others -join ', ') + ' (target is ' + $wantDir + '; close them or pass --app)' }
      elseif ($f.err) { $last = 'COM_UNAVAILABLE: Photoshop is registered but not answering: ' + $f.err }
      else { $last = 'COM_UNAVAILABLE: target Photoshop is running but not in the Running Object Table yet (still starting?)' }
    } catch { $last = 'COM_UNAVAILABLE: ' + $_.Exception.Message }
  }
  if ((Get-Date) -gt $deadline) { Fail $last }
  Start-Sleep -Milliseconds 1000
}
while ($true) {
  try {
    $r = $app.DoJavaScriptFile($Loader)
    [Console]::Out.Write([string]$r)
    exit 0
  } catch {
    $hr = ChainHr $_.Exception
    $busy = ($hr -contains 2147549185) -or ($hr -contains 2147549450)   # 0x80010001 CALL_REJECTED / 0x8001010A RETRYLATER
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
        cap = ae + wait + 20 if launched else ae + 20
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=min(cap, timeout), stdin=subprocess.DEVNULL)
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
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=min(ae + 30, timeout))
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


def finalize(res, disk, ping):
    """正常运行和 --poll 共用的结果归类：暂存盘满、超时的下一步提示、探活附系统盘信息。"""
    err = res.get("error") or ""
    code = res.get("error_code") or error_code(err)  # 已有结构化代码优先，文字解析兜底
    # 暂存盘：PS 原生错误号 -25010；文字匹配只用于不带 CODE 的原生错误（免得文件名里的「暂存盘」被误判）
    if res.get("error_number") == -25010 or (err and code is None and re.search(r"暂存盘|scratch disk", err, re.I)):
        res["error_code"] = "SCRATCH_DISK_FULL"
        res["error"] = "SCRATCH_DISK_FULL: %s %s" % (err, scratch_note(disk) if disk else SCRATCH_RECOVERY)
    elif code == "TIMEOUT":
        nxt = ("PS 没响应：先看 PS 窗口有没有弹窗或对话框，关掉后再 --ping。" if ping else
               "下一步：先 --ping 看 PS 有没有响应，再 inspect 核对图层和历史记录。")
        res["error"] = "%s %s" % (err, nxt)
        if disk and disk["low"]:
            res["error"] += " " + scratch_note(disk)
    if ping and res.get("ok") and isinstance(res.get("data"), dict):
        res["data"]["disk"] = disk
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
    ap.add_argument("--timeout", type=float, default=None, help="总等待秒数（默认 900；--ping 默认 30）")
    ap.add_argument("--ae-timeout", type=float, default=None, help="AppleEvent 等待秒数，超时后改轮询（默认 120；--ping 默认 15）")
    ap.add_argument("--app", help='应用名，如 "Adobe Photoshop 2026"；默认自动找')
    ap.add_argument("--ping", action="store_true", help="探活：PS 能否马上响应，附系统盘剩余空间（只读）")
    ap.add_argument("--list", action="store_true", help="列出配方")
    ap.add_argument("--check", action="store_true", help="只做语法检查（node）和 ES3 写法扫描，不碰 PS")
    ap.add_argument("--poll", help="等待某个结果文件")
    ap.add_argument("--keep-script", action="store_true", help="保留拼好的脚本（调试用）")
    ns = ap.parse_args()
    if ns.ping:
        ns.recipe, ns.jsx = "ping", None
    timeout = ns.timeout if ns.timeout is not None else (30.0 if ns.ping else 900.0)
    ae_timeout = ns.ae_timeout if ns.ae_timeout is not None else (15.0 if ns.ping else 120.0)

    if ns.list:
        print(json.dumps(list_recipes(), ensure_ascii=False, indent=1))
        return
    if ns.poll:
        t0 = time.time()
        res = poll_result(ns.poll, t0 + timeout)
        if res is None:
            res = {"ok": False, "recipe": None, "error": "TIMEOUT: 结果文件仍未出现 " + ns.poll,
                   "elapsed_ms": int((time.time() - t0) * 1000)}
        emit(finalize(res, disk_status(), False))

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
        body, raw = load_body(ns.recipe, ns.jsx)
    except (ValueError, OSError) as e:
        emit({"ok": False, "recipe": label, "error": "USAGE: %s" % e}, 2)

    run_dir = tempfile.mkdtemp(prefix="psrun-")
    result_path = os.path.join(run_dir, "result.json")
    body_name = os.path.basename(ns.jsx) if ns.jsx else ns.recipe + ".jsx"
    # Windows：结果路径用正斜杠写进 jsx，免得反斜杠在 ExtendScript 字符串里出岔子
    script, segments = compose(body, args, result_path.replace("\\", "/") if IS_WIN else result_path, label, body_name)
    with open(LIB, encoding="utf-8") as f:
        es3 = es3_lint(f.read(), "_lib.jsx") + es3_lint(raw, body_name)

    if ns.check:
        ok, msg = syntax_check(script)
        shutil.rmtree(run_dir, ignore_errors=True)
        err = None
        if ok is False:
            err = "SYNTAX: " + map_lines(msg, segments)
        elif es3:
            err = "ES3: ExtendScript 不支持的写法 %d 处：%s" % (len(es3), "；".join(es3))
        emit({"ok": err is None, "recipe": label, "data": {"checked": ok is not None, "es3_checked": True, "note": msg or None},
              "error": err})
    for h in es3:  # 真跑时只警告，不拦（误报时不至于挡住修图）
        warn("ES3: " + h)

    t0 = time.time()  # 总时限从找 PS 这一步算起（--ping 的 30 秒含查进程、排队等锁）
    app = find_app(ns.app)
    launched = False
    if not app:
        where = ("Program Files\\Adobe 下没找到 Adobe Photoshop 正式版（Beta 要用 --app 显式指定；--app 也可直接给 Photoshop.exe 路径）"
                 if IS_WIN else "/Applications 下没找到 Adobe Photoshop 正式版（Beta 要用 --app 显式指定）")
        emit({"ok": False, "recipe": label, "error": "PS_NOT_FOUND: " + where}, 2)
    running = app_running(app)
    if running is None:
        emit({"ok": False, "recipe": label, "error": "PROCESS_QUERY_FAILED: 查不到进程列表，不知道 %s 在不在跑；"
              "为免重复启动，这次不动 PS，稍后再试" % app}, 2)
    if not running:
        if ns.ping:  # 探活只看不启动，时限才有保证
            emit({"ok": False, "recipe": label, "error": "PS_NOT_RUNNING: %s 没在运行（--ping 不启动 PS；%s）"
                  % (app, "Windows 上跑别的配方会自动启动" if IS_WIN else "请先打开")}, 2)
        if not IS_WIN:
            emit({"ok": False, "recipe": label, "error": "PS_NOT_RUNNING: %s 没在运行，请先打开" % app}, 2)
        eprint("Photoshop 没在运行，正在启动 %s ……" % app)
        launch_win(app)
        launched = True

    check_mcp_lock()
    disk = disk_status()
    if disk and disk["low"]:
        warn("SCRATCH_DISK_LOW: 系统盘 %s 只剩 %.1f GB（Adobe 建议至少留 20 GB）；暂存盘满时 PS 会弹窗卡住，"
             "大图和生成式填充前先腾空间。暂存盘已改到别的盘的话可忽略。" % (disk["path"], disk["free_gb"]))
    fd = acquire_lock(t0 + timeout)
    if fd is None:
        emit({"ok": False, "recipe": label, "error": "BUSY: 等待其他 psrun 超时"})
    try:
        # Windows 上 jsx 带 BOM：ExtendScript 读无 BOM 文件会按系统代码页解码，中文会坏
        with open(os.path.join(run_dir, "script.jsx"), "w", encoding="utf-8-sig" if IS_WIN else "utf-8") as f:
            f.write(script)
        remaining = max(1.0 if ns.ping else 10.0, timeout - (time.time() - t0))
        if IS_WIN:
            res = run_script_win(app, run_dir, result_path, remaining, ae_timeout, segments, label, launched)
        else:
            res = run_script(app, script, result_path, remaining, ae_timeout, segments, label)
    finally:
        release_lock(fd)
    res = finalize(res, disk, ns.ping)
    if res.get("ok") and not ns.keep_script:
        shutil.rmtree(run_dir, ignore_errors=True)
    elif not res.get("ok") and not res.get("keep_run_dir"):
        res["error"] = "%s [拼好的脚本：%s]" % (res.get("error"), os.path.join(run_dir, "script.jsx"))
    emit(res)


if __name__ == "__main__":
    main()
