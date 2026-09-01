#!/usr/bin/env python3
"""
Batch Runner — execute a list of scripts with parallelism and resource control.
Supports MATLAB (.m) and Python (.py); executor chosen by file extension.
Cross-platform (Windows & Linux).  Zero dependencies.
"""

import argparse
import json
import logging
import os
import platform
import re
import signal
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from abc import ABC, abstractmethod
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from multiprocessing import Manager
from typing import Any, Optional

IS_WINDOWS = platform.system() == "Windows"

try:
    import psutil  # type: ignore[import-untyped]

    HAS_PSUTIL = True
except ImportError:
    psutil = None  # type: ignore[assignment]
    HAS_PSUTIL = False


def _parse_script_line(line: str, lineno: int, source: str, cwd: str) -> str | None:
    """Parse a single line from a task file or stdin.

    Returns the validated absolute script path, or *None* for blank/comment lines.
    Raises :class:`FileNotFoundError` or :class:`ValueError` on invalid input.
    """
    content = re.split(r"#|;|(?:(?<=\s)|^)%", line, maxsplit=1)[0].strip()
    if not content:
        return None

    if not os.path.isabs(content):
        content = os.path.normpath(os.path.join(cwd, content))

    if not os.path.isfile(content):
        raise FileNotFoundError(f"{source}:{lineno}: file not found: {content}")

    ext = os.path.splitext(content)[1]
    if ext not in (".m", ".py"):
        raise ValueError(f"{source}:{lineno}: unsupported file type '{ext}': {content}")

    return content


def parse_taskfiles(paths: list[str]) -> list[str]:
    """Parse one or more task files into a deduplicated list of script paths.

    Task file format::

        # comment (full-line)
        ; also a comment
        % also a comment
        path/to/script.py
        path/to/another.m  # inline comment
        path/to/third.m  ; inline comment
        path/to/fourth.m  % inline comment

    - One script path per line (absolute, or relative to CWD).
    - ``#``, ``;``, ``%`` start a comment — full-line or inline.
      ``%`` must be preceded by whitespace (so it won't split on ``%`` in filenames).
    - Blank lines are ignored.
    - Each path must exist and have a ``.m`` or ``.py`` extension.
    - Duplicates (by absolute path) are removed; first occurrence wins.
    - Pass ``"-"`` to read from stdin.

    Raises :class:`FileNotFoundError` or :class:`ValueError` on invalid input.
    """
    scripts: list[str] = []
    seen: set[str] = set()
    cwd = os.getcwd()

    for filepath in paths:
        if filepath == "-":
            _parse_lines(sys.stdin, "-", cwd, seen, scripts)
            continue

        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"task file not found: {filepath}")

        with open(filepath, "r", encoding="utf-8") as f:
            _parse_lines(f, filepath, cwd, seen, scripts)

    return scripts


def _parse_lines(
    lines, source: str, cwd: str, seen: set[str], scripts: list[str]
) -> None:
    for lineno, line in enumerate(lines, 1):
        sp = _parse_script_line(line, lineno, source, cwd)
        if sp is None:
            continue
        key = os.path.abspath(sp)
        if key not in seen:
            seen.add(key)
            scripts.append(sp)


def _parse_duration(s: str) -> float:
    """Parse a duration string like '2h', '30m', '1h30m', '45s' into seconds."""
    s = s.strip()
    if not s:
        raise ValueError("empty duration")
    if s == "0":
        return 0.0
    total = 0.0
    idx = 0
    while idx < len(s):
        start = idx
        while idx < len(s) and (s[idx].isdigit() or s[idx] == "."):
            idx += 1
        if idx == start:
            raise ValueError(f"Invalid duration: {s!r}")
        value = float(s[start:idx])
        if idx >= len(s):
            raise ValueError(f"Missing unit (h/m/s) in: {s!r}")
        unit = s[idx].lower()
        idx += 1
        if unit == "h":
            total += value * 3600
        elif unit == "m":
            total += value * 60
        elif unit == "s":
            total += value
        else:
            raise ValueError(f"Unknown unit {unit!r} in: {s!r} (use h/m/s)")
    return total


def _fmt_dh(seconds: float) -> str:
    """Format seconds as a human-readable string: 1h30m, 5m30s, 45s, 0.3s."""
    if seconds < 0:
        return "0s"
    if seconds < 1:
        return f"{seconds:.1f}s"
    if seconds < 60:
        return f"{int(seconds)}s"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}h{m}m" if m > 0 else f"{h}h"
    return f"{m}m{s}s" if s > 0 else f"{m}m"


class Executor(ABC):
    @abstractmethod
    def build_command(self, script_path: str) -> list[str]: ...
    @property
    @abstractmethod
    def name(self) -> str: ...


class MatlabExecutor(Executor):
    def __init__(self, cmd: str = "matlab"):
        self.cmd = cmd

    @property
    def name(self) -> str:
        return "MATLAB"

    def build_command(self, script_path: str) -> list[str]:
        d = os.path.dirname(os.path.abspath(script_path))
        n = os.path.splitext(os.path.basename(script_path))[0]
        return [self.cmd, "-batch", f"cd('{d}'); {n};"]


class PythonExecutor(Executor):
    def __init__(self, cmd: str = "python"):
        self.cmd = cmd

    @property
    def name(self) -> str:
        return "Python"

    def build_command(self, script_path: str) -> list[str]:
        return [self.cmd, os.path.abspath(script_path)]


