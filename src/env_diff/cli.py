"""Command-line entry point for env-diff."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from env_diff import __version__
from env_diff.compare import EnvComparison, compare_env_mappings
from env_diff.parser import EnvParseError, read_env_file

# Exit codes are part of the CLI contract so scripts can tell "your .env is
# incomplete" (1) apart from "env-diff could not even read the files" (2).
EXIT_OK = 0
EXIT_PROBLEMS_FOUND = 1
EXIT_USAGE_ERROR = 2


def build_argument_parser() -> argparse.ArgumentParser:
    """Create the argparse parser for the ``env-diff`` command.

    Returns:
        A configured :class:`argparse.ArgumentParser`.
    """
    argument_parser = argparse.ArgumentParser(
        prog="env-diff",
        description="Compare a .env.example template against a .env file.",
    )
    argument_parser.add_argument(
        "example_path",
        nargs="?",
        default=".env.example",
        help="template listing the keys that should exist (default: .env.example)",
    )
    argument_parser.add_argument(
        "env_path",
        nargs="?",
        default=".env",
        help="real env file to check (default: .env)",
    )
    argument_parser.add_argument(
        "--check",
        action="store_true",
        help="exit with status 1 when keys are missing or empty (for CI and git hooks)",
    )
    argument_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="report format: human-readable text (default) or JSON for scripts",
    )
    argument_parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return argument_parser


def format_text_report(comparison: EnvComparison, example_path: str, env_path: str) -> str:
    """Render a comparison as a human-readable report.

    Args:
        comparison: Result from :func:`compare_env_mappings`.
        example_path: Template path, shown in the header.
        env_path: Checked path, shown in the header.

    Returns:
        Multi-line text ending without a trailing newline. Sections with no
        keys are omitted so a clean result is a single short line.
    """
    report_lines = [f"Comparing {env_path} against {example_path}"]
    sections = [
        ("Missing", comparison.missing_keys, "-"),
        ("Empty", comparison.empty_keys, "?"),
        ("Extra", comparison.extra_keys, "+"),
    ]
    for section_title, section_keys, marker in sections:
        if section_keys:
            report_lines.append(f"{section_title} ({len(section_keys)}):")
            report_lines.extend(f"  {marker} {key}" for key in section_keys)
    if not (comparison.missing_keys or comparison.empty_keys or comparison.extra_keys):
        report_lines.append("All keys match.")
    return "\n".join(report_lines)


def format_json_report(comparison: EnvComparison, example_path: str, env_path: str) -> str:
    """Render a comparison as a JSON object for scripts and CI.

    Args:
        comparison: Result from :func:`compare_env_mappings`.
        example_path: Template path, echoed back so multi-file jobs can tell
            reports apart.
        env_path: Checked path, echoed back for the same reason.

    Returns:
        A JSON string with ``example_path``, ``env_path``, ``missing``,
        ``empty``, ``extra`` (key names only, never values) and ``ok``, which
        is true exactly when ``--check`` would pass. Lists keep file order so
        output is stable across runs and easy to diff.
    """
    report_payload = {
        "example_path": example_path,
        "env_path": env_path,
        "missing": comparison.missing_keys,
        "empty": comparison.empty_keys,
        "extra": comparison.extra_keys,
        "ok": not comparison.has_problems,
    }
    return json.dumps(report_payload, indent=2)


def main(argv: Optional[List[str]] = None) -> int:
    """Run env-diff and return a process exit code.

    Args:
        argv: Arguments without the program name; defaults to ``sys.argv[1:]``.

    Returns:
        ``EXIT_OK`` normally, ``EXIT_PROBLEMS_FOUND`` when ``--check`` is set
        and keys are missing or empty, ``EXIT_USAGE_ERROR`` when a file is
        missing or malformed.
    """
    arguments = build_argument_parser().parse_args(argv)
    try:
        example_entries = read_env_file(Path(arguments.example_path))
        actual_entries = read_env_file(Path(arguments.env_path))
    except FileNotFoundError as error:
        print(f"env-diff: file not found: {error.filename}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    except EnvParseError as error:
        print(f"env-diff: could not parse file: {error}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    comparison = compare_env_mappings(example_entries, actual_entries)
    report_formatter = format_json_report if arguments.format == "json" else format_text_report
    print(report_formatter(comparison, arguments.example_path, arguments.env_path))
    if arguments.check and comparison.has_problems:
        return EXIT_PROBLEMS_FOUND
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - exercised through the console script
    sys.exit(main())
