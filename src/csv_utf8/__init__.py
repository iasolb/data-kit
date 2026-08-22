"""Rewrite non-UTF-8 CSV files as UTF-8 in place, reporting every action."""

from __future__ import annotations

from .ensure_utf8 import collect_csvs, decode_bytes, main

__all__ = ["collect_csvs", "decode_bytes", "main"]
