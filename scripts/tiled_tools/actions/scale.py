# -*- coding: utf-8 -*-
"""scale: 缩放图像，支持非等比。

参数（按优先级）：
- size      : (w, h) 直接指定目标像素尺寸。
- sx / sy   : 各自的缩放系数。比如 sy=0.5 = 把高度压成一半（iso 视角必用）。
- factor    : 等比缩放系数（同时设给 sx 和 sy）。
- resample  : 同 rotate。
"""

from __future__ import annotations

from typing import Optional, Tuple

from PIL import Image

from ..core.action import Action, Context
from ..core.registry import register


_RESAMPLE = {
    "nearest": Image.NEAREST,
    "bilinear": Image.BILINEAR,
    "bicubic": Image.BICUBIC,
    "lanczos": Image.LANCZOS,
}


@register("scale")
class ScaleAction(Action):
    description = "缩放图像，支持非等比（sx/sy）或直接给 size"
    param_hints = {
        "resample": {"enum": ["nearest", "bilinear", "bicubic", "lanczos"]},
    }

    def run(
        self,
        ctx: Context,
        size: Optional[Tuple[int, int]] = None,
        sx: Optional[float] = None,
        sy: Optional[float] = None,
        factor: Optional[float] = None,
        resample: str = "bicubic",
    ) -> Context:
        img = self.require_image(ctx, "scale")
        rs = _RESAMPLE.get(resample.lower())
        if rs is None:
            raise ValueError(f"[scale] 未知 resample: {resample}")

        w, h = img.size
        if size is not None:
            tw, th = int(size[0]), int(size[1])
        else:
            fx = sx if sx is not None else (factor if factor is not None else 1.0)
            fy = sy if sy is not None else (factor if factor is not None else 1.0)
            tw = max(1, int(round(w * fx)))
            th = max(1, int(round(h * fy)))

        if (tw, th) == (w, h):
            print(f"[scale] 目标尺寸与原图一致 {w}x{h}，跳过")
            return ctx

        out = img.resize((tw, th), resample=rs)
        print(f"[scale] {w}x{h} -> {tw}x{th}  resample={resample}")
        return ctx.with_image(out)
