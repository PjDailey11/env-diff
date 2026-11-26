"""Parse dotenv-style files into ordered key/value entries.

The parser deliberately understands only the common subset of the dotenv
format (``KEY=value``, optional ``export`` prefix, quotes, ``#`` comments,
and double-quoted values spanning several lines).
It never expands ``${VAR}`` references or runs anything: env-diff only needs
to know which keys exist and whether their values are empty.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

# Shell-style variable names. Dotenv files in the wild sometimes use dots or
# dashes (e.g. Spring's ``server.port``), so those are accepted too rather than
# being reported as syntax errors.
_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*$")

# Inline marker that flags a template key as optional, e.g.
# ``SENTRY_DSN=  # env-diff: optional``. Matching is case-insensitive and
# tolerant of spacing because people type these by hand; the word boundary
# keeps ``optionally`` or ``optional-ish`` from counting by accident.
_OPTIONAL_MARKER_PATTERN = re.compile(r"env-diff:\s*optional\b", re.IGNORECASE)


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
        optional: True when the line's inline comment contains
            ``env-diff: optional``. Only meaningful in the template; defaults
            to False so existing ``EnvEntry(key, value, line)`` calls still work.
    """

    key: str
    value: str
    line_number: int
    optional: bool = False


def _strip_value(raw_value: str) -> str:
    """Return ``raw_value`` without surrounding quotes or a trailing comment.

    Quoted values keep everything inside the quotes, including ``#``, because
    ``PASSWORD="abc#123"`` is a real password, not a comment. Unquoted values
    treat `` #`` (space then hash) as the start of a comment, matching how
    python-dotenv and docker compose behave; a bare ``#`` with no space before
    it (``COLOR=#fff``) stays part of the value.
    """
    stripped = raw_value.strip()
    if raw_value[:1].isspace() and stripped.startswith("#"):
        # ``KEY= # note`` is an empty value followed by a comment (as in
        # python-dotenv), while ``COLOR=#fff`` with no space is a real value.
        return ""
    if len(stripped) >= 2 and stripped[0] in "\"'":
        quote = stripped[0]
        closing_index = stripped.find(quote, 1)
        if closing_index != -1:
            return stripped[1:closing_index]
        # Unterminated quote: keep the text after the opening quote instead of
        # failing. Multi-line double-quoted values were already joined by
        # parse_env_text, so this only happens for an unclosed single quote
        # or a double quote that runs to the end of the file.
        return stripped[1:]
    comment_index = stripped.find(" #")
    if comment_index != -1:
        stripped = stripped[:comment_index]
    return stripped.strip()


def _trailing_comment(raw_value: str) -> str:
    """Return the inline comment after a value, or ``""`` if there is none.

    Uses the same rules as :func:`_strip_value` so the two never disagree:
    for a quoted value the comment can only start after the closing quote
    (``"a # b"`` has no comment), and for an unquoted value it starts at the
    first `` #``. An unterminated quote swallows the rest of the line, so it
    has no comment either.
    """
    stripped = raw_value.strip()
    if len(stripped) >= 2 and stripped[0] in "\"'":
        closing_index = stripped.find(stripped[0], 1)
        if closing_index == -1:
            return ""
        after_quote = stripped[closing_index + 1:]
        hash_index = after_quote.find("#")
        return after_quote[hash_index + 1:].strip() if hash_index != -1 else ""
    if raw_value[:1].isspace() and stripped.startswith("#"):
        # ``KEY= # note``: the value is empty and the remainder is a comment.
        # Without the leading space (``COLOR=#fff``) the ``#`` is the value.
        return stripped[1:].strip()
    comment_index = stripped.find(" #")
    return stripped[comment_index + 2:].strip() if comment_index != -1 else ""


def _opens_multiline_value(raw_value: str) -> bool:
    """Return True if ``raw_value`` starts a double-quoted value left open.

    Only double quotes may span lines, following python-dotenv and docker
    compose, where multi-line values are almost always PEM keys or
    certificates written as ``KEY="-----BEGIN ...``. Single-quoted values stay
    single-line so a stray apostrophe (``NAME='O``) cannot swallow the rest of
    the file.
    """
    stripped = raw_value.strip()
    return stripped.startswith('"') and stripped.find('"', 1) == -1


def _join_multiline_value(first_raw_value: str, following_lines: List[str]) -> Tuple[str, int]:
    """Collect a multi-line double-quoted value.

    Args:
        first_raw_value: The text after ``=`` on the line that opened the
            quote (it contains the opening ``"`` but no closing one).
        following_lines: The lines after that one, in order.

    Returns:
        ``(raw_value, consumed_line_count)``: ``raw_value`` is the whole quoted
        value joined with ``\n`` (plus anything after the closing quote, such
        as an inline comment), shaped so :func:`_strip_value` and
        :func:`_trailing_comment` treat it like a single-line value. If the
        quote is never closed, every remaining line is consumed, matching the
        lenient single-line rule that an unterminated quote keeps the rest.
    """
    collected_parts = [first_raw_value.rstrip("\r")]
    for consumed_count, line_text in enumerate(following_lines, start=1):
        collected_parts.append(line_text)
        if '"' in line_text:
            return "\n".join(collected_parts), consumed_count
    return "\n".join(collected_parts), len(following_lines)


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
    all_lines = env_text.splitlines()
    line_index = 0
    # A while loop instead of enumerate() because a multi-line value consumes
    # several physical lines at once.
    while line_index < len(all_lines):
        line_text = all_lines[line_index]
        line_number = line_index + 1
        line_index += 1
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
        if _opens_multiline_value(raw_value):
            # The entry keeps the line number where it starts, which is where
            # people look for the key.
            raw_value, consumed_line_count = _join_multiline_value(
                raw_value, all_lines[line_index:]
            )
            line_index += consumed_line_count
        is_optional = bool(_OPTIONAL_MARKER_PATTERN.search(_trailing_comment(raw_value)))
        parsed_entries.append(
            EnvEntry(key, _strip_value(raw_value), line_number, optional=is_optional)
        )
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


def find_optional_keys(entries: List[EnvEntry]) -> List[str]:
    """List keys whose assignment carries a ``# env-diff: optional`` marker.

    Args:
        entries: Entries from :func:`parse_env_text`, normally the template's.

    Returns:
        Marked keys in first-appearance order, without duplicates. If a key is
        assigned twice, it counts as optional when *any* assignment is marked:
        the marker documents intent, and a duplicate is already reported as a
        warning, so being lenient here avoids surprising check failures.
    """
    optional_keys: List[str] = []
    for entry in entries:
        if entry.optional and entry.key not in optional_keys:
            optional_keys.append(entry.key)
    return optional_keys


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
