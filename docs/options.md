# env-diff options

```text
env-diff [EXAMPLE_PATH] [ENV_PATH] [--check] [--strict] [--ignore KEY ...] [--ignore-file PATH] [--format {text,json}] [--version]
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

### `--fix`

Appends every **missing** key to `ENV_PATH`, using the template's value as a
placeholder, then prints the report for the updated file.

- Only appends. Existing lines, comments, and order are never changed, so the
  worst case is an extra block you can delete.
- The block starts with `# Added by env-diff --fix: fill in these values`,
  separated from existing content by a blank line (a missing final newline is
  handled).
- `ENV_PATH` is created if it does not exist; without `--fix`, a missing env
  file is still exit `2`.
- Placeholders are re-quoted when needed (whitespace, `#`, leading quotes) so
  they parse back to exactly the template value.
- Optional (`# env-diff: optional`) and ignored keys are not added. Empty
  keys are left alone: they already exist and only need a value.
- A summary line naming the added keys (never values) goes to stderr unless
  `--quiet` is set. Keys added with an empty placeholder then show as
  *empty*, so `--fix --check` keeps failing until real values are filled in.
- A write failure (for example, a missing directory) exits `2`.

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

### `--ignore-file PATH` (default `./.env-diff-ignore` if it exists)

Reads keys to ignore from a file instead of (or in addition to) repeated
`--ignore` flags, so the list of optional keys can be committed once and
shared by git hooks, CI jobs, and teammates.

```text
# .env-diff-ignore
SENTRY_DSN          # only configured in production
DEBUG
```

- One key per line. Blank lines, full-line `#` comments, and trailing
  `# comments` are skipped; surrounding whitespace, `\r\n` line endings, and a
  UTF-8 BOM are tolerated.
- Keys from the file are combined with `--ignore` flags and behave exactly the
  same way (removed from every section and from `--check` / `--strict`).
- Without the flag, `./.env-diff-ignore` in the **current directory** is used
  when it exists; a missing default file is silently fine.
- An explicit `--ignore-file` that does not exist is a usage error (exit `2`),
  because a typo there would otherwise silently ignore nothing.

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
  "optional": ["SENTRY_DSN"],
  "ok": false
}
```

- Lists keep file order (missing/empty follow the template, extra follows
  `.env`), so output is stable and diffable between runs.
- `optional` lists template keys marked `# env-diff: optional` that are
  missing or empty; they never make `ok` false.
- `ok` is `true` exactly when `--check` would exit `0` (honoring `--strict`).
- Values are never included, so the JSON is safe to upload as a CI artifact.
- The format does not change exit codes; combine it with `--check` to both
  gate and capture details.
- Errors (exit `2`) are still plain text on stderr, and stdout stays empty.

### `-q`, `--quiet`

Suppresses all normal output: no text or JSON report on stdout and no
duplicate-key warnings on stderr. The exit code is unchanged, so
`env-diff --check -q` is the quietest possible gate for a git hook.

- Usage errors (missing file, malformed line, missing explicit
  `--ignore-file`) are still printed to stderr with exit `2`. Hiding them
  would make a misconfigured hook look like a passing one.
- `--format` is accepted alongside `--quiet` and simply has no visible
  effect, so scripts can add or drop `-q` without editing anything else.

### `--version`

Prints `env-diff <version>` and exits `0`.

## Exit codes

| Code | When |
| --- | --- |
| `0` | Comparison ran (and, with `--check`, nothing is missing or empty). |
| `1` | `--check` and at least one key is missing or empty (or extra, with `--strict`). |
| `2` | A file (including an explicit `--ignore-file`) does not exist, a line could not be parsed, or `--fix` could not write the env file. The error on stderr names the line number. |

Exit code `2` is distinct from `1` so CI scripts can tell "your config is
incomplete" apart from "env-diff could not read the files at all". argparse
also uses `2` for invalid command-line usage.

## Warnings

Keys assigned more than once in either file produce one line per key on
stderr, for example:

```text
env-diff: warning: .env: SECRET_KEY is set 2 times (lines 2, 7); the last value wins
```

Warnings are informational: they do not affect the exit code (with or without
`--check` / `--strict`) and never appear on stdout, so `--format json` output
stays valid. `--quiet` suppresses them.

## Text output format

```text
Comparing <ENV_PATH> against <EXAMPLE_PATH>
Missing (N):
  - KEY
Empty (N):
  ? KEY
Extra (N):
  + KEY
Optional, not set (N):
  ~ KEY
```

Sections with no keys are omitted. `Optional, not set` lists template keys
marked `# env-diff: optional` that are missing or empty; they are
informational, so `All keys match.` can still follow them. When there is nothing to report, the second
line is `All keys match.` Values are never printed.
