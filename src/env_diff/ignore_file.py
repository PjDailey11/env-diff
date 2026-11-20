"""Load ignored key names from a shared ignore file.

A file is easier to review and share than a long chain of ``--ignore`` flags
spread across a git hook, a CI job, and a README. The format is intentionally
the same shape as ``.gitignore``: one entry per line, ``#`` comments allowed.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

# Picked up automatically from the current directory when present, so a repo
# can commit its optional keys once and every env-diff invocation honors them.
DEFAULT_IGNORE_FILENAME = ".env-diff-ignore"


def parse_ignore_text(ignore_text: str) -> List[str]:
    """Extract key names from the contents of an ignore file.

    Args:
        ignore_text: Full file contents.

    Returns:
        Key names in file order, without duplicates. Blank lines and lines
        starting with ``#`` are skipped, and surrounding whitespace is removed
        so indented or Windows-style (``\\r\\n``) files work. Trailing comments
        after a key (``SENTRY_DSN  # only in prod``) are dropped as well,
        since ``#`` can never be part of a valid key name.
    """
    ignored_keys: List[str] = []
    for line_text in ignore_text.splitlines():
        key_name = line_text.split("#", 1)[0].strip()
        if key_name and key_name not in ignored_keys:
            ignored_keys.append(key_name)
    return ignored_keys


def read_ignore_file(ignore_path: Path) -> List[str]:
    """Read an ignore file from disk.

    Args:
        ignore_path: Path to the file.

    Returns:
        Key names as returned by :func:`parse_ignore_text`.

    Raises:
        FileNotFoundError: If the file does not exist. The CLI only raises
            this for an explicit ``--ignore-file``; the default file is
            optional and checked with ``exists()`` first.
    """
    return parse_ignore_text(Path(ignore_path).read_text(encoding="utf-8-sig"))
