# toolbox

Reusable scripts and drop-in components for research workflows and numerical experiments.

This is a toolbox, not a Python package or MATLAB package.
Copy the tool you need into a project, or run it directly from this checkout.
See each tool's own `README.md` for usage details.

## Python

| Tool | Purpose |
| --- | --- |
| `python/archive/` | Archive selected files and directories. |
| `python/batch_runner/` | Run Python and MATLAB scripts in batches. |
| `python/monitor/` | Monitor log files in a live browser dashboard. |
| `python/tablegen/` | Generate plain-text or LaTeX experiment tables. |
| `python/metatag/` | Read, write, and delete PNG metadata. |
| `python/texmerge/` | Merge multi-file LaTeX projects into one `.tex` file. |
| `python/git_check/` | Inspect Git repository status and upstream sync. |
| `python/net_check/` | Diagnose network and proxy state. |

Example:

```bash
python python/tablegen/tablegen.py python/tablegen/data.json
```

## MATLAB

| Component | Purpose |
| --- | --- |
| `matlab/Logger/` | Lightweight logging. |
| `matlab/Trigger/` | Progress, counter, and wall-time triggers. |
| `matlab/OutputManager/` | Timestamped output directory management. |
| `matlab/run_tasks/` | Serial, parallel, and debug task execution. |
| `matlab/evaluate_struct_expression/` | Evaluate formulas using struct fields as variables. |
| `matlab/ColorManager/` | Color palettes and plot styles. |

Most MATLAB folders include a `demo_*.m` file.
