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
- Understands the common dotenv syntax: comments, `export` prefixes, single
  and double quotes, inline `# comments`, values containing `=`.
- Clear errors with line numbers for malformed lines.
- `--ignore KEY` (repeatable) for optional keys that may be missing or empty.
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
env-diff [EXAMPLE_PATH] [ENV_PATH] [--check] [--ignore KEY ...] [--format {text,json}] [--version]
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

### Example: allowing optional keys

`SENTRY_DSN` is optional on laptops, so skip it (repeat `--ignore` for more):

```text
$ env-diff --check --ignore SENTRY_DSN --ignore DEBUG
```

Ignored keys disappear from every section (missing, empty, and extra) and
never affect the exit code.

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

### Example: a git pre-commit hook

```bash
#!/bin/sh
# .git/hooks/pre-commit
exec env-diff --check
```

## Options

| Option | Default | Description |
| --- | --- | --- |
| `EXAMPLE_PATH` | `.env.example` | Template listing the keys that should exist. Its values are ignored. |
| `ENV_PATH` | `.env` | The real env file to check. |
| `--check` | off | Exit with status `1` if any key is missing or empty. |
| `--ignore KEY` | none | Skip `KEY` everywhere, including `--check`. Repeat for several keys. |
| `--format {text,json}` | `text` | Report format. JSON contains `missing`, `empty`, `extra`, `ok`, and both paths. |
| `--version` | | Print the version and exit. |

More detail: [docs/options.md](docs/options.md).

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Comparison ran. With `--check`, no keys are missing or empty. |
| `1` | `--check` was given and at least one key is missing or empty. |
| `2` | A file was not found or contains a malformed line. |

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
| `# comment` / blank line | skipped | |
| `server.port=80` | `server.port` | `80` (dots and dashes allowed in keys) |

If a key appears twice, the last value wins (the same as a shell reading the
file top to bottom). Not supported on purpose: multi-line values, `${VAR}`
expansion, and command substitution. env-diff only needs key names and
emptiness, and it should never execute anything from your env file.

See [docs/how-it-works.md](docs/how-it-works.md) for the parsing rules.

## Project structure

```text
env-diff/
├── LICENSE
├── README.md
├── pyproject.toml          # package metadata and the env-diff console script
├── docs/
│   ├── how-it-works.md     # parser and comparison design notes
│   └── options.md          # every CLI option and exit code in detail
├── src/env_diff/
│   ├── __init__.py         # __version__
│   ├── __main__.py         # python -m env_diff
│   ├── cli.py              # argument parsing, report formatting, exit codes
│   ├── compare.py          # EnvComparison and compare_env_mappings
│   └── parser.py           # dotenv parsing (EnvEntry, EnvParseError)
└── tests/
    ├── test_cli.py
    ├── test_compare.py
    └── test_parser.py
```

## How it works

1. **Parse** both files with `parser.parse_env_text`, which walks the file line
   by line, skips comments and blanks, strips `export`, splits on the first
   `=`, validates the key, and unquotes the value. Each assignment becomes an
   `EnvEntry(key, value, line_number)`.
2. **Collapse** entries into a `key -> entry` dict (`entries_to_mapping`);
   later duplicates overwrite earlier ones but keep the first key's position.
3. **Compare** the two mappings (`compare.compare_env_mappings`): template keys
   not in `.env` are *missing*, template keys whose `.env` value is empty are
   *empty*, and `.env` keys not in the template are *extra*. Keys are
   case-sensitive, matching how Linux and macOS treat environment variables.
4. **Filter** out any `--ignore` keys with `compare.without_ignored_keys`.
5. **Report** with `cli.format_text_report` (or `cli.format_json_report` for
   `--format json`) and choose the exit code.

## Testing

```bash
python3 -m venv /tmp/env-diff-venv
/tmp/env-diff-venv/bin/pip install -e . pytest
/tmp/env-diff-venv/bin/pytest -q
```

The suite covers the parser (quoting, comments, `export`, duplicates, BOM,
errors), the comparison rules, and the CLI end to end through `main()` with
temporary files.

## Roadmap

- Read ignored keys from a `.env-diff-ignore` file or `# env-diff: optional` comments in the template.
- Optional `--strict` mode where extra keys also fail `--check`.
- `--fix` to append missing keys (with the template's placeholder) to `.env`.
- Multi-line quoted values.

## Contributing

Issues and pull requests are welcome. Keep changes small and focused, add a
test for every behavior change, and update this README and `docs/` in the same
pull request so the documentation never drifts from the code. Run
`pytest -q` before opening a PR.

## License

MIT. See [LICENSE](LICENSE).
