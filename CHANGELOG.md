# Changelog

All notable user-visible changes to env-diff are recorded here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project uses [Semantic Versioning](https://semver.org/). While the version is
`0.x`, new flags may still be added in minor releases, but existing flags,
exit codes, and the JSON field names are treated as stable.

Every pull request that changes behavior should add a line under
**Unreleased** so a release is just a matter of renaming that heading.

## Unreleased

Nothing yet.

## 0.2.0 - 2026-11-25

### Added

- `--strict`: with `--check`, keys in `.env` that the template does not list
  also fail; JSON `ok` becomes false when extra keys exist (#5, #8).
- `--ignore-file PATH`, plus automatic loading of `./.env-diff-ignore` when it
  exists, so a team can share its ignore list (#6, #9).
- Warnings on stderr when a key is assigned more than once in either file,
  naming every line; the last value still wins (#7, #10).
- `-q` / `--quiet`: print nothing but usage errors and rely on the exit
  code (#11, #14).
- `# env-diff: optional` inline markers in the template; missing or empty
  optional keys are listed in a separate *optional* bucket and never fail
  `--check` (#12, #15).
- `--fix`: append missing keys to the env file using the template's
  placeholder values, creating the file if needed (#13, #16).
- `--dry-run`: with `--fix`, print the block that would be appended instead
  of writing it (#17).
- Multi-line double-quoted values (PEM keys, certificates) are parsed as one
  entry that keeps the line number of its `KEY=` line; `--fix` re-quotes
  multi-line placeholders so they parse back unchanged (#18).
- `--no-warnings`: hide duplicate-key warnings but keep the report and exit
  code, unlike `--quiet` which hides everything (#19).

### Fixed

- `KEY= # note` now parses as an empty value followed by a comment instead of
  the value `# note`, matching python-dotenv (#15).

## 0.1.0 - 2026-11-18

### Added

- Dotenv parser for `KEY=value`, `export`, single and double quotes, inline
  `#` comments, a UTF-8 BOM, and keys containing dots or dashes.
- Comparison of a template against an env file into *missing*, *empty*, and
  *extra* keys (key names only; values are never printed).
- `--check` exit code `1` for CI and git hooks; exit code `2` for missing or
  malformed files.
- `--format json` for scripts (#1, #3).
- `--ignore KEY`, repeatable (#2, #4).
