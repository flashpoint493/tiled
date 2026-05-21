# -*- coding: utf-8 -*-
"""tileset_to_iso45_matrix: convert a whole topdown tileset sheet to iso45 cells.

The action keeps tile id order unchanged:
- cut the source sheet by tile_width / tile_height / columns / spacing / margin;
- convert each tile to an iso45 diamond using the shared iso45_tile_spec preset;
- place each converted tile into a fixed cell;
- pack cells back into a sheet with the same columns by default.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PIL import Image

from ..core.action import Action, Context
from ..core.registry import register
from .canvas_square import _ANCHORS, _anchor_offset
from .iso45_tile_spec import resolve_iso45_tile_spec
from .topdown_to_iso import TopdownToIsoAction
from .scale import ScaleAction


def _optional_positive_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    parsed = int(float(value))
    return parsed if parsed > 0 else None


def _auto_tile_count(
    image_w: int,
    image_h: int,
    tile_w: int,
    tile_h: int,
    columns: int,
    spacing: int,
    margin: int,
) -> int:
    usable_h = image_h - margin * 2
    if usable_h < tile_h:
        return 0
    rows = 1 + max(0, (usable_h - tile_h) // (tile_h + spacing))
    return max(0, rows * columns)


def _fit_tile_to_iso45_cell(
    tile: Image.Image,
    spec: Dict[str, int | str],
    anchor: str,
    resample: str,
    background: Tuple[int, int, int, int],
) -> Image.Image:
    ctx = Context(image=tile.convert("RGBA"))
    ctx = TopdownToIsoAction().run(
        ctx,
        anchor="center",
        angle=45,
        y_scale=0.5,
        expand=True,
        resample=resample,
        trim=False,
        background=background,
    )
    ctx = ScaleAction().run(
        ctx,
        size=(int(spec["footprint_width"]), int(spec["footprint_height"])),
        resample=resample,
    )
    iso = Action.require_image(ctx, "tileset_to_iso45_matrix")

    cell_w = int(spec["cell_width"])
    cell_h = int(spec["cell_height"])
    canvas = Image.new("RGBA", (cell_w, cell_h), background)
    ox, oy = _anchor_offset((cell_w, cell_h), iso.size, anchor)
    canvas.alpha_composite(iso, dest=(ox, oy))
    return canvas


@register("tileset_to_iso45_matrix")
class TilesetToIso45MatrixAction(Action):
    description = "整张 topdown tileset sheet → iso matrix 45 PNG（保持 tile id 顺序）"
    param_hints = {
        "preset": {"enum": ["96", "128", "256", "512", "custom", "context"]},
        "tile_width": {"min": 1, "step": 1},
        "tile_height": {"min": 1, "step": 1},
        "columns": {"min": 1, "step": 1},
        "tile_count": {"min": 0, "step": 1},
        "spacing": {"min": 0, "step": 1},
        "margin": {"min": 0, "step": 1},
        "output_columns": {"min": 1, "step": 1},
        "cell_size": {"min": 1, "step": 1},
        "cell_width": {"min": 1, "step": 1},
        "cell_height": {"min": 1, "step": 1},
        "footprint_width": {"min": 1, "step": 1},
        "footprint_height": {"min": 1, "step": 1},
        "anchor": {"enum": sorted(_ANCHORS)},
        "resample": {"enum": ["nearest", "bilinear", "bicubic", "lanczos"]},
        "background": {"widget": "rgba"},
    }

    def run(
        self,
        ctx: Context,
        tile_width: int = 256,
        tile_height: int = 256,
        columns: Optional[int] = None,
        tile_count: Optional[int] = None,
        spacing: int = 0,
        margin: int = 0,
        output_columns: Optional[int] = None,
        preset: str = "256",
        cell_size: Optional[int] = None,
        cell_width: Optional[int] = None,
        cell_height: Optional[int] = None,
        footprint_width: Optional[int] = None,
        footprint_height: Optional[int] = None,
        anchor: str = "center",
        resample: str = "bicubic",
        background: Tuple[int, int, int, int] = (0, 0, 0, 0),
    ) -> Context:
        src = self.require_image(ctx, "tileset_to_iso45_matrix").convert("RGBA")
        tile_w = max(1, int(tile_width))
        tile_h = max(1, int(tile_height))
        spacing = max(0, int(spacing))
        margin = max(0, int(margin))

        if columns is None or int(columns) <= 0:
            usable_w = src.width - margin * 2
            if usable_w < tile_w:
                raise ValueError(
                    f"[tileset_to_iso45_matrix] 输入宽度 {src.width} 放不下 tile_width={tile_w} margin={margin}"
                )
            columns = 1 + max(0, (usable_w - tile_w) // (tile_w + spacing))
        cols = max(1, int(columns))

        if tile_count is None or int(tile_count) <= 0:
            tile_count = _auto_tile_count(src.width, src.height, tile_w, tile_h, cols, spacing, margin)
        count = max(0, int(tile_count))
        if count <= 0:
            raise ValueError("[tileset_to_iso45_matrix] tile_count 为 0，无法生成 sheet")

        spec = resolve_iso45_tile_spec(
            ctx,
            preset=preset,
            cell_size=_optional_positive_int(cell_size),
            cell_width=_optional_positive_int(cell_width),
            cell_height=_optional_positive_int(cell_height),
            footprint_width=_optional_positive_int(footprint_width),
            footprint_height=_optional_positive_int(footprint_height),
        )
        ctx.meta["iso45_tile_spec"] = spec
        bg = self.normalize_color(background, channels=4)

        out_cols = max(1, int(output_columns or cols))
        out_rows = math.ceil(count / out_cols)
        cell_w = int(spec["cell_width"])
        cell_h = int(spec["cell_height"])
        sheet = Image.new("RGBA", (out_cols * cell_w, out_rows * cell_h), bg)

        converted = 0
        for idx in range(count):
            src_row = idx // cols
            src_col = idx % cols
            x = margin + src_col * (tile_w + spacing)
            y = margin + src_row * (tile_h + spacing)
            if x + tile_w > src.width or y + tile_h > src.height:
                continue
            tile = src.crop((x, y, x + tile_w, y + tile_h))
            cell = _fit_tile_to_iso45_cell(tile, spec, anchor, resample, bg)
            dst_row = idx // out_cols
            dst_col = idx % out_cols
            sheet.alpha_composite(cell, dest=(dst_col * cell_w, dst_row * cell_h))
            converted += 1

        sheet_meta: Dict[str, Any] = {
            "path": "",
            "sheet_w": sheet.width,
            "sheet_h": sheet.height,
            "tile_w": cell_w,
            "tile_h": cell_h,
            "columns": out_cols,
            "rows": out_rows,
            "spacing": 0,
            "margin": 0,
            "tile_count": count,
            "tile_names": [],
        }
        ctx.extras["sheet"] = sheet_meta
        ctx.meta["last_sheet"] = sheet_meta
        ctx.meta["tileset_to_iso45_matrix"] = {
            "source_tile_width": tile_w,
            "source_tile_height": tile_h,
            "source_columns": cols,
            "converted": converted,
        }
        source_name = Path(str(ctx.meta.get("source_path") or "tileset")).stem
        ctx.meta["suggested_output"] = f"{source_name}_iso45_matrix.png"

        print(
            "[tileset_to_iso45_matrix] "
            f"{src.size} tile={tile_w}x{tile_h} count={count} src_cols={cols} -> "
            f"{sheet.size} cell={cell_w}x{cell_h} grid={out_cols}x{out_rows} converted={converted}"
        )
        return ctx.with_image(sheet)
