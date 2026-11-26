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
   - If a **double** quote is not closed on its line, the value continues on
     the following lines until a line containing `"` (`_opens_multiline_value`
     and `_join_multiline_value`). The pieces are joined with `\n`, the entry
     keeps the line number of the `KEY=` line, and parsing resumes after the
     closing line. Single quotes never span lines, so an apostrophe typo
     cannot swallow the rest of the file.
   - If a quote is never closed at all (a single quote on its line, or a
     double quote that runs to the end of the file), keep the rest of the
     text rather than erroring.
   - Otherwise, cut at ` #` (space, hash) to drop an inline comment. A hash
     with no space before it (`COLOR=#fff`) is part of the value. This matches
     python-dotenv and docker compose.

Each assignment becomes a frozen `EnvEntry(key, value, line_number)`.

### Duplicates

`entries_to_mapping` builds a dict from the entries. A later assignment of the
same key replaces the earlier value (last one wins, like a shell), while the
key keeps its original position in the dict, so reports stay in file order.

### Inline comments and optional markers

An unquoted value ends at the first space followed by `#`, and a value that
*starts* with whitespace then `#` (`KEY= # fill me in`) is empty, matching
python-dotenv. `COLOR=#fff` keeps its `#` because there is no space before it.
`_trailing_comment` applies the same quote-aware rules to extract the comment
text, and if it contains `env-diff: optional` (case-insensitive, word
boundary) the entry's `optional` flag is set. `find_optional_keys` returns the
marked keys in order; a key counts as optional if any of its assignments is
marked.

### What the parser does not do

- No `${VAR}` interpolation and no command substitution. env-diff must never
  execute or resolve anything from a secrets file.
- No backslash escapes inside double quotes (`\n` stays a backslash and an
  `n`); a real newline is only produced by an actual line break.
- No multi-line single-quoted or unquoted values.

## Comparing (`env_diff/compare.py`)

`compare_env_mappings(example, actual)` produces an `EnvComparison`:

| Bucket | Rule | Order |
| --- | --- | --- |
| `missing_keys` | key in example, not in actual | example file order |
| `empty_keys` | key in both, actual value is `""` | example file order |
| `extra_keys` | key in actual, not in example | actual file order |
| `optional_keys` | key marked optional in example and missing or empty in actual | example file order |

Comparison is case-sensitive (`API_KEY` and `api_key` are different variables
on Linux and macOS). `has_problems` is true for missing or empty keys only.
`fails_check(strict=False)` is what the CLI uses for the exit code and the
JSON `ok` flag: it returns `has_problems`, or, in strict mode, also true when
any extra key remains after `--ignore` filtering.

Optional keys are checked before the missing/empty split, so an unset
optional key lands in exactly one bucket. `optional_keys` never counts toward
`has_problems` or `fails_check`, even in strict mode, and a template key is
never extra by definition.

`without_ignored_keys(comparison, keys)` returns a filtered copy for
`--ignore`. It runs after the comparison rather than editing the parsed files,
so an ignored key is removed consistently from all four buckets and the
original result is never mutated.

## Duplicate keys

`find_duplicate_keys(entries)` maps every key assigned more than once to all
of its line numbers (an `export KEY=` and a plain `KEY=` count as the same
key). The CLI reads each file once with `read_env_entries`, prints one
`env-diff: warning: ...` line per duplicate to **stderr**, and only then
collapses the entries with `entries_to_mapping`. Warnings never include values
and never change the exit code, because the file still loads exactly as a
shell would read it; they exist to catch merge leftovers such as an empty
`SECRET_KEY=` shadowing the real value.

## Ignore files (`env_diff/ignore_file.py`)

`parse_ignore_text` reads one key per line and strips everything after `#`
(a `#` can never appear in a valid key, so this is safe), skipping blanks and
de-duplicating while keeping file order. `read_ignore_file` opens the file as
`utf-8-sig` for the same BOM reason as the env parser. `cli.collect_ignored_keys`
merges these keys with `--ignore` flags; it only falls back to
`./.env-diff-ignore` when no `--ignore-file` was given, and only if that file
exists.

## Fixing (`env_diff/fixer.py`)

`build_missing_key_lines(missing_keys, example_entries)` produces
`KEY=placeholder` lines in template order. `_format_placeholder` quotes a value
when the parser would otherwise change it (surrounding whitespace, `#`, a
leading quote, or an embedded newline from a multi-line template value, which
only survives inside double quotes), preferring double quotes and falling back to single quotes
when the value contains `"`. `append_missing_keys(path, lines)` opens the file
in append mode, adds a blank line and a header comment, and creates the file
if needed; it writes nothing when there is nothing to add.

In `cli.main`, `--fix` runs after the first comparison (so ignored and
optional keys are already filtered out), then the env file is re-read and
`cli.compare_files` runs again so the report and exit code describe the file
as it is now.

`render_fix_block(lines)` returns the header plus assignments as one string;
`append_missing_keys` writes that string (after a separator) and
`--fix --dry-run` prints it instead. `cli._finish_report` prints the report
and picks the exit code for both paths, so a dry run reports and exits exactly
like a plain run on the unchanged file.

## Reporting (`env_diff/cli.py`)

`format_text_report` prints a header and one section per non-empty bucket,
using `-` for missing, `?` for empty, and `+` for extra (diff-like markers).
`format_json_report` serializes the same three buckets plus an `ok` flag for
`--format json`.
With `--quiet`, `main` skips both the warnings and the report but still
prints usage errors, which happen earlier, before any output decision.
`main` maps outcomes to exit codes `0`, `1` (`--check` with problems), and
`2` (missing or malformed file).
