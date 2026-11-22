"""End-to-end tests for env_diff.cli.main."""

import json

from env_diff.cli import EXIT_OK, EXIT_PROBLEMS_FOUND, EXIT_USAGE_ERROR, main


def _write_pair(tmp_path, example_text, env_text):
    example_path = tmp_path / ".env.example"
    env_path = tmp_path / ".env"
    example_path.write_text(example_text)
    env_path.write_text(env_text)
    return str(example_path), str(env_path)


def test_clean_pair_prints_all_keys_match(tmp_path, capsys):
    example_path, env_path = _write_pair(tmp_path, "A=\nB=\n", "A=1\nB=2\n")
    assert main([example_path, env_path, "--check"]) == EXIT_OK
    assert "All keys match." in capsys.readouterr().out


def test_report_lists_missing_empty_and_extra_sections(tmp_path, capsys):
    example_path, env_path = _write_pair(
        tmp_path, "DATABASE_URL=\nSECRET_KEY=\nPORT=8000\n", "SECRET_KEY=\nPORT=9000\nDEBUG=1\n"
    )
    assert main([example_path, env_path]) == EXIT_OK
    output = capsys.readouterr().out
    assert "Missing (1):\n  - DATABASE_URL" in output
    assert "Empty (1):\n  ? SECRET_KEY" in output
    assert "Extra (1):\n  + DEBUG" in output


def test_check_returns_one_when_keys_missing(tmp_path):
    example_path, env_path = _write_pair(tmp_path, "A=\nB=\n", "A=1\n")
    assert main([example_path, env_path, "--check"]) == EXIT_PROBLEMS_FOUND


def test_check_ignores_extra_keys(tmp_path):
    example_path, env_path = _write_pair(tmp_path, "A=\n", "A=1\nLOCAL_ONLY=1\n")
    assert main([example_path, env_path, "--check"]) == EXIT_OK


def test_missing_file_is_usage_error(tmp_path, capsys):
    assert main([str(tmp_path / "nope"), str(tmp_path / "nope2")]) == EXIT_USAGE_ERROR
    assert "file not found" in capsys.readouterr().err


def test_malformed_file_is_usage_error(tmp_path, capsys):
    example_path, env_path = _write_pair(tmp_path, "A=\n", "this is not valid\n")
    assert main([example_path, env_path]) == EXIT_USAGE_ERROR
    assert "line 1" in capsys.readouterr().err


def test_defaults_to_dotenv_files_in_current_directory(tmp_path, monkeypatch, capsys):
    _write_pair(tmp_path, "A=\n", "A=1\n")
    monkeypatch.chdir(tmp_path)
    assert main([]) == EXIT_OK
    assert "Comparing .env against .env.example" in capsys.readouterr().out


