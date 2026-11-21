"""Command-line entry point for env-diff."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from env_diff import __version__
from env_diff.compare import EnvComparison, compare_env_mappings, without_ignored_keys
from env_diff.ignore_file import DEFAULT_IGNORE_FILENAME, read_ignore_file
from env_diff.parser import (
    EnvParseError,
    entries_to_mapping,
    find_duplicate_keys,
    read_env_entries,
)

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
        "--strict",
        action="store_true",
        help="with --check, also fail when .env has keys the template does not list",
    )
    argument_parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        metavar="KEY",
        help="skip KEY in every section and in --check; repeat for several keys",
    )
    argument_parser.add_argument(
        "--ignore-file",
        metavar="PATH",
        default=None,
        help=(
            "read keys to ignore from PATH, one per line "
            f"(default: ./{DEFAULT_IGNORE_FILENAME} if it exists)"
        ),
    )
    argument_parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="print no report and no warnings; only the exit code (errors are still shown)",
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


def format_json_report(
    comparison: EnvComparison, example_path: str, env_path: str, strict: bool = False
) -> str:
    """Render a comparison as a JSON object for scripts and CI.

    Args:
        comparison: Result from :func:`compare_env_mappings`.
        example_path: Template path, echoed back so multi-file jobs can tell
            reports apart.
        env_path: Checked path, echoed back for the same reason.
        strict: Whether ``--strict`` was given. ``ok`` must agree with the
            exit code ``--check`` would produce, so extra keys make it false
            in strict mode.

    Returns:
        A JSON string with ``example_path``, ``env_path``, ``missing``,
        ``empty``, ``extra`` (key names only, never values) and ``ok``, which
        is true exactly when ``--check`` (with the same ``--strict``) would pass. Lists keep file order so
        output is stable across runs and easy to diff.
    """
    report_payload = {
        "example_path": example_path,
        "env_path": env_path,
        "missing": comparison.missing_keys,
        "empty": comparison.empty_keys,
        "extra": comparison.extra_keys,
        "ok": not comparison.fails_check(strict=strict),
    }
    return json.dumps(report_payload, indent=2)


def collect_ignored_keys(flag_keys: List[str], ignore_file_path: Optional[str]) -> List[str]:
    """Combine ``--ignore`` flags with keys from an ignore file.

    Args:
        flag_keys: Keys given with repeated ``--ignore`` flags.
        ignore_file_path: Value of ``--ignore-file``, or ``None`` to fall back
            to ``./.env-diff-ignore`` when that file exists.

    Returns:
        Flag keys followed by file keys. Duplicates are harmless because the
        result is only used for membership checks.

    Raises:
        FileNotFoundError: If an explicitly requested ignore file is missing.
            A missing default file is not an error, since most repos will not
            have one.
    """
    if ignore_file_path is not None:
        return list(flag_keys) + read_ignore_file(Path(ignore_file_path))
    default_ignore_path = Path(DEFAULT_IGNORE_FILENAME)
    if default_ignore_path.is_file():
        return list(flag_keys) + read_ignore_file(default_ignore_path)
    return list(flag_keys)


def format_duplicate_warnings(env_path: str, duplicate_lines_by_key: Dict[str, List[int]]) -> List[str]:
    """Build one warning line per key that is assigned more than once.

    Args:
        env_path: File the duplicates were found in, shown so the user knows
            which of the two files to edit.
        duplicate_lines_by_key: Output of :func:`find_duplicate_keys`.

    Returns:
        Lines such as ``env-diff: warning: .env: KEY is set 2 times (lines 3,
        9); the last value wins``. Values are never included.
    """
    return [
        f"env-diff: warning: {env_path}: {key} is set {len(line_numbers)} times "
        f"(lines {', '.join(str(line_number) for line_number in line_numbers)}); "
        "the last value wins"
        for key, line_numbers in duplicate_lines_by_key.items()
    ]


def main(argv: Optional[List[str]] = None) -> int:
    """Run env-diff and return a process exit code.

    Args:
        argv: Arguments without the program name; defaults to ``sys.argv[1:]``.

    Returns:
        ``EXIT_OK`` normally, ``EXIT_PROBLEMS_FOUND`` when ``--check`` is set
        and keys are missing or empty (or extra, with ``--strict``), ``EXIT_USAGE_ERROR`` when a file is
        missing or malformed.
    """
    arguments = build_argument_parser().parse_args(argv)
    try:
        example_entry_list = read_env_entries(Path(arguments.example_path))
        actual_entry_list = read_env_entries(Path(arguments.env_path))
        ignored_keys = collect_ignored_keys(arguments.ignore, arguments.ignore_file)
    except FileNotFoundError as error:
        print(f"env-diff: file not found: {error.filename}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    except EnvParseError as error:
        print(f"env-diff: could not parse file: {error}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    # Warnings go to stderr so text reports and JSON on stdout stay
    # machine-readable, and they never change the exit code: duplicates are
    # suspicious but the file still loads the same way a shell would read it.
    # --quiet silences them too, but the usage errors above are deliberately
    # printed before this point so a broken setup is never hidden.
    if not arguments.quiet:
        for checked_path, entry_list in (
            (arguments.example_path, example_entry_list),
            (arguments.env_path, actual_entry_list),
        ):
            for warning_line in format_duplicate_warnings(checked_path, find_duplicate_keys(entry_list)):
                print(warning_line, file=sys.stderr)

    example_entries = entries_to_mapping(example_entry_list)
    actual_entries = entries_to_mapping(actual_entry_list)
    comparison = without_ignored_keys(
        compare_env_mappings(example_entries, actual_entries), ignored_keys
    )
    # --quiet skips the report entirely; --format is still accepted so
    # scripts can toggle -q without rebuilding the rest of the command line.
    if not arguments.quiet:
        if arguments.format == "json":
            print(
                format_json_report(
                    comparison, arguments.example_path, arguments.env_path, strict=arguments.strict
                )
            )
        else:
            print(format_text_report(comparison, arguments.example_path, arguments.env_path))
    # --strict without --check only changes the JSON "ok" flag; the exit code
    # stays 0 so informational runs never fail unexpectedly.
    if arguments.check and comparison.fails_check(strict=arguments.strict):
        return EXIT_PROBLEMS_FOUND
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover - exercised through the console script
    sys.exit(main())
