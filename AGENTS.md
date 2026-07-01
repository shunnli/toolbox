# AGENTS.md

Instructions for agents working in this repository.

## Project

This repository is a toolbox of lightweight, reusable Python scripts and MATLAB
components for research workflows and numerical experiments. It is not a Python
package or MATLAB package. Keep tools easy to run directly from this checkout or
copy into another project.

## Repository Layout

- `python/` contains standalone Python command-line tools.
- `matlab/` contains standalone MATLAB components.
- Each tool or component should keep its own local documentation and examples
  when useful.

## General Editing

- Prefer minimal, targeted edits.
- Preserve the existing structure and style of the tool being changed.
- Do not expand the repository into a packaged application unless explicitly
  requested.
- Keep files UTF-8 with LF line endings and spaces.
- Keep code cross-platform for Windows and Linux.
- Avoid adding dependencies. If a dependency is necessary, make it optional when
  practical and provide graceful fallback behavior.

## Python

- Target Python 3.11 or newer.
- Prefer `uv` for environment and dependency management.
- Do not install packages globally.
- Prefer the standard library.
- Keep each tool as a standalone CLI script with a `main()` entry point,
  `argparse`, and an `if __name__ == "__main__": main()` guard.
- Use modern type hints.
- Use `pathlib` for filesystem paths.
- Prefer `unittest` for tests, with focused tests beside the tool being tested.

## MATLAB

- Target MATLAB R2023b or newer.
- Keep components self-contained and easy to copy.
- Use `classdef < handle` for stateful components and plain function files for
  pure functions.
- Public functions and class methods should have clear MATLAB help text.
- Include a demo script when a component has workflows worth demonstrating.

## User Interfaces

- Python tools are CLI-first.
- Keep command interfaces lean: positional arguments and flags are preferred.
- Avoid interactive prompts except for explicit confirmations.
- When live progress or richer output is needed, prefer a small standard-library
  HTTP server over terminal UI frameworks or external web frameworks.

## Validation

- Run the smallest relevant validation for the edited tool.
- For Python changes, prefer targeted `unittest` commands.
- For MATLAB changes, run a focused MATLAB command or demo when MATLAB is
  available.
- State clearly when validation was not run.
