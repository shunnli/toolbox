# batch_runner

Execute MATLAB and Python scripts or function calls with parallelism and resource control. Script executors are chosen by file extension (`.m` or `.py`).

Requires Python 3.11+. Cross-platform (Windows & Linux). Zero mandatory dependencies; `psutil` is optional for CPU/memory-aware throttling.

## Quick start

Run the examples from `python/batch_runner/demo_project`:

```bash
# Python scripts
python ../batch_runner.py -f tasks.txt -j 2 --port 0 -y

# MATLAB and Python calls (requires MATLAB)
python ../batch_runner.py -f tasks.toml -j 2 --port 0 -y
```

Both [tasks.txt](demo_project/tasks.txt) and [tasks.toml](demo_project/tasks.toml)
use this working directory. Relative paths resolve from the launch directory.
Scripts run in their own directory; inline MATLAB/Python code runs in the launch
directory. Commands below use `demo_project` unless stated otherwise.

You can also pass scripts directly or combine them with a task file:

```bash
python ../batch_runner.py analysis_main.py group_a/main_calc.py -j 2 --port 0 -y
python ../batch_runner.py analysis_main.py -f tasks.txt -j 2 --port 0 -y
```

## Plain-text task files (existing format)

One script path per line, relative to the launch directory:

```text
analysis_main.py       # comment
main_setup.py          ; also a comment
group_a/main_calc.py   % also a comment
```

| Pattern                   | Meaning                                                      |
| ------------------------- | ------------------------------------------------------------ |
| `path/to/script`          | Script to execute (absolute, or relative to CWD)             |
| `# ...`, `; ...`, `% ...` | Comment — full-line or inline (`%` needs leading whitespace) |
| (blank line)              | Ignored                                                      |

- Each path must exist and have a `.m` or `.py` extension.
- Invalid paths cause an immediate error with `file:line` location.
- Duplicates (by absolute path) are removed; first occurrence is kept.

## TOML task files: function calls and arguments

Use `-f tasks.toml` for a commented task list. Each `[[tasks]]` entry contains
exactly one field: `script`, `matlab`, or `python`.

For your own scripts and functions:

```toml
# Ordinary scripts (.m or .py)
[[tasks]]
script = "main.m"

[[tasks]]
script = "analyze.py"

# Native MATLAB arguments: scalars, strings, matrices, structs, etc.
[[tasks]]
matlab = "solve_case(128, 0.01, 'implicit')"  # Small experiment

[[tasks]]
matlab = "solve_case([128 256; 512 1024], struct('tol', 1e-6))"

# Native Python arguments, including keyword arguments
[[tasks]]
python = "from experiment import solve_case; solve_case(128, tol=1e-6)"

# Multiline code and per-task environment setup
[[tasks]]
matlab = '''
% This comment belongs to MATLAB
setenv('MY_MODE', 'test');
solve_case(256, 0.01, 'implicit');
'''

[[tasks]]
python = '''
# This comment belongs to Python
import os
os.environ['MY_MODE'] = 'test'
from experiment import solve_case
solve_case(256, tol=1e-6)
'''
```

```bash
python ../batch_runner.py -f tasks.toml -j 4 --timeout 2h
```

- `matlab` code runs via MATLAB `-batch`; `python` code runs via Python `-c`.
  Code is passed unchanged as one argument, without shell interpretation. These
  entries execute code, so use task files you trust, just as you would scripts.
- TOML uses `#` for full-line and inline comments. Characters inside strings,
  including `#`, `%`, semicolons and quotes, are preserved. Multiline literal
  strings (`'''`) are useful for code containing backslashes or comments.
- Functions and modules use the interpreter's normal search rules.
- Each task gets a separate process and inherits the launch environment.
  `setenv` / `os.environ` changes are local to that task; tasks do not share variables.
- Every TOML entry executes, including repeated scripts or identical calls.
  Entries receive independent task numbers, status and output logs.
- Runtime settings such as concurrency, timeout and resource limits are supplied
  only on the command line. There are no defaults, working-directory, timeout or
  environment fields in the config. Unknown fields cause an error before execution.
- You can mix `.toml`, plain-text `-f` files and positional scripts. Deduplication
  applies only among plain-text lists and positional scripts. `-f -` keeps reading
  a plain-text list from stdin.

## CLI

```
python ../batch_runner.py [script ...] [-f TASKFILE ...] [options]
```

At least one source (script or `-f`) must be provided. Task files can be repeated;
their tasks are collected in order, followed by positional scripts.

| Flag           | Default     | Description                                                   |
| -------------- | ----------- | ------------------------------------------------------------- |
| `scripts`      | (none)      | Script files to run (`.py` or `.m`)                           |
| `-f`, `--file` | (none)      | Plain-text lists or `.toml` tasks (repeatable; `-f -` reads a plain-text list) |
| `-j`, `--jobs` | `1`         | Max concurrent workers                                        |
| `--timeout`    | `24h`       | Timeout for each task (`2h`, `90m`, `45s`; `0` = no limit)       |
| `--cpu-limit`  | `80`        | Max CPU % before throttling (`0` = off; needs `psutil`)       |
| `--mem-limit`  | `80`        | Max memory % before throttling (`0` = off; needs `psutil`)    |
| `-p`, `--port` | `8080`      | HTTP status server port (0 = off)                             |
| `--bind`       | `127.0.0.1` | Bind address for status server (use `0.0.0.0` for LAN access) |
| `-y`, `--yes`  | off         | Skip confirmation prompt                                      |

