"""Tests for env_diff.ignore_file."""

import pytest

from env_diff.ignore_file import parse_ignore_text, read_ignore_file


def test_parses_one_key_per_line_skipping_comments_and_blanks():
    ignore_text = "# optional keys\nSENTRY_DSN\n\n   DEBUG  \n"
    assert parse_ignore_text(ignore_text) == ["SENTRY_DSN", "DEBUG"]


def test_drops_trailing_comments_and_duplicates():
    ignore_text = "SENTRY_DSN  # only set in production\nSENTRY_DSN\nDEBUG\r\n"
    assert parse_ignore_text(ignore_text) == ["SENTRY_DSN", "DEBUG"]


def test_empty_file_ignores_nothing():
    assert parse_ignore_text("") == []


def test_read_ignore_file_handles_bom(tmp_path):
    ignore_path = tmp_path / ".env-diff-ignore"
    ignore_path.write_text("\ufeffFIRST_KEY\nSECOND_KEY\n", encoding="utf-8")
    assert read_ignore_file(ignore_path) == ["FIRST_KEY", "SECOND_KEY"]


def test_read_ignore_file_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_ignore_file(tmp_path / "does-not-exist")
