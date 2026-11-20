"""Tests for env_diff.parser."""

import pytest

from env_diff.parser import (
    EnvParseError,
    entries_to_mapping,
    find_duplicate_keys,
    parse_env_text,
    read_env_entries,
    read_env_file,
)


def test_parses_simple_assignments_in_file_order():
    entries = parse_env_text("A=1\nB=two\n")
    assert [(entry.key, entry.value, entry.line_number) for entry in entries] == [
        ("A", "1", 1),
        ("B", "two", 2),
    ]


def test_skips_blank_lines_and_full_line_comments():
    entries = parse_env_text("\n# comment\n   \nKEY=value\n")
    assert [entry.key for entry in entries] == ["KEY"]
    assert entries[0].line_number == 4


def test_strips_export_prefix():
    entries = parse_env_text("export DATABASE_URL=postgres://localhost/db")
    assert entries[0].key == "DATABASE_URL"
    assert entries[0].value == "postgres://localhost/db"


@pytest.mark.parametrize(
    "line, expected_value",
    [
        ('PASSWORD="abc#123"', "abc#123"),
        ("GREETING='hello world'", "hello world"),
        ("PORT=8080 # default port", "8080"),
        ("COLOR=#fff", "#fff"),
        ("EMPTY=", ""),
        ('EMPTY_QUOTED=""', ""),
        ('UNTERMINATED="oops', "oops"),
        ("WITH_EQUALS=a=b=c", "a=b=c"),
    ],
)
def test_value_quoting_and_inline_comments(line, expected_value):
    assert parse_env_text(line)[0].value == expected_value


def test_accepts_dotted_and_dashed_keys():
    entries = parse_env_text("server.port=80\nmy-key=1")
    assert [entry.key for entry in entries] == ["server.port", "my-key"]


def test_line_without_equals_raises_with_line_number():
    with pytest.raises(EnvParseError) as error_info:
        parse_env_text("GOOD=1\nNOT_AN_ASSIGNMENT\n")
    assert error_info.value.line_number == 2
    assert "expected KEY=value" in str(error_info.value)


def test_invalid_key_name_raises():
    with pytest.raises(EnvParseError, match="invalid key name"):
        parse_env_text("1BAD=value")


def test_duplicate_keys_last_value_wins_but_first_position_kept():
    mapping = entries_to_mapping(parse_env_text("A=1\nB=2\nA=3\n"))
    assert list(mapping) == ["A", "B"]
    assert mapping["A"].value == "3"
    assert mapping["A"].line_number == 3


def test_read_env_file_drops_utf8_bom(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_bytes("\ufeffFIRST=1\n".encode("utf-8"))
    assert list(read_env_file(env_path)) == ["FIRST"]


def test_read_env_file_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_env_file(tmp_path / "nope.env")


def test_find_duplicate_keys_reports_every_line():
    entries = parse_env_text("A=1\nB=2\nA=3\n# note\nB=\nA=5\nC=1\n")
    assert find_duplicate_keys(entries) == {"A": [1, 3, 6], "B": [2, 5]}


def test_find_duplicate_keys_empty_for_clean_file():
    assert find_duplicate_keys(parse_env_text("A=1\nB=2\n")) == {}


def test_export_prefix_does_not_hide_a_duplicate():
    entries = parse_env_text("export TOKEN=abc\nTOKEN=\n")
    assert find_duplicate_keys(entries) == {"TOKEN": [1, 2]}


def test_read_env_entries_keeps_duplicates(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("KEY=first\nKEY=second\n")
    assert [entry.value for entry in read_env_entries(env_path)] == ["first", "second"]
