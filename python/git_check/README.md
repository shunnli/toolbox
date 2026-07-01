# git_check

Show a compact status overview for one or more Git repositories.

This is a standalone script with no third-party Python dependencies.

It is useful when you maintain several research/project repositories and want a
quick reminder of which ones have uncommitted work, missing Git identity
configuration, no upstream branch, or local/remote divergence.

## What it checks

For each repository, `git_check.py` prints:

- repository root
- current branch
- `user.name` and `user.email`, showing whether each value comes from local or
  global Git config
- short working tree status from `git status -s`
- branch sync status against the configured upstream
- last commit summary
- remotes and branch list, unless `--brief` is used

By default, the sync check uses local remote-tracking refs only. Use `--fetch`
when you want to update remote refs before comparing ahead/behind counts.

## Usage

Check a repository:

```bash
python git_check.py path/to/repo
```

Check the current repository:

```bash
python git_check.py
```

Check multiple repositories:

```bash
python git_check.py project-a project-b ../project-c
```

Show only the compact summary:

```bash
python git_check.py --brief path/to/repo
```

Fetch first, then compare against upstream:

```bash
python git_check.py --fetch path/to/repo
```

Disable ANSI colors for logs, terminals, or redirected output:

```bash
python git_check.py --no-color path/to/repo
```

## Repository discovery

Repository paths can come from one of three places:

1. positional arguments, if any are provided
2. a config file, if it exists
3. the current working directory, if it is inside a Git repository

The default config file is:

```text
~/.config/git-check/repos.txt
```

Use `--config` to point to a different file:

```bash
python git_check.py --config repos.txt
```

Config file format:

```text
# One repository per line.
~/work/project-a
D:/Work/project-b
relative/path/from/home
```

Blank lines and lines starting with `#` are ignored. Relative paths in the
config file are resolved against the user's home directory.

Positional repository paths and `--config` are mutually exclusive.

## CLI reference

```text
python git_check.py [repo ...] [options]
```

| Argument / option | Default | Description |
| --- | --- | --- |
| `repo` | none | One or more Git repository paths. If provided, these override config-file discovery. |
| `-c`, `--config PATH` | `~/.config/git-check/repos.txt` | File containing repository paths, one per line. |
| `-b`, `--brief` | off | Hide the detailed remotes and branch sections. |
| `-f`, `--fetch` | off | Run `git fetch --all --quiet` before checking upstream sync status. |
| `--no-color` | auto | Disable colored output. Colors are also disabled automatically when stdout is not a TTY. |
| `--log-level LEVEL` | `WARNING` | Set logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. |

## Output notes

The branch sync line reports one of these states:

- `up-to-date (<upstream>)`
- `ahead N (<upstream>)`
- `behind N (<upstream>)`
- `ahead N | behind M (<upstream>)`
- `no upstream configured`
- `Detached HEAD`
- `Branch unknown`

If the working tree contains changes, the script prints the raw `git status -s`
output so staged, unstaged, untracked, renamed, and deleted files keep Git's
normal two-column status notation.

## Requirements

- Python 3.10 or newer
- `git` available on `PATH`

No third-party Python packages are required.

## Exit behavior

The script is primarily a human-readable diagnostic. It logs errors for invalid
repositories or missing Git context and then continues where possible. Use
`--log-level DEBUG` when diagnosing path discovery or Git command failures.
