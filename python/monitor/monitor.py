#!/usr/bin/env python3
"""
Robust Real-time Log Monitor — tail -f on steroids.
Monitors one or more log files, highlights errors/warnings,
and optionally serves a live web dashboard.
Cross-platform (Windows & Linux).  Zero dependencies.
"""

import argparse
import collections
import glob
import json
import os
import re
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ERROR_PATTERN = r"\b(?:ERR|ERROR|EXCEPTION|CATCH|FATAL|FAIL|PANIC)\b"
WARN_PATTERN = r"\b(?:WARN|WARNING|CAUTION|DEPRECATED|INF|NAN)\b"
END_PATTERN = r"\b(?:END|FINISH|CLOSED|COMPLETED|EXIT|TERMINATED)\b"

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    kb = size_bytes / 1024
    if kb < 1024:
        return f"{kb:.2f} KB"
    mb = kb / 1024
    if mb < 1024:
        return f"{mb:.2f} MB"
    gb = mb / 1024
    return f"{gb:.2f} GB"


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


def _expand_paths(raw: list[str]) -> list[str]:
    all_files: list[str] = []
    for p in raw:
        expanded = glob.glob(os.path.expanduser(p).replace("\\", "/"))
        if expanded:
            all_files.extend(expanded)
        else:
            all_files.append(os.path.expanduser(p).replace("\\", "/"))
    return sorted(set(all_files))


def _fmt_dh(seconds: float) -> str:
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


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

_STATUS_CSS = """
:root{--bg:#0d1117;--fg:#c9d1d9;--border:#30363d;--card-bg:#161b22;--card-hover:#1c2333;--meta:#8b949e;--link:#58a6ff;--line-err-bg:#490202;--line-err-fg:#ff7b72;--line-warn-bg:#3d3200;--line-warn-fg:#d29922;--line-end-bg:#0d3d1a;--line-end-fg:#7ee787;--badge-active-bg:#1a3d1a;--badge-active-fg:#7ee787;--badge-idle-bg:#1a2d3d;--badge-idle-fg:#7eb8da;--badge-missing-bg:#3d1a1a;--badge-missing-fg:#ff7b72;--heading-border:#30363d;--row-hover:#161b22;--table-border:#21262d}
:root.light{--bg:#fff;--fg:#24292f;--border:#d0d7de;--card-bg:#f6f8fa;--card-hover:#eaeef2;--meta:#656d76;--link:#0969da;--line-err-bg:#ffebe9;--line-err-fg:#cf222e;--line-warn-bg:#fff8c5;--line-warn-fg:#9a6700;--line-end-bg:#dafbe1;--line-end-fg:#1a7f37;--badge-active-bg:#dafbe1;--badge-active-fg:#1a7f37;--badge-idle-bg:#ddf4ff;--badge-idle-fg:#0969da;--badge-missing-bg:#ffebe9;--badge-missing-fg:#cf222e;--heading-border:#d0d7de;--row-hover:#f6f8fa;--table-border:#d0d7de}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--fg);padding:20px;max-width:1100px;margin:0 auto}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}
h1{font-size:20px}
h2{font-size:16px;margin:16px 0 8px;border-bottom:1px solid var(--heading-border);padding-bottom:4px}
#theme-toggle{background:none;border:1px solid var(--border);color:var(--fg);cursor:pointer;font-size:16px;padding:3px 8px;border-radius:6px;line-height:1.4}
#theme-toggle:hover{background:var(--card-bg)}
.meta{color:var(--meta);font-size:13px;margin:2px 0 8px}
.meta a{color:var(--link)}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:4px 8px;font-size:13px;border-bottom:1px solid var(--table-border)}
th{color:var(--meta);font-weight:600}
tr:hover{background:var(--row-hover)}
.file-card{border:1px solid var(--border);border-radius:6px;margin:12px 0;overflow:hidden}
.file-header{background:var(--card-bg);padding:8px 12px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;cursor:pointer;user-select:none}
.file-header:hover{background:var(--card-hover)}
.file-path{font-family:monospace;font-size:13px;color:var(--link)}
.file-path::before{content:"\\25b6\\a0";font-size:10px;color:var(--meta);transition:transform .2s}
.file-card.compact .file-path::before,.file-card.expanded .file-path::before{content:"\\25bc\\a0"}
.file-meta{font-size:12px;color:var(--meta)}
.file-lines{display:none;padding:4px 0}
.file-card.compact .file-lines{display:block}
.file-card.compact .file-lines pre:not(:nth-last-of-type(-n+5)){display:none}
.file-card.expanded .file-lines{display:block}
.line-badge{display:none;font-size:9px;color:var(--meta);font-family:system-ui;margin-left:4px}
.file-card.compact .compact-badge{display:inline}
.file-card.expanded .expanded-badge{display:inline}
.file-lines pre{margin:0;padding:2px 12px;font-size:12px;font-family:monospace;white-space:pre-wrap;word-break:break-all;line-height:1.5}
.file-lines pre.line-err{background:var(--line-err-bg);color:var(--line-err-fg)}
.file-lines pre.line-warn{background:var(--line-warn-bg);color:var(--line-warn-fg)}
.file-lines pre.line-end{background:var(--line-end-bg);color:var(--line-end-fg)}
.badge{display:inline-block;padding:1px 6px;border-radius:10px;font-size:11px;font-weight:600}
.badge-active{background:var(--badge-active-bg);color:var(--badge-active-fg)}
.badge-idle{background:var(--badge-idle-bg);color:var(--badge-idle-fg)}
.badge-missing{background:var(--badge-missing-bg);color:var(--badge-missing-fg)}
.stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:12px 0}
.stat{background:var(--card-bg);border:1px solid var(--border);border-radius:6px;padding:12px}
.stat .label{font-size:11px;color:var(--meta);text-transform:uppercase;letter-spacing:.5px}
.stat .value{font-size:22px;font-weight:600}
@media (max-width:640px){body{padding:12px}.header{flex-wrap:wrap;gap:8px}h1{font-size:17px}#theme-toggle{font-size:14px;padding:2px 6px}h2{font-size:14px}.stat-grid{grid-template-columns:repeat(2,1fr);gap:6px}.stat{padding:8px 10px}.stat .value{font-size:18px}.stat .label{font-size:10px}.file-header{padding:6px 8px}.file-path{font-size:11px}.file-meta{font-size:10px}.file-lines pre{font-size:10px;padding:1px 8px}.badge{font-size:10px}.meta{font-size:11px}}
"""


