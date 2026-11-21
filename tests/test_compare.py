"""Tests for env_diff.compare."""

from env_diff.compare import compare_env_mappings, without_ignored_keys
from env_diff.parser import entries_to_mapping, parse_env_text


def _mapping(env_text):
    return entries_to_mapping(parse_env_text(env_text))


def test_identical_files_have_no_problems():
    comparison = compare_env_mappings(_mapping("A=x\nB=y"), _mapping("A=1\nB=2"))
    assert comparison.missing_keys == []
    assert comparison.extra_keys == []
    assert comparison.empty_keys == []
    assert not comparison.has_problems


def test_missing_keys_follow_example_order():
    comparison = compare_env_mappings(_mapping("C=\nA=\nB="), _mapping("A=1"))
    assert comparison.missing_keys == ["C", "B"]
    assert comparison.has_problems


def test_extra_keys_reported_but_not_a_problem():
    comparison = compare_env_mappings(_mapping("A="), _mapping("A=1\nDEBUG=1"))
    assert comparison.extra_keys == ["DEBUG"]
    assert not comparison.has_problems


def test_empty_actual_value_is_flagged():
    comparison = compare_env_mappings(_mapping("SECRET=changeme"), _mapping('SECRET=""'))
    assert comparison.empty_keys == ["SECRET"]
    assert comparison.missing_keys == []
    assert comparison.has_problems


def test_example_values_are_ignored():
    # An empty placeholder in the template must not mark the real key empty.
    comparison = compare_env_mappings(_mapping("TOKEN="), _mapping("TOKEN=abc"))
    assert not comparison.has_problems


def test_comparison_is_case_sensitive():
    comparison = compare_env_mappings(_mapping("API_KEY="), _mapping("api_key=1"))
    assert comparison.missing_keys == ["API_KEY"]
    assert comparison.extra_keys == ["api_key"]


def test_without_ignored_keys_drops_from_every_bucket():
    original = compare_env_mappings(_mapping("A=\nB=\nC="), _mapping("B=\nC=1\nX=1"))
    filtered = without_ignored_keys(original, ["A", "B", "X", "NOT_PRESENT"])
    assert (filtered.missing_keys, filtered.empty_keys, filtered.extra_keys) == ([], [], [])
    assert not filtered.has_problems
    # The input comparison must be left untouched.
    assert original.missing_keys == ["A"]


def test_fails_check_ignores_extra_keys_by_default():
    comparison = compare_env_mappings(_mapping("A="), _mapping("A=1\nDEBUG=1"))
    assert not comparison.fails_check()


def test_fails_check_strict_treats_extra_keys_as_failures():
    comparison = compare_env_mappings(_mapping("A="), _mapping("A=1\nDEBUG=1"))
    assert comparison.fails_check(strict=True)
    # Strict mode with no extra keys behaves exactly like the default.
    clean_comparison = compare_env_mappings(_mapping("A="), _mapping("A=1"))
    assert not clean_comparison.fails_check(strict=True)


def test_fails_check_missing_keys_fail_in_both_modes():
    comparison = compare_env_mappings(_mapping("A=\nB="), _mapping("A=1"))
    assert comparison.fails_check()
    assert comparison.fails_check(strict=True)