def _which(cmd: str) -> bool:
    """Return True if *cmd* can be found on PATH."""
    return (
        subprocess.run(
            ["where" if IS_WINDOWS else "which", cmd], capture_output=True
        ).returncode
        == 0
    )


def make_executor(ext: str) -> Executor:
    """Return a (cached) executor for the given file extension."""
    if ext == ".m":
        return MatlabExecutor(os.getenv("BATCH_MATLAB_CMD", "matlab"))
    elif ext == ".py":
        py = os.getenv("BATCH_PYTHON_CMD", "")
        if not py:
            py = "python3" if _which("python3") else "python"
        return PythonExecutor(py)
    raise ValueError(f"Unsupported extension: {ext}")


def _kill_pid(pid: int) -> None:
    """Kill a process and its children cross-platform."""
    try:
        if IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(pid)],
                capture_output=True,
            )
        else:
            os.killpg(os.getpgid(pid), signal.SIGKILL)  # type: ignore[attr-defined]
    except (ProcessLookupError, OSError):
        pass


def run_script(
    cmd: list[str],
    script_path: str,
    timeout_s: Optional[int],
    cwd: str,
    active_pids: Any,
) -> dict:
    t0 = time.time()
    proc: Any = None
    try:
        if IS_WINDOWS:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=cwd,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=cwd,
                preexec_fn=getattr(os, "setsid"),
            )
        active_pids.append(proc.pid)
        try:
            out, err = proc.communicate(timeout=timeout_s)
            return {
                "script_path": script_path,
                "returncode": proc.returncode,
                "stdout": out,
                "stderr": err,
                "duration": time.time() - t0,
                "success": proc.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            _kill_pid(proc.pid)
            proc.wait()
            return {
                "script_path": script_path,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Timeout ({(timeout_s or 0) / 3600:.0f}h)",
                "duration": time.time() - t0,
                "success": False,
            }
    except KeyboardInterrupt:
        return {
            "script_path": script_path,
            "returncode": -3,
            "stdout": "",
            "stderr": "Cancelled (Ctrl+C)",
            "duration": time.time() - t0,
            "success": False,
        }
    except Exception as exc:
        return {
            "script_path": script_path,
            "returncode": -2,
            "stdout": "",
            "stderr": str(exc),
            "duration": time.time() - t0,
            "success": False,
        }
    finally:
        if proc is not None and proc.pid in active_pids:
            active_pids.remove(proc.pid)


# ---------------------------------------------------------------------------
# HTTP status server
# ---------------------------------------------------------------------------

_STATUS_CSS = """\
:root{--bg:#0b1017;--fg:#e6edf3;--border:#303b4a;--card-bg:#151c26;--card-hover:#1b2532;--meta:#8d9aaa;--link:#69b1ff;--success:#3fb950;--error:#f85149;--running:#388bfd;--queued:#4b5563;--gauge-bg:#273140;--gauge-safe:#3fb950;--gauge-warn:#d29922;--gauge-danger:#f85149;--progress-bg:#202938;--throttle-bg:#d299221a;--throttle-border:#d29922;--throttle-fg:#e3b341;--heading-border:#273140;--table-border:#273140;--shadow:0 12px 32px #00000026}
:root.light{--bg:#f4f7fb;--fg:#1f2937;--border:#d7dee8;--card-bg:#fff;--card-hover:#f8fafc;--meta:#667085;--link:#0969da;--success:#1a7f37;--error:#cf222e;--running:#0969da;--queued:#afb8c1;--gauge-bg:#d8dee7;--gauge-safe:#1a7f37;--gauge-warn:#9a6700;--gauge-danger:#cf222e;--progress-bg:#e7ebf0;--throttle-bg:#fff8c5;--throttle-border:#9a6700;--throttle-fg:#7d4e00;--heading-border:#d8dee7;--table-border:#e5e9ef;--shadow:0 12px 32px #1f293712}
*{margin:0;padding:0;box-sizing:border-box}
body{font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--bg);color:var(--fg);padding:32px 20px;max-width:1040px;margin:0 auto}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
h1{font-size:22px;letter-spacing:-.02em}
#theme-toggle{background:var(--card-bg);border:1px solid var(--border);color:var(--fg);cursor:pointer;font-size:16px;padding:5px 10px;border-radius:9px;line-height:1.4;box-shadow:var(--shadow)}
#theme-toggle:hover{background:var(--card-bg)}
#theme-toggle svg{display:block;width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
#theme-toggle .icon-sun{display:none}:root.light #theme-toggle .icon-sun{display:block}:root.light #theme-toggle .icon-moon{display:none}
h2{font-size:13px;color:var(--meta);margin:24px 0 8px;text-transform:uppercase;letter-spacing:.08em}
.stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:12px 0}
.stat{background:var(--card-bg);border:1px solid var(--border);border-radius:12px;padding:14px 16px;box-shadow:var(--shadow)}
.stat .label{font-size:11px;color:var(--meta);text-transform:uppercase;letter-spacing:.5px}
.stat .value{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums}
.progress{display:flex;background:var(--progress-bg);border:1px solid var(--border);border-radius:10px;margin:18px 0 8px;height:30px;overflow:hidden;box-shadow:var(--shadow)}
.progress-segment{height:100%;min-width:2px;transition:background-color .3s;box-shadow:inset -1px 0 #ffffff28}
.progress-segment.success{background:var(--success)}.progress-segment.failed{background:var(--error)}.progress-segment.running{background:var(--running)}.progress-segment.queued{background:var(--queued)}
.legend{display:flex;flex-wrap:wrap;gap:8px 16px;color:var(--meta);font-size:12px;margin-bottom:4px}.legend span{display:flex;align-items:center;gap:6px}.legend i{width:8px;height:8px;border-radius:50%;background:var(--queued)}.legend .running i{background:var(--running)}.legend .success i{background:var(--success)}.legend .failed i{background:var(--error)}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--meta);font-weight:500;padding:4px 8px}
td{padding:7px 8px;border-top:1px solid var(--table-border)}
tr:hover td{background:var(--card-hover)}
td.ok{color:var(--success)}
td.fail{color:var(--error)}
.meta{font-size:12px;color:var(--meta);margin-top:16px}
.gauge{display:flex;align-items:center;gap:8px}
.gauge-bar{flex:1;background:var(--gauge-bg);border-radius:3px;height:8px;overflow:hidden}
.gauge-fill{height:100%;border-radius:3px}
.gauge-fill.safe{background:var(--gauge-safe)}
.gauge-fill.warn{background:var(--gauge-warn)}
.gauge-fill.danger{background:var(--gauge-danger)}
.throttle{background:var(--throttle-bg);border:1px solid var(--throttle-border);border-radius:10px;padding:8px 12px;margin:12px 0;color:var(--throttle-fg)}
.table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
@media (max-width:640px){body{padding:18px 12px}.header{gap:8px}h1{font-size:18px}#theme-toggle{font-size:14px;padding:4px 8px}h2{font-size:12px;margin-top:20px}.stat-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.stat{padding:10px 12px;border-radius:10px}.stat .value{font-size:20px}.progress{height:24px;margin-top:14px}.legend{gap:5px 12px}table{font-size:12px;min-width:420px}th,td{padding:6px 5px}.meta{font-size:11px;margin-top:10px;overflow-wrap:anywhere}.gauge{font-size:12px}}
"""


def _build_status_html(runner: "BatchRunner") -> str:
    s = runner._snapshot()
    elapsed = time.time() - s["start_time"] if s["start_time"] else 0
    total = s["total"]
    done = s["completed"]
    is_done = done >= total and total > 0

    parts = [
        "<!DOCTYPE html><html><head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">',
        f'<title>batch_runner · {done}/{total} · {s["success"]} OK · {s["failed"]} failed</title>',
        '<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 64 64%27%3E%3Crect width=%2764%27 height=%2764%27 rx=%2714%27 fill=%27%23388bfd%27/%3E%3Cpath d=%27M21 16l23 16-23 16z%27 fill=%27white%27/%3E%3C/svg%3E">',
        "<script>document.documentElement.className=localStorage.getItem('batch-runner-theme')||''</script>",
        f"<style>{_STATUS_CSS}</style></head><body>",
        '<div class="header">',
        f'<h1>🚀 batch_runner &mdash; <span id="h1-total">{total}</span> scripts</h1>',
        '<button id="theme-toggle" title="Toggle theme" aria-label="Toggle color theme">'
        '<svg class="icon-moon" viewBox="0 0 24 24" aria-hidden="true">'
        '<path d="M20.5 14.3A8.5 8.5 0 0 1 9.7 3.5 8.5 8.5 0 1 0 20.5 14.3Z"/>'
        '</svg><svg class="icon-sun" viewBox="0 0 24 24" aria-hidden="true">'
        '<circle cx="12" cy="12" r="3.5"/><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.65 17.65l1.42 1.42M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.65 6.35l1.42-1.42"/>'
        '</svg></button>',
        "</div>",
    ]

    if s["start_time"]:
        t0 = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(s["start_time"]))
        parts.append(
            f'<div class="meta">Started {t0} &middot; '
            f'<span id="meta-elapsed">Elapsed {_fmt_dh(elapsed)}</span></div>'
        )

    parts.append(
        '<div id="throttle-banner" class="throttle"'
        f' style="display:{"block" if s["throttled"] else "none"}">⚠️ THROTTLED</div>'
    )

    # One equally sized segment per task so mixed outcomes remain visible.
    progress_states = [
        "success" if result["success"] else "failed" for result in s["results"]
    ]
    progress_states.extend("running" for _ in s["running"])
    progress_states.extend("queued" for _ in range(max(0, total - len(progress_states))))
    parts.append('<div id="prog" class="progress" aria-label="Task progress">')
    for state in progress_states:
        parts.append(f'<span class="progress-segment {state}" style="flex:1"></span>')
    parts.append("</div>")
    parts.append(
        '<div class="legend"><span><i></i>🕒 Queued</span>'
        '<span class="running"><i></i>⚙️ Running</span>'
        '<span class="success"><i></i>✅ Succeeded</span>'
        '<span class="failed"><i></i>❌ Failed</span></div>'
    )

    # stats
    running_n = len(s["running"])
    parts.append('<div class="stat-grid">')
    parts.append(
        '<div class="stat"><div class="label">📋 Completed</div>'
        f'<div class="value" id="st-completed">{done}/{total}</div></div>'
    )
    parts.append(
        '<div class="stat"><div class="label">⚙️ Running</div>'
        f'<div class="value" id="st-running">{running_n}</div></div>'
    )
    parts.append(
        '<div class="stat"><div class="label">✅ Succeeded</div>'
        f'<div class="value" style="color:var(--success)" id="st-success">{s["success"]}</div></div>'
    )
    parts.append(
        '<div class="stat"><div class="label">❌ Failed</div>'
        f'<div class="value" style="color:var(--error)" id="st-failed">{s["failed"]}</div></div>'
    )
    parts.append("</div>")

    # running / queued / completed — rendered server-side then updated by JS
    parts.append('<div id="running-section">')
    if s["running"]:
        parts.append('<h2>⚙️ Running</h2><div class="table-wrap"><table>')
        parts.append("<tr><th>Script</th><th>Duration</th></tr>")
        for r in s["running"]:
            dur = _fmt_dh(time.time() - r["start"])
            parts.append(
                f"<tr><td>{_h_esc(_sanitize_path(r['script']))}</td><td>{dur}</td></tr>"
            )
        parts.append("</table></div>")
    parts.append("</div>")

    parts.append('<div id="queued-section">')
    if s["queued"]:
        parts.append('<h2>🕒 Queued</h2><div class="table-wrap"><table>')
        for q in s["queued"][:30]:
            parts.append(f"<tr><td>{_h_esc(_sanitize_path(q['path']))}</td></tr>")
        if len(s["queued"]) > 30:
            parts.append(f"<tr><td>... and {len(s['queued']) - 30} more</td></tr>")
        parts.append("</table></div>")
    parts.append("</div>")

    parts.append('<div id="completed-section">')
    if s["results"]:
        recent = s["results"][-20:]
        parts.append('<h2>📋 Completed</h2><div class="table-wrap"><table>')
        parts.append("<tr><th>Script</th><th>Duration</th><th>Status</th></tr>")
        for r in recent:
            status = "✅ OK" if r["success"] else f"❌ FAIL rc={r['returncode']}"
            cls = "ok" if r["success"] else "fail"
            parts.append(
                f"<tr><td>{_h_esc(_sanitize_path(r['script_path']))}</td>"
                f"<td>{_fmt_dh(r['duration'])}</td>"
                f'<td class="{cls}">{status}</td></tr>'
            )
        parts.append("</table></div>")
    parts.append("</div>")

    # resources
    parts.append('<div id="resources-section">')
    if s.get("cpu_percent") is not None:
        cpu = s["cpu_percent"]
        mem = s["mem_percent"]
        cpu_cls = "safe" if cpu < 70 else ("warn" if cpu < 90 else "danger")
        mem_cls = "safe" if mem < 70 else ("warn" if mem < 90 else "danger")
        parts.append('<div class="gauge"><span>CPU</span>')
        parts.append(
            '<div class="gauge-bar"><div id="cpu-fill" class="gauge-fill '
            f'{cpu_cls}" style="width:{min(100, cpu):.0f}%"></div></div>'
        )
        parts.append(f'<span id="cpu-val">{cpu:.1f}%</span></div>')
        parts.append('<div class="gauge"><span>Mem</span>')
        parts.append(
            '<div class="gauge-bar"><div id="mem-fill" class="gauge-fill '
            f'{mem_cls}" style="width:{min(100, mem):.0f}%"></div></div>'
        )
        parts.append(f'<span id="mem-val">{mem:.1f}%</span></div>')
    parts.append("</div>")

    parts.append(
        '<div class="meta">' '<a href="/api/status" style="color:var(--link)">JSON</a>'
    )
    if s.get("output_dir"):
        parts.append(f" &middot; Output: {_h_esc(s['output_dir'])}")
    parts.append("</div>")

    # -- JS polling --
    parts.append(
        "<script>"
        "(function(){"
        "var btn=document.getElementById('theme-toggle');"
        "var root=document.documentElement;"
        "btn.addEventListener('click',function(){"
        "var isLight=root.classList.toggle('light');"
        "localStorage.setItem('batch-runner-theme',isLight?'light':'');"
        "});"
        "})();"
        "var _poll=null,_done=" + ("true" if is_done else "false") + ";"
        "function _esc(t){return t.replace(/&/g,'&amp;').replace(/</g,'&lt;')"
        ".replace(/>/g,'&gt;');}"
        "function _dh(s){if(s<60)return s.toFixed(1)+'s';"
        "if(s<3600){var m=Math.floor(s/60),r=Math.floor(s%60);"
        "return m+'m'+r+'s';}"
        "var h=Math.floor(s/3600),m=Math.floor((s%3600)/60);"
        "return h+'h'+m+'m';}"
        "function _update(){"
        "fetch('/api/status').then(function(r){return r.json()}).then(function(s){"
        "var t=s.total,d=s.completed;"
        "var el=s.start_time?_dh(Date.now()/1000-s.start_time):'0s';"
        "var states=s.results.map(function(r){return r.success?'success':'failed';});"
        "s.running.forEach(function(){states.push('running');});"
        "while(states.length<t)states.push('queued');"
        "document.getElementById('prog').innerHTML=states.map(function(st){"
        "return '<span class=\"progress-segment '+st+'\" style=\"flex:1\"></span>';}).join('');"
        "document.getElementById('st-completed').textContent=d+'/'+t;"
        "document.getElementById('st-running').textContent=s.running.length;"
        "document.getElementById('st-success').textContent=s.success;"
        "document.getElementById('st-failed').textContent=s.failed;"
        "document.title='batch_runner · '+d+'/'+t+' · '+s.success+' OK · '+s.failed+' failed';"
        "document.getElementById('meta-elapsed').textContent='Elapsed '+el;"
        "document.getElementById('throttle-banner').style.display=s.throttled?'block':'none';"
        "document.getElementById('h1-total').textContent=t;"
        "var rn=document.getElementById('running-section');"
        "if(s.running.length){"
        "var h='<h2>⚙️ Running</h2><div class=\"table-wrap\"><table><tr><th>Script</th><th>Duration</th></tr>';"
        "var now=Date.now()/1000;"
        "s.running.forEach(function(r){h+='<tr><td>'+_esc(r.display||r.script)+'</td><td>'+_dh(now-r.start)+'</td></tr>';});"
        "h+='</table></div>';rn.innerHTML=h;}else{rn.innerHTML='';}"
        "var qn=document.getElementById('queued-section');"
        "if(s.queued.length){"
        "var h='<h2>🕒 Queued</h2><div class=\"table-wrap\"><table>';"
        "s.queued.slice(0,30).forEach(function(q){h+='<tr><td>'+_esc(q.display||q.path||q)+'</td></tr>';});"
        "if(s.queued.length>30)h+='<tr><td>... and '+(s.queued.length-30)+' more</td></tr>';"
        "h+='</table></div>';qn.innerHTML=h;}else{qn.innerHTML='';}"
        "var cn=document.getElementById('completed-section');"
        "if(s.results.length){"
        "var h='<h2>📋 Completed</h2><div class=\"table-wrap\"><table><tr><th>Script</th><th>Duration</th><th>Status</th></tr>';"
        "s.results.slice(-20).forEach(function(r){"
        "var st=r.success?'✅ OK':'❌ FAIL rc='+r.returncode;"
        "var cl=r.success?'ok':'fail';"
        "h+='<tr><td>'+_esc(r.display||r.script_path)+'</td><td>'+_dh(r.duration)+'</td><td class=\"'+cl+'\">'+st+'</td></tr>';"
        "});h+='</table></div>';cn.innerHTML=h;}else{cn.innerHTML='';}"
        "if(s.cpu_percent!=null){"
        "var cpu=s.cpu_percent,mem=s.mem_percent;"
        "var cc=cpu<70?'safe':(cpu<90?'warn':'danger');"
        "var mc=mem<70?'safe':(mem<90?'warn':'danger');"
        "document.getElementById('cpu-fill').className='gauge-fill '+cc;"
        "document.getElementById('cpu-fill').style.width=Math.min(100,cpu)+'%';"
        "document.getElementById('cpu-val').textContent=cpu.toFixed(1)+'%';"
        "document.getElementById('mem-fill').className='gauge-fill '+mc;"
        "document.getElementById('mem-fill').style.width=Math.min(100,mem)+'%';"
        "document.getElementById('mem-val').textContent=mem.toFixed(1)+'%';}"
        "if(d>=t&&t>0){if(_poll){clearInterval(_poll);_poll=null;}}"
        "});}"
        "if(!_done){_poll=setInterval(_update,2000);_update();}"
        "</script>"
    )

    parts.append("</body></html>")
    return "\n".join(parts)