def _build_status_html(monitor: "LogMonitor") -> str:
    s = monitor._snapshot()
    files = s["files"]
    total = s["total"]
    is_running = s["running"]

    parts = [
        "<!DOCTYPE html><html><head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">',
        "<title>monitor status</title>",
        "<script>document.documentElement.className=localStorage.getItem('monitor-theme')||''</script>",
        f"<style>{_STATUS_CSS}</style></head><body>",
        '<div class="header">',
        f'<h1>monitor &mdash; <span id="h1-total">{total}</span> file{"s" if total != 1 else ""}</h1>',
        '<button id="theme-toggle" title="Toggle theme">☽</button>',
        "</div>",
    ]

    # started / elapsed
    if s["start_time"]:
        t0 = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(s["start_time"]))
        elapsed = time.time() - s["start_time"]
        parts.append(
            f'<div class="meta">Started {t0} &middot; '
            f'<span id="meta-elapsed">Elapsed {_fmt_dh(elapsed)}</span></div>'
        )

    meta_parts = []
    if s["interval"]:
        meta_parts.append(f"Interval: {s['interval']}s")
    if is_running:
        meta_parts.append('<a href="/api/status">JSON</a>')
    parts.append(
        f'<div class="meta" id="meta-bar">' f'{" &middot; ".join(meta_parts)}</div>'
    )

    active_c = sum(1 for f in files if f["status"] == "active")
    idle_c = sum(1 for f in files if f["status"] == "idle")
    missing_c = sum(1 for f in files if f["status"] == "missing")
    parts.append('<div class="stat-grid" id="stat-grid">')
    parts.append(
        '<div class="stat" title="Total files being monitored">'
        '<div class="label">Total</div>'
        f'<div class="value" id="st-total">{total}</div></div>'
    )
    parts.append(
        '<div class="stat" title="File is open and has received new content within the last 30 seconds">'
        '<div class="label">Active</div>'
        f'<div class="value" style="color:var(--badge-active-fg)" id="st-active">{active_c}</div></div>'
    )
    parts.append(
        '<div class="stat" title="File exists but no new content for over 30 seconds">'
        '<div class="label">Idle</div>'
        f'<div class="value" style="color:var(--badge-idle-fg)" id="st-idle">{idle_c}</div></div>'
    )
    parts.append(
        '<div class="stat" title="File not found or cannot be opened">'
        '<div class="label">Missing</div>'
        f'<div class="value" style="color:var(--badge-missing-fg)" id="st-missing">{missing_c}</div></div>'
    )
    parts.append("</div>")

    # file cards container
    parts.append('<div id="files-container">')
    for f in files:
        _append_file_card(parts, f)
    parts.append("</div>")

    # -- JS --
    parts.append(
        "<script>"
        "var _poll=null,_running=" + ("true" if is_running else "false") + ";"
        "function _esc(t){return t.replace(/&/g,'&amp;').replace(/</g,'&lt;')"
        ".replace(/>/g,'&gt;');}"
        "function _dh(s){if(s<60)return s.toFixed(1)+'s';"
        "if(s<3600){var m=Math.floor(s/60),r=Math.floor(s%60);"
        "return m+'m'+r+'s';}"
        "var h=Math.floor(s/3600),m=Math.floor((s%3600)/60);"
        "return h+'h'+m+'m';}"
        "(function(){"
        "var btn=document.getElementById('theme-toggle');"
        "var root=document.documentElement;"
        "btn.textContent=root.classList.contains('light')?'\\u2600':'\\u263d';"
        "btn.addEventListener('click',function(){"
        "var isLight=root.classList.toggle('light');"
        "btn.textContent=isLight?'\\u2600':'\\u263d';"
        "localStorage.setItem('monitor-theme',isLight?'light':'');"
        "});"
        "})();"
        "document.getElementById('files-container').addEventListener('click',function(e){"
        "var hdr=e.target.closest('.file-header');"
        "if(hdr){"
        "var card=hdr.parentElement;"
        "if(card.classList.contains('expanded')){card.classList.remove('expanded','compact');}"
        "else if(card.classList.contains('compact')){card.classList.remove('compact');card.classList.add('expanded');}"
        "else{card.classList.add('compact');}"
        "}"
        "});"
        "function _update(){"
        "fetch('/api/status').then(function(r){return r.json()}).then(function(s){"
        "var total=s.total,a=0,i=0,m=0;"
        "s.files.forEach(function(f){"
        "if(f.status==='active')a++;"
        "else if(f.status==='idle')i++;"
        "else if(f.status==='missing')m++;"
        "});"
        "document.getElementById('h1-total').textContent=total;"
        "document.getElementById('st-total').textContent=total;"
        "document.getElementById('st-active').textContent=a;"
        "document.getElementById('st-idle').textContent=i;"
        "document.getElementById('st-missing').textContent=m;"
        "var meta=s.interval?'Interval: '+s.interval+'s':'';"
        "if(s.running)meta+=(meta?' &middot; ':'')+'<a href=\"/api/status\">JSON</a>';"
        "document.getElementById('meta-bar').innerHTML=meta;"
        "if(s.start_time){document.getElementById('meta-elapsed').textContent='Elapsed '+_dh(Date.now()/1000-s.start_time);}"
        "var fc=document.getElementById('files-container');"
        "var expanded=[],compact=[],collapsed=[];"
        "fc.querySelectorAll('.file-card.expanded').forEach(function(c){"
        "var dp=c.getAttribute('data-path');"
        "if(dp)expanded.push(dp);"
        "});"
        "fc.querySelectorAll('.file-card.compact').forEach(function(c){"
        "var dp=c.getAttribute('data-path');"
        "if(dp)compact.push(dp);"
        "});"
        "fc.querySelectorAll('.file-card:not(.expanded):not(.compact)').forEach(function(c){"
        "var dp=c.getAttribute('data-path');"
        "if(dp)collapsed.push(dp);"
        "});"
        "var h='';"
        "s.files.forEach(function(f){"
        "var sc='badge-active';"
        "if(f.status==='idle')sc='badge-idle';"
        "else if(f.status==='missing')sc='badge-missing';"
        "var dp=f.display||f.path;"
        "h+='<div class=\"file-card\" data-path=\"'+_esc(dp)+'\">';"
        "h+='<div class=\"file-header\">';"
        "h+='<span class=\"file-path\">'+_esc(dp)+'<span class=\"line-badge compact-badge\">last 5 lines</span><span class=\"line-badge expanded-badge\">last '+Math.min(f.last_lines.length,30)+' lines</span></span>';"
        "h+='<span class=\"file-meta\">'+(f.size_display||'')+' &middot; <span class=\"badge '+sc+'\">'+f.status+'</span></span>';"
        "h+='</div>';"
        "if(f.last_lines&&f.last_lines.length){"
        "h+='<div class=\"file-lines\">';"
        "var lines=f.last_lines.slice(-30);"
        "lines.forEach(function(l){"
        "var u=l.toUpperCase();"
        "var cl='';"
        "if(/\\b(?:ERR|ERROR|EXCEPTION|CATCH|FATAL|FAIL|PANIC)\\b/.test(u))cl='line-err';"
        "else if(/\\b(?:WARN|WARNING|CAUTION|DEPRECATED|INF|NAN)\\b/.test(u))cl='line-warn';"
        "else if(/\\b(?:END|FINISH|CLOSED|COMPLETED|EXIT|TERMINATED)\\b/.test(u))cl='line-end';"
        "h+='<pre class=\"'+cl+'\">'+_esc(l)+'</pre>';"
        "});"
        "h+='</div>';}"
        "h+='</div>';"
        "});"
        "fc.innerHTML=h;"
        "if(expanded.length){"
        "fc.querySelectorAll('.file-card').forEach(function(c){"
        "var dp=c.getAttribute('data-path');"
        "if(dp&&expanded.indexOf(dp)>=0)c.classList.add('expanded');"
        "});}"
        "if(compact.length){"
        "fc.querySelectorAll('.file-card').forEach(function(c){"
        "var dp=c.getAttribute('data-path');"
        "if(dp&&compact.indexOf(dp)>=0)c.classList.add('compact');"
        "});}"
        "fc.querySelectorAll('.file-card:not(.expanded):not(.compact)').forEach(function(c){"
        "var dp=c.getAttribute('data-path');"
        "if(dp&&expanded.indexOf(dp)<0&&compact.indexOf(dp)<0&&collapsed.indexOf(dp)<0)"
        "c.classList.add('compact');"
        "});"
        "if(!s.running){if(_poll){clearInterval(_poll);_poll=null;}}"
        "});}"
        "if(_running){_poll=setInterval(_update,3000);_update();}"
        "</script>"
    )

    parts.append("</body></html>")
    return "\n".join(parts)


