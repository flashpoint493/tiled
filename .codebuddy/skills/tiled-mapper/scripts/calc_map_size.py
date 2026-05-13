#!/usr/bin/env python3
"""calc_map_size.py — Compute Tiled map dimensions from a reference image.

Usage:
    python calc_map_size.py <image_path> <tile_size> [--tile-height N]

Examples:
    # Square tiles 16x16
    python calc_map_size.py preview.png 16
    # Tile width 64, tile height 32 (e.g. some pseudo-isometric layouts)
    python calc_map_size.py preview.png 64 --tile-height 32

If the image dimensions don't divide evenly by the tile size, the script
reports the rounded result plus the leftover pixels so the user can adjust
either the source crop or the tile size.

Implementation note: tries Pillow first; falls back to a hand-rolled PNG
header parser (no third-party dependency) when Pillow isn't installed.
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path


def read_png_size(path: Path) -> tuple[int, int]:
    """Return (width, height) for a PNG by parsing the IHDR chunk."""
    with path.open("rb") as f:
        signature = f.read(8)
        if signature != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"Not a PNG file: {path}")
        # IHDR is always the first chunk: 4-byte length, 4-byte type, data, 4-byte CRC.
        length = struct.unpack(">I", f.read(4))[0]
        chunk_type = f.read(4)
        if chunk_type != b"IHDR":
            raise ValueError(f"Expected IHDR chunk, got {chunk_type!r}")
        width, height = struct.unpack(">II", f.read(8))
        return width, height


def read_image_size(path: Path) -> tuple[int, int]:
    """Return (width, height) using Pillow if available, else PNG-only fallback."""
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as img:
            return img.size
    except ImportError:
        pass

    if path.suffix.lower() == ".png":
        return read_png_size(path)

    raise SystemExit(
        f"Cannot read dimensions of {path}: Pillow is not installed and the file "
        f"is not a PNG. Install Pillow (`pip install pillow`) or convert to PNG."
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("image", type=Path, help="Reference image path")
    parser.add_argument("tile_size", type=int, help="Tile width in pixels (also height if --tile-height is omitted)")
    parser.add_argument("--tile-height", type=int, default=None, help="Optional separate tile height in pixels")
    args = parser.parse_args(argv)

    if not args.image.exists():
        print(f"Error: {args.image} does not exist", file=sys.stderr)
        return 1

    tile_w = args.tile_size
    tile_h = args.tile_height if args.tile_height is not None else args.tile_size
    if tile_w <= 0 or tile_h <= 0:
        print("Error: tile size must be positive", file=sys.stderr)
        return 1

    width, height = read_image_size(args.image)

    cols = width // tile_w
    rows = height // tile_h
    leftover_x = width - cols * tile_w
    leftover_y = height - rows * tile_h

    print(f"Image: {args.image}")
    print(f"  Pixels   : {width} x {height}")
    print(f"  Tile size: {tile_w} x {tile_h}")
    print(f"  Map size : {cols} cols x {rows} rows")
    if leftover_x or leftover_y:
        print(
            f"  Warning  : image not evenly divisible — leftover {leftover_x}px wide x {leftover_y}px tall."
        )
        if leftover_x:
            print(f"             Consider tile width {width // (cols + 1)} or cropping the source.")
        if leftover_y:
            print(f"             Consider tile height {height // (rows + 1)} or cropping the source.")
    else:
        print("  Note     : image divides evenly. Use these as 'Width' and 'Height' in New Map dialog.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
