"""Compare a template env mapping against a real one."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from env_diff.parser import EnvEntry


@dataclass
class EnvComparison:
    """Result of comparing an example file against an actual env file.

    Attributes:
        missing_keys: Keys declared in the example but absent from the actual
            file, in example-file order. These are the ones that usually break
            an app at startup.
        extra_keys: Keys in the actual file that the example does not mention,
            in actual-file order. Often stale settings or undocumented config.
        empty_keys: Keys present in both files whose actual value is empty.
            A key set to ``""`` is technically defined but is almost always a
            forgotten placeholder.
    """

    missing_keys: List[str] = field(default_factory=list)
    extra_keys: List[str] = field(default_factory=list)
    empty_keys: List[str] = field(default_factory=list)

    @property
    def has_problems(self) -> bool:
        """True when any key is missing or empty.

        Extra keys are reported but intentionally do not count as a problem:
        local overrides (``DEBUG=1``) are normal and should not fail CI.
        """
        return bool(self.missing_keys or self.empty_keys)


def compare_env_mappings(
    example_entries: Dict[str, EnvEntry],
    actual_entries: Dict[str, EnvEntry],
) -> EnvComparison:
    """Compare two parsed env mappings key by key.

    Args:
        example_entries: Parsed ``.env.example`` (the source of truth for which
            keys should exist). Its values are ignored; templates usually hold
            placeholders.
        actual_entries: Parsed ``.env`` being checked.

    Returns:
        An :class:`EnvComparison`. Key comparison is case-sensitive because
        environment variables are case-sensitive on Linux and macOS.
    """
    comparison = EnvComparison()
    for example_key in example_entries:
        if example_key not in actual_entries:
            comparison.missing_keys.append(example_key)
        elif actual_entries[example_key].value == "":
            comparison.empty_keys.append(example_key)
    for actual_key in actual_entries:
        if actual_key not in example_entries:
            comparison.extra_keys.append(actual_key)
    return comparison