def _append_file_card(parts: list[str], f: dict) -> None:
    status_cls = {
        "active": "badge-active",
        "idle": "badge-idle",
        "missing": "badge-missing",
    }.get(f["status"], "badge-idle")
    lines = f.get("last_lines", [])
    parts.append('<div class="file-card compact">')
    parts.append('<div class="file-header">')
    parts.append(
        f'<span class="file-path">{_h_esc(f.get("display", f.get("path", "")))}'
        f'<span class="line-badge compact-badge">last 5 lines</span>'
        f'<span class="line-badge expanded-badge">last {min(len(lines), 30)} lines</span>'
        f"</span>"
    )
    parts.append(
        f'<span class="file-meta">{_format_size(f.get("size", 0))}'
        f' &middot; <span class="badge {status_cls}">{f["status"]}</span></span>'
    )
    parts.append("</div>")
    if lines:
        parts.append('<div class="file-lines">')
        for line in lines[-30:]:
            upper = line.upper()
            if re.search(ERROR_PATTERN, upper):
                cls = "line-err"
            elif re.search(WARN_PATTERN, upper):
                cls = "line-warn"
            elif re.search(END_PATTERN, upper):
                cls = "line-end"
            else:
                cls = ""
            parts.append(f'<pre class="{cls}">' f"{_h_esc(line)}" f"</pre>")
        parts.append("</div>")
    parts.append("</div>")


