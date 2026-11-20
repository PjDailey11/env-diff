"""Parse dotenv-style files into ordered key/value entries.

The parser deliberately understands only the common subset of the dotenv
format (``KEY=value``, optional ``export`` prefix, quotes, ``#`` comments).
It never expands ``${VAR}`` references or runs anything: env-diff only needs
to know which keys exist and whether their values are empty.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

# Shell-style variable names. Dotenv files in the wild sometimes use dots or
# dashes (e.g. Spring's ``server.port``), so those are accepted too rather than
# being reported as syntax errors.
_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*$")


class EnvParseError(ValueError):
    """Raised when a non-comment line cannot be read as ``KEY=value``.

    Attributes:
        line_number: 1-based line number of the offending line.
        line_text: The raw line, so callers can show it in an error message.
    """

    def __init__(self, line_number: int, line_text: str, reason: str) -> None:
        super().__init__(f"line {line_number}: {reason}: {line_text.strip()!r}")
        self.line_number = line_number
        self.line_text = line_text


@dataclass(frozen=True)
class EnvEntry:
    """One ``KEY=value`` assignment found in a dotenv file.

    Attributes:
        key: Variable name with any ``export`` prefix removed.
        value: Value with surrounding quotes and inline comments stripped.
        line_number: 1-based line where the assignment appeared, used to point
            users at the exact line in reports.
    """

    key: str
    value: str
    line_number: int


def _strip_value(raw_value: str) -> str:
    """Return ``raw_value`` without surrounding quotes or a trailing comment.

    Quoted values keep everything inside the quotes, including ``#``, because
    ``PASSWORD="abc#123"`` is a real password, not a comment. Unquoted values
    treat `` #`` (space then hash) as the start of a comment, matching how
    python-dotenv and docker compose behave; a bare ``#`` with no space before
    it (``COLOR=#fff``) stays part of the value.
    """
    stripped = raw_value.strip()
    if len(stripped) >= 2 and stripped[0] in "\"'":
        quote = stripped[0]
        closing_index = stripped.find(quote, 1)
        if closing_index != -1:
            return stripped[1:closing_index]
        # Unterminated quote: keep the text after the opening quote instead of
        # failing, since multi-line values are out of scope for this tool.
        return stripped[1:]
    comment_index = stripped.find(" #")
    if comment_index != -1:
        stripped = stripped[:comment_index]
    return stripped.strip()


def parse_env_text(env_text: str) -> List[EnvEntry]:
    """Parse dotenv-formatted text into a list of entries in file order.

    Args:
        env_text: Full contents of a ``.env``-style file.

    Returns:
        Entries in the order they appear. Duplicate keys are all returned so
        callers can decide how to handle them (see :func:`entries_to_mapping`).

    Raises:
        EnvParseError: If a non-blank, non-comment line has no ``=`` or has an
            invalid key name.
    """
    parsed_entries: List[EnvEntry] = []
    for line_number, line_text in enumerate(env_text.splitlines(), start=1):
        content = line_text.strip()
        if not content or content.startswith("#"):
            continue
        if content.startswith("export "):
            content = content[len("export "):].lstrip()
        if "=" not in content:
            raise EnvParseError(line_number, line_text, "expected KEY=value")
        raw_key, raw_value = content.split("=", 1)
        key = raw_key.strip()
        if not _KEY_PATTERN.match(key):
            raise EnvParseError(line_number, line_text, f"invalid key name {key!r}")
        parsed_entries.append(EnvEntry(key, _strip_value(raw_value), line_number))
    return parsed_entries


def entries_to_mapping(entries: List[EnvEntry]) -> Dict[str, EnvEntry]:
    """Collapse entries into a ``key -> entry`` mapping.

    When a key is assigned more than once, the last assignment wins, which is
    what shells and most dotenv loaders do when they read the file top to
    bottom. Insertion order follows each key's first appearance so reports
    stay in the same order as the file.
    """
    mapping: Dict[str, EnvEntry] = {}
    for entry in entries:
        mapping[entry.key] = entry
    return mapping


def find_duplicate_keys(entries: List[EnvEntry]) -> Dict[str, List[int]]:
    """Find keys that are assigned more than once.

    A repeated key is almost always a mistake: a merge conflict resolved by
    keeping both sides, or a pasted block that re-declares ``SECRET_KEY=``
    below the real value. Because the last assignment silently wins, the
    empty copy can hide the real one, so callers surface these as warnings.

    Args:
        entries: Entries from :func:`parse_env_text`, in file order.

    Returns:
        Mapping of each duplicated key to every line number where it is
        assigned, ordered by the key's first appearance. Keys assigned only
        once are omitted, so an empty dict means the file is clean.
    """
    line_numbers_by_key: Dict[str, List[int]] = {}
    for entry in entries:
        line_numbers_by_key.setdefault(entry.key, []).append(entry.line_number)
    return {
        key: line_numbers
        for key, line_numbers in line_numbers_by_key.items()
        if len(line_numbers) > 1
    }


def read_env_entries(env_path: Path) -> List[EnvEntry]:
    """Read and parse a dotenv file from disk, keeping every assignment.

    Args:
        env_path: Path to the file.

    Returns:
        All entries in file order, including duplicates, so callers can both
        build a mapping and look for repeated keys from a single read.

    Raises:
        FileNotFoundError: If the file does not exist.
        EnvParseError: If the file contains a malformed line.
    """
    # utf-8-sig drops a BOM that Windows editors sometimes add, which would
    # otherwise glue itself onto the first key name.
    env_text = Path(env_path).read_text(encoding="utf-8-sig")
    return parse_env_text(env_text)


def read_env_file(env_path: Path) -> Dict[str, EnvEntry]:
    """Read and parse a dotenv file from disk.

    Args:
        env_path: Path to the file.

    Returns:
        Mapping of key to its (last) entry.

    Raises:
        FileNotFoundError: If the file does not exist.
        EnvParseError: If the file contains a malformed line.
    """
    return entries_to_mapping(read_env_entries(env_path))
