# data-kit

The data surface: validation, checks, and transforms that make messy data
usable before anything else touches it.

## What is here

`csv-utf8` rewrites non-UTF-8 CSV files as UTF-8 in place. Built because
mixed-encoding CSVs (cp1252 exports, UTF-16 spreadsheet dumps, BOM-prefixed
files) keep breaking pandas reads.

Install it, which puts an `ensure-utf8` command on the path:

```bash
pip install -e .
ensure-utf8 path/to/file.csv
ensure-utf8 path/to/dir            # walks the tree for *.csv
ensure-utf8 path/to/dir --dry-run
```

Better detection with `pip install -e ".[detect]"`, which adds
charset-normalizer.

Every file gets one report line: `ok` (already clean UTF-8, untouched),
`converted` (rewritten, with the detected source encoding), `empty`, or
`FAILED`. Exit code is 1 only if something failed.

## How detection works

BOM sniff (utf-8-sig, utf-16, utf-32, stripped on rewrite), then a strict
UTF-8 decode (the fast path, no rewrite), then charset-normalizer if
installed, then a builtin cp1252 and latin-1 fallback. Output is always
UTF-8 without a BOM.

## Where this fits

- The `--csv` flag on the `machine-sync` commands in `cloud-kit` runs this
  tool over the transfer destination after a successful transfer. It looks
  for the installed `ensure-utf8` command first and falls back to a checkout
  path, so installing this package is enough; the receiving machine needs a
  Python but not a copy of this repo.
- The naming convention is `<domain>-kit`. Siblings: `dev-kit` (editor and
  tooling config), `cloud-kit` (syncing between machines), `research-kit`
  (the analysis framework and API wrappers), `ai-kit` (the AI tooling
  umbrella).

## Start here

Run `ensure-utf8 --dry-run` on a directory of CSVs and read the report
lines.
