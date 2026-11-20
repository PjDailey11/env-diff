# env-diff options

```text
env-diff [EXAMPLE_PATH] [ENV_PATH] [--check] [--strict] [--ignore KEY ...] [--format {text,json}] [--version]
```

## Positional arguments

### `EXAMPLE_PATH` (default `.env.example`)

The template that defines which keys *should* exist. Only key names matter;
values in the template are treated as placeholders and ignored, so
`SENTRY_DSN=` in the template does not mean your real value must be empty.

### `ENV_PATH` (default `.env`)

The real environment file being checked. Paths are resolved relative to the
current working directory. Both files are read as UTF-8; a leading byte-order
mark (common from Windows editors) is dropped automatically.

## Flags

### `--check`

Turns env-diff into a gate. The report is still printed, and then:

- exit `1` if any key is **missing** or **empty**;
- exit `0` otherwise, **even if there are extra keys**.

Extra keys are deliberately not a failure: local-only overrides (`DEBUG=1`,
`LOG_LEVEL=debug`) are normal and should not break CI. Use `--strict` (below)
when they should fail too.

Without `--check`, env-diff always exits `0` after a successful comparison,
so it is safe to run as an informational step.

### `--strict`

Makes `--check` treat **extra** keys as failures in addition to missing and
empty ones. Intended for production or CI env files, where a key the template
does not list usually means the template is out of date:

```bash
env-diff .env.example .env.production --check --strict
```

- Without `--check`, `--strict` never changes the exit code (it stays `0`), so
  informational runs cannot fail unexpectedly.
- With `--format json`, `ok` follows the same rule, so `ok` is `false` when
  extra keys exist in strict mode.
- `--ignore` is applied first, so an ignored extra key never fails strict mode.

### `--ignore KEY` (repeatable)

Drops `KEY` from the missing, empty, and extra sections before the report is
printed and before `--check` decides the exit code. Use it for optional
settings such as `SENTRY_DSN` or local-only overrides:

```bash
env-diff --check --ignore SENTRY_DSN --ignore DEBUG
```

- Matching is exact and case-sensitive, like the comparison itself.
- Ignoring a key that does not appear in either file is not an error, so one
  shared command line works across `.env`, `.env.ci`, and `.env.production`.
- Filtering is applied after comparison, so it behaves the same whichever
  bucket the key would have landed in. JSON output is filtered too.

### `--format {text,json}` (default `text`)

`text` prints the human-readable report described below. `json` prints a
single JSON object instead:

```json
{
  "example_path": ".env.example",
  "env_path": ".env",
  "missing": ["DATABASE_URL"],
  "empty": ["SECRET_KEY"],
  "extra": ["DEBUG"],
  "ok": false
}
```

- Lists keep file order (missing/empty follow the template, extra follows
  `.env`), so output is stable and diffable between runs.
- `ok` is `true` exactly when `--check` would exit `0` (honoring `--strict`).
- Values are never included, so the JSON is safe to upload as a CI artifact.
- The format does not change exit codes; combine it with `--check` to both
  gate and capture details.
- Errors (exit `2`) are still plain text on stderr, and stdout stays empty.

### `--version`

Prints `env-diff <version>` and exits `0`.

## Exit codes

| Code | When |
| --- | --- |
| `0` | Comparison ran (and, with `--check`, nothing is missing or empty). |
| `1` | `--check` and at least one key is missing or empty (or extra, with `--strict`). |
| `2` | A file does not exist, or a line could not be parsed. The error on stderr names the line number. |

Exit code `2` is distinct from `1` so CI scripts can tell "your config is
incomplete" apart from "env-diff could not read the files at all". argparse
also uses `2` for invalid command-line usage.

## Text output format

```text
Comparing <ENV_PATH> against <EXAMPLE_PATH>
Missing (N):
  - KEY
Empty (N):
  ? KEY
Extra (N):
  + KEY
```

Sections with no keys are omitted. When there is nothing to report, the second
line is `All keys match.` Values are never printed.
