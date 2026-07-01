# output-manager

An **output directory management solution** for **scientific computing and numerical experiments** in MATLAB.
It helps standardize and organize experiment results for easy saving and retrieval.

## Overview

To use the manager, create an `OutputManager` object with two optional arguments:

- `output_path`: the base directory for all outputs (default: `"outputs"`)
- `label_name`: a label identifying the current experiment (e.g., method name, parameter set), default is empty

For example, construct an `OutputManager` instance in the main script as follows:

```matlab
root = fileparts(mfilename('fullpath'));
om = OutputManager(fullfile(root, "../outputs"), "matlab-test");
```

If the current script is `project/matlab/test.m`, then:

- The output base directory (`base_dir`) is `project/outputs/`
- The current output directory (`cur_dir`) is
  `project/outputs/matlab-test-20251207-143210/`

The constructor automatically creates the corresponding directory. If creation fails, it gracefully falls back to the current working directory while ensuring path validity.

To obtain a full file path within the current output directory, use `om.get_file_path`. This method guarantees that all intermediate subdirectories are created as needed.

For example:

```matlab
data_file = om.get_file_path('data/sin_wave.mat');
log_file  = om.get_file_path('logs/log.txt');
fig_file  = om.get_file_path('figures/figure.png');
```

The resulting directory structure becomes:

```
outputs/
    matlab-test-20251207-143210/
        data/
            sin_wave.mat
        logs/
            log.txt
        figures/
            figure.png
```

## Reusing an Existing Directory

When postprocessing results from a previous run, use the `ExistingDir` name-value pair to reuse an existing output directory instead of creating a new timestamped one:

```matlab
om = OutputManager(ExistingDir="outputs/my-experiment-20251207-143210");
```

This mode:
- Uses the given directory directly as `cur_dir`; no new timestamp is appended.
- Sets `base_dir` to the parent of the given directory.
- Issues an error if the specified directory does not exist.
- Is exclusive — `ExistingDir` cannot be combined with `output_path` or `label_name`.

> **Note:** The `ExistingDir` mode ignores `OUTPUT_MANAGER_OUTPUT_PATH` and `OUTPUT_MANAGER_LABEL_NAME` environment variables.

## Label Name Validation

The `label_name` argument is validated automatically:
- Must not contain path separators (`/`, `\`) or `..`.
- An empty string is allowed (the directory name will be just the timestamp).

If a label name fails validation, an error with ID `OutputManager:invalidLabelName` is raised.

## Environment Variable Overrides

The following environment variables take precedence over constructor arguments:

| Variable                     | Overrides                      |
| ---------------------------- | ------------------------------ |
| `OUTPUT_MANAGER_OUTPUT_PATH` | `output_path` (base directory) |
| `OUTPUT_MANAGER_LABEL_NAME`  | `label_name`                   |

When an environment variable overrides a constructor argument, a warning is issued to make the override visible. This is useful for redirecting outputs in batch or CI environments without modifying scripts.

```matlab
% Without env vars — uses constructor args
om = OutputManager("outputs", "my-experiment");
% Creates: outputs/my-experiment-20251207-143210/

% With OUTPUT_MANAGER_OUTPUT_PATH=/tmp/results
om = OutputManager("outputs", "my-experiment");
% Warning: env overrides output_path
% Creates: /tmp/results/my-experiment-20251207-143210/
```

> Environment variables are ignored when using the `ExistingDir` mode.