## How it works

1. Collect tasks from `-f` task files and positional arguments. Validate config structure and script paths; deduplicate plain-text and positional scripts.
2. Show the task list and a confirmation prompt (unless `-y`).
3. Submit tasks to a process pool up to `-j` workers. Each start line shows running/queued/done counts.
4. Before each submission, check CPU/memory usage (if `psutil` is installed). If limits are exceeded, throttle and wait for conditions to improve.
5. Each task runs in a subprocess that inherits the parent's full environment variables. Stdout and stderr are captured to per-task log files.
6. On completion, show results for all tasks.

### Throttling

CPU readings use a 3-sample moving average to smooth out transient spikes. After throttling, a 5-second cooldown prevents rapid oscillation.

### Output

Console output is human-readable, with date-time timestamps on key events:

```
batch_runner — 2 tasks from /home/user/project/tasks.txt
  [1] /home/user/project/analysis_main.py
  [2] /home/user/project/main_calc.py

Workers: 2  |  Timeout: 30s
Output: .batch_runner/20260509_011055/

  start  [1] /home/user/project/analysis_main.py  (1 running, 1 queued, 0/2 done)  (2026-05-09 01:10:55)
  start  [2] /home/user/project/main_calc.py  (2 running, 0 queued, 0/2 done)  (2026-05-09 01:10:55)
  OK  0.3s  [2] /home/user/project/main_calc.py  (2026-05-09 01:10:56)
  OK  0.4s  [1] /home/user/project/analysis_main.py  (2026-05-09 01:10:56)

===== Results =====
  OK    0.3s  [2] /home/user/project/main_calc.py
  OK    0.4s  [1] /home/user/project/analysis_main.py
===== 2 succeeded, 0 failed — 0.9s =====
```

Each run writes `runner.log` and task output to `.batch_runner/<timestamp>/`.
All inputs (plain-text lists, TOML and positional scripts) use the same naming:
`task_<number>_<kind>.log`, such as `task_0001_script.log`, `task_0002_matlab.log`
or `task_0003_python.log`. The same task numbers appear in the console, runner
log and status page. Each output file contains stdout followed by stderr;
tasks producing neither do not create an output log.

Exit code is 0 only when all scripts succeed; 1 if any fail or time out.

### HTTP status server

By default, batch_runner serves a live status page on localhost port 8080. Use
`--port 0` to disable it or `-p` / `--port` to choose another port:

- **`http://localhost:<port>/`** — auto-refreshing HTML dashboard (progress bar, running/queued/completed lists, resource gauges)
- **`http://localhost:<port>/api/status`** — JSON endpoint for programmatic monitoring

After all tasks complete, the server stays alive so you can inspect results remotely. Press `Ctrl+C` to stop.

```bash
# Start with status server on port 8080
python ../batch_runner.py -f tasks.txt -j 4 --port 8080

# Allow LAN access
python ../batch_runner.py -f tasks.txt -j 4 --port 8080 --bind 0.0.0.0
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
python ../batch_runner.py analysis_main.py group_a/main_calc.py -j 4 --timeout 2h

# Task file (via -f)
python ../batch_runner.py -f tasks.txt -j 4 --timeout 2h

# Multiple task files
python ../batch_runner.py -f core.txt -f extra.txt -j 4 -y

# Mixed: direct scripts + task files
python ../batch_runner.py analysis_main.py -f tasks.txt -j 4

# Resource-aware throttling
python ../batch_runner.py -f tasks.txt -j 8 --cpu-limit 90 --mem-limit 85

# Pipeline — scripts from stdin (bash / Linux)
find . -name "step_*.py" | python ../batch_runner.py -f - -j 8

# Pipeline — scripts from stdin (PowerShell / Windows)
Get-ChildItem -Recurse -File -Filter "step_*.py" | Select-Object -ExpandProperty FullName | python ../batch_runner.py -f - -j 8

# Disable a throttle while keeping the other
python ../batch_runner.py -f tasks.txt -j 8 --cpu-limit 90 --mem-limit 0

# HTTP status server (stays alive after completion — press Ctrl+C to stop)
python ../batch_runner.py -f tasks.txt -j 4 --port 8080

# HTTP server accessible from LAN
python ../batch_runner.py -f tasks.txt -j 4 --port 8080 --bind 0.0.0.0
```

## Environment variables

| Variable           | Default              | Description             |
| ------------------ | -------------------- | ----------------------- |
| `BATCH_MATLAB_CMD` | `matlab`             | Override MATLAB command |
| `BATCH_PYTHON_CMD` | `python3` → `python` | Override Python command |

Both overrides apply to scripts and inline code.

## Validation

Run the focused standard-library tests from the repository root:

```bash
python -m unittest discover -s python/batch_runner -p "test_*.py"
```

The tests exercise real Python subprocesses. Set `BATCH_RUNNER_TEST_MATLAB` to a
MATLAB executable path to also run the optional MATLAB integration test.
