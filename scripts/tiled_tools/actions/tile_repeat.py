"""tile_repeat: 把单张图按 N×M 网格平铺成一张大图。

典型用途：
- 验证循环 tile 是否真的无缝（肉眼看 3×3 拼出来是否有缝）
- 给美术做"铺地"成品预览
- 把单 tile 直接贴成大块材质

输入：ctx.image（单张贴图）
输出：ctx.image 替换为平铺后的大图；
      ctx.extras["tile_repeat"] = {cols, rows, tile_w, tile_h, gap}

跟 pack_sheet 的区别：
- pack_sheet: 多张 tiles → 拼成一张 sheet（每格不同图）
- tile_repeat: 1 张 tile → 自我复制 N×M 份（每格同一张图）
"""
from __future__ import annotations

from typing import Optional

from PIL import Image

from ..core.action import Action, Context
from ..core.registry import register


@register("tile_repeat")
class TileRepeatAction(Action):
    description = "把单张贴图按 N×M 网格平铺复制成一张大图（验证循环 / 铺地预览）"
    param_hints = {
        "cols": {"min": 1, "max": 64, "step": 1},
        "rows": {"min": 1, "max": 64, "step": 1},
        "count": {"min": 0, "max": 64, "step": 1},
        "gap": {"min": 0, "max": 64, "step": 1},
        "background": {"widget": "rgba"},
    }

    def run(
        self,
        ctx: Context,
        cols: int = 3,
        rows: int = 3,
        count: Optional[int] = None,
        gap: int = 0,
        background=(0, 0, 0, 0),
    ) -> Context:
        img = self.require_image(ctx, "tile_repeat")

        # count 是 cols/rows 的便捷写法：count=3 等价于 cols=3, rows=3
        # 适合用户只想说"3×3"或"5×5"的场景；> 0 时覆盖 cols/rows。
        if count and count > 0:
            cols = rows = int(count)

        cols = max(1, int(cols))
        rows = max(1, int(rows))
        gap = max(0, int(gap))

        tile_w, tile_h = img.size
        if tile_w == 0 or tile_h == 0:
            raise ValueError("[tile_repeat] 输入图尺寸为 0，无法平铺")

        # 大图尺寸 = N 张 tile + (N-1) 段 gap
        out_w = cols * tile_w + max(0, cols - 1) * gap
        out_h = rows * tile_h + max(0, rows - 1) * gap

        bg = self.normalize_color(background, channels=4)
        canvas = Image.new("RGBA", (out_w, out_h), bg)

        # 保证 alpha 通道正确合成（否则 RGB 输入会盖掉透明背景）
        tile_rgba = img if img.mode == "RGBA" else img.convert("RGBA")

        for r in range(rows):
            for c in range(cols):
                x = c * (tile_w + gap)
                y = r * (tile_h + gap)
                canvas.paste(tile_rgba, (x, y), tile_rgba)

        ctx.image = canvas
        ctx.extras["tile_repeat"] = {
            "cols": cols,
            "rows": rows,
            "tile_w": tile_w,
            "tile_h": tile_h,
            "gap": gap,
        }

        print(
            f"[tile_repeat] {tile_w}x{tile_h} -> {out_w}x{out_h}  "
            f"grid={cols}x{rows}  gap={gap}"
        )
        return ctx