def _h_esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _sanitize_path(path: str) -> str:
    home = os.path.normpath(os.path.expanduser("~"))
    p = os.path.normpath(path)
    if p == home:
        return "~"
    if p.startswith(home + os.sep):
        return "~" + p[len(home) :].replace("\\", "/")
    return path.replace("\\", "/")


class _StatusHandler(BaseHTTPRequestHandler):
    runner: "BatchRunner" = None  # type: ignore[assignment]

    def log_message(self, format: str, *args: object) -> None:  # type: ignore[override]
        pass  # suppress access logs

    def do_GET(self) -> None:
        if self.path == "/api/status":
            self._json_response()
        else:
            self._html_response()

    def _html_response(self) -> None:
        html = _build_status_html(self.runner)
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_response(self) -> None:
        s = self.runner._snapshot()
        body = json.dumps(s, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# BatchRunner
# ---------------------------------------------------------------------------


class BatchRunner:
    _POLL_INTERVAL = 0.5  # seconds between completion checks

    def __init__(
        self,
        args,
        scripts: list[str],
        taskfiles: list[str],
        direct_scripts: list[str] | None = None,
    ):
        self.args = args
        self.scripts = scripts
        self._taskfiles = [os.path.abspath(tf) for tf in taskfiles]
        self._direct_scripts: list[str] = list(direct_scripts or [])

        self.log = logging.getLogger("batch")
        self.log.setLevel(logging.INFO)
        self.log.handlers.clear()

        self._exec_cache: dict[str, Executor] = {}
        self._lock = threading.Lock()
        self._start_time: float = 0
        self._pending: list[str] = []
        self._port: int = getattr(args, "port", 0) or 0
        self._httpd: ThreadingHTTPServer | None = None
        self.completed = 0
        self.success = 0
        self.failed = 0
        self._total = 0
        self._results: list[dict] = []
        self._futures: dict = {}
        self._stop = False
        self._force_stop = False
        self._pool: Optional[ProcessPoolExecutor] = None
        self._timeout_s: Optional[int] = None
        self._output_dir: str = ""
        self._manager = Manager()
        self._active_pids = self._manager.list()
        self._throttled: bool = False
        self._cpu_ok: bool = True
        self._mem_ok: bool = True
        self._cpu_window: list[float] = []  # rolling window for SMA
        self._cpu_window_size: int = 3
        self._running_start_times: dict[str, float] = {}
        self._throttle_until: float = 0  # cooldown deadline

    def run(self) -> None:
        scripts = self.scripts

        # --- header (console only — log file not set up yet) ---
        source_parts: list[str] = []
        if self._taskfiles:
            source_parts.append(" + ".join(self._taskfiles))
        if self._direct_scripts:
            n = len(self._direct_scripts)
            if n <= 3:
                source_parts.extend(self._direct_scripts)
            else:
                source_parts.append(f"{n} scripts")
        source = " + ".join(source_parts) if source_parts else "(none)"
        print(f"\nbatch_runner — {len(scripts)} scripts from {source}")
        for s in scripts[:20]:
            print(f"  {s}")
        if len(scripts) > 20:
            print(f"  ... and {len(scripts) - 20} more")

        if not scripts:
            return

        timeout_s = _parse_duration(self.args.timeout)
        self._timeout_s = None if timeout_s <= 0 else int(timeout_s)

        # Resource limits
        cpu_limit = self.args.cpu_limit
        mem_limit = self.args.mem_limit
        if not HAS_PSUTIL:
            cpu_limit = mem_limit = 0.0
        if HAS_PSUTIL and cpu_limit > 0:
            assert psutil is not None
            psutil.cpu_percent()  # seed first reading
        self._cpu_limit = cpu_limit
        self._mem_limit = mem_limit

        parts = [
            f"Workers: {self.args.jobs}",
            f"Timeout: {_fmt_dh(timeout_s) if timeout_s > 0 else 'no limit'}",
        ]
        if self._cpu_limit > 0:
            parts.append(f"CPU limit: {self._cpu_limit:.0f}%")
        if self._mem_limit > 0:
            parts.append(f"Mem limit: {self._mem_limit:.0f}%")
        config_line = "  |  ".join(parts)
        print(f"\n{config_line}")

        # Confirmation (before creating any output directory)
        if not self.args.yes:
            try:
                input("\nPress Enter to continue...")
            except (EOFError, KeyboardInterrupt):
                print("Aborted.")
                return

        # -- Start status server (after confirmation) --
        self._start_server()

        # -- Set up output directory and file logger --
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.join(os.getcwd(), ".batch_runner", ts)
        os.makedirs(out_dir, exist_ok=True)
        self._output_dir = out_dir
        print(f"\nOutput: {os.path.abspath(out_dir)}")

        fmt = logging.Formatter(
            "%(asctime)s  [%(levelname)s]  %(message)s", "%Y-%m-%d %H:%M:%S"
        )
        fh = logging.FileHandler(os.path.join(out_dir, "runner.log"), encoding="utf-8")
        fh.setFormatter(fmt)
        self.log.addHandler(fh)

        # Replay header to log file
        self.log.info("Found %d script(s) from %s", len(scripts), source)
        for s in scripts:
            self.log.info("  %s", s)
        if self._cpu_limit > 0 or self._mem_limit > 0:
            if not HAS_PSUTIL:
                self.log.info("psutil not installed; resource limits ignored.")
        self.log.info(config_line)
        self.log.info("Output dir: %s", os.path.abspath(out_dir))

        signal.signal(signal.SIGINT, self._on_signal)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, self._on_signal)

        t0 = time.time()
        self._start_time = t0
        self._pool = ProcessPoolExecutor(max_workers=self.args.jobs)
        pending = list(scripts)
        self._pending = pending
        self._total = len(scripts)

        try:
            while pending or self._futures:
                if self._force_stop:
                    self._kill_all_children()
                    break
                if self._stop and not self._futures:
                    break
                self._submit(pending)
                if not self._futures:
                    break
                self._wait()
        except KeyboardInterrupt:
            print("\nInterrupted.")
            self._force_stop = True
            self.log.warning("Interrupted by user.")
        finally:
            self._kill_all_children()
            if self._pool:
                self._pool.shutdown(wait=False, cancel_futures=True)
            self._manager.shutdown()

        # --- results ---
        elapsed = time.time() - t0
        print("\n===== Results =====")
        for r in self._results:
            if r["success"]:
                print(f"  OK    {_fmt_dh(r['duration'])}  {r['script_path']}")
            else:
                print(
                    f"  FAIL  {_fmt_dh(r['duration'])}  rc={r['returncode']}  {r['script_path']}"
                )
                err = r["stderr"].strip()
                if err:
                    for line in err.splitlines()[:3]:
                        print(f"        {line[:120]}")
        print(
            f"===== {self.success} succeeded, {self.failed} failed — {_fmt_dh(elapsed)} ====="
        )
        self.log.info("Results:")
        for r in self._results:
            if r["success"]:
                self.log.info(
                    "  OK    %s  (%s)", r["script_path"], _fmt_dh(r["duration"])
                )
            else:
                self.log.info(
                    "  FAIL  %s  rc=%d  (%s)",
                    r["script_path"],
                    r["returncode"],
                    _fmt_dh(r["duration"]),
                )
        self.log.info(
            "Finished  %d scripts  |  %d succeeded  |  %d failed  |  %s elapsed",
            self._total,
            self.success,
            self.failed,
            _fmt_dh(elapsed),
        )

        if self._port > 0 and not self._force_stop:
            print(
                f"\nAll tasks complete.  Server: http://localhost:{self._port}"
                f"  |  Press Ctrl+C to stop."
            )
            try:
                while not self._force_stop:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nShutting down server...")
        self._stop_server()

    def _ex_for(self, path: str) -> Executor:
        ext = os.path.splitext(path)[1]
        if ext not in self._exec_cache:
            self._exec_cache[ext] = make_executor(ext)
        return self._exec_cache[ext]

    def _can_submit(self) -> bool:
        if not HAS_PSUTIL:
            return True
        assert psutil is not None
        if not self._futures:
            return True  # always allow at least one worker

        # honour cooldown after a throttle event
        if self._throttled and time.time() < self._throttle_until:
            return False

        ok = True
        if self._cpu_limit > 0:
            cpu = psutil.cpu_percent(interval=None)
            self._cpu_window.append(cpu)
            if len(self._cpu_window) > self._cpu_window_size:
                self._cpu_window.pop(0)
            avg = sum(self._cpu_window) / len(self._cpu_window)
            if avg > self._cpu_limit:
                ok = False
                self._cpu_ok = False
            else:
                self._cpu_ok = True
        if self._mem_limit > 0:
            mem = psutil.virtual_memory()
            if mem.percent > self._mem_limit:
                ok = False
                self._mem_ok = False
            else:
                self._mem_ok = True
        return ok

    def _submit(self, pending: list[str]) -> None:
        assert self._pool is not None
        while (
            not self._stop
            and not self._force_stop
            and pending
            and len(self._futures) < self.args.jobs
        ):
            if not self._can_submit():
                if not self._throttled:
                    self._throttled = True
                    reason = []
                    if not self._cpu_ok:
                        assert psutil is not None
                        cpu = psutil.cpu_percent(interval=None)
                        reason.append(f"CPU {cpu:.0f}% > {self._cpu_limit:.0f}%")
                    if not self._mem_ok:
                        assert psutil is not None
                        reason.append(
                            f"mem {psutil.virtual_memory().percent:.0f}% > {self._mem_limit:.0f}%"
                        )
                    self.log.warning(
                        "Throttled  %s  [%d queued]", ", ".join(reason), len(pending)
                    )
                    print(f"  throttled: {', '.join(reason)}  [{len(pending)} queued]")
                    self._throttle_until = time.time() + 5  # cooldown
                break
            if self._throttled:
                self._throttled = False
                self.log.info("Throttle cleared  [resuming submission]")
                print("  resuming submission")
            s = pending.pop(0)
            n_running = len(self._futures) + 1
            n_queued = len(pending)
            self.log.info(
                "Submit  %s  [%d running, %d queued]",
                s,
                n_running,
                n_queued,
            )
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            print(
                f"  start  {s}  ({n_running} running, {n_queued} queued, "
                f"{self.completed}/{self._total} done)  ({ts})"
            )
            cmd = self._ex_for(s).build_command(s)
            cwd = os.path.dirname(os.path.abspath(s))
            fut = self._pool.submit(
                run_script, cmd, s, self._timeout_s, cwd, self._active_pids
            )
            self._futures[fut] = s
            self._running_start_times[s] = time.time()

    def _wait(self) -> None:
        done, _ = wait(
            self._futures, timeout=self._POLL_INTERVAL, return_when=FIRST_COMPLETED
        )
        for fut in done:
            s = self._futures.pop(fut)
            self._running_start_times.pop(s, None)
            try:
                r = fut.result(timeout=1)
            except Exception as exc:
                self.failed += 1
                self.completed += 1
                self.log.error("Exception in worker for %s: %s", s, exc)
                continue
            self.completed += 1
            self._write_output(r)
            self._results.append(r)
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            if r["success"]:
                self.success += 1
                print(f"  OK  {_fmt_dh(r['duration'])}  {s}  ({ts})")
                self.log.info(
                    "Done   %s  (%s)",
                    s,
                    _fmt_dh(r["duration"]),
                )
            else:
                self.failed += 1
                err_preview = r["stderr"].strip()[:120]
                print(
                    f"  FAIL  rc={r['returncode']}  {_fmt_dh(r['duration'])}  "
                    f"{s}  ({ts})"
                )
                if err_preview:
                    print(f"         {err_preview}")
                self.log.error(
                    "Fail   %s  rc=%d  %s",
                    s,
                    r["returncode"],
                    r["stderr"][:120],
                )

    def _write_output(self, r: dict) -> None:
        content = f"{r['stdout']}{r['stderr']}"
        if not content:
            return
        name = re.sub(r"[\\/:*?\"<>|]", "_", r["script_path"])
        fpath = os.path.join(self._output_dir, f"{name}.log")
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)

    def _on_signal(self, *_args: object) -> None:  # type: ignore[unused-argument]
        if self._futures or self._pending:
            print("\nStopping... (killing running tasks)")
            self.log.warning("Stopping... (killing running tasks)")
        else:
            print("")
        self._stop = True
        self._force_stop = True

    def _kill_all_children(self) -> None:
        for pid in list(self._active_pids):
            _kill_pid(pid)
        self._active_pids[:] = []

    # -- status server --

    def _snapshot(self) -> dict:
        """Thread-safe snapshot of current state."""
        with self._lock:
            running = []
            for _fut, path in list(self._futures.items()):
                running.append(
                    {
                        "script": path,
                        "display": _sanitize_path(path),
                        "start": self._running_start_times.get(path, time.time()),
                    }
                )
            queued = [{"path": p, "display": _sanitize_path(p)} for p in self._pending]
            results = []
            for r in self._results:
                r2 = dict(r)
                r2["display"] = _sanitize_path(r["script_path"])
                results.append(r2)
            state = {
                "total": self._total,
                "completed": self.completed,
                "success": self.success,
                "failed": self.failed,
                "throttled": self._throttled,
                "start_time": self._start_time,
                "running": running,
                "queued": queued,
                "results": results,
                "output_dir": _sanitize_path(self._output_dir),
            }
        if HAS_PSUTIL and self._port > 0:
            assert psutil is not None
            try:
                state["cpu_percent"] = psutil.cpu_percent(interval=None)
                state["mem_percent"] = psutil.virtual_memory().percent
            except Exception:
                state["cpu_percent"] = None
                state["mem_percent"] = None
        return state

    def _start_server(self) -> None:
        if self._port <= 0:
            return
        _StatusHandler.runner = self
        port = self._port
        max_tries = 100
        for _ in range(max_tries):
            try:
                self._httpd = ThreadingHTTPServer(
                    (self.args.bind, port), _StatusHandler
                )
                self._httpd.timeout = 0.5
                t = threading.Thread(target=self._httpd.serve_forever, daemon=True)
                t.start()
                self._port = port
                print(f"Status server: http://localhost:{self._port}")
                return
            except OSError:
                port += 1
        print(
            f"Warning: Could not start status server "
            f"(ports {self._port}–{port - 1} in use)"
        )
        self._port = 0

    def _stop_server(self) -> None:
        if self._httpd is None:
            return
        # Close the socket to unblock serve_forever's select() before shutdown
        try:
            self._httpd.socket.close()
        except Exception:
            pass
        try:
            self._httpd.shutdown()
        except Exception:
            pass
        self._httpd.server_close()
        self._httpd = None


