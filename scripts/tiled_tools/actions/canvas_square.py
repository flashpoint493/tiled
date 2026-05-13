# -*- coding: utf-8 -*-
"""square_canvas: 把图像扩成正方形画布。

为什么要有这一步？
- topdown 贴图常见情况是宽高不等（例如 64x32 的菱形 footprint，或者 96x80
  的角色立绘）。直接旋转 45° 会让贴图被裁掉一角。
- 先把短边补齐到长边，所有像素都不会丢失，再旋转就稳了。

参数：
- size       : 目标正方形边长。默认 None = 取 max(w, h)。
- anchor     : 原图在新画布里的锚点。可选：
                 "center"（默认）、"top-left"、"bottom-center"、"top-center"、
                 "bottom-left"...
               topdown 资源（人物/树木）一般 "bottom-center" 更合理，
               因为脚下中心是世界坐标参考点。
- background : 填充色（R,G,B,A）。默认透明 (0,0,0,0)。
"""

from __future__ import annotations

from typing import Optional, Tuple

from PIL import Image

from ..core.action import Action, Context
from ..core.registry import register


_ANCHORS = {
    "top-left", "top-center", "top-right",
    "center-left", "center", "center-right",
    "bottom-left", "bottom-center", "bottom-right",
}


def _anchor_offset(
    canvas: Tuple[int, int],
    inner: Tuple[int, int],
    anchor: str,
) -> Tuple[int, int]:
    cw, ch = canvas
    iw, ih = inner
    if anchor not in _ANCHORS:
        raise ValueError(f"[square_canvas] 未知 anchor: {anchor}")
    vert, horz = anchor.split("-") if "-" in anchor else (anchor, anchor)

    if horz == "left":
        x = 0
    elif horz == "right":
        x = cw - iw
    else:  # center
        x = (cw - iw) // 2

    if vert == "top":
        y = 0
    elif vert == "bottom":
        y = ch - ih
    else:  # center
        y = (ch - ih) // 2
    return x, y


@register("square_canvas")
class SquareCanvasAction(Action):
    description = "把图像扩成正方形画布（旋转前预处理）"
    param_hints = {
        "anchor": {"enum": sorted(_ANCHORS)},
        "background": {"widget": "rgba"},
    }

    def run(
        self,
        ctx: Context,
        size: Optional[int] = None,
        anchor: str = "center",
        background: Tuple[int, int, int, int] = (0, 0, 0, 0),
    ) -> Context:
        img = self.require_image(ctx, "square_canvas")
        w, h = img.size
        side = size if size else max(w, h)

        if w == side and h == side:
            print(f"[square_canvas] 已是 {side}x{side}，跳过")
            return ctx

        bg = self.normalize_color(background, channels=4)
        canvas = Image.new("RGBA", (side, side), bg)
        ox, oy = _anchor_offset((side, side), (w, h), anchor)
        canvas.alpha_composite(img, dest=(ox, oy))
        ctx.meta["square_size"] = side
        print(f"[square_canvas] {w}x{h} -> {side}x{side}  anchor={anchor}")
        return ctx.with_image(canvas)
