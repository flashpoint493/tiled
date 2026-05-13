# -*- coding: utf-8 -*-
"""rotate: 旋转图像。

参数：
- angle    : 角度（逆时针为正，与 PIL 一致）。topdown→iso45 用 45 即可。
- expand   : True 时画布扩大以容纳旋转后的全部像素；False 保留原尺寸。
- resample : "bicubic"（默认）/ "bilinear" / "nearest"。
             像素风资源若想保留硬边可以用 "nearest"。
- background: 旋转留白处的填充色。默认透明。
"""

from __future__ import annotations

from typing import Tuple

from PIL import Image

from ..core.action import Action, Context
from ..core.registry import register


_RESAMPLE = {
    "nearest": Image.NEAREST,
    "bilinear": Image.BILINEAR,
    "bicubic": Image.BICUBIC,
    "lanczos": Image.LANCZOS,
}


@register("rotate")
class RotateAction(Action):
    description = "旋转图像，可选是否扩画布"
    param_hints = {
        "angle": {"min": -360, "max": 360, "step": 1},
        "resample": {"enum": ["nearest", "bilinear", "bicubic", "lanczos"]},
        "background": {"widget": "rgba"},
    }

    def run(
        self,
        ctx: Context,
        angle: float = 45.0,
        expand: bool = True,
        resample: str = "bicubic",
        background: Tuple[int, int, int, int] = (0, 0, 0, 0),
    ) -> Context:
        img = self.require_image(ctx, "rotate")
        rs = _RESAMPLE.get(resample.lower())
        if rs is None:
            raise ValueError(f"[rotate] 未知 resample: {resample}")

        rotated = img.rotate(
            angle,
            resample=rs,
            expand=expand,
            fillcolor=self.normalize_color(background, channels=4),
        )
        ctx.meta["last_rotation"] = angle
        print(f"[rotate] angle={angle}  expand={expand}  "
              f"size {img.size} -> {rotated.size}")
        return ctx.with_image(rotated)
