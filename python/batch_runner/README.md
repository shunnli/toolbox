# batch_runner

Execute a list of scripts with parallelism and resource control. Supports MATLAB (`.m`) and Python (`.py`); executor chosen by file extension.

Cross-platform (Windows & Linux). Zero mandatory dependencies; `psutil` is optional for CPU/memory-aware throttling.

## Quick start

Pass scripts directly on the command line:

```bash
python batch_runner.py main_calc.py analysis.py -j 4 --timeout 2h
```

Or create a task file — one script path per line:

```
# core scripts
main_calc.py
analysis.py     # takes ~30 min
extra.py        ; also works as comment
special.m       % also works as comment
../other/main.m
```

Run it with `-f`:

```bash
python batch_runner.py -f tasks.txt -j 4 --timeout 2h
```

You can mix both: `python batch_runner.py quick_test.py -f tasks.txt -j 4`

## Task file format

| Pattern                   | Meaning                                                      |
| ------------------------- | ------------------------------------------------------------ |
| `path/to/script`          | Script to execute (absolute, or relative to CWD)             |
| `# ...`, `; ...`, `% ...` | Comment — full-line or inline (`%` needs leading whitespace) |
| (blank line)              | Ignored                                                      |

- Each path must exist and have a `.m` or `.py` extension.
- Invalid paths cause an immediate error with `file:line` location.
- Duplicates (by absolute path) are removed; first occurrence is kept.

## CLI

```
python batch_runner.py [script ...] [-f TASKFILE ...] [options]
```

At least one source (script or `-f`) must be provided. Task files can be repeated, and their scripts are processed in order with cross-source deduplication.

| Flag           | Default     | Description                                                   |
| -------------- | ----------- | ------------------------------------------------------------- |
| `scripts`      | (none)      | Script files to run (`.py` or `.m`)                           |
| `-f`, `--file` | (none)      | Task file(s) listing scripts (repeatable; `-f -` reads stdin) |
| `-j`, `--jobs` | `1`         | Max concurrent workers                                        |
| `--timeout`    | `24h`       | Per-script timeout (`2h`, `90m`, `45s`; `0` = no limit)       |
| `--cpu-limit`  | `80`        | Max CPU % before throttling (`0` = off; needs `psutil`)       |
| `--mem-limit`  | `80`        | Max memory % before throttling (`0` = off; needs `psutil`)    |
| `-p`, `--port` | `8080`      | HTTP status server port (0 = off)                             |
| `--bind`       | `127.0.0.1` | Bind address for status server (use `0.0.0.0` for LAN access) |
| `-y`, `--yes`  | off         | Skip confirmation prompt                                      |

## How it works

1. Collect scripts from `-f` task files and positional arguments — validate paths, resolve relative paths, deduplicate across all sources.
2. Show the script list and a confirmation prompt (unless `-y`).
3. Submit scripts to a process pool up to `-j` workers. Each start line shows running/queued/done counts.
4. Before each submission, check CPU/memory usage (if `psutil` is installed). If limits are exceeded, throttle and wait for conditions to improve.
5. Each script runs in a subprocess that inherits the parent's full environment variables. Stdout and stderr are captured to per-script log files.
6. On completion, show results for all scripts.

### Throttling

CPU readings use a 3-sample moving average to smooth out transient spikes. After throttling, a 5-second cooldown prevents rapid oscillation.

### Output

Console output is human-readable, with date-time timestamps on key events:

```
batch_runner — 3 scripts from /home/user/project/tasks.txt + quick_test.py
  /home/user/project/analysis_main.py
  /home/user/project/main_calc.py
  /home/user/project/main_setup.py

Workers: 2  |  Timeout: 30s
Output: .batch_runner/20260509_011055/

  start  /home/user/project/analysis_main.py  (1 running, 2 queued, 0/3 done)  (2026-05-09 01:10:55)
  start  /home/user/project/main_calc.py  (2 running, 1 queued, 0/3 done)  (2026-05-09 01:10:55)
  OK  0.3s  /home/user/project/main_calc.py  (2026-05-09 01:10:56)
  OK  0.4s  /home/user/project/analysis_main.py  (2026-05-09 01:10:56)

===== Results =====
  OK    0.3s  /home/user/project/main_calc.py
  OK    0.4s  /home/user/project/analysis_main.py
===== 3 succeeded, 0 failed — 0.9s =====
```

Each run also writes a structured log to `.batch_runner/<timestamp>/runner.log` and per-script output to `.batch_runner/<timestamp>/<script>.log`.

Exit code is 0 only when all scripts succeed; 1 if any fail or time out.

### HTTP status server

By default, batch_runner serves a live status page on localhost port 8080. Use
`--port 0` to disable it or `-p` / `--port` to choose another port:

- **`http://localhost:<port>/`** — auto-refreshing HTML dashboard (progress bar, running/queued/completed lists, resource gauges)
- **`http://localhost:<port>/api/status`** — JSON endpoint for programmatic monitoring

After all tasks complete, the server stays alive so you can inspect results remotely. Press `Ctrl+C` to stop.

```bash
# Start with status server on port 8080
python batch_runner.py -f tasks.txt -j 4 --port 8080

# Allow LAN access
python batch_runner.py -f tasks.txt -j 4 --port 8080 --bind 0.0.0.0
```

## Generating task files

Use system tools to generate the task list:

```bash
# Linux / macOS
find . -name "main_*.py" | sort > tasks.txt

# Windows PowerShell
Get-ChildItem -Recurse -File -Filter "main_*.py" | Select-Object -ExpandProperty FullName > tasks.txt
```

Edit the file to remove or reorder scripts before running.

## Examples

```bash
# Direct scripts
python batch_runner.py main.py analysis.py -j 4 --timeout 2h

# Task file (via -f)
python batch_runner.py -f tasks.txt -j 4 --timeout 2h

# Multiple task files
python batch_runner.py -f core.txt -f extra.txt -j 4 -y

# Mixed: direct scripts + task files
python batch_runner.py quick_test.py -f tasks.txt -j 4

# Resource-aware throttling
python batch_runner.py -f tasks.txt -j 8 --cpu-limit 90 --mem-limit 85

# Pipeline — scripts from stdin (bash / Linux)
find . -name "step_*.py" | python batch_runner.py -f - -j 8

# Pipeline — scripts from stdin (PowerShell / Windows)
Get-ChildItem -Recurse -File -Filter "step_*.py" | Select-Object -ExpandProperty FullName | python batch_runner.py -f - -j 8

# Disable a throttle while keeping the other
python batch_runner.py -f tasks.txt -j 8 --cpu-limit 90 --mem-limit 0

# HTTP status server (stays alive after completion — press Ctrl+C to stop)
python batch_runner.py -f tasks.txt -j 4 --port 8080

# HTTP server accessible from LAN
python batch_runner.py -f tasks.txt -j 4 --port 8080 --bind 0.0.0.0
```

## Environment variables

| Variable           | Default              | Description             |
| ------------------ | -------------------- | ----------------------- |
| `BATCH_MATLAB_CMD` | `matlab`             | Override MATLAB command |
| `BATCH_PYTHON_CMD` | `python3` → `python` | Override Python command |
