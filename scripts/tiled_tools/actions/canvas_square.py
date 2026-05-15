# -*- coding: utf-8 -*-
"""square_canvas: 把图像放进指定画布（兼容旧的正方形用法）。

为什么要有这一步？
- topdown 贴图常见情况是宽高不等（例如 64x32 的菱形 footprint，或者 96x80
  的角色立绘）。直接旋转 45° 会让贴图被裁掉一角。
- 旋转前常用默认正方形画布（max(w,h)）；但很多批量素材 / footprint / UI 图块
  本身需要矩形画布，比如 96x48 的 iso footprint，所以这里也支持 width/height
  或 size=[w,h]。

参数：
- size       : int 表示正方形边长；[w,h] / "w,h" / "wxh" 表示矩形画布。
               默认 None = 取 max(w, h) 的正方形（保持历史行为）。
- width/height: 可显式指定矩形画布宽高；会覆盖 size 对应维度。
- anchor     : 原图在新画布里的锚点。可选：
                 "center"（默认）、"top-left"、"bottom-center"、"top-center"、
                 "bottom-left"...
               topdown 资源（人物/树木）一般 "bottom-center" 更合理，
               因为脚下中心是世界坐标参考点。
- background : 填充色（R,G,B,A）。默认透明 (0,0,0,0)。
"""


from __future__ import annotations

from typing import Any, Optional, Tuple


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


def _parse_size(size: Any, default: Tuple[int, int]) -> Tuple[int, int]:
    """解析画布尺寸。int=正方形；list/tuple/"w,h"/"wxh"=矩形。"""
    if size is None or size == "":
        return default
    if isinstance(size, (int, float)):
        side = max(1, int(size))
        return side, side
    if isinstance(size, (list, tuple)):
        if len(size) == 1:
            side = max(1, int(size[0]))
            return side, side
        if len(size) >= 2:
            return max(1, int(size[0])), max(1, int(size[1]))
    if isinstance(size, str):
        s = size.lower().replace("×", "x").replace(",", "x")
        parts = [p.strip() for p in s.split("x") if p.strip()]
        if len(parts) == 1:
            side = max(1, int(float(parts[0])))
            return side, side
        if len(parts) >= 2:
            return max(1, int(float(parts[0]))), max(1, int(float(parts[1])))
    raise TypeError(f"[square_canvas] 无法解析 size: {size!r}")


@register("square_canvas")
class SquareCanvasAction(Action):
    description = "把图像放进指定画布（默认正方形；也支持矩形 width/height 或 size=[w,h]）"
    param_hints = {
        "anchor": {"enum": sorted(_ANCHORS)},
        "background": {"widget": "rgba"},
        "width": {"min": 1, "step": 1},
        "height": {"min": 1, "step": 1},
    }

    def run(
        self,
        ctx: Context,
        size: Optional[Any] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        anchor: str = "center",
        background: Tuple[int, int, int, int] = (0, 0, 0, 0),
    ) -> Context:
        img = self.require_image(ctx, "square_canvas")
        w, h = img.size
        cw, ch = _parse_size(size, default=(max(w, h), max(w, h)))
        if width:
            cw = max(1, int(width))
        if height:
            ch = max(1, int(height))

        if w == cw and h == ch:
            print(f"[square_canvas] 已是 {cw}x{ch}，跳过")
            return ctx

        bg = self.normalize_color(background, channels=4)
        canvas = Image.new("RGBA", (cw, ch), bg)
        ox, oy = _anchor_offset((cw, ch), (w, h), anchor)

        # 如果目标画布比原图小，按 anchor 进行裁切；比直接 alpha_composite 更稳。
        src_x = max(0, -ox)
        src_y = max(0, -oy)
        dst_x = max(0, ox)
        dst_y = max(0, oy)
        paste_w = min(w - src_x, cw - dst_x)
        paste_h = min(h - src_y, ch - dst_y)
        if paste_w > 0 and paste_h > 0:
            cropped = img.crop((src_x, src_y, src_x + paste_w, src_y + paste_h))
            if cropped.mode != "RGBA":
                cropped = cropped.convert("RGBA")
            canvas.alpha_composite(cropped, dest=(dst_x, dst_y))

        ctx.meta["canvas_size"] = (cw, ch)
        if cw == ch:
            ctx.meta["square_size"] = cw  # 兼容旧 meta
        print(f"[square_canvas] {w}x{h} -> {cw}x{ch}  anchor={anchor}")
        return ctx.with_image(canvas)

