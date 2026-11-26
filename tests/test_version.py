"""Guard against the package version drifting between its sources.

The version lives in ``pyproject.toml`` (used by pip) and in
``env_diff.__version__`` (printed by ``--version``). Both are bumped by hand at
release time, together with a dated CHANGELOG heading, so these tests fail if
one of the three is forgotten.
"""

import re
from pathlib import Path

import pytest

from env_diff import __version__
from env_diff.cli import main

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _read_pyproject_version() -> str:
    """Return the ``[project]`` version string from ``pyproject.toml``.

    ``tomllib`` only exists on Python 3.11+ and env-diff supports 3.9, so a
    narrow regex is used instead of adding a test dependency. It matches the
    first line that starts with ``version =``, which is the ``[project]``
    table's in this file; a second table with its own ``version`` key would
    need a real TOML parser.
    """
    pyproject_text = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version_match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject_text, re.MULTILINE)
    assert version_match is not None, "pyproject.toml has no version line"
    return version_match.group(1)


def test_package_version_matches_pyproject():
    assert __version__ == _read_pyproject_version()


def test_version_is_plain_semver():
    # Keep-a-Changelog headings and the release notes assume MAJOR.MINOR.PATCH
    # with no suffix; a pre-release tag would need a matching changelog style.
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_changelog_has_a_dated_section_for_the_current_version():
    changelog_text = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(
        rf"^## {re.escape(__version__)} - \d{{4}}-\d{{2}}-\d{{2}}$", changelog_text, re.MULTILINE
    ), "CHANGELOG.md needs a '## <version> - YYYY-MM-DD' heading for the current version"


def test_changelog_keeps_an_unreleased_section_on_top():
    # New pull requests add lines under "Unreleased"; it must stay above the
    # newest release so entries are not filed under an already shipped version.
    changelog_text = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    unreleased_position = changelog_text.find("## Unreleased")
    current_release_position = changelog_text.find(f"## {__version__} - ")
    assert 0 <= unreleased_position < current_release_position


def test_cli_version_flag_prints_the_package_version(capsys):
    # argparse's "version" action prints and then raises SystemExit(0).
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"env-diff {__version__}"
