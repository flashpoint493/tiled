#!/usr/bin/env python3
"""tileset_audit.py — Inspect a Tiled JSON tileset (.tsj).

Reports:
  - Basic geometry (tile size, columns, tilecount, margin/spacing).
  - Per-tile features: animations, collision shapes, custom properties.
  - Probabilities deviating from 1 (useful for random brushes).
  - Whether it's a single-image or collection tileset.
  - Possible alignment hint (image dims vs tile size + margin + spacing).

Usage:
    python tileset_audit.py path/to/tileset.tsj
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def audit(path: Path) -> int:
    data = load(path)
    if data.get("type") != "tileset":
        print(f"[ERR] Top-level type is {data.get('type')!r}, expected 'tileset'.", file=sys.stderr)
        return 1

    name = data.get("name", "<unnamed>")
    tile_w = data.get("tilewidth")
    tile_h = data.get("tileheight")
    margin = data.get("margin", 0)
    spacing = data.get("spacing", 0)
    columns = data.get("columns")
    tilecount = data.get("tilecount", 0)
    is_collection = "image" not in data

    print(f"Tileset: {name}")
    print(f"  Kind         : {'collection of images' if is_collection else 'single image'}")
    print(f"  Tile size    : {tile_w} x {tile_h}")
    print(f"  Margin       : {margin}")
    print(f"  Spacing      : {spacing}")
    print(f"  Columns      : {columns}")
    print(f"  Tile count   : {tilecount}")

    if not is_collection:
        image = data.get("image")
        iw = data.get("imagewidth", 0)
        ih = data.get("imageheight", 0)
        print(f"  Image        : {image}  ({iw} x {ih})")
        # Verify the math: columns * (tile_w + spacing) + margin*2 - spacing should equal imagewidth
        if tile_w and columns:
            expected_w = columns * tile_w + (columns - 1) * spacing + margin * 2
            if expected_w != iw:
                print(
                    f"  [WARN] columns ({columns}) * tilewidth ({tile_w}) + spacings + margins = "
                    f"{expected_w}, but imagewidth is {iw}. Re-check margin/spacing."
                )

    # Per-tile pass
    anims = []
    collisions = []
    props = []
    probabilities = []
    image_rects = []  # tiles with width/height that crop a source image

    for t in data.get("tiles", []) or []:
        tid = t.get("id")
        if "animation" in t:
            anims.append((tid, len(t["animation"]), t["animation"][0].get("duration") if t["animation"] else None))
        if "objectgroup" in t:
            shapes = t["objectgroup"].get("objects", [])
            if shapes:
                collisions.append((tid, len(shapes)))
        if "properties" in t and t["properties"]:
            kvs = [(p.get("name"), p.get("type"), p.get("value")) for p in t["properties"]]
            props.append((tid, kvs))
        if "probability" in t and t["probability"] != 1:
            probabilities.append((tid, t["probability"]))
        if is_collection and "image" in t:
            image_rects.append((tid, t.get("image"), t.get("width"), t.get("height")))

    if anims:
        print(f"\nAnimations ({len(anims)} tiles):")
        for tid, n, dur in anims:
            print(f"  tile {tid}: {n} frames, first duration {dur} ms")
    if collisions:
        print(f"\nCollision shapes ({len(collisions)} tiles):")
        for tid, n in collisions:
            print(f"  tile {tid}: {n} shape(s)")
    if probabilities:
        print(f"\nProbabilities ≠ 1 ({len(probabilities)} tiles):")
        for tid, p in probabilities:
            print(f"  tile {tid}: probability={p}")
    if props:
        print(f"\nCustom properties ({len(props)} tiles):")
        for tid, kvs in props:
            print(f"  tile {tid}: " + ", ".join(f"{n}({t})={v}" for n, t, v in kvs))
    if image_rects:
        print(f"\nCollection tiles ({len(image_rects)}):")
        for tid, img, w, h in image_rects:
            print(f"  tile {tid}: {img}  rect={w}x{h}")

    # Terrain sets summary
    sets = data.get("wangsets") or []
    if sets:
        print(f"\nTerrain sets ({len(sets)}):")
        for s in sets:
            stype = s.get("type", "?")
            terrains = s.get("colors", [])
            print(f"  - {s.get('name', '?')} ({stype}): {len(terrains)} terrain(s)")

    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print("Usage: python tileset_audit.py <tileset.tsj>", file=sys.stderr)
        return 2
    path = Path(argv[0])
    if not path.exists():
        print(f"Error: {path} does not exist", file=sys.stderr)
        return 1
    return audit(path)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
