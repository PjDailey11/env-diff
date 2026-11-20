# How env-diff works

env-diff is three small modules wired together by the CLI:

```text
parser.py  ->  compare.py  ->  cli.py
(text to entries)  (entries to EnvComparison)  (report + exit code)
```

## Parsing (`env_diff/parser.py`)

`parse_env_text` processes the file one line at a time:

1. Strip surrounding whitespace. Skip blank lines and lines starting with `#`.
2. Remove a leading `export ` so files that are also `source`-able by a shell
   parse the same way.
3. Split on the **first** `=` only, so values like `postgres://u:p@h/db?x=1`
   survive intact. A line with no `=` raises `EnvParseError` with its line
   number.
4. Validate the key against `[A-Za-z_][A-Za-z0-9_.-]*`. Dots and dashes are
   allowed because Spring-style and some Docker setups use them.
5. Clean the value:
   - If it starts with `'` or `"`, take everything up to the matching closing
     quote. `#` inside quotes is kept (`PASSWORD="abc#123"`).
   - If the quote is never closed, keep the rest of the line rather than
     erroring; multi-line values are out of scope.
   - Otherwise, cut at ` #` (space, hash) to drop an inline comment. A hash
     with no space before it (`COLOR=#fff`) is part of the value. This matches
     python-dotenv and docker compose.

Each assignment becomes a frozen `EnvEntry(key, value, line_number)`.

### Duplicates

`entries_to_mapping` builds a dict from the entries. A later assignment of the
same key replaces the earlier value (last one wins, like a shell), while the
key keeps its original position in the dict, so reports stay in file order.

### What the parser does not do

- No `${VAR}` interpolation and no command substitution. env-diff must never
  execute or resolve anything from a secrets file.
- No multi-line values.

## Comparing (`env_diff/compare.py`)

`compare_env_mappings(example, actual)` produces an `EnvComparison`:

| Bucket | Rule | Order |
| --- | --- | --- |
| `missing_keys` | key in example, not in actual | example file order |
| `empty_keys` | key in both, actual value is `""` | example file order |
| `extra_keys` | key in actual, not in example | actual file order |

Comparison is case-sensitive (`API_KEY` and `api_key` are different variables
on Linux and macOS). `has_problems` is true for missing or empty keys only.
`fails_check(strict=False)` is what the CLI uses for the exit code and the
JSON `ok` flag: it returns `has_problems`, or, in strict mode, also true when
any extra key remains after `--ignore` filtering.

`without_ignored_keys(comparison, keys)` returns a filtered copy for
`--ignore`. It runs after the comparison rather than editing the parsed files,
so an ignored key is removed consistently from all three buckets and the
original result is never mutated.

## Ignore files (`env_diff/ignore_file.py`)

`parse_ignore_text` reads one key per line and strips everything after `#`
(a `#` can never appear in a valid key, so this is safe), skipping blanks and
de-duplicating while keeping file order. `read_ignore_file` opens the file as
`utf-8-sig` for the same BOM reason as the env parser. `cli.collect_ignored_keys`
merges these keys with `--ignore` flags; it only falls back to
`./.env-diff-ignore` when no `--ignore-file` was given, and only if that file
exists.

## Reporting (`env_diff/cli.py`)

`format_text_report` prints a header and one section per non-empty bucket,
using `-` for missing, `?` for empty, and `+` for extra (diff-like markers).
`format_json_report` serializes the same three buckets plus an `ok` flag for
`--format json`.
`main` maps outcomes to exit codes `0`, `1` (`--check` with problems), and
`2` (missing or malformed file).
