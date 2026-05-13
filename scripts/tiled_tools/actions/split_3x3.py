# -*- coding: utf-8 -*-
"""split_3x3：把"循环边界 tile"图按 3×3 拆成 9 张子贴图。

适用场景
--------
循环 tile（auto-tile / wang tile 边界集）的特征：把贴图均分成 3×3 九块后，
- 中央那块（C）可以自身平铺，得到一片无缝填充；
- 外围 8 块（NW/N/NE/W/E/SW/S/SE）用于在边界处替换中央图，
  让填充区域和邻居拼接时不会有撕裂。

所以这个 action 仅对"3×3 循环 tile"图有意义。普通 sprite 别用。

切法
----
- mode = "equal"：把宽高均分 3 等份，向最近整数取整。源图随便多大都能切。
  最常见，对应"作者按规则画的 3×3 大图"。
- mode = "border"：外圈厚度 = border 像素，中央占剩余区域。常用于像素美术
  指定"边框 16px、中心 32px"这种明确规格。

产物
----
- ctx.image       = 中央块 C（方便 pipeline 后续继续处理它，比如直接 iso 化）
- ctx.extras["tiles_3x3"] = {
      "NW": Image, "N": Image, "NE": Image,
      "W":  Image, "C": Image, "E":  Image,
      "SW": Image, "S": Image, "SE": Image,
  }
- ctx.extras["tiles"]   = 上面 9 张的有序列表（行优先），供 save_all 消费
- ctx.extras["tile_names"] = 与 tiles 对应的名字列表，save_all 用它生成文件名
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from PIL import Image

from ..core.action import Action, Context
from ..core.registry import register


# 行优先：[NW, N, NE, W, C, E, SW, S, SE]
_NAMES_3x3: List[str] = [
    "NW", "N", "NE",
    "W",  "C", "E",
    "SW", "S", "SE",
]


def _equal_grid(w: int, h: int) -> Tuple[List[int], List[int]]:
    """均分成 3 段。返回 4 个 x 切点和 4 个 y 切点（含两端）。"""
    xs = [round(w * i / 3) for i in range(4)]
    ys = [round(h * i / 3) for i in range(4)]
    return xs, ys


def _border_grid(w: int, h: int, border: int) -> Tuple[List[int], List[int]]:
    """外圈厚度 = border。检查中心至少 1px。"""
    if border <= 0:
        raise ValueError("[split_3x3] mode=border 时 border 必须为正整数")
    if 2 * border >= w or 2 * border >= h:
        raise ValueError(
            f"[split_3x3] border={border} 太大，源图 {w}x{h} 中央会变成 0 像素"
        )
    xs = [0, border, w - border, w]
    ys = [0, border, h - border, h]
    return xs, ys


@register("split_3x3")
class Split3x3Action(Action):
    description = "把 3x3 循环 tile 图拆成 9 张（NW/N/NE/W/C/E/SW/S/SE）"
    param_hints = {
        "mode": {"enum": ["equal", "border"]},
        "border": {"min": 0, "step": 1},
    }

    def run(
        self,
        ctx: Context,
        mode: str = "equal",
        border: int = 0,
    ) -> Context:
        img = self.require_image(ctx, "split_3x3")
        # 统一 RGBA，避免下游做 alpha 操作时出错
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        w, h = img.size

        if mode == "equal":
            xs, ys = _equal_grid(w, h)
        elif mode == "border":
            xs, ys = _border_grid(w, h, border)
        else:
            raise ValueError(f"[split_3x3] 未知 mode: {mode}")

        tiles_dict: Dict[str, Image.Image] = {}
        tiles_list: List[Image.Image] = []
        sizes: List[Tuple[int, int]] = []
        idx = 0
        for r in range(3):
            for c in range(3):
                box = (xs[c], ys[r], xs[c + 1], ys[r + 1])
                piece = img.crop(box)
                name = _NAMES_3x3[idx]
                tiles_dict[name] = piece
                tiles_list.append(piece)
                sizes.append(piece.size)
                idx += 1

        ctx.extras["tiles_3x3"] = tiles_dict
        ctx.extras["tiles"] = tiles_list
        ctx.extras["tile_names"] = list(_NAMES_3x3)
        ctx.meta["split_3x3_mode"] = mode
        if mode == "border":
            ctx.meta["split_3x3_border"] = border

        print(
            f"[split_3x3] mode={mode}"
            + (f" border={border}" if mode == "border" else "")
            + f"  源 {w}x{h} -> 9 块，"
            + " ".join(f"{n}={s[0]}x{s[1]}" for n, s in zip(_NAMES_3x3, sizes))
        )

        # 主输出设为中央块 C，方便链式继续处理它
        return ctx.with_image(tiles_dict["C"])
