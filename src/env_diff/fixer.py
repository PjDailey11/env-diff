"""Append missing template keys to an env file (``env-diff --fix``).

The fixer only ever *appends*. It never rewrites, reorders, or deletes an
existing line, because a ``.env`` holds hand-tuned secrets and comments that
a tool has no business touching. Appending is also trivially reversible: the
added block is clearly labelled and sits at the end of the file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from env_diff.parser import EnvEntry

# Written above the appended block so a later reader (or a code reviewer of a
# committed .env.local) can tell which lines came from the tool.
FIX_BLOCK_HEADER = "# Added by env-diff --fix: fill in these values"


def _format_placeholder(placeholder: str) -> str:
    """Quote a template value so it parses back to the same string.

    The parser treats `` #`` as the start of a comment and strips surrounding
    whitespace, so values containing whitespace, ``#``, or a leading quote
    must be quoted to survive a round trip. Double quotes are preferred;
    single quotes are used when the value itself contains a double quote.
    Plain values (the common case: empty or ``8000``) are written as-is.
    """
    needs_quotes = (
        placeholder != placeholder.strip()
        or " " in placeholder
        or "\t" in placeholder
        or "#" in placeholder
        # A newline only survives inside double quotes (multi-line values).
        or "\n" in placeholder
        or placeholder.startswith(('"', "'"))
    )
    if not needs_quotes:
        return placeholder
    if '"' not in placeholder:
        return f'"{placeholder}"'
    return f"'{placeholder}'"


def build_missing_key_lines(missing_keys: List[str], example_entries: Dict[str, EnvEntry]) -> List[str]:
    """Build ``KEY=placeholder`` lines for keys missing from the env file.

    Args:
        missing_keys: Keys to add, in the order they should be written
            (normally :attr:`EnvComparison.missing_keys`, i.e. template order).
        example_entries: Parsed template mapping; each key's template value
            becomes the placeholder. Keys absent from the mapping get an empty
            value rather than raising, since an empty value is still a valid,
            obviously unfinished assignment.

    Returns:
        One assignment line per key, without trailing newlines.
    """
    lines: List[str] = []
    for key in missing_keys:
        template_entry = example_entries.get(key)
        placeholder = template_entry.value if template_entry is not None else ""
        lines.append(f"{key}={_format_placeholder(placeholder)}")
    return lines


def render_fix_block(assignment_lines: List[str]) -> str:
    """Return the labelled block that ``--fix`` appends, without separators.

    Shared by :func:`append_missing_keys` and ``--fix --dry-run`` so the
    preview is byte-for-byte the text that a real run would write; keeping a
    second copy of the formatting in the CLI would let the two drift apart.

    Args:
        assignment_lines: Output of :func:`build_missing_key_lines`.

    Returns:
        The header comment followed by one assignment per line, ending with a
        newline, or ``""`` when there is nothing to add.
    """
    if not assignment_lines:
        return ""
    return "\n".join([FIX_BLOCK_HEADER, *assignment_lines]) + "\n"


def append_missing_keys(env_path: Path, assignment_lines: List[str]) -> int:
    """Append assignment lines to ``env_path`` under a labelled header.

    Args:
        env_path: Env file to extend. It is created (with parent directories
            left as they are) if it does not exist yet, which is the normal
            situation right after cloning a repository.
        assignment_lines: Output of :func:`build_missing_key_lines`.

    Returns:
        The number of assignments written. Nothing is written, and the file
        is not created or touched, when ``assignment_lines`` is empty.

    Raises:
        OSError: If the file cannot be read or written (e.g. a missing parent
            directory or no permission).
    """
    if not assignment_lines:
        return 0
    env_path = Path(env_path)
    existing_text = env_path.read_text(encoding="utf-8-sig") if env_path.exists() else ""
    separator = ""
    if existing_text:
        # Make sure the block starts on its own line even if the file lacked
        # a final newline, and leave one blank line before the header so the
        # appended section is easy to spot.
        separator = "\n" if existing_text.endswith("\n") else "\n\n"
    appended_block = separator + render_fix_block(assignment_lines)
    with env_path.open("a", encoding="utf-8") as env_file:
        env_file.write(appended_block)
    return len(assignment_lines)