class _StatusHandler(BaseHTTPRequestHandler):
    monitor: "LogMonitor" = None  # type: ignore[assignment]

    def log_message(self, format: str, *args: object) -> None:  # type: ignore[override]
        pass

    def do_GET(self) -> None:
        if self.path == "/api/status":
            self._json_response()
        else:
            self._html_response()

    def _send(self, content: str, content_type: str) -> None:
        body = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html_response(self) -> None:
        self._send(_build_status_html(self.monitor), "text/html; charset=utf-8")

    def _json_response(self) -> None:
        s = self.monitor._snapshot()
        self._send(json.dumps(s, default=str), "application/json; charset=utf-8")


# ---------------------------------------------------------------------------
# LogMonitor
# ---------------------------------------------------------------------------


class LogMonitor:
    _MAX_LINES = 200
    _IDLE_TIMEOUT = 30  # seconds of no new content before active → idle

    def __init__(
        self,
        raw_paths: list[str],
        port: int = 8080,
        bind: str = "127.0.0.1",
    ):
        self._raw_paths = list(raw_paths)
        self.interval = 3  # seconds between file checks
        self.port = port
        self.bind = bind

        self._lock = threading.Lock()
        self._state: dict[str, dict] = {}  # path -> file state
        self._known_paths: set[str] = set()
        self._start_time: float = 0.0
        self._httpd: ThreadingHTTPServer | None = None
        self._stop = False

    # -- state snapshot (thread-safe) --

    def _snapshot(self) -> dict:
        with self._lock:
            files = []
            for path, st in self._state.items():
                files.append(
                    {
                        "path": path,
                        "display": _sanitize_path(path),
                        "size": st.get("size", 0),
                        "size_display": _format_size(st.get("size", 0)),
                        "last_lines": list(st["last_lines"]),
                        "status": st.get("status", "idle"),
                        "last_activity": st.get("last_activity", 0.0),
                    }
                )
            return {
                "files": files,
                "total": len(self._state),
                "interval": self.interval,
                "start_time": self._start_time,
                "running": not self._stop,
            }

    # -- file handling --

    def _open_file(self, path: str, st: dict) -> None:
        try:
            if not os.path.exists(path) or not os.path.isfile(path):
                st["f"] = None
                st["status"] = "missing"
                return

            f = open(path, "r", encoding="utf-8", errors="replace")
            for line in f.readlines():
                st["last_lines"].append(line.rstrip("\n"))

            f.seek(0, os.SEEK_END)
            st["f"] = f
            st["last_size"] = os.path.getsize(path)
            st["status"] = "active"
            st["size"] = st["last_size"]
            st["last_activity"] = time.time()
        except Exception:
            st["f"] = None
            st["status"] = "missing"

    def _check_file_state(self, path: str, st: dict) -> bool:
        """Handle file deletion, truncation, and (re)creation."""
        try:
            if os.path.exists(path) and os.path.isfile(path):
                current_size = os.path.getsize(path)
                if st["f"] is None or current_size < st["last_size"]:
                    if st["f"]:
                        st["f"].close()
                    self._open_file(path, st)
                    return True
                st["last_size"] = current_size
                st["size"] = current_size
                # downgrade active → idle after no new content for a while
                if st.get("status") == "active":
                    if time.time() - st.get("last_activity", 0) > self._IDLE_TIMEOUT:
                        st["status"] = "idle"
            else:
                if st["f"]:
                    st["f"].close()
                    st["f"] = None
                st["status"] = "missing"
        except Exception:
            pass
        return False

    def _read_new_lines(self, path: str, st: dict) -> bool:
        """Read all buffered new lines from a file. Returns True if any new content."""
        if st["f"] is None:
            return False

        any_new = False
        try:
            while True:
                line = st["f"].readline()
                if not line:
                    break
                st["last_lines"].append(line.rstrip("\n"))
                st["last_activity"] = time.time()
                st["status"] = "active"
                any_new = True
        except Exception:
            pass

        return any_new

    # -- file discovery --

    def _new_file_state(self) -> dict:
        return {
            "f": None,
            "last_size": 0,
            "last_lines": collections.deque(maxlen=self._MAX_LINES),
            "status": "idle",
            "last_activity": 0.0,
            "size": 0,
        }

    def _rescan(self) -> int:
        """Re-expand glob patterns; add newly discovered files to state.
        Returns the number of new files found.
        """
        current = set(_expand_paths(self._raw_paths))
        new_paths = current - self._known_paths
        self._known_paths |= new_paths

        for p in sorted(new_paths):
            st = self._new_file_state()
            with self._lock:
                self._state[p] = st
            self._open_file(p, st)

        return len(new_paths)

    # -- console output --

    def _count_statuses(self) -> dict[str, int]:
        counts = {"active": 0, "idle": 0, "missing": 0}
        for st in self._state.values():
            s = st.get("status", "idle")
            if s in counts:
                counts[s] += 1
        return counts

    def _print_connection_info(self) -> None:
        print(f"Status server: http://localhost:{self.port}")
        if self.bind in ("127.0.0.1", "::1"):
            print()
            print("If connecting remotely, use SSH port forwarding:")
            print(f"  ssh -L {self.port}:localhost:{self.port} user@remote-host")
            print()
            print(f"Then open http://localhost:{self.port} in your local browser.")
        else:
            print(f"  (listening on {self.bind}:{self.port})")
        print()

    def _print_summary(self) -> None:
        total = len(self._state)
        c = self._count_statuses()
        print(f"Monitoring {total} file(s) " f"(refresh: {self.interval}s)")
        if total > 0:
            parts = [f"  {c['active']} active"]
            if c["missing"]:
                parts.append(f"{c['missing']} missing")
            print(", ".join(parts))
        print("Press Ctrl+C to stop.")
        print()

    def _print_status_line(self, counts: dict[str, int], total: int) -> None:
        ts = time.strftime("%H:%M:%S")
        c = counts
        status_parts = [f"{c['active']} active"]
        if c["idle"]:
            status_parts.append(f"{c['idle']} idle")
        if c["missing"]:
            status_parts.append(f"{c['missing']} missing")
        print(
            f"[{ts}] {total} file(s)  ({', '.join(status_parts)})  "
            f"http://localhost:{self.port}"
        )

    # -- HTTP server --

    def _start_server(self) -> None:
        _StatusHandler.monitor = self
        port = self.port
        max_tries = 100
        for _ in range(max_tries):
            try:
                self._httpd = ThreadingHTTPServer((self.bind, port), _StatusHandler)
                self._httpd.timeout = 0.5

                def _serve() -> None:
                    try:
                        self._httpd.serve_forever()  # type: ignore[union-attr]
                    except Exception:
                        pass  # socket closed during shutdown

                t = threading.Thread(target=_serve, daemon=True)
                t.start()
                self.port = port
                return
            except OSError:
                port += 1

        print(
            f"Warning: Could not start status server "
            f"(ports {self.port}–{port - 1} in use)"
        )
        self.port = 0

    def _stop_server(self) -> None:
        if self._httpd is None:
            return
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

    def _close_all(self) -> None:
        for st in self._state.values():
            if st["f"]:
                try:
                    st["f"].close()
                except Exception:
                    pass
                st["f"] = None

    # -- main entry --

    def run(self) -> None:
        self._start_time = time.time()
        # initial scan
        new_count = self._rescan()
        if not self._state:
            print(f"No files found matching: {self._raw_paths}")
            return

        if new_count:
            print(f"Found {new_count} file(s) matching patterns.")

        self._start_server()
        self._print_connection_info()
        self._print_summary()

        prev_total = len(self._state)
        prev_counts = self._count_statuses()

        try:
            while not self._stop:
                # rescan for new files
                new = self._rescan()
                if new:
                    print(f"  + {new} new file(s) discovered")

                # read from all files
                for path, st in list(self._state.items()):
                    self._check_file_state(path, st)
                    self._read_new_lines(path, st)

                # print only when counts change
                cur_total = len(self._state)
                cur_counts = self._count_statuses()
                if new or cur_total != prev_total or cur_counts != prev_counts:
                    self._print_status_line(cur_counts, cur_total)
                    prev_total = cur_total
                    prev_counts = cur_counts

                time.sleep(self.interval)

        except KeyboardInterrupt:
            print("\nMonitoring stopped.")
        finally:
            self._stop_server()
            self._close_all()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="monitor",
        description="Robust Real-time Log Monitor for Academic Simulations",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "path",
        nargs="+",
        help="Path(s) or glob(s) to the file(s) to monitor, e.g., '*.log'.",
    )
    p.add_argument(
        "-p",
        "--port",
        type=int,
        default=8080,
        help="HTTP status server port.",
    )
    p.add_argument(
        "--bind",
        default="127.0.0.1",
        help="Bind address for status server (use 0.0.0.0 for LAN access).",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    monitor = LogMonitor(
        raw_paths=args.path,
        port=args.port,
        bind=args.bind,
    )

    monitor.run()


if __name__ == "__main__":
    main()
