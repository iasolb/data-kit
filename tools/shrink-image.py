#!/usr/bin/env python3
"""Shrink images to a pixel size or file-size target.

    python tools/shrink-image.py logo.png --max-width 400
    python tools/shrink-image.py photo.jpg --max-kb 150 -o photo-small.jpg
    python tools/shrink-image.py assets/ --max-width 1600 --dry-run
    python tools/shrink-image.py --self-test

WHY THIS EXISTS. Images copied into websites and repositories are often much
larger than they need to be. Shrinking one used to mean writing a throwaway
script each time; this standalone tool makes the common resize and compression
steps repeatable. EXIF is removed by default because it can contain GPS data.
"""

from __future__ import annotations

import argparse
import io
import math
import sys
import tempfile
from pathlib import Path

SUPPORTED = {".png", ".jpg", ".jpeg", ".webp"}


def _save_options(image_format: str, exif: bytes | None, keep_metadata: bool,
                  quality: int) -> dict:
    options = {}
    if image_format == "JPEG":
        options.update(quality=quality, optimize=True)
    elif image_format == "WEBP":
        options.update(quality=quality, method=6)
    elif image_format == "PNG":
        options.update(optimize=True)
    if keep_metadata and exif:
        options["exif"] = exif
    return options


def _encoded(image, image_format: str, exif: bytes | None,
             keep_metadata: bool, quality: int = 90) -> bytes:
    if image_format == "JPEG" and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    out = io.BytesIO()
    image.save(out, format=image_format,
               **_save_options(image_format, exif, keep_metadata, quality))
    return out.getvalue()


def make_result(path: Path, max_width: int | None, max_height: int | None,
                max_kb: float | None, keep_metadata: bool, Image) -> tuple:
    """Return encoded bytes, source/result dimensions, and target success."""
    with Image.open(path) as source:
        image_format = source.format
        if image_format not in {"JPEG", "PNG", "WEBP"}:
            raise ValueError(f"unsupported image format {image_format!r}")
        original_size = source.size
        exif = source.info.get("exif")
        image = source.copy()

    width, height = image.size
    scale = 1.0
    if max_width is not None:
        scale = min(scale, max_width / width)
    if max_height is not None:
        scale = min(scale, max_height / height)
    if scale < 1:
        new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        image = image.resize(new_size, Image.Resampling.LANCZOS)

    if image_format in {"JPEG", "WEBP"}:
        qualities = range(90, 39, -5) if max_kb is not None else (90,)
        payload = b""
        target_met = max_kb is None
        for quality in qualities:
            candidate = _encoded(image, image_format, exif, keep_metadata, quality)
            if not payload or len(candidate) < len(payload):
                payload = candidate
            if max_kb is not None and len(candidate) <= max_kb * 1024:
                payload = candidate
                target_met = True
                break
    else:
        payload = _encoded(image, image_format, exif, keep_metadata)
        target_met = max_kb is None or len(payload) <= max_kb * 1024
        if max_kb is not None and not target_met:
            try:
                palette = image.quantize(colors=256)
            except ValueError:
                mode = "RGBA" if "A" in image.getbands() else "RGB"
                palette = image.convert(mode).quantize(colors=256)
            palette_payload = _encoded(palette, image_format, exif, keep_metadata)
            if len(palette_payload) < len(payload):
                payload = palette_payload
            target_met = len(payload) <= max_kb * 1024

    return payload, original_size, image.size, target_met


def _write_if_smaller(source: Path, output: Path, payload: bytes,
                      dry_run: bool) -> bool:
    """Write the result only when it is smaller than the original; return wrote."""
    if len(payload) >= source.stat().st_size:
        return False
    if not dry_run:
        output.write_bytes(payload)
        return True
    return False


def shrink_one(path: Path, output: Path, max_width: int | None,
               max_height: int | None, max_kb: float | None,
               keep_metadata: bool, dry_run: bool, Image) -> dict:
    payload, old_dimensions, new_dimensions, target_met = make_result(
        path, max_width, max_height, max_kb, keep_metadata, Image)
    old_size = path.stat().st_size
    if len(payload) >= old_size:
        status = "kept"
        wrote = False
    else:
        status = "shrunk"
        wrote = _write_if_smaller(path, output, payload, dry_run)
    return {
        "status": status,
        "old_size": old_size,
        "new_size": len(payload),
        "old_dimensions": old_dimensions,
        "new_dimensions": new_dimensions,
        "target_met": target_met,
        "wrote": wrote,
    }


def _kb(size: int) -> str:
    return f"{size / 1024:.0f} KB"


def _report(path: Path, result: dict) -> None:
    if result["status"] == "kept":
        line = f"kept {_kb(result['old_size'])} (result {_kb(result['new_size'])}) {path}"
    else:
        old = "x".join(map(str, result["old_dimensions"]))
        new = "x".join(map(str, result["new_dimensions"]))
        line = (f"shrunk {_kb(result['old_size'])} -> {_kb(result['new_size'])} "
                f"({old} -> {new}) {path}")
    if not result["target_met"]:
        line += "; max-kb target not met"
    if result["status"] == "shrunk" and not result["wrote"]:
        line += " (dry-run)"
    print(line)