def test_json_format_lists_buckets_and_ok_flag(tmp_path, capsys):
    example_path, env_path = _write_pair(tmp_path, "A=\nB=\nC=\n", "B=\nC=3\nX=1\n")
    assert main([example_path, env_path, "--format", "json"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["missing"] == ["A"]
    assert payload["empty"] == ["B"]
    assert payload["extra"] == ["X"]
    assert payload["ok"] is False
    assert payload["env_path"] == env_path


def test_json_format_never_includes_values(tmp_path, capsys):
    example_path, env_path = _write_pair(tmp_path, "TOKEN=\n", "TOKEN=super-secret\n")
    main([example_path, env_path, "--format", "json"])
    assert "super-secret" not in capsys.readouterr().out


def test_json_format_keeps_check_exit_code(tmp_path):
    example_path, env_path = _write_pair(tmp_path, "A=\n", "")
    assert main([example_path, env_path, "--format", "json", "--check"]) == EXIT_PROBLEMS_FOUND


def test_ignore_flag_lets_check_pass_for_optional_keys(tmp_path, capsys):
    example_path, env_path = _write_pair(tmp_path, "A=\nSENTRY_DSN=\nB=\n", "A=1\nB=\n")
    assert main([example_path, env_path, "--check"]) == EXIT_PROBLEMS_FOUND
    capsys.readouterr()
    exit_code = main([example_path, env_path, "--check", "--ignore", "SENTRY_DSN", "--ignore", "B"])
    assert exit_code == EXIT_OK
    assert "All keys match." in capsys.readouterr().out


def test_strict_check_fails_on_extra_keys(tmp_path):
    example_path, env_path = _write_pair(tmp_path, "A=\n", "A=1\nSTALE=1\n")
    assert main([example_path, env_path, "--check"]) == EXIT_OK
    assert main([example_path, env_path, "--check", "--strict"]) == EXIT_PROBLEMS_FOUND


def test_strict_without_check_still_exits_zero(tmp_path):
    example_path, env_path = _write_pair(tmp_path, "A=\n", "A=1\nSTALE=1\n")
    assert main([example_path, env_path, "--strict"]) == EXIT_OK


def test_strict_json_ok_flag_matches_exit_code(tmp_path, capsys):
    example_path, env_path = _write_pair(tmp_path, "A=\n", "A=1\nSTALE=1\n")
    main([example_path, env_path, "--format", "json"])
    assert json.loads(capsys.readouterr().out)["ok"] is True
    main([example_path, env_path, "--format", "json", "--strict"])
    assert json.loads(capsys.readouterr().out)["ok"] is False


def test_strict_respects_ignored_extra_keys(tmp_path):
    example_path, env_path = _write_pair(tmp_path, "A=\n", "A=1\nDEBUG=1\n")
    exit_code = main([example_path, env_path, "--check", "--strict", "--ignore", "DEBUG"])
    assert exit_code == EXIT_OK


def test_ignore_file_flag_skips_listed_keys(tmp_path, capsys):
    example_path, env_path = _write_pair(tmp_path, "A=\nSENTRY_DSN=\nB=\n", "A=1\n")
    ignore_path = tmp_path / "optional-keys.txt"
    ignore_path.write_text("# optional\nSENTRY_DSN\n")
    # B is still missing, so check fails until it is ignored with a flag too.
    assert main([example_path, env_path, "--check", "--ignore-file", str(ignore_path)]) == EXIT_PROBLEMS_FOUND
    capsys.readouterr()
    exit_code = main(
        [example_path, env_path, "--check", "--ignore-file", str(ignore_path), "--ignore", "B"]
    )
    assert exit_code == EXIT_OK
    assert "All keys match." in capsys.readouterr().out


def test_default_ignore_file_is_used_when_present(tmp_path, monkeypatch):
    _write_pair(tmp_path, "A=\nSENTRY_DSN=\n", "A=1\n")
    monkeypatch.chdir(tmp_path)
    assert main(["--check"]) == EXIT_PROBLEMS_FOUND
    (tmp_path / ".env-diff-ignore").write_text("SENTRY_DSN\n")
    assert main(["--check"]) == EXIT_OK


def test_missing_explicit_ignore_file_is_usage_error(tmp_path, capsys):
    example_path, env_path = _write_pair(tmp_path, "A=\n", "A=1\n")
    missing_path = str(tmp_path / "nope-ignore")
    assert main([example_path, env_path, "--ignore-file", missing_path]) == EXIT_USAGE_ERROR
    assert "file not found" in capsys.readouterr().err


def test_duplicate_keys_warn_on_stderr_without_changing_exit_code(tmp_path, capsys):
    example_path, env_path = _write_pair(
        tmp_path, "SECRET_KEY=\n", "SECRET_KEY=real-value\nPORT=1\nSECRET_KEY=\n"
    )
    assert main([example_path, env_path, "--format", "json"]) == EXIT_OK
    captured = capsys.readouterr()
    assert f"{env_path}: SECRET_KEY is set 2 times (lines 1, 3)" in captured.err
    # stdout must stay valid JSON and must never leak the shadowed value.
    assert "real-value" not in captured.err + captured.out
    assert json.loads(captured.out)["empty"] == ["SECRET_KEY"]


def test_clean_files_print_no_warnings(tmp_path, capsys):
    example_path, env_path = _write_pair(tmp_path, "A=\n", "A=1\n")
    main([example_path, env_path])
    assert capsys.readouterr().err == ""


def test_quiet_prints_nothing_but_keeps_check_exit_code(tmp_path, capsys):
    example_path, env_path = _write_pair(tmp_path, "A=\nB=\n", "A=1\n")
    assert main([example_path, env_path, "--check", "--quiet"]) == EXIT_PROBLEMS_FOUND
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")


def test_quiet_short_flag_and_clean_pair_exit_zero(tmp_path, capsys):
    example_path, env_path = _write_pair(tmp_path, "A=\n", "A=1\n")
    assert main([example_path, env_path, "--check", "-q", "--format", "json"]) == EXIT_OK
    assert capsys.readouterr().out == ""


def test_quiet_silences_duplicate_key_warnings(tmp_path, capsys):
    example_path, env_path = _write_pair(tmp_path, "A=\n", "A=1\nA=2\n")
    assert main([example_path, env_path, "--quiet"]) == EXIT_OK
    assert capsys.readouterr().err == ""


def test_quiet_still_reports_usage_errors(tmp_path, capsys):
    missing_path = str(tmp_path / "missing.env")
    example_path, _ = _write_pair(tmp_path, "A=\n", "A=1\n")
    assert main([example_path, missing_path, "--quiet"]) == EXIT_USAGE_ERROR
    assert "file not found" in capsys.readouterr().err


def test_optional_marker_keeps_check_green_and_lists_key(tmp_path, capsys):
    example_path, env_path = _write_pair(
        tmp_path, "A=\nSENTRY_DSN=  # env-diff: optional\n", "A=1\n"
    )
    assert main([example_path, env_path, "--check", "--strict"]) == EXIT_OK
    output = capsys.readouterr().out
    assert "Optional, not set (1):\n  ~ SENTRY_DSN" in output
    assert "All keys match." in output


def test_optional_keys_appear_in_json(tmp_path, capsys):
    example_path, env_path = _write_pair(tmp_path, "A=\nB= # env-diff: optional\n", "")
    assert main([example_path, env_path, "--format", "json"]) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["missing"] == ["A"]
    assert payload["optional"] == ["B"]
    assert payload["ok"] is False


def test_fix_appends_missing_keys_and_reports_them_as_empty(tmp_path, capsys):
    example_path, env_path = _write_pair(tmp_path, "A=\nPORT=8000\nB=\n", "A=1\n")
    assert main([example_path, env_path, "--fix", "--check"]) == EXIT_PROBLEMS_FOUND
    captured = capsys.readouterr()
    assert "added 2 missing key(s)" in captured.err and "PORT, B" in captured.err
    # PORT got a real placeholder so it is now fine; B is empty and still fails.
    assert "Missing" not in captured.out
    assert "Empty (1):\n  ? B" in captured.out
    assert (tmp_path / ".env").read_text().startswith("A=1\n")


def test_fix_creates_missing_env_file(tmp_path, capsys):
    example_path = tmp_path / ".env.example"
    example_path.write_text("PORT=8000\n")
    env_path = tmp_path / ".env"
    assert main([str(example_path), str(env_path), "--fix", "--check"]) == EXIT_OK
    assert "PORT=8000" in env_path.read_text()


def test_fix_skips_optional_and_ignored_keys(tmp_path, capsys):
    example_path, env_path = _write_pair(
        tmp_path, "A=\nSENTRY_DSN= # env-diff: optional\nLOCAL=\n", "A=1\n"
    )
    assert main([example_path, env_path, "--fix", "--ignore", "LOCAL"]) == EXIT_OK
    assert (tmp_path / ".env").read_text() == "A=1\n"
    assert capsys.readouterr().err == ""


def test_fix_quiet_json_keeps_stdout_clean(tmp_path, capsys):
    example_path, env_path = _write_pair(tmp_path, "A=\nB=2\n", "A=1\n")
    assert main([example_path, env_path, "--fix", "--format", "json"]) == EXIT_OK
    captured = capsys.readouterr()
    assert json.loads(captured.out)["missing"] == []
    assert main([example_path, env_path, "--fix", "-q"]) == EXIT_OK
    assert capsys.readouterr().err == ""


def test_fix_dry_run_previews_block_and_leaves_file_untouched(tmp_path, capsys):
    example_path, env_path = _write_pair(tmp_path, "A=\nPORT=8000\n", "A=1\n")
    assert main([example_path, env_path, "--fix", "--dry-run", "--check"]) == EXIT_PROBLEMS_FOUND
    output = capsys.readouterr().out
    assert "would append 1 key(s)" in output
    assert "# Added by env-diff --fix" in output and "PORT=8000" in output
    # The report describes the unchanged file, so PORT is still missing.
    assert "Missing (1):\n  - PORT" in output
    assert (tmp_path / ".env").read_text() == "A=1\n"


def test_fix_dry_run_does_not_create_missing_env_file(tmp_path, capsys):
    example_path = tmp_path / ".env.example"
    example_path.write_text("A=\n")
    env_path = tmp_path / ".env"
    assert main([str(example_path), str(env_path), "--fix", "--dry-run"]) == EXIT_OK
    assert not env_path.exists()


def test_fix_dry_run_json_sends_preview_to_stderr(tmp_path, capsys):
    example_path, env_path = _write_pair(tmp_path, "A=\nB=\n", "A=1\n")
    main([example_path, env_path, "--fix", "--dry-run", "--format", "json"])
    captured = capsys.readouterr()
    assert json.loads(captured.out)["missing"] == ["B"]
    assert "would append 1 key(s)" in captured.err


def test_dry_run_without_fix_is_usage_error(tmp_path, capsys):
    example_path, env_path = _write_pair(tmp_path, "A=\n", "A=1\n")
    assert main([example_path, env_path, "--dry-run"]) == EXIT_USAGE_ERROR
    assert "--dry-run only makes sense together with --fix" in capsys.readouterr().err
