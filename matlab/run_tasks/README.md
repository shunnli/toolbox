# run_tasks — A Unified Task Execution Wrapper for MATLAB

`run_tasks` is a lightweight MATLAB utility that provides a unified interface for executing **independent tasks** in **serial**, **parfor**, **parfeval**, or **debug** modes.
It offers consistent error handling and optional control over computational resources, making it suitable for benchmarking, experimentation, batch execution workflows, and interactive debugging.

## Features

- Unified execution interface for independent tasks:
  - serial execution (`Mode = "serial"`; `"for"` is an alias)
  - parallel execution using `parfor`
  - asynchronous execution using `parfeval`
  - debug execution (`Mode = "debug"`) for interactive error inspection
- Automatic parallel pool configuration:
  - worker count is selected based on the number of tasks,
    available physical CPU cores, and a user-defined upper bound
  - enabled by default; disable via `LimitWorkers = false`
- Optional control of computational threads per worker
  (`maxNumCompThreads`) to avoid CPU oversubscription
  - enabled by default; disable via `LimitThreads = false`
- Robust and deterministic error handling:
  - in `"serial"`, `"parfor"`, and `"parfeval"` modes:
    - all task errors are caught and collected
    - optional early termination on the first error
      (enabled by default; disable via `StopOnFirstError = false`)
    - the first encountered error is rethrown after execution
    - automatic error logging when multiple errors occur
      (written to `run_tasks_errors_yyyyMMdd-HHmmss.log`)
  - in `"debug"` mode:
    - errors are not caught
    - execution stops immediately at the error location under
      `dbstop if error`
- Preserves task–result correspondence:
  results are returned in the same shape as the input task list

## Debug Mode (`Mode = "debug"`)

Debug mode is designed for interactive debugging of task code.

- Tasks are executed sequentially in the client MATLAB process
- `dbstop if error` is:
  - automatically enabled on entry
  - automatically cleared on exit
- MATLAB stop exactly at the line where the error occurs
- Debug mode is strictly serial and cannot be combined with
  `parfor` or `parfeval`
- In all non-debug modes (`"serial"`, `"parfor"`, `"parfeval"`),
  the global debug state must be empty; otherwise `run_tasks`
  aborts with an error to avoid ambiguous behavior

This mode is particularly useful when diagnosing numerical errors,
unexpected exceptions, or logic bugs inside task functions.

## Environment Variables

### `RUN_TASKS_MODE`

Overrides the `"Mode"` name-value argument. Valid values: `"serial"`, `"for"`, `"parfor"`, `"parfeval"`, `"debug"`.

Priority (highest to lowest):

1. **Environment variable** `RUN_TASKS_MODE` — takes effect immediately; a warning is emitted to make the override visible. If the value is invalid, a warning is issued and falls back to the next level.
2. **Name-value argument** `Mode` — used when no valid env var is present.
3. **Default** — `"serial"`.

```matlab
setenv('RUN_TASKS_MODE', 'parfor');
results = run_tasks(tasks, Mode="serial");
% Runs in parfor mode — env var takes precedence
```

This is useful for switching execution modes in batch or CI environments without modifying scripts.

### `RUN_TASKS_PROFILE`

Enables the MATLAB Profiler during execution and auto-saves an HTML report. Valid values: `"on"`, `"1"`, `"true"` (enable); `"off"`, `"0"`, `"false"` (disable). Defaults to off when not set. No name-value option is exposed — the environment variable is the only entry point.

Priority (highest to lowest):

1. **External profiler already active** (e.g. via the GUI "Run and Time" button or a manual `profile on`) — `RUN_TASKS_PROFILE` is silently ignored. `run_tasks` does not save or stop the external profiler.
2. **Environment variable** `RUN_TASKS_PROFILE` set to `"on"` — profiler runs during execution; an HTML report is auto-saved to `profile_results_YYYYMMDD-HHMMSS/`; profiler is stopped cleanly on exit. A warning is emitted when the variable takes effect.
3. **Default** — profiling is off.

If the environment variable is set but contains an invalid value, a warning is issued and it is ignored.

```matlab
setenv('RUN_TASKS_PROFILE', 'on');
results = run_tasks(tasks, Mode="serial");
% Profiler runs → report saved to profile_results_YYYYMMDD-HHMMSS/
```

## Notes on Parallel Execution (`Mode = "parfor"`, `Mode = "parfeval"`)

- `parfor` mode supports early termination on error, but the loop
  completes at the current iteration boundary
- `parfeval` mode executes tasks asynchronously:
  - worker stdout is not forwarded to the client
  - interactive interruption (GUI pause or Ctrl+C) is **not reliable**
  - if `StopOnFirstError = true`, remaining futures are canceled
    when the first error is detected
- Worker-side output can be safely collected on the client using `parallel.pool.DataQueue`.
