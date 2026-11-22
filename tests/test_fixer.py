"""Tests for env_diff.fixer."""

import pytest

from env_diff.fixer import (
    FIX_BLOCK_HEADER,
    append_missing_keys,
    build_missing_key_lines,
    render_fix_block,
)
from env_diff.parser import entries_to_mapping, parse_env_text, read_env_file


def _mapping(env_text):
    return entries_to_mapping(parse_env_text(env_text))


def test_build_lines_use_template_placeholders_in_given_order():
    template = _mapping("PORT=8000\nDATABASE_URL=\nREGION=us-east-1 # default\n")
    lines = build_missing_key_lines(["REGION", "DATABASE_URL", "PORT"], template)
    assert lines == ["REGION=us-east-1", "DATABASE_URL=", "PORT=8000"]


@pytest.mark.parametrize(
    "template_line",
    ['GREETING="hello world"', 'TAG="a#b"', "SAY='he said \"hi\"'", 'PADDED="  x  "'],
)
def test_placeholders_that_need_quotes_round_trip(template_line):
    template = _mapping(template_line)
    (key,) = template
    (line,) = build_missing_key_lines([key], template)
    assert parse_env_text(line)[0].value == template[key].value


def test_unknown_key_gets_empty_value():
    assert build_missing_key_lines(["NEW"], {}) == ["NEW="]


def test_append_creates_missing_file(tmp_path):
    env_path = tmp_path / ".env"
    assert append_missing_keys(env_path, ["A=", "B=2"]) == 2
    assert env_path.read_text() == f"{FIX_BLOCK_HEADER}\nA=\nB=2\n"


def test_append_keeps_existing_lines_and_fixes_missing_newline(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("# mine\nSECRET=keep-me")
    append_missing_keys(env_path, ["A="])
    assert env_path.read_text() == f"# mine\nSECRET=keep-me\n\n{FIX_BLOCK_HEADER}\nA=\n"
    assert read_env_file(env_path)["SECRET"].value == "keep-me"


def test_append_nothing_leaves_file_untouched(tmp_path):
    env_path = tmp_path / ".env"
    assert append_missing_keys(env_path, []) == 0
    assert not env_path.exists()


def test_render_fix_block_matches_what_append_writes(tmp_path):
    env_path = tmp_path / ".env"
    assignment_lines = ["A=", "PORT=8000"]
    append_missing_keys(env_path, assignment_lines)
    assert env_path.read_text() == render_fix_block(assignment_lines)


def test_render_fix_block_is_empty_without_lines():
    assert render_fix_block([]) == ""
