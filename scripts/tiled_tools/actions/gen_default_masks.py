"""gen_default_masks: 生成 16 张 wang 2-edge 几何蒙版。

用途：
  在画美术蒙版之前，先用几何蒙版跑通整条"蒙版混合 → sheet → tsx → Tiled"
  链路，验证边码约定、Edge Set 标记顺序都对，再去花时间画美术蒙版。

边码约定（4-bit N E S W）：
  bit 0 (=1)   N 边是 foreground (默认 sand)
  bit 1 (=2)   E 边是 foreground
  bit 2 (=4)   S 边是 foreground
  bit 3 (=8)   W 边是 foreground

  code 0  = 全 background (water)
  code 15 = 全 foreground (sand)

几何蒙版的画法（白 = foreground / sand，黑 = background / water）：
  对每条 fg 边，在该边附近一半画白；对 fg 角，在该角的扇形区域画白。
  最终对所有 "贡献区" 取并集（max），并按 feather 距离做边缘羽化。

输出：
  ctx.extras["tiles"] = 16 张蒙版（按 code 0..15 顺序，L 模式灰度图）
  ctx.extras["tile_names"] = ["mask_00", "mask_01", ..., "mask_15"]
  ctx.image = code 15（全白）当主图占位

后续可以接 `save_all` 写到磁盘当美术起稿模板，或者直接接 `mask_blend_set`。
"""
from __future__ import annotations

from typing import List

import numpy as np
from PIL import Image

from ..core.action import Action, Context
from ..core.registry import register


def _edge_field(size: int, edge: str, half_extent: float) -> np.ndarray:
    """生成单条"边贡献"灰度场（0..255 float），值越大表示越靠近 fg 边。

    half_extent: 蒙版"伸入" tile 内部的比例（0..1），决定过渡带宽度。
                 0.5 = 半张 tile，相邻 tile 对接处刚好补足。
    """
    # 归一化坐标 [0, 1]
    ys = np.linspace(0, 1, size, dtype=np.float32)
    xs = np.linspace(0, 1, size, dtype=np.float32)
    Y, X = np.meshgrid(ys, xs, indexing="ij")

    if edge == "N":
        d = 1.0 - Y                  # 越靠上越大
    elif edge == "S":
        d = Y
    elif edge == "W":
        d = 1.0 - X
    elif edge == "E":
        d = X
    else:
        raise ValueError(edge)

    # d ∈ [0,1]，>= (1 - half_extent) 的部分算贡献。线性渐变：
    t = (d - (1.0 - half_extent)) / max(1e-6, half_extent)
    t = np.clip(t, 0.0, 1.0)
    return t * 255.0


def _corner_field(size: int, corner: str, half_extent: float) -> np.ndarray:
    """生成相邻两条 fg 边夹角处的圆角贡献场。

    之前只叠加 N/E/S/W 四条边，会在 code 3/6/9/12 这类"拐角 tile"
    里形成直角块；整体拼成大图后四个角会显得没有被 mask 处理。
    这里额外给相邻 fg 边的公共角补一个四分之一圆渐变，让转角变成连续弧面。
    """
    ys = np.linspace(0, 1, size, dtype=np.float32)
    xs = np.linspace(0, 1, size, dtype=np.float32)
    Y, X = np.meshgrid(ys, xs, indexing="ij")

    if corner == "NW":
        dist = np.sqrt(X * X + Y * Y)
    elif corner == "NE":
        dist = np.sqrt((1.0 - X) * (1.0 - X) + Y * Y)
    elif corner == "SE":
        dist = np.sqrt((1.0 - X) * (1.0 - X) + (1.0 - Y) * (1.0 - Y))
    elif corner == "SW":
        dist = np.sqrt(X * X + (1.0 - Y) * (1.0 - Y))
    else:
        raise ValueError(corner)

    # half_extent=0.5 时，圆角半径刚好从角落延伸到 tile 中心附近。
    radius = max(1e-6, float(half_extent) * 2 ** 0.5)
    t = np.clip((radius - dist) / radius, 0.0, 1.0)
    # smoothstep，比线性边缘更自然。
    t = t * t * (3.0 - 2.0 * t)
    return t * 255.0


