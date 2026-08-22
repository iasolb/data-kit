"""Rewrite non-UTF-8 CSV files as UTF-8 in place, reporting every action."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

# Longer BOMs first: the utf-32-le BOM starts with the utf-16-le bytes.
_BOMS: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xfe\x00\x00", "utf-32"),
    (b"\x00\x00\xfe\xff", "utf-32"),
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
)

# Tried in order when there is no BOM and strict utf-8 fails. latin-1 cannot
# fail, so it stays last as the everything-decodes fallback.
_FALLBACK_ENCODINGS: tuple[str, ...] = ("cp1252", "latin-1")


def _normalizer_decode(raw: bytes) -> tuple[str, str] | None:
    """Best-effort decode via charset-normalizer when it is installed."""
    try:
        from charset_normalizer import from_bytes
    except ImportError:
        return None
    best = from_bytes(raw).best()
    if best is None:
        return None
    return str(best), str(best.encoding)


def decode_bytes(raw: bytes) -> tuple[str, str]:
    """Return (text, source encoding label) for raw CSV bytes."""
    for bom, encoding in _BOMS:
        if raw.startswith(bom):
            return raw.decode(encoding), encoding
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    from_normalizer = _normalizer_decode(raw)
    if from_normalizer is not None:
        return from_normalizer
    for encoding in _FALLBACK_ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError("no candidate encoding decoded the file")


def collect_csvs(target: Path) -> list[Path]:
    """Return CSV files under target (a single .csv file or a directory tree)."""
    if target.is_file():
        return [target] if target.suffix.lower() == ".csv" else []
    return sorted(p for p in target.rglob("*.csv") if ".git" not in p.parts)


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Rewrite non-UTF-8 CSV files as UTF-8 in place."
    )
    parser.add_argument("path", help="a .csv file or a directory to walk for .csv files")
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would change without writing"
    )
    args = parser.parse_args()

    target = Path(args.path).expanduser()
    if not target.exists():
        print(f"ensure_utf8: no such path: {target}", file=sys.stderr)
        return 1

    csv_paths = collect_csvs(target)
    if not csv_paths:
        print(f"ensure_utf8: no .csv files found under {target}")
        return 0
    if importlib.util.find_spec("charset_normalizer") is None:
        print(
            "ensure_utf8: charset-normalizer not installed, "
            "using builtin cp1252/latin-1 fallback"
        )

    converted = 0
    failed = 0
    for path in csv_paths:
        raw = path.read_bytes()
        if not raw:
            print(f"  empty      {path}")
            continue
        try:
            text, encoding = decode_bytes(raw)
        except ValueError:
            print(f"  FAILED     {path} (could not decode)", file=sys.stderr)
            failed += 1
            continue
        if encoding == "utf-8":
            print(f"  ok         {path}")
            continue
        if args.dry_run:
            print(f"  would fix  {path} ({encoding} -> utf-8)")
        else:
            path.write_bytes(text.encode("utf-8"))
            print(f"  converted  {path} ({encoding} -> utf-8)")
        converted += 1

    verb = "would convert" if args.dry_run else "converted"
    print(
        f"ensure_utf8: {len(csv_paths)} csv(s) checked, "
        f"{verb} {converted}, failed {failed}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
