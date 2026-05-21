# -*- coding: utf-8 -*-
"""brush_remap_tsx: create a brush tileset TSX with remap metadata.

The action compares a large brush-variant sheet against a compact runtime
source tileset. Both images are interpreted as fixed-size tile grids. For each
non-empty brush tile, the dominant RGB color is matched to the dominant RGB color
of source tiles. The generated TSX keeps the brush image for editing in Tiled,
while tile properties record which runtime source tile should replace it during
map post-processing.
"""

from __future__ import annotations

import json
import os
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape as xml_escape

from PIL import Image

from ..core.action import Action, Context
from ..core.registry import register
from .build_tsx_sheet import TILED_VERSION, TSX_VERSION


Color = Tuple[int, int, int]


def _parse_color(value: Any) -> Tuple[int, int, int, int]:
    color = Action.normalize_color(value, channels=4)
    if len(color) == 3:
        return int(color[0]), int(color[1]), int(color[2]), 255
    return int(color[0]), int(color[1]), int(color[2]), int(color[3])


def _dominant_tile_color(
    img: Image.Image,
    box: Tuple[int, int, int, int],
    transparent: Tuple[int, int, int, int],
    min_alpha: int,
) -> Tuple[Optional[Color], int, int]:
    crop = img.crop(box).convert("RGBA")
    counts: Counter[Color] = Counter()
    non_transparent = 0
    tr, tg, tb, ta = transparent

    for r, g, b, a in crop.getdata():
        if a < min_alpha:
            continue
        if (r, g, b, a) == (tr, tg, tb, ta):
            continue
        non_transparent += 1
        counts[(r, g, b)] += 1

    if not counts:
        return None, 0, non_transparent
    color, count = counts.most_common(1)[0]
    return color, int(count), non_transparent


def _cells_for_image(
    img: Image.Image,
    tile_width: int,
    tile_height: int,
    transparent: Tuple[int, int, int, int],
    min_alpha: int,
) -> Tuple[int, int, List[Dict[str, Any]]]:
    width, height = img.size
    cols = width // tile_width
    rows = height // tile_height
    cells: List[Dict[str, Any]] = []

    for y in range(rows):
        for x in range(cols):
            tile_id = y * cols + x
            box = (
                x * tile_width,
                y * tile_height,
                (x + 1) * tile_width,
                (y + 1) * tile_height,
            )
            color, dominant_pixels, non_transparent_pixels = _dominant_tile_color(
                img,
                box,
                transparent=transparent,
                min_alpha=min_alpha,
            )
            cells.append({
                "id": tile_id,
                "x": x,
                "y": y,
                "color": color,
                "dominant_pixels": dominant_pixels,
                "non_transparent_pixels": non_transparent_pixels,
            })
    return cols, rows, cells


def _color_to_hex(color: Optional[Color]) -> str:
    if color is None:
        return ""
    return "#{:02X}{:02X}{:02X}".format(*color)


