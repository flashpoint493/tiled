# -*- coding: utf-8 -*-
"""pack_sheet：把 ctx.extras["tiles"] 里的多张图拼成一张 sprite sheet。

为什么要单独做这个 action
-------------------------
Tiled 的 "Based on Tileset Image" 类型 tileset 要求：
- 所有 tile 在同一张 PNG 里，尺寸必须完全一致；
- tsx 里通过 tilewidth/tileheight/columns/spacing/margin 描述如何采样。

所以这个 action 做三件事：
1. 把所有 tile 规格化到统一尺寸（按 max w/max h 做 pad，保证像素无损）；
2. 按 cols × rows 网格拼进一张大图；
3. 把 sheet 路径与规格（tile_w/tile_h/columns/rows/spacing/margin/tile_count）
   放到 ctx.extras["sheet"]，供下游 build_tsx_sheet 消费。

参数
----
- path      : 输出 PNG 路径。web 模式下相对路径会落到 OUTPUT_DIR，
              "auto" / 缺省 = 自动分配 out_<uuid>.png。
- columns   : 列数。默认 None = 自动：
                * 9 张 → 3 列（3x3 自然形态）；
                * 否则 = ceil(sqrt(n))。
- spacing   : 相邻 tile 之间的像素间隔。默认 0。
- margin    : sheet 边到第一个 tile 的像素距离。默认 0。
- tile_w / tile_h : 显式指定统一 tile 尺寸。默认 None = 取所有 tile 的最大宽高。
- pad_anchor: 把小 tile 补到统一尺寸时的锚点，可选 top-left / center / bottom-center 等。
              默认 center（居中，符合大多数直觉）。
- background: 间隔/边距/pad 处的填充色，默认透明。
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PIL import Image

from ..core.action import Action, Context
from ..core.registry import register
from .canvas_square import _ANCHORS, _anchor_offset


def _auto_columns(n: int) -> int:
    if n <= 0:
        return 1
    if n == 9:
        return 3                  # 3x3 tile 的自然形态
    return max(1, math.ceil(math.sqrt(n)))


@register("pack_sheet")
class PackSheetAction(Action):
    description = "把 tiles 拼成单张 sprite sheet PNG（供 Tiled 识别）"
    param_hints = {
        "path": {"widget": "filepath"},
        "pad_anchor": {"enum": sorted(_ANCHORS)},
        "spacing": {"min": 0, "step": 1},
        "margin": {"min": 0, "step": 1},
        "columns": {"min": 1, "step": 1},
        "tile_w": {"min": 1, "step": 1},
        "tile_h": {"min": 1, "step": 1},
        "background": {"widget": "rgba"},
    }

    def run(
        self,
        ctx: Context,
        path: str = "auto",
        columns: Optional[int] = None,
        spacing: int = 0,
        margin: int = 0,
        tile_w: Optional[int] = None,
        tile_h: Optional[int] = None,
        pad_anchor: str = "center",
        background: Tuple[int, int, int, int] = (0, 0, 0, 0),
    ) -> Context:
        tiles = ctx.extras.get("tiles")
        if not tiles:
            raise RuntimeError(
                "[pack_sheet] ctx.extras['tiles'] 为空。"
                "请先放一个会产出多图的 action（如 split_3x3 + for_each）。"
            )

        # 规格化：统一 tile 尺寸
        widths = [t.size[0] for t in tiles]
        heights = [t.size[1] for t in tiles]
        TW = int(tile_w) if tile_w else max(widths)
        TH = int(tile_h) if tile_h else max(heights)
        bg = self.normalize_color(background, channels=4)

        normalized = []
        any_resized = False
        for t in tiles:
            if t.mode != "RGBA":
                t = t.convert("RGBA")
            if t.size == (TW, TH):
                normalized.append(t)
                continue
            any_resized = True
            # 居中/锚点 pad；不缩放，保证像素无损
            canvas = Image.new("RGBA", (TW, TH), bg)
            ox, oy = _anchor_offset((TW, TH), t.size, pad_anchor)
            # 若原 tile 比目标大（tile_w/tile_h 指定得比 max 还小），crop 到目标
            if t.size[0] > TW or t.size[1] > TH:
                t = t.crop((0, 0, min(t.size[0], TW), min(t.size[1], TH)))
                ox = oy = 0
            canvas.alpha_composite(t, dest=(ox, oy))
            normalized.append(canvas)

        n = len(normalized)
        cols = int(columns) if columns else _auto_columns(n)
        cols = max(1, cols)
        rows = math.ceil(n / cols)

        sheet_w = margin * 2 + cols * TW + max(0, cols - 1) * spacing
        sheet_h = margin * 2 + rows * TH + max(0, rows - 1) * spacing

        sheet = Image.new("RGBA", (sheet_w, sheet_h), bg)
        for idx, tile in enumerate(normalized):
            r = idx // cols
            c = idx % cols
            x = margin + c * (TW + spacing)
            y = margin + r * (TH + spacing)
            sheet.alpha_composite(tile, dest=(x, y))

        # 解析输出路径
        if not path or path == "auto":
            # 没绝对路径的话落到 workdir/sheet.png；web 侧会在 server 预处理时重写
            out_path = (ctx.workdir / "sheet.png").resolve()
        else:
            out_path = Path(path).expanduser()
            if not out_path.is_absolute():
                out_path = (ctx.workdir / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(out_path)

        # 写入 sheet 元数据（给 build_tsx_sheet 用）
        sheet_meta: Dict[str, Any] = {
            "path": str(out_path),
            "sheet_w": sheet_w,
            "sheet_h": sheet_h,
            "tile_w": TW,
            "tile_h": TH,
            "columns": cols,
            "rows": rows,
            "spacing": spacing,
            "margin": margin,
            "tile_count": n,
            "tile_names": list(ctx.extras.get("tile_names") or []),
        }
        ctx.extras["sheet"] = sheet_meta
        ctx.meta["last_sheet"] = sheet_meta

        msg = (f"[pack_sheet] -> {out_path.name}  "
               f"{sheet_w}x{sheet_h}  tile={TW}x{TH}  "
               f"grid={cols}x{rows}  spacing={spacing} margin={margin} "
               f"count={n}")
        if any_resized:
            msg += f"  (pad anchor={pad_anchor})"
        print(msg)

        # 主图换成 sheet，方便预览
        return ctx.with_image(sheet)