def _make_edge_mask(code: int, size: int, half_extent: float) -> Image.Image:
    """根据 4-bit 边码合成单张 Edge Set 蒙版（bit=N/E/S/W）。

    策略：对每条 fg 边算贡献场；对相邻 fg 边的公共角额外算圆角贡献场；
    最后取 max，避免重叠区域过曝，同时让拐角不再是生硬直角。
    """

    if code == 15:
        return Image.new("L", (size, size), 255)
    if code == 0:
        return Image.new("L", (size, size), 0)

    acc = np.zeros((size, size), dtype=np.float32)
    edges_on = []
    if code & 1: edges_on.append("N")
    if code & 2: edges_on.append("E")
    if code & 4: edges_on.append("S")
    if code & 8: edges_on.append("W")
    for e in edges_on:
        acc = np.maximum(acc, _edge_field(size, e, half_extent))

    # 相邻边同时为 fg 时，补对应公共角的圆角过渡。
    # 例：N+E(code 3) 补 NE；E+S(code 6) 补 SE。
    if (code & 1) and (code & 2):
        acc = np.maximum(acc, _corner_field(size, "NE", half_extent))
    if (code & 2) and (code & 4):
        acc = np.maximum(acc, _corner_field(size, "SE", half_extent))
    if (code & 4) and (code & 8):
        acc = np.maximum(acc, _corner_field(size, "SW", half_extent))
    if (code & 8) and (code & 1):
        acc = np.maximum(acc, _corner_field(size, "NW", half_extent))

    return Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8), mode="L")


def _make_corner_mask(code: int, size: int) -> Image.Image:
    """根据 4-bit 角码合成单张 Corner Set 蒙版（bit=TL/TR/BR/BL）。

    用四个角点的 terrain 值做双线性插值，得到连续、可平滑拼接的转角过渡。
    """
    if code == 15:
        return Image.new("L", (size, size), 255)
    if code == 0:
        return Image.new("L", (size, size), 0)

    tl = 1.0 if code & 1 else 0.0
    tr = 1.0 if code & 2 else 0.0
    br = 1.0 if code & 4 else 0.0
    bl = 1.0 if code & 8 else 0.0

    ys = np.linspace(0, 1, size, dtype=np.float32)
    xs = np.linspace(0, 1, size, dtype=np.float32)
    Y, X = np.meshgrid(ys, xs, indexing="ij")
    top = tl * (1.0 - X) + tr * X
    bottom = bl * (1.0 - X) + br * X
    acc = top * (1.0 - Y) + bottom * Y
    # smoothstep，避免纯线性过渡显得太硬。
    acc = acc * acc * (3.0 - 2.0 * acc)
    return Image.fromarray(np.clip(acc * 255.0, 0, 255).astype(np.uint8), mode="L")




@register("gen_default_masks")
class GenDefaultMasksAction(Action):
    description = (
        "生成 wang 几何蒙版：edge=16 张边缘集，corner=16 张转角集，"
        "both=32 张（先 edge 后 corner）。白=foreground，黑=background。"
    )
    param_hints = {
        "size": {"min": 8, "max": 1024, "step": 1},
        "half_extent": {"min": 0.1, "max": 1.0, "step": 0.05},
        "mode": {"enum": ["edge", "corner", "both"]},
    }

    def run(
        self,
        ctx: Context,
        size: int = 32,
        half_extent: float = 0.5,
        mode: str = "edge",
    ) -> Context:
        size = max(2, int(size))
        mode = (mode or "edge").lower()
        if mode not in ("edge", "corner", "both"):
            raise ValueError("[gen_default_masks] mode 应为 edge / corner / both")

        masks: List[Image.Image] = []
        names: List[str] = []
        if mode in ("edge", "both"):
            for code in range(16):
                masks.append(_make_edge_mask(code, size, float(half_extent)))
                names.append(f"edge_{code:02d}")
        if mode in ("corner", "both"):
            for code in range(16):
                masks.append(_make_corner_mask(code, size))
                names.append(f"corner_{code:02d}")

        ctx.image = masks[-1]
        ctx.extras["tiles"] = masks
        ctx.extras["tile_names"] = names
        ctx.extras["wang_masks"] = {"mode": mode, "size": size, "count": len(masks)}
        if mode in ("edge", "both"):
            ctx.extras["wang_2edge"] = {"size": size, "count": 16, "offset": 0}
        if mode in ("corner", "both"):
            ctx.extras["wang_2corner"] = {
                "size": size,
                "count": 16,
                "offset": 0 if mode == "corner" else 16,
            }
        print(f"[gen_default_masks] mode={mode} {len(masks)} 张 {size}x{size} 几何蒙版")
        return ctx

