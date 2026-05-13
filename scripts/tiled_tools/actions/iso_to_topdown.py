# -*- coding: utf-8 -*-
"""iso_to_topdown：把 iso 45° 视角的贴图反向变换回 topdown 视角。

这是 topdown_to_iso 的几何逆。正向链路是：
    topdown → square_canvas → rotate(+45°) → scale(sy=0.5)  → iso
逆向链路是：
    iso    → scale(sy=2.0)  → rotate(-45°) → trim          → topdown

两种典型用例
------------
1. **闭环验证 / 还原自己生成的 iso**：直接默认参数即可几乎无损还原
   （会有一次 bicubic 重采样的轻微模糊，pixel-art 改用 resample=nearest）。
2. **把第三方 iso 资产反推 topdown**：用户拿到一张已经画好的 iso 图，
   想反推出对应的 topdown footprint。这种情况下需要：
   - 适当调 y_scale（dimetric=2.0；60° 真等距≈1.732）
   - 通常加大 padding 避免旋转后裁掉边缘
   - 像素风务必 resample=nearest

为什么单独做一个 action
-----------------------
和 topdown_to_iso 对称，最常见用法一行就完。复杂场景仍可拆成 scale + rotate
两个原子 action 自己组合。

参数
----
- y_scale   : 高度反向缩放因子。**注意是"乘"不是"除"**。dimetric 反算用
              2.0（默认），60° 真等距用 1/0.5774 ≈ 1.732。
- angle     : 反向旋转角度，默认 -45（与正向 +45 对称）。
- resample  : 默认 "bicubic"；像素风改 "nearest"。
- trim      : 旋转后是否裁掉透明边，默认 True。
- pad_before_scale : 在 scale 之前先把画布加一圈 padding（像素），避免旋转
              后角被裁掉。默认 0（不加）；如果输入 iso 是紧贴边缘的，
              建议设 ≥ tile 尺寸的 1/4。
- background: 旋转/扩边的填充色，默认透明。
"""

from __future__ import annotations

from typing import Tuple

from PIL import Image

from ..core.action import Action, Context
from ..core.registry import register
from .rotate import RotateAction
from .scale import ScaleAction
from .topdown_to_iso import _trim_transparent


@register("iso_to_topdown")
class IsoToTopdownAction(Action):
    description = "Iso 45° 贴图 → Topdown 视角（topdown_to_iso 的几何逆）"
    param_hints = {
        "angle": {"min": -360, "max": 360, "step": 1},
        "y_scale": {"min": 0.5, "max": 4.0, "step": 0.01},
        "resample": {"enum": ["nearest", "bilinear", "bicubic", "lanczos"]},
        "pad_before_scale": {"min": 0, "step": 1},
        "background": {"widget": "rgba"},
    }

    def run(
        self,
        ctx: Context,
        y_scale: float = 2.0,
        angle: float = -45.0,
        expand: bool = True,
        resample: str = "bicubic",
        trim: bool = True,
        pad_before_scale: int = 0,
        background: Tuple[int, int, int, int] = (0, 0, 0, 0),
    ) -> Context:
        img = self.require_image(ctx, "iso_to_topdown")

        # 0) 可选先加 padding：用户提供的 iso 紧贴画布边缘时防角被裁。
        if pad_before_scale > 0:
            bg = self.normalize_color(background, channels=4)
            w, h = img.size
            p = int(pad_before_scale)
            canvas = Image.new(
                "RGBA",
                (w + 2 * p, h + 2 * p),
                bg,
            )
            canvas.alpha_composite(img.convert("RGBA"), dest=(p, p))
            print(f"[iso_to_topdown] pad {w}x{h} -> {canvas.size}  padding={p}")
            ctx = ctx.with_image(canvas)

        # 1) 高度反向拉伸（dimetric 默认 ×2，把 0.5 抵消回 1）
        ctx = ScaleAction().run(ctx, sy=y_scale, resample=resample)

        # 2) 反向旋转 -45°
        ctx = RotateAction().run(
            ctx, angle=angle, expand=expand,
            resample=resample, background=background,
        )

        # 3) 可选：裁透明边（旋转后四周必然有透明三角）
        if trim:
            img2 = self.require_image(ctx, "iso_to_topdown")
            trimmed = _trim_transparent(img2)
            if trimmed.size != img2.size:
                print(f"[iso_to_topdown] trim {img2.size} -> {trimmed.size}")
                ctx = ctx.with_image(trimmed)

        ctx.meta["topdown_restored"] = True
        return ctx