def main() -> None:
    p = argparse.ArgumentParser(
        description="Run a list of scripts in parallel with resource control.",
    )

    p.add_argument(
        "scripts",
        nargs="*",
        metavar="script",
        help="Script files to run (.py or .m).",
    )
    p.add_argument(
        "-f",
        "--file",
        action="append",
        default=[],
        metavar="TASKFILE",
        help="Task file(s) listing scripts (repeatable, one script per line).",
    )
    p.add_argument(
        "-j", "--jobs", type=int, default=1, help="Max concurrent workers (default: 1)."
    )
    p.add_argument(
        "--timeout",
        type=str,
        default="24h",
        help="Per-script timeout, e.g. 2h, 90m, 45s (default: 24h; 0 = no limit).",
    )
    p.add_argument(
        "--cpu-limit",
        type=float,
        default=80,
        metavar="PCT",
        help="Max CPU %% before throttling submission (default: 80; 0 = off; requires psutil).",
    )
    p.add_argument(
        "--mem-limit",
        type=float,
        default=80,
        metavar="PCT",
        help="Max memory usage %% before throttling submission (default: 80; 0 = off; requires psutil).",
    )
    p.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt.")
    p.add_argument(
        "-p",
        "--port",
        type=int,
        default=8080,
        metavar="PORT",
        help="HTTP status server port (default: 8080; 0 = off).",
    )
    p.add_argument(
        "--bind",
        type=str,
        default="127.0.0.1",
        metavar="ADDR",
        help="Bind address for status server (default: 127.0.0.1; use 0.0.0.0 for LAN access).",
    )

    args = p.parse_args()

    # No TTY means pipeline / redirect — can't prompt for confirmation
    if not sys.stdin.isatty():
        args.yes = True

    if not args.scripts and not args.file:
        print(
            "Error: no inputs. Provide scripts as positional arguments "
            "or use -f/--file for task files.",
            file=sys.stderr,
        )
        sys.exit(1)

    scripts: list[str] = []
    seen: set[str] = set()

    # Step 1: task files via -f
    for tf in args.file:
        try:
            for s in parse_taskfiles([tf]):
                key = os.path.abspath(s)
                if key not in seen:
                    seen.add(key)
                    scripts.append(s)
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    # Step 2: direct scripts from positional args
    for s in args.scripts:
        if not os.path.isfile(s):
            print(f"Error: script not found: {s}", file=sys.stderr)
            sys.exit(1)
        ext = os.path.splitext(s)[1].lower()
        if ext not in (".m", ".py"):
            print(f"Error: unsupported file type '{ext}': {s}", file=sys.stderr)
            sys.exit(1)
        key = os.path.abspath(s)
        if key not in seen:
            seen.add(key)
            scripts.append(s)

    if not scripts:
        print("Error: no scripts found.", file=sys.stderr)
        sys.exit(1)

    taskfiles_display = [tf if tf != "-" else "(stdin)" for tf in args.file]
    runner = BatchRunner(args, scripts, taskfiles_display, args.scripts)
    runner.run()
    if runner.failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
