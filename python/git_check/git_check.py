#!/usr/bin/env python3

import subprocess
import argparse
import logging
from pathlib import Path
import sys

logger = logging.getLogger(__name__)


class Colors:
    enabled = True

    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    RED_BG = "\033[41m"
    GRAY = "\033[90m"
    RESET = "\033[0m"

    @staticmethod
    def wrap(text: str, color: str) -> str:
        if Colors.enabled and color:
            return f"{color}{text}{Colors.RESET}"
        return text


def print_cyan(text: str):
    print(Colors.wrap(text, Colors.CYAN))


def print_yellow(text: str):
    print(Colors.wrap(text, Colors.YELLOW))


def load_repos_from_config(config_path: Path) -> list[Path]:
    repos: list[Path] = []

    for line in config_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        logger.debug(f"Get raw path: {line}")
        path = Path(line).expanduser()

        if not path.is_absolute():
            path = Path.home() / path

        logger.debug(f"Add path: {path.resolve()}")
        repos.append(path.resolve())

    return repos


def run_git_command(
    repo_path: Path,
    args: list[str],
    *,
    check: bool = True,
    quiet: bool = False,
) -> str:
    cmd = ["git"] + args

    logger.debug(f"$ {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            text=True,
            capture_output=True,
            check=check,
        )
        return result.stdout.rstrip()
    except subprocess.CalledProcessError as e:
        if not quiet:
            logger.error(f"{' '.join(cmd)} failed: {e.stderr.strip()}")
        return ""


def get_git_config(repo_path: Path, key: str):
    for scope in ["--local", "--global"]:
        out = run_git_command(
            repo_path,
            ["config", scope, "--get", key],
            quiet=True,
            check=False,
        )
        if out:
            return out, "local" if scope == "--local" else "global"
    return None, "not set"


def is_git_repo(path: Path) -> bool:
    out = run_git_command(
        path,
        ["rev-parse", "--is-inside-work-tree"],
        quiet=True,
        check=False,
    )
    return out == "true"


def find_git_root(start: Path) -> Path | None:
    out = run_git_command(
        start,
        ["rev-parse", "--show-toplevel"],
        quiet=True,
        check=False,
    )
    if out:
        return Path(out).resolve()
    return None


def check_sync_status(repo_path: Path, *, do_fetch: bool) -> str:
    if do_fetch:
        logger.info("Fetching remote updates...")
        run_git_command(repo_path, ["fetch", "--all", "--quiet"])

    current_branch = run_git_command(
        repo_path, ["rev-parse", "--abbrev-ref", "HEAD"], check=False
    ).strip()

    if not current_branch:
        logger.warning("Cannot determine current branch.")
        return "Branch unknown"

    if current_branch == "HEAD":
        logger.warning("Detached HEAD state; sync status unavailable.")
        return "Detached HEAD"

    upstream = run_git_command(
        repo_path,
        ["rev-parse", "--abbrev-ref", f"{current_branch}@{{u}}"],
        check=False,
    ).strip()

    if not upstream:
        logger.warning("Branch %s : no upstream configured", current_branch)
        return f"Branch {current_branch}: no upstream configured"

    behind_ahead = run_git_command(
        repo_path,
        ["rev-list", "--left-right", "--count", f"{upstream}...{current_branch}"],
        check=False,
    )

    try:
        behind, ahead = map(int, behind_ahead.split())
        status = []
        warning_flag = False
        if ahead == 0 and behind == 0:
            status.append(f"up-to-date ({upstream})")
        if ahead > 0:
            status.append(f"ahead {ahead} ({upstream})")
            warning_flag = True
        if behind > 0:
            status.append(f"behind {behind} ({upstream})")
            warning_flag = True

        msg = f"Branch {current_branch}: {' | '.join(status)}"
        if warning_flag:
            return Colors.wrap(msg, Colors.YELLOW)
        else:
            return Colors.wrap(msg, Colors.GREEN)

    except Exception:
        logger.warning("Branch %s : cannot determine sync status", current_branch)
        return "Branch sync unknown"


def show_repo_info(repo_path: Path, *, brief_flag: bool, do_fetch: bool):
    repo_path = repo_path.resolve()

    if not is_git_repo(repo_path):
        logger.error(f"{repo_path} is not a git repository")
        return

    repo_root = find_git_root(repo_path) or repo_path

    print_cyan(f"Repository: {repo_root}")

    branch = run_git_command(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    print_cyan(f"Current branch: {branch}")

    for key in ["user.name", "user.email"]:
        value, source = get_git_config(repo_root, key)
        if value:
            print_cyan(f"{key}: {value} ({source})")
        else:
            print_yellow(
                f"{key}: not set. Please set it using `git config {key} <value>`"
            )

    status = run_git_command(repo_root, ["status", "-s"])
    if not status:
        print_cyan("Working tree clean")
    else:
        print_yellow("Uncommitted changes present")
        print(status)

    msg = check_sync_status(repo_root, do_fetch=do_fetch)
    print(msg)

    last_commit = run_git_command(
        repo_root,
        ["log", "-1", "--pretty=format:%h | %an <%ae> | %ar | %s"],
        quiet=True,
        check=False,
    )
    print_cyan(f"Last commit: {last_commit}")

    if brief_flag:
        return

    print("")
    remotes = run_git_command(
        repo_root,
        ["remote", "-v"],
        quiet=True,
        check=False,
    )
    print_cyan("Remotes:")
    print(remotes if remotes else "  (none)")

    print("")
    branches = run_git_command(
        repo_root,
        ["branch", "-vva"],
        quiet=True,
        check=False,
    )
    print_cyan("Branches:")
    print(branches or "  (none)")
    print("")


def args_parse():
    parser = argparse.ArgumentParser(
        prog="git-check",
        description="Show information about one or more Git repositories.",
    )
    parser.add_argument(
        "repos",
        nargs="*",
        type=Path,
        help="Git repository paths (override --config if provided)",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=Path,
        help=(
            "Path to a config file listing repository paths, one per line. "
            "Default: ~/.config/git-check/repos.txt. "
            "Relative paths are resolved against the user's home directory."
        ),
    )
    parser.add_argument(
        "--log-level",
        type=str.upper,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="WARNING",
        help="Set log level (default: WARNING)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )
    parser.add_argument(
        "-b",
        "--brief",
        action="store_true",
        help="Show brief output",
    )
    parser.add_argument(
        "-f",
        "--fetch",
        action="store_true",
        help="Run 'git fetch' before checking branch sync status",
    )
    return parser.parse_args()


def main():
    args = args_parse()

    logging.basicConfig(
        level=getattr(logging, args.log_level, logging.WARNING),
        format="[%(levelname)s] %(message)s",
    )

    if args.no_color or not sys.stdout.isatty():
        Colors.enabled = False

    if args.repos and args.config:
        logger.error("Cannot specify both repos and --config")
        return

    repos = args.repos

    if not repos:
        config = args.config or Path.home() / ".config/git-check/repos.txt"
        if config.exists():
            logger.debug(f"Using config file {config}")
            repos = load_repos_from_config(config)
        else:
            logger.debug(f"No config file found at {config}")

    if not repos:
        root = find_git_root(Path.cwd())
        if root:
            repos = [root]
            logger.debug(f"Using git repository {root}")
        else:
            logger.error("Not inside a git repository")
            logger.error("Cannot determine git repository root")
            return

    for repo in repos:
        logger.debug(f"Checking repository {repo}")
        show_repo_info(repo, brief_flag=args.brief, do_fetch=args.fetch)


if __name__ == "__main__":
    main()
