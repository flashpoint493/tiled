# -*- coding: utf-8 -*-
"""topdown_to_iso: 把 topdown 视角的贴图转换成 iso (45°) 视角。

实现就是 square_canvas + rotate(45) + scale(sy=0.5) 的复合体，但作为单独
action 暴露，方便最常见用法。

参数：
- anchor    : 透传给 square_canvas（默认 "bottom-center"，最适合人物/物件
              站立的情形；如果是地面 tile 推荐用 "center"）。
- angle     : 旋转角度，默认 45。
- y_scale   : 旋转后高度压缩比例。标准菱形 iso 是 0.5，
              "2:1 像素 iso"（dimetric）也是 0.5；改成 0.577 可以拟合 60°
              真等距。
- expand    : 旋转时是否扩画布，默认 True。
- resample  : 默认 "bicubic"；像素风可改 "nearest"。
- trim      : 是否在最后裁掉透明边（保持画布最小），默认 True。
"""

from __future__ import annotations

from typing import Tuple

from PIL import Image, ImageChops

from ..core.action import Action, Context
from ..core.registry import register
from .canvas_square import SquareCanvasAction
from .rotate import RotateAction
from .scale import ScaleAction


def _trim_transparent(img: Image.Image) -> Image.Image:
    """裁掉四周完全透明的留白。"""
    if img.mode != "RGBA":
        return img
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    if bbox is None:
        return img
    if bbox == (0, 0, img.width, img.height):
        return img
    return img.crop(bbox)


@register("topdown_to_iso")
class TopdownToIsoAction(Action):
    description = "Topdown 贴图 → Iso 45° 视角（square + rotate45 + scale + trim）"
    param_hints = {
        "anchor": {
            "enum": [
                "top-left", "top-center", "top-right",
                "center-left", "center", "center-right",
                "bottom-left", "bottom-center", "bottom-right",
            ],
        },
        "angle": {"min": -360, "max": 360, "step": 1},
        "y_scale": {"min": 0.1, "max": 2.0, "step": 0.01},
        "resample": {"enum": ["nearest", "bilinear", "bicubic", "lanczos"]},
        "background": {"widget": "rgba"},
    }

    def run(
        self,
        ctx: Context,
        anchor: str = "bottom-center",
        angle: float = 45.0,
        y_scale: float = 0.5,
        expand: bool = True,
        resample: str = "bicubic",
        trim: bool = True,
        background: Tuple[int, int, int, int] = (0, 0, 0, 0),
    ) -> Context:
        # 1) 正方化（防止旋转裁角）
        ctx = SquareCanvasAction().run(
            ctx, anchor=anchor, background=background,
        )
        # 2) 旋转 45°
        ctx = RotateAction().run(
            ctx, angle=angle, expand=expand,
            resample=resample, background=background,
        )
        # 3) 高度压扁
        ctx = ScaleAction().run(ctx, sy=y_scale, resample=resample)

        # 4) 可选：裁透明边
        if trim:
            img = self.require_image(ctx, "topdown_to_iso")
            trimmed = _trim_transparent(img)
            if trimmed.size != img.size:
                print(f"[topdown_to_iso] trim {img.size} -> {trimmed.size}")
                ctx = ctx.with_image(trimmed)

        ctx.meta["iso_converted"] = True
        return ctx
