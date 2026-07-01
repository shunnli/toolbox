#!/usr/bin/env python3

import argparse
import logging
import sys
from pathlib import Path, PurePosixPath
from datetime import datetime
import tarfile
import zipfile


logger = logging.getLogger(__name__)

IGNORED_DIRS = {
    ".git",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".cache",
}

IGNORED_FILES = {
    ".DS_Store",
    "Thumbs.db",
}


def format_size(size_bytes: int) -> str:
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


def resolve_archive_format(fmt: str) -> str:
    if fmt != "auto":
        return fmt

    if sys.platform.startswith("win"):
        return "zip"
    return "tar.gz"


def parse_exts(exts):
    if not exts:
        return None
    return {e.lower().lstrip(".") for e in exts}


def build_archive_name(base: str, fmt: str, no_timestamp: bool) -> str:
    if not no_timestamp:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        base = f"{base}-{ts}"

    if fmt == "zip":
        return f"{base}.zip"
    elif fmt == "tar.gz":
        return f"{base}.tar.gz"
    else:
        raise ValueError(f"Unsupported archive format: {fmt}")


def format_size_mb(size_bytes: int) -> float:
    return size_bytes / (1024 * 1024)


def validate_directories(targets: list[Path], output: Path):
    all_dirs = targets + [output]

    for i, a in enumerate(all_dirs):
        for b in all_dirs[i + 1 :]:
            if a in b.parents or b in a.parents:
                raise ValueError(
                    "Error: Directory containment detected:\n"
                    f"  {a.as_posix()}\n"
                    f"  {b.as_posix()}"
                )


def resolve_and_validate_targets(targets: list[str], output: str):
    resolved_targets = [Path(t).resolve() for t in targets]
    resolved_output = Path(output).resolve()

    dir_targets: list[Path] = []
    file_targets: list[Path] = []

    for t in resolved_targets:
        if t.is_dir():
            dir_targets.append(t)
        elif t.is_file():
            file_targets.append(t)
        else:
            raise ValueError(f"Target does not exist: {t.as_posix()}")

    validate_directories(dir_targets, resolved_output)

    return dir_targets, file_targets, resolved_output


def should_ignore(path: Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.parts)


def collect_files(
    dir_roots: list[Path],
    file_targets: list[Path],
    exts: set[str] | None,
) -> list[tuple[Path | None, Path]]:
    collected: list[tuple[Path | None, Path]] = []

    for root in dir_roots:
        for p in root.rglob("*"):
            if should_ignore(p):
                continue
            if not p.is_file():
                continue
            if p.name in IGNORED_FILES:
                continue
            if exts is not None and p.suffix.lstrip(".").lower() not in exts:
                continue

            collected.append((root, p))

    # handle file targets
    for f in file_targets:
        if f.name in IGNORED_FILES:
            continue
        if exts is not None and f.suffix.lstrip(".").lower() not in exts:
            continue

        collected.append((None, f))

    def archive_sort_key(item: tuple[Path | None, Path]) -> str:
        root, f = item
        if root is None:
            return f.name
        return f"{root.name}/{f.relative_to(root).as_posix()}"

    return sorted(collected, key=archive_sort_key)


def ensure_output_dir(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)


def create_tar_archive(
    files: list[tuple[Path | None, Path]],
    output_dir: Path,
    archive_name: str,
):
    archive_path = output_dir / archive_name

    if archive_path.exists():
        raise FileExistsError(f"Archive already exists: {archive_path.as_posix()}")

    with tarfile.open(archive_path, "w:gz", format=tarfile.USTAR_FORMAT) as tar:
        for root, f in files:
            if root is None:
                arc = PurePosixPath(f.name)
            else:
                arc = PurePosixPath(root.name) / PurePosixPath(f.relative_to(root))

            tar.add(f, arcname=str(arc))

    return archive_path


def create_zip_archive(
    files: list[tuple[Path | None, Path]],
    output_dir: Path,
    archive_name: str,
):
    archive_path = output_dir / archive_name

    if archive_path.exists():
        raise FileExistsError(f"Archive already exists: {archive_path.as_posix()}")

    with zipfile.ZipFile(
        archive_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as zf:
        for root, f in files:
            if root is None:
                arc = PurePosixPath(f.name)
            else:
                arc = PurePosixPath(root.name) / PurePosixPath(f.relative_to(root))

            zf.write(f, arcname=str(arc))

    return archive_path


def create_archive(
    files: list[tuple[Path | None, Path]],
    output_dir: Path,
    archive_name: str,
    fmt: str,
):
    if fmt == "tar.gz":
        return create_tar_archive(files, output_dir, archive_name)
    elif fmt == "zip":
        return create_zip_archive(files, output_dir, archive_name)
    else:
        raise ValueError(f"Unsupported archive format: {fmt}")


def parse_args():
    parser = argparse.ArgumentParser(
        prog="archive",
        description="Pack selected targets (directories or files) into a tar.gz archive.",
    )

    parser.add_argument(
        "--targets",
        nargs="+",
        required=True,
        metavar="PATH",
        help="One or more targeths (directories or files) to archive",
    )

    parser.add_argument(
        "--output",
        required=True,
        metavar="DIR",
        help="Output directory for the archive (must be outside targets)",
    )

    parser.add_argument(
        "--name",
        required=True,
        metavar="NAME",
        help="Base name of the archive (without extension)",
    )

    parser.add_argument(
        "--ext",
        nargs="+",
        metavar="EXT",
        help=(
            "File extensions to include (e.g. tex bib cls). "
            "If omitted, include all files except ignored directories"
        ),
    )

    parser.add_argument(
        "--no-timestamp",
        action="store_true",
        help="Do not append timestamp to the archive name",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be archived without creating files or directories",
    )

    parser.add_argument(
        "--format",
        choices=["auto", "zip", "tar.gz"],
        default="auto",
        help=(
            "Archive format. "
            "'auto' selects zip on Windows and tar.gz on other platforms"
        ),
    )

    return parser.parse_args()


def main():
    args = parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(message)s",
    )

    targets = args.targets  # list[str]
    exts = parse_exts(args.ext)  # args.ext: None | list[str]

    try:
        dir_targets, file_targets, output_dir = resolve_and_validate_targets(
            targets, args.output
        )
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    files = collect_files(dir_targets, file_targets, exts)

    if not files:
        logger.error("No matching files found")
        sys.exit(2)

    fmt = resolve_archive_format(args.format)

    archive_name = build_archive_name(
        args.name, fmt=fmt, no_timestamp=args.no_timestamp
    )
    archive_path = output_dir / archive_name

    if args.dry_run:
        print("[archive] Dry run (no side effects):")
        print("")
        print("  Archive would be created at:")
        print(f"    {archive_path.as_posix()}")
        print("")
        print("  Files to be archived:")
        for root, f in files:
            if root is None:
                shown = PurePosixPath(f.name)
            else:
                shown = PurePosixPath(root.name) / PurePosixPath(f.relative_to(root))
            print(f"    {shown}")
        return

    ensure_output_dir(output_dir)

    try:
        final_path = create_archive(
            files,
            output_dir,
            archive_name,
            fmt=fmt,
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

    size_str = format_size(final_path.stat().st_size)
    print(f"[archive] Archive created: {final_path.as_posix()} (size: {size_str})")


if __name__ == "__main__":
    main()
