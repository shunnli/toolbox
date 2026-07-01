# monitor

A robust real-time log monitor — `tail -f` on steroids.

Monitor one or more log files via glob patterns, highlight errors / warnings / termination markers, and view everything through a live web dashboard. Periodically rescans for new files matching your patterns.

Cross-platform (Windows & Linux). Zero mandatory dependencies (Python standard library only).

## Quick start

```bash
python monitor.py simulation.log
```

Then open **http://localhost:8080** in your browser.

Monitor multiple files via glob:

```bash
python monitor.py "outputs/*.log"
```

## CLI

```
python monitor.py <path...> [-p PORT] [--bind ADDR]
```

| Argument | Default | Description |
|---|---|---|
| `path` | (required) | File path(s) or glob pattern(s), e.g. `*.log` |
| `-p`, `--port` | `8080` | HTTP status server port (auto-increments if occupied) |
| `--bind` | `127.0.0.1` | Bind address (use `0.0.0.0` for LAN access) |

Press `Ctrl+C` to stop. The server shuts down cleanly.

## Web dashboard

### Layout

```
┌──────────────────────────────────────────────┐
│  monitor — 5 files                  [☽/☀]   │  header + theme toggle
│  Interval: 3s · JSON                        │  refresh rate + API link
├──────────────────────────────────────────────┤
│  Total:5  Active:2  Idle:1  Missing:2        │  stat grid (4 cards, colored)
├──────────────────────────────────────────────┤
│  ▶ progress1.log    12.5 KB · active         │  collapsed
│  ▼ progress2.log    8.2 KB · idle  last 5    │  compact (5 lines)
│    [2026-05-15 14:23:01] 45.00%              │
│    [2026-05-15 14:23:04] 46.00%              │
│    [2026-05-15 14:23:07] 47.00% ...          │
│  ▼ progress3.log    3.1 KB · active last 30  │  expanded (all lines)
│    ... all visible lines ...                  │
└──────────────────────────────────────────────┘
```

### File cards — three display modes

Click the file header to cycle:

| Click | Mode | Arrow | Content | Badge |
|---|---|---|---|---|
| (default) | compact | ▼ | last 5 lines | `last 5 lines` |
| 1st | expanded | ▼ | all lines (max 30) | `last N lines` |
| 2nd | collapsed | ▶ | none | none |
| 3rd | compact | ▼ | … | … |

- **New files default to compact** — you immediately see the most recent output.
- **Manually collapsed files stay collapsed** across auto-refresh (state tracked in-memory).
- The last 5 lines in compact mode are controlled purely by CSS (`:nth-last-of-type`), so highlighting still works.

### File status badges

Each file card shows a colored status badge:

| Badge | Color | Meaning |
|---|---|---|
| **active** | green | file open, new content received within last 30s |
| **idle** | blue | file exists but no new content for >30s |
| **missing** | red | file not found or cannot be opened |

**State transitions:**

```
[file discovered]  →  active  →  idle  →  missing
                        ↑          │          │
                        └──────────┘          │
                        (new content)         │
                                              │
                        ┌─────────────────────┘
                        ↓
                      active  (file reappears)
```

- **active → idle**: triggered after 30s of no new output.
- **idle → active**: triggered immediately when new output is read.
- **missing → active**: file reappears (e.g. a new simulation creates it).

Hover over each stat card at the top of the page for a brief description.

### Line highlighting

Lines are matched **case-insensitively** and color-coded:

| Category | Keywords | Color |
|---|---|---|
| Errors | `ERR`, `ERROR`, `EXCEPTION`, `FATAL`, `FAIL`, `PANIC` | red background |
| Warnings | `WARN`, `WARNING`, `CAUTION`, `DEPRECATED`, `INF`, `NAN` | yellow background |
| Termination | `END`, `FINISH`, `COMPLETED`, `EXIT`, `TERMINATED` | green background |

### Dark / light theme

Click the ☽/☀ button in the header to toggle between dark and light themes. The choice is persisted in `localStorage` and applied before the page renders (no flash).

### Mobile support

The dashboard is fully responsive — viewport meta tag + `@media (max-width: 640px)` breakpoint shrinks fonts, padding, and stat cards for phone screens.

## HTTP API

| Route | Content-Type | Description |
|---|---|---|
| `GET /` | `text/html` | Live dashboard page (auto-refreshes every 3s via JS) |
| `GET /api/status` | `application/json` | Machine-readable snapshot |

### JSON schema

```json
{
  "files": [
    {
      "path": "/abs/path/to/progress1.log",
      "display": "progress1.log",
      "size": 12345,
      "size_display": "12.06 KB",
      "last_lines": ["line 1", "line 2", "..."],
      "status": "active",
      "last_activity": 1715765432.123
    }
  ],
  "total": 5,
  "interval": 3,
  "running": true
}
```

- `display` uses `~` for home directory shortening.
- `last_lines` holds up to 200 most recent lines (oldest first).
- `last_activity` is a UNIX timestamp (seconds since epoch).

## Remote access

By default the server binds to `127.0.0.1` (localhost only). For remote access, use SSH port forwarding:

```bash
ssh -L 8080:localhost:8080 user@remote-host
```

Then open `http://localhost:8080` in your local browser.

Or bind to all interfaces: `--bind 0.0.0.0` (be careful with firewall rules).

## Console output

```
Status server: http://localhost:8080

If connecting remotely, use SSH port forwarding:
  ssh -L 8080:localhost:8080 user@remote-host

Then open http://localhost:8080 in your local browser.

Monitoring 3 file(s) (refresh: 3s)
  3 active
Press Ctrl+C to stop.

  + 1 new file(s) discovered
[16:45:30] 4 file(s)  (4 active)  http://localhost:8080
[16:45:52] 4 file(s)  (3 active, 1 idle)  http://localhost:8080
[16:47:05] 4 file(s)  (2 active, 1 idle, 1 missing)  http://localhost:8080
```

- Status lines print **only when counts change** — not on a fixed timer.
- New files matching your glob patterns are discovered and announced automatically.

## Demo script

`gen_data_for_monitor_demo.py` generates realistic log files that exercise every status transition:

```bash
# Terminal 1 — start the demo
python gen_data_for_monitor_demo.py

# Terminal 2 — start the monitor (in the same directory)
python monitor.py *.log
```

Timeline (seconds from start):

| Time | Event | Status change |
|---|---|---|
| 0 | 3 persistent files start looping | — |
| 20 | `dynamic_appear.log` created, writes ~15s then stops | active → idle |
| 40 | `progress1.log` paused | active → idle |
| 65 | `dynamic_appear.log` deleted | idle → missing |
| 75 | `progress1.log` resumed | idle → active |
| 90 | `late_burst.log` created (late arrival) | active |
| 110 | `late_burst.log` deleted | active → missing |
| 130 | `final_arrival.log` created | active |

## Technical notes

- **Zero dependencies**: uses only `threading`, `http.server`, `glob`, `collections.deque`, and filesystem I/O from the standard library.
- **Truncation detection**: compares `os.path.getsize()` with a cached size; re-opens the file if it shrinks.
- **Thread safety**: `threading.Lock` protects dict insertion in `_rescan()` to avoid race conditions with the HTTP handler thread.
- **Line buffer**: each file keeps a `deque(maxlen=200)` — old lines are silently dropped.
- **Port auto-increment**: if the requested port is busy, monitor tries up to 100 subsequent ports.
- **Glob re-expansion**: `_rescan()` re-evaluates glob patterns every cycle, so files created after startup are picked up within 3s.
