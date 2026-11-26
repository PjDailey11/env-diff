# env-diff

Compare a `.env.example` template against your real `.env` and see which keys
are missing, which are extra, and which are present but empty.

```text
$ env-diff --check
Comparing .env against .env.example
Missing (1):
  - DATABASE_URL
Empty (1):
  ? SECRET_KEY
Extra (1):
  + DEBUG
$ echo $?
1
```

## Table of contents

- [Overview and motivation](#overview-and-motivation)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Options](#options)
- [Exit codes](#exit-codes)
- [Supported .env syntax](#supported-env-syntax)
- [Project structure](#project-structure)
- [How it works](#how-it-works)
- [Testing](#testing)
- [Changelog and versioning](#changelog-and-versioning)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

## Overview and motivation

Most projects commit a `.env.example` that lists every environment variable
the app needs, while the real `.env` (with secrets) stays out of git. The two
drift apart constantly: someone adds `STRIPE_WEBHOOK_SECRET` to the example,
your local `.env` never gets it, and the app crashes at startup with a vague
`KeyError` twenty minutes later.

`env-diff` answers one question quickly: *is my `.env` complete compared to the
template?* It is a single dependency-free Python package, so it runs in a
fresh checkout, a git hook, or a CI job before anything else is installed.
It never prints secret values, only key names, so its output is safe to paste
into an issue or a CI log.

## Features

- Reports **missing** keys (in the example, not in `.env`), in template order.
- Reports **empty** keys (present in `.env` but set to nothing, e.g. `SECRET_KEY=`).
- Reports **extra** keys (in `.env`, not in the example) so stale settings get noticed.
- `--check` mode exits with status `1` when keys are missing or empty, for CI
  and pre-commit hooks. Extra keys never fail the check, because local
  overrides like `DEBUG=1` are normal.
- `--strict` makes extra keys fail `--check` too, for production and CI files
  where an undocumented key means the template is stale.
- Understands the common dotenv syntax: comments, `export` prefixes, single
  and double quotes, inline `# comments`, values containing `=`, and
  double-quoted values that span several lines (PEM keys, certificates).
- Clear errors with line numbers for malformed lines.
- Warns on stderr when a key is assigned more than once in either file (the
  last value silently wins, which can hide a real secret behind `KEY=`).
- `# env-diff: optional` inline markers in the template: such keys may be
  missing or empty without failing `--check` (even with `--strict`) and are
  listed in their own "Optional, not set" section.
- `--ignore KEY` (repeatable) for optional keys that may be missing or empty.
- `--ignore-file PATH` (or an automatic `./.env-diff-ignore`) to commit the
  list of optional keys once and share it between hooks, CI, and teammates.
- `--fix` appends missing keys to `.env` (creating it if needed) using the
  template's placeholder values; existing lines are never modified.
- `--fix --dry-run` prints exactly the block `--fix` would append, without
  writing or creating anything, so you can review it first.
- `--quiet` / `-q` prints nothing (no report, no warnings) for hooks and CI
  steps that only need the exit code; file and parse errors still show.
- `--no-warnings` hides just the duplicate-key warnings and keeps the report,
  for files with intentional duplicates.
- `--format json` for scripts, CI annotations, and editor integrations.
- Never prints values, only key names (in both text and JSON output).
- Zero runtime dependencies; Python 3.9+.

## Installation

From a clone (the package is not on PyPI yet):

```bash
git clone https://github.com/PjDailey11/env-diff.git
cd env-diff
python3 -m pip install .
```

For development, install in editable mode inside a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e . pytest
```

You can also run it without installing the console script:

```bash
PYTHONPATH=src python3 -m env_diff .env.example .env
```

## Usage

```text
env-diff [EXAMPLE_PATH] [ENV_PATH] [--check] [--strict] [--ignore KEY ...] [--ignore-file PATH] [--format {text,json}] [--version]
```

Both paths are optional. With no arguments, `env-diff` compares `./.env`
against `./.env.example`.

### Example: a typical drifted project

`.env.example`:

```dotenv
DATABASE_URL=postgres://localhost/app
SECRET_KEY=changeme
PORT=8000
SENTRY_DSN=
```

`.env`:

```dotenv
SECRET_KEY=
PORT=9000
SENTRY_DSN=https://example.ingest.sentry.io/1
DEBUG=1
```

```text
$ env-diff
Comparing .env against .env.example
Missing (1):
  - DATABASE_URL
Empty (1):
  ? SECRET_KEY
Extra (1):
  + DEBUG
```

Note that `SENTRY_DSN` is empty in the *example* but filled in `.env`, so it is
fine: template values are placeholders and are ignored.

### Example: everything matches

```text
$ env-diff config/.env.example config/.env.production
Comparing config/.env.production against config/.env.example
All keys match.
```

### Example: failing CI when keys are missing

```bash
env-diff .env.example .env.ci --check || {
  echo "Your .env.ci is missing required keys"; exit 1;
}
```

### Example: strict check for production files

Extra keys pass `--check` by default. Add `--strict` when the template must
list every key, for example a production env file reviewed in CI:

```text
$ env-diff .env.example .env.production --check --strict
Comparing .env.production against .env.example
Extra (1):
  + LEGACY_API_URL
$ echo $?
1
```

### Example: allowing optional keys

`SENTRY_DSN` is optional on laptops, so skip it (repeat `--ignore` for more):

```text
$ env-diff --check --ignore SENTRY_DSN --ignore DEBUG
```

Ignored keys disappear from every section (missing, empty, and extra) and
never affect the exit code.

### Example: filling in a fresh `.env` with `--fix`

```text
$ cat .env
SECRET_KEY=dev-secret
$ env-diff --fix --check
env-diff: added 2 missing key(s) to .env: DATABASE_URL, PORT
Comparing .env against .env.example
Empty (1):
  ? DATABASE_URL
$ echo $?
1
$ cat .env
SECRET_KEY=dev-secret

# Added by env-diff --fix: fill in these values
DATABASE_URL=
PORT=8000
```

`PORT` picked up the template's `8000`, so it is done; `DATABASE_URL` had an
empty placeholder, so `--check` keeps failing until you fill it in. Optional
(`# env-diff: optional`) and ignored keys are never added.

### Example: previewing `--fix` with `--dry-run`

```text
$ cat .env
SECRET_KEY=dev-secret
$ env-diff --fix --dry-run --check
env-diff: --dry-run: would append 2 key(s) to .env:
# Added by env-diff --fix: fill in these values
DATABASE_URL=
PORT=8000

Comparing .env against .env.example
Missing (2):
  - DATABASE_URL
  - PORT
$ echo $?
1
$ cat .env
SECRET_KEY=dev-secret
```

The preview is the same text a real `--fix` run would write (both use
`fixer.render_fix_block`). Because nothing was written, the report and the
exit code still describe the file as it is. With `--format json` the preview
goes to stderr so stdout stays valid JSON; `--quiet` hides it. `--dry-run`
without `--fix` is a usage error (exit `2`).

### Example: marking optional keys in the template

Annotate the template itself so every teammate and CI job agrees on which
keys are optional, without any extra flags:

```bash
# .env.example
DATABASE_URL=
SENTRY_DSN=        # env-diff: optional
REGION=us-east-1   # env-diff: optional (defaults to us-east-1)
```

```text
$ env-diff --check
Comparing .env against .env.example
Optional, not set (2):
  ~ SENTRY_DSN
  ~ REGION
All keys match.
$ echo $?
0
```

The marker is case-insensitive and must be in the inline comment (after a
space and `#`). A marker inside a quoted value does not count.

### Example: sharing optional keys in `.env-diff-ignore`

Commit a `.env-diff-ignore` next to `.env.example` (one key per line, `#`
comments allowed) and every run from that directory picks it up:

```text
$ cat .env-diff-ignore
# Only configured in production
SENTRY_DSN
DEBUG   # local override
$ env-diff --check
Comparing .env against .env.example
Missing (1):
  - DATABASE_URL
Empty (1):
  ? SECRET_KEY
```

Use `--ignore-file path/to/file` to read a different file; keys from the file
and from `--ignore` flags are combined.

### Example: JSON output for scripts

```text
$ env-diff --format json
{
  "example_path": ".env.example",
  "env_path": ".env",
  "missing": [
    "DATABASE_URL"
  ],
  "empty": [
    "SECRET_KEY"
  ],
  "extra": [
    "DEBUG"
  ],
  "ok": false
}
```

`ok` is `true` exactly when `--check` would pass. Pipe it into `jq`:

```bash
env-diff --format json | jq -r '.missing[]'
```

### Example: duplicate key warning

If `.env` sets `SECRET_KEY` on line 2 and again (empty) on line 7, the report
shows it as empty and stderr explains why:

```text
$ env-diff
env-diff: warning: .env: SECRET_KEY is set 2 times (lines 2, 7); the last value wins
Comparing .env against .env.example
Empty (1):
  ? SECRET_KEY
```

Warnings never change the exit code and never go to stdout, so JSON output
stays parseable. If the duplicates are intentional, `env-diff --no-warnings`
prints the same report without the warning line.

### Example: a git pre-commit hook

```bash
#!/bin/sh
# .git/hooks/pre-commit
exec env-diff --check
```

### Example: exit code only

```text
$ env-diff --check --quiet
$ echo $?
1
```

Nothing is printed on stdout or stderr unless a file is missing or malformed
(exit `2`), so a silent hook still tells you when its setup is broken.

## Options

| Option | Default | Description |
| --- | --- | --- |
| `EXAMPLE_PATH` | `.env.example` | Template listing the keys that should exist. Its values are ignored. |
| `ENV_PATH` | `.env` | The real env file to check. |
| `--check` | off | Exit with status `1` if any key is missing or empty. |
| `--strict` | off | With `--check`, extra keys also fail. Also makes JSON `ok` false when extra keys exist. |
| `--fix` | off | Append missing keys to `ENV_PATH` with the template's placeholder values (creates the file if needed), then report on the updated file. Never edits existing lines. |
| `--dry-run` | off | With `--fix`, print the block that would be appended (stdout, or stderr with `--format json`) and write nothing. Without `--fix`, exit `2`. |
| `--ignore KEY` | none | Skip `KEY` everywhere, including `--check`. Repeat for several keys. |
| `--ignore-file PATH` | `./.env-diff-ignore` if present | Read keys to ignore from a file, one per line, `#` comments allowed. Combined with `--ignore`. A missing explicit file exits `2`. |
| `-q`, `--quiet` | off | Print no report and no duplicate-key warnings; only the exit code. Errors (exit `2`) are still printed. |
| `--no-warnings` | off | Hide only the duplicate-key warnings on stderr; the report and exit code are unchanged. Errors (exit `2`) are still printed. |
| `--format {text,json}` | `text` | Report format. JSON contains `missing`, `empty`, `extra`, `optional`, `ok`, and both paths. |
| `--version` | | Print the version and exit. |

More detail: [docs/options.md](docs/options.md).

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Comparison ran. With `--check`, no keys are missing or empty. |
| `1` | `--check` was given and at least one key is missing or empty (or extra, with `--strict`). |
| `2` | A file (including an explicit `--ignore-file`) was not found, an env file contains a malformed line, `--fix` could not write the env file, or `--dry-run` was given without `--fix`. |

## Supported .env syntax

| Line | Parsed key | Parsed value |
| --- | --- | --- |
| `PORT=8080` | `PORT` | `8080` |
| `export PORT=8080` | `PORT` | `8080` |
| `PORT=8080 # default` | `PORT` | `8080` |
| `COLOR=#fff` | `COLOR` | `#fff` (no space before `#`, so not a comment) |
| `PASSWORD="abc#123"` | `PASSWORD` | `abc#123` (quotes protect `#`) |
| `GREETING='hi there'` | `GREETING` | `hi there` |
| `URL=a=b=c` | `URL` | `a=b=c` (split on the first `=` only) |
| `EMPTY=` / `EMPTY=""` | `EMPTY` | empty string |
| `KEY= # note` | `KEY` | empty string (space then `#` starts a comment) |
| `KEY= # env-diff: optional` | `KEY` | empty string, and the key is marked optional |
| `# comment` / blank line | skipped | |
| `server.port=80` | `server.port` | `80` (dots and dashes allowed in keys) |
| `KEY="line one` + newline + `line two"` | `KEY` | `line one\nline two` (only double quotes may span lines) |

If a key appears twice, the last value wins (the same as a shell reading the
file top to bottom), and env-diff prints a warning naming every line.

A double-quoted value may continue over several lines until the next `"`;
the entry keeps the line number where it starts, so warnings and errors point
at the key. This is how PEM keys and certificates are usually stored:

```dotenv
TLS_KEY="-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASC...
-----END PRIVATE KEY-----"
NEXT_KEY=value
```

Single-quoted values stay on one line on purpose, so a stray apostrophe
(`NAME='O`) cannot swallow the rest of the file. A double quote that is never
closed consumes the remaining lines (the same lenient rule as an unterminated
quote on one line). When `--fix` copies a multi-line placeholder from the
template, it writes it double-quoted so the result parses back to the same
value.

Not supported on purpose: `${VAR}`
expansion, and command substitution. env-diff only needs key names and
emptiness, and it should never execute anything from your env file.

See [docs/how-it-works.md](docs/how-it-works.md) for the parsing rules.

## Project structure

```text
env-diff/
├── CHANGELOG.md            # user-visible changes per release, plus Unreleased
├── LICENSE
├── README.md
├── pyproject.toml          # package metadata and the env-diff console script
├── docs/
│   ├── how-it-works.md     # parser and comparison design notes
│   └── options.md          # every CLI option and exit code in detail
├── src/env_diff/
│   ├── __init__.py         # __version__ (must match pyproject.toml)
│   ├── __main__.py         # python -m env_diff
│   ├── cli.py              # argument parsing, report formatting, exit codes
│   ├── compare.py          # EnvComparison and compare_env_mappings
│   ├── fixer.py            # --fix: build and append missing assignments
│   ├── ignore_file.py      # .env-diff-ignore / --ignore-file loading
│   └── parser.py           # dotenv parsing (EnvEntry, EnvParseError)
└── tests/
    ├── test_cli.py
    ├── test_compare.py
    ├── test_fixer.py
    ├── test_ignore_file.py
    ├── test_parser.py
    └── test_version.py     # __version__, pyproject, and CHANGELOG agree
```

## How it works

1. **Parse** both files with `parser.parse_env_text`, which walks the file line
   by line, skips comments and blanks, strips `export`, splits on the first
   `=`, validates the key, and unquotes the value. Each assignment becomes an
   `EnvEntry(key, value, line_number)`.
2. **Warn** about keys assigned more than once (`parser.find_duplicate_keys`,
   printed to stderr by `cli.format_duplicate_warnings`), then **collapse**
   entries into a `key -> entry` dict (`entries_to_mapping`); later duplicates
   overwrite earlier ones but keep the first key's position.
3. **Compare** the two mappings (`compare.compare_env_mappings`): template keys
   not in `.env` are *missing*, template keys whose `.env` value is empty are
   *empty*, and `.env` keys not in the template are *extra*. Template keys
   marked `# env-diff: optional` (`parser.find_optional_keys`) that are
   missing or empty go to a separate *optional* bucket instead. Keys are
   case-sensitive, matching how Linux and macOS treat environment variables.
4. **Filter** out ignored keys with `compare.without_ignored_keys`. The list
   is `--ignore` flags plus `--ignore-file` (or `./.env-diff-ignore`), merged
   by `cli.collect_ignored_keys` using `ignore_file.read_ignore_file`.
5. **Fix** (only with `--fix`): `fixer.build_missing_key_lines` turns each
   missing key into `KEY=placeholder` (re-quoting values that need it), and
   `fixer.append_missing_keys` appends them under a labelled header. The env
   file is then re-read and compared again so the report shows the new state.
   With `--dry-run`, `fixer.render_fix_block` builds the same block and it is
   printed instead of written, and the report covers the unchanged file.
6. **Report** with `cli.format_text_report` (or `cli.format_json_report` for
   `--format json`) and choose the exit code with
   `EnvComparison.fails_check(strict=...)`.

## Testing

```bash
python3 -m venv /tmp/env-diff-venv
/tmp/env-diff-venv/bin/pip install -e . pytest
/tmp/env-diff-venv/bin/pytest -q
```

The suite (109 tests, under a second) is plain pytest with no fixtures beyond
`tmp_path` and `capsys`, and it never touches a real `.env`:

| Module | What it covers |
| --- | --- |
| `test_parser.py` | Quoting, inline comments, `export`, duplicates and their line numbers, BOM, optional markers, multi-line double-quoted values, malformed lines. |
| `test_compare.py` | Missing/empty/extra buckets, order preservation, case sensitivity, ignored and optional keys, `--strict` semantics. |
| `test_fixer.py` | Placeholder quoting round trips (including multi-line values), creating missing files, files without a final newline, and that the `--dry-run` preview matches what is written. |
| `test_ignore_file.py` | One key per line, comments and blank lines, trailing comments and duplicates, empty files, a UTF-8 BOM, and a missing file raising. |
| `test_cli.py` | `main()` end to end with temporary files: text and JSON reports, exit codes, `--check`, `--strict`, `--fix`, `--dry-run`, `--quiet`, `--no-warnings`, and usage errors. |
| `test_version.py` | `__version__` equals the `pyproject.toml` version, the CHANGELOG has a dated heading for it below **Unreleased**, and `--version` prints it. |

Run a single module or test while iterating, for example
`pytest -q tests/test_parser.py -k multiline`.

## Changelog and versioning

User-visible changes are listed in [CHANGELOG.md](CHANGELOG.md) in the
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format. The current
release is **0.2.0** (2026-11-25), which added `--strict`, `--ignore-file`,
duplicate-key warnings, `--quiet`, `--no-warnings`, optional-key markers,
`--fix`, `--dry-run`, and multi-line values on top of 0.1.0.

- Every pull request that changes behavior adds a line under **Unreleased**.
- A release renames that heading to `## X.Y.Z - YYYY-MM-DD` and bumps both
  `pyproject.toml` and `src/env_diff/__init__.py`; `tests/test_version.py`
  fails if any of the three disagree.
- While the version is `0.x`, new flags arrive in minor releases, but existing
  flags, exit codes, and JSON field names are treated as stable.

## Roadmap

- Comparing several env files at once (for example `.env` and `.env.local`).

## Contributing

Issues and pull requests are welcome. Keep changes small and focused, add a
test for every behavior change, and update this README, `docs/`, and the
**Unreleased** section of `CHANGELOG.md` in the same pull request so the
documentation never drifts from the code. Run `pytest -q` before opening a PR.

## License

MIT. See [LICENSE](LICENSE).
