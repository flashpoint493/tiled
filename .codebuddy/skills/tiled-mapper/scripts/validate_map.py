#!/usr/bin/env python3
"""validate_map.py — Lightweight sanity checks for a Tiled JSON map (.tmj).

Checks performed:
  1. File parses as JSON and looks like a Tiled map (`type == "map"`).
  2. Every `tilesets[*].source` resolves on disk (relative to the map file).
  3. Every non-zero gid in every tile layer falls within one of the referenced
     tilesets (gid in [firstgid, firstgid + tilecount)).
  4. Object-layer objects have a non-empty `name` and a non-empty `type`/`class`
     (warning if missing).
  5. Layer/object/property names that contain CJK characters (warning — engines
     often choke on these).

Exit code 0 = clean, 1 = at least one error, 2 = at least one warning only.

Usage:
    python validate_map.py path/to/level1.tmj
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

CJK_RE = re.compile(r"[\u3000-\u303f\u3040-\u309f\u30a0-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]")


def has_cjk(s: str) -> bool:
    return bool(s and CJK_RE.search(s))


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_tileset_tile_count(tileset_path: Path) -> int:
    """Return the tilecount of an external tileset (or 0 if unreadable)."""
    try:
        data = load_json(tileset_path)
    except Exception:
        return 0
    return int(data.get("tilecount", 0))


def validate_map(map_path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    try:
        m = load_json(map_path)
    except Exception as e:
        return [f"Cannot parse JSON: {e}"], []

    if m.get("type") != "map":
        errors.append(f"Top-level type is {m.get('type')!r}, expected 'map'.")

    # --- Tilesets
    base_dir = map_path.parent
    resolved: list[tuple[int, int]] = []  # (firstgid, tilecount)
    for ts in m.get("tilesets", []):
        firstgid = int(ts.get("firstgid", 0))
        if "source" in ts:
            src = (base_dir / ts["source"]).resolve()
            if not src.exists():
                errors.append(f"Tileset source missing: {ts['source']} (resolved {src})")
                continue
            tilecount = load_tileset_tile_count(src)
            if tilecount == 0:
                warnings.append(f"Tileset {ts['source']} parsed but tilecount=0.")
        else:
            tilecount = int(ts.get("tilecount", 0))
        resolved.append((firstgid, tilecount))

    if not resolved:
        warnings.append("Map references no tilesets.")

    max_gid = 0
    for fg, tc in resolved:
        max_gid = max(max_gid, fg + tc - 1)

    # Strip flip flags from gids before range checking
    GID_FLIPS = 0xE0000000
    GID_MASK = 0x1FFFFFFF

    # --- Layers
    def walk_layers(layers: list[dict[str, Any]], path: str = "") -> None:
        for layer in layers:
            name = layer.get("name", "<unnamed>")
            kind = layer.get("type")
            full = f"{path}/{name}" if path else name

            if has_cjk(name):
                warnings.append(f"Layer name contains CJK: {full!r}")

            if kind == "tilelayer":
                data = layer.get("data")
                if isinstance(data, list):
                    bad = 0
                    for gid_raw in data:
                        gid = int(gid_raw) & GID_MASK
                        if gid == 0:
                            continue
                        if not any(fg <= gid < fg + tc for fg, tc in resolved):
                            bad += 1
                    if bad:
                        errors.append(
                            f"Tile layer {full!r}: {bad} cells reference unknown tiles "
                            f"(gid not in any tileset)."
                        )
            elif kind == "objectgroup":
                for obj in layer.get("objects", []):
                    oname = obj.get("name", "")
                    oclass = obj.get("type", "") or obj.get("class", "")
                    if has_cjk(oname):
                        warnings.append(f"Object name contains CJK in {full!r}: {oname!r}")
                    if not oname:
                        warnings.append(f"Object id={obj.get('id')} in {full!r} has empty name.")
                    if not oclass:
                        warnings.append(f"Object id={obj.get('id')} in {full!r} has no class/type.")
                    if "gid" in obj:
                        gid = int(obj["gid"]) & GID_MASK
                        if gid and not any(fg <= gid < fg + tc for fg, tc in resolved):
                            errors.append(
                                f"Object id={obj.get('id')} in {full!r} references unknown tile gid={gid}."
                            )
                    for prop in obj.get("properties", []) or []:
                        if has_cjk(prop.get("name", "")):
                            warnings.append(f"Property name contains CJK on object {oname!r}: {prop['name']!r}")
            elif kind == "group":
                walk_layers(layer.get("layers", []), full)

    walk_layers(m.get("layers", []))

    return errors, warnings


def main(argv: list[str]) -> int:
    if not argv:
        print("Usage: python validate_map.py <map.tmj>", file=sys.stderr)
        return 2
    path = Path(argv[0])
    if not path.exists():
        print(f"Error: {path} does not exist", file=sys.stderr)
        return 1

    errors, warnings = validate_map(path)

    if errors:
        print(f"[ERR] {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
    if warnings:
        print(f"[WARN] {len(warnings)} warning(s):")
        for w in warnings:
            print(f"  - {w}")
    if not errors and not warnings:
        print(f"OK: {path} looks clean.")

    return 1 if errors else (2 if warnings else 0)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