def _image_files(path: Path, recursive: bool) -> list[Path]:
    if path.is_file():
        return [path]
    pattern = "**/*" if recursive else "*"
    return sorted(p for p in path.glob(pattern)
                  if p.is_file() and p.suffix.lower() in SUPPORTED)


def run(path: Path, output: Path | None, recursive: bool,
        max_width: int | None, max_height: int | None, max_kb: float | None,
        keep_metadata: bool, dry_run: bool, Image) -> int:
    files = _image_files(path, recursive)
    if not files:
        print(f"FAILED no supported images found: {path}")
        return 1
    failures = 0
    for image_path in files:
        destination = output if output is not None else image_path
        try:
            result = shrink_one(image_path, destination, max_width, max_height,
                                max_kb, keep_metadata, dry_run, Image)
            _report(image_path, result)
        except Exception as exc:
            print(f"FAILED {exc}: {image_path}")
            failures += 1
    return 1 if failures else 0


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def _positive_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="shrink-image")
    ap.add_argument("path", nargs="?", help="an image file or directory")
    ap.add_argument("-o", "--output", help="output path (only valid for one file)")
    ap.add_argument("--max-width", type=_positive_int)
    ap.add_argument("--max-height", type=_positive_int)
    ap.add_argument("--max-kb", type=_positive_float)
    ap.add_argument("--recursive", action="store_true",
                    help="include images in subdirectories")
    ap.add_argument("--keep-metadata", action="store_true",
                    help="keep EXIF metadata; removed by default")
    ap.add_argument("--dry-run", action="store_true",
                    help="report results without writing files")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        try:
            from PIL import Image
        except ImportError:
            print("shrink-image: needs Pillow: pip install pillow", file=sys.stderr)
            return 2
        return self_test(Image)
    if not args.path:
        ap.error("an image file or directory is required")
    if args.max_width is None and args.max_height is None and args.max_kb is None:
        ap.error("at least one of --max-width, --max-height or --max-kb is required")
    path = Path(args.path)
    if not path.exists():
        print(f"FAILED path does not exist: {path}")
        return 1
    output = Path(args.output) if args.output else None
    if output is not None and not path.is_file():
        ap.error("-o/--output is only valid with a single file")
    try:
        from PIL import Image
    except ImportError:
        print("shrink-image: needs Pillow: pip install pillow", file=sys.stderr)
        return 2
    return run(path, output, args.recursive, args.max_width, args.max_height,
               args.max_kb, args.keep_metadata, args.dry_run, Image)


def self_test(Image) -> int:
    fails: list[str] = []
    checks = 0

    def want(label: str, condition: bool) -> None:
        nonlocal checks
        checks += 1
        print(f"  {'ok  ' if condition else 'FAIL'} {label}")
        if not condition:
            fails.append(label)

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        import random

        rng = random.Random(7)
        noise = bytes(rng.randrange(256) for _ in range(1200 * 800 * 3))
        jpeg = root / "noisy.jpg"
        exif = Image.Exif()
        exif[270] = "self-test"
        Image.frombytes("RGB", (1200, 800), noise).save(
            jpeg, format="JPEG", quality=98, exif=exif)
        original_jpeg = jpeg.read_bytes()
        result = shrink_one(jpeg, jpeg, 400, None, None, False, False, Image)
        want("width is capped and aspect ratio is kept",
             result["new_dimensions"] == (400, 267))
        with Image.open(jpeg) as resized:
            want("EXIF is removed by default", not resized.getexif())

        small = root / "small.jpg"
        Image.new("RGB", (100, 50), (30, 80, 120)).save(small, quality=96)
        result = shrink_one(small, small, 400, None, None, False, False, Image)
        want("an image already under the maximum is never upscaled",
             result["new_dimensions"] == (100, 50))

        target_jpeg = root / "target.jpg"
        target_jpeg.write_bytes(original_jpeg)
        result = shrink_one(target_jpeg, target_jpeg, None, None, 900,
                            False, False, Image)
        resulting_size = (target_jpeg.stat().st_size if result["wrote"]
                          else result["old_size"])
        want("JPEG max-kb reaches the requested target",
             result["target_met"] and resulting_size <= 900 * 1024)

        png = root / "alpha.png"
        rgba = Image.new("RGBA", (1000, 1000), (20, 100, 220, 128))
        rgba.save(png, optimize=False)
        png_source_size = png.stat().st_size
        payload = b"x" * (png_source_size + 1)
        destination = root / "must-stay.txt"
        destination.write_bytes(b"keep")
        wrote = _write_if_smaller(png, destination, payload, False)
        want("a result larger than its source is not written",
             not wrote and destination.read_bytes() == b"keep")

        dry = root / "dry.jpg"
        dry.write_bytes(original_jpeg)
        before = dry.read_bytes()
        dry_result = shrink_one(dry, dry, 400, None, None,
                                False, True, Image)
        want("dry-run changes nothing on disk",
             dry_result["status"] == "shrunk" and dry.read_bytes() == before)

        with Image.open(png) as alpha:
            alpha_payload = _encoded(alpha, "PNG", None, False)
        with Image.open(io.BytesIO(alpha_payload)) as compressed:
            want("PNG alpha is preserved", "A" in compressed.getbands())

    if fails:
        print(f"\nshrink-image self-test: {len(fails)} of {checks} FAILED")
        return 1
    print(f"\nshrink-image self-test: {checks} assertions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
