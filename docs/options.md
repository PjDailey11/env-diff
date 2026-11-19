# env-diff options

```text
env-diff [EXAMPLE_PATH] [ENV_PATH] [--check] [--version]
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
`LOG_LEVEL=debug`) are normal and should not break CI. A future `--strict`
flag may make them fail too (see the README roadmap).

Without `--check`, env-diff always exits `0` after a successful comparison,
so it is safe to run as an informational step.

### `--version`

Prints `env-diff <version>` and exits `0`.

## Exit codes

| Code | When |
| --- | --- |
| `0` | Comparison ran (and, with `--check`, nothing is missing or empty). |
| `1` | `--check` and at least one key is missing or empty. |
| `2` | A file does not exist, or a line could not be parsed. The error on stderr names the line number. |

Exit code `2` is distinct from `1` so CI scripts can tell "your config is
incomplete" apart from "env-diff could not read the files at all". argparse
also uses `2` for invalid command-line usage.

## Output format

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