def _choose_source_tile(ids: List[int], mode: str) -> int:
    if not ids:
        return -1
    mode = (mode or "first").lower()
    if mode == "last":
        return ids[-1]
    if mode == "middle":
        return ids[len(ids) // 2]
    return ids[0]


@register("brush_remap_tsx")
class BrushRemapTsxAction(Action):
    description = "生成 brush variants .tsx，并写入映射回源 tileset 的 tile 属性"
    param_hints = {
        "source": {"widget": "filepath"},
        "brush": {"widget": "filepath"},
        "tsx": {"widget": "filepath"},
        "mapping_json": {"widget": "filepath"},
        "tile_width": {"min": 1, "step": 1},
        "tile_height": {"min": 1, "step": 1},
        "firstgid": {"min": 1, "step": 1},
        "min_alpha": {"min": 0, "max": 255, "step": 1},
        "empty_color": {"widget": "rgba"},
        "ambiguous": {"enum": ["first", "middle", "last"]},
    }

    def run(
        self,
        ctx: Context,
        source: str,
        brush: str,
        tsx: str = "auto",
        mapping_json: str = "auto",
        name: str = "brush_remap",
        source_name: str = "source_tileset",
        tile_width: int = 256,
        tile_height: int = 256,
        firstgid: int = 1,
        min_alpha: int = 1,
        empty_color: Tuple[int, int, int, int] = (0, 0, 0, 0),
        ambiguous: str = "first",
        include_empty_tiles: bool = False,
        copy_brush_image: bool = True,
    ) -> Context:
        source_path = Path(source).expanduser().resolve()
        brush_path = Path(brush).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(f"[brush_remap_tsx] 找不到源 tileset: {source_path}")
        if not brush_path.is_file():
            raise FileNotFoundError(f"[brush_remap_tsx] 找不到 brush variants: {brush_path}")

        tile_width = int(tile_width)
        tile_height = int(tile_height)
        if tile_width <= 0 or tile_height <= 0:
            raise ValueError("[brush_remap_tsx] tile_width/tile_height 必须大于 0")

        source_img = Image.open(source_path).convert("RGBA")
        brush_img = Image.open(brush_path).convert("RGBA")
        if source_img.width % tile_width or source_img.height % tile_height:
            raise ValueError(
                f"[brush_remap_tsx] 源图尺寸 {source_img.size} 不能被 "
                f"tile={tile_width}x{tile_height} 整除"
            )
        if brush_img.width % tile_width or brush_img.height % tile_height:
            raise ValueError(
                f"[brush_remap_tsx] brush 图尺寸 {brush_img.size} 不能被 "
                f"tile={tile_width}x{tile_height} 整除"
            )

        transparent = _parse_color(empty_color)
        min_alpha = max(0, min(255, int(min_alpha)))
        source_cols, source_rows, source_cells = _cells_for_image(
            source_img,
            tile_width,
            tile_height,
            transparent=transparent,
            min_alpha=min_alpha,
        )
        brush_cols, brush_rows, brush_cells = _cells_for_image(
            brush_img,
            tile_width,
            tile_height,
            transparent=transparent,
            min_alpha=min_alpha,
        )

        source_by_color: Dict[Color, List[int]] = defaultdict(list)
        for cell in source_cells:
            color = cell["color"]
            if color is not None:
                source_by_color[color].append(int(cell["id"]))

        brush_count = len(brush_cells)
        mapped_entries: List[Dict[str, Any]] = []
        unmapped_entries: List[Dict[str, Any]] = []
        ambiguous_entries: List[Dict[str, Any]] = []
        tile_properties: Dict[int, Dict[str, Any]] = {}

        for cell in brush_cells:
            brush_id = int(cell["id"])
            color = cell["color"]
            if color is None:
                if include_empty_tiles:
                    tile_properties[brush_id] = {
                        "brush_tile_id": brush_id,
                        "empty": True,
                    }
                continue

            candidates = source_by_color.get(color, [])
            target_tile_id = _choose_source_tile(candidates, ambiguous)
            entry = {
                "brush_tile_id": brush_id,
                "brush_x": int(cell["x"]),
                "brush_y": int(cell["y"]),
                "color": _color_to_hex(color),
                "target_tile_id": target_tile_id,
                "target_gid": int(firstgid) + target_tile_id if target_tile_id >= 0 else 0,
                "candidate_tile_ids": candidates,
            }
            if target_tile_id >= 0:
                mapped_entries.append(entry)
            else:
                unmapped_entries.append(entry)
            if len(candidates) > 1:
                ambiguous_entries.append(entry)

            tile_properties[brush_id] = {
                "brush_tile_id": brush_id,
                "brush_x": int(cell["x"]),
                "brush_y": int(cell["y"]),
                "source_tileset": source_name,
                "source_color": _color_to_hex(color),
                "target_tile_id": target_tile_id,
                "target_gid": int(firstgid) + target_tile_id if target_tile_id >= 0 else 0,
                "candidate_tile_ids": ",".join(str(v) for v in candidates),
                "candidate_count": len(candidates),
            }

        if not tsx or tsx == "auto":
            tsx_path = brush_path.with_name(f"{brush_path.stem}_remap.tsx")
        else:
            tsx_path = Path(tsx).expanduser()
            if not tsx_path.is_absolute():
                tsx_path = (brush_path.parent / tsx_path).resolve()
        tsx_path.parent.mkdir(parents=True, exist_ok=True)

        if not mapping_json or mapping_json == "auto":
            mapping_path = tsx_path.with_suffix(".remap.json")
        else:
            mapping_path = Path(mapping_json).expanduser()
            if not mapping_path.is_absolute():
                mapping_path = (tsx_path.parent / mapping_path).resolve()
        mapping_path.parent.mkdir(parents=True, exist_ok=True)

        image_path_for_tsx = brush_path
        if copy_brush_image:
            image_path_for_tsx = tsx_path.with_name(brush_path.name)
            if image_path_for_tsx.resolve() != brush_path.resolve():
                shutil.copy2(brush_path, image_path_for_tsx)

        brush_rel = os.path.relpath(image_path_for_tsx, start=tsx_path.parent).replace(os.sep, "/")
        tileset_name = name or tsx_path.stem
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            (
                f'<tileset version="{TSX_VERSION}" tiledversion="{TILED_VERSION}" '
                f'name="{xml_escape(tileset_name)}" tilewidth="{tile_width}" '
                f'tileheight="{tile_height}" tilecount="{brush_count}" columns="{brush_cols}">'
            ),
            (
                f' <image source="{xml_escape(brush_rel)}" '
                f'width="{brush_img.width}" height="{brush_img.height}"/>'
            ),
        ]

        for tile_id in sorted(tile_properties):
            props = tile_properties[tile_id]
            lines.append(f' <tile id="{tile_id}">')
            lines.append('  <properties>')
            for key, value in props.items():
                if isinstance(value, bool):
                    lines.append(
                        f'   <property name="{xml_escape(str(key))}" type="bool" '
                        f'value="{str(value).lower()}"/>'
                    )
                elif isinstance(value, int):
                    lines.append(
                        f'   <property name="{xml_escape(str(key))}" type="int" '
                        f'value="{value}"/>'
                    )
                else:
                    lines.append(
                        f'   <property name="{xml_escape(str(key))}" '
                        f'value="{xml_escape(str(value))}"/>'
                    )
            lines.append('  </properties>')
            lines.append(' </tile>')
        lines.append('</tileset>')
        tsx_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        mapping = {
            "name": tileset_name,
            "source_name": source_name,
            "source_image": str(source_path),
            "brush_image": str(brush_path),
            "tsx_image": str(image_path_for_tsx),
            "tile_width": tile_width,
            "tile_height": tile_height,
            "firstgid": int(firstgid),
            "source_grid": {
                "columns": source_cols,
                "rows": source_rows,
                "tile_count": len(source_cells),
            },
            "brush_grid": {
                "columns": brush_cols,
                "rows": brush_rows,
                "tile_count": brush_count,
            },
            "mapped_count": len(mapped_entries),
            "unmapped_count": len(unmapped_entries),
            "ambiguous_count": len(ambiguous_entries),
            "mappings": mapped_entries,
            "unmapped": unmapped_entries,
            "ambiguous": ambiguous_entries,
        }
        mapping_path.write_text(
            json.dumps(mapping, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        ctx.extras["brush_remap"] = {
            "tsx": str(tsx_path),
            "mapping_json": str(mapping_path),
            "image": str(image_path_for_tsx),
            "mapped_count": len(mapped_entries),
            "unmapped_count": len(unmapped_entries),
            "ambiguous_count": len(ambiguous_entries),
        }
        ctx.meta["last_tsx"] = str(tsx_path)
        ctx.meta["last_mapping_json"] = str(mapping_path)
        print(
            f"[brush_remap_tsx] -> {tsx_path.name}, {mapping_path.name}  "
            f"brush={brush_cols}x{brush_rows} count={brush_count}  "
            f"mapped={len(mapped_entries)} unmapped={len(unmapped_entries)} "
            f"ambiguous={len(ambiguous_entries)}"
        )
        return ctx.with_image(brush_img)
