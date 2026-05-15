"""mask_blend_set: 用蒙版混合两张底图，生成 wang 2-edge tile 集合。

公式：
  tile = foreground * mask + background * (1 - mask)

输入：
  - 参数 foreground: 一张图（文件路径或 file_id）。蒙版白色区域用它。
  - 参数 background: 一张图。蒙版黑色区域用它。
  - ctx.extras["tiles"]: 蒙版列表（L 或 RGBA，按 code 0..15 顺序）

行为约定：
  - tile 尺寸 = 第 0 张蒙版的尺寸。所有蒙版必须同尺寸。
  - 底图尺寸不必等于 tile 尺寸：用 resize 适配。对像素美术请把
    resample 设为 "nearest"。
  - 底图被当做可循环：先把底图 resize 到 tile 尺寸（最简单稳健的做法）。
    如果底图本来就是循环 tile，这步无损；如果不是，效果取决于素材。
  - 输出 ctx.image = code 15 那张（即纯 foreground），ctx.extras["tiles"]
    被替换为 16 张合成 tile，tile_names 保留（如 mask_00..mask_15 或
    用户自定义）。

后续接 `pack_sheet(cols=4)` → `build_tsx_sheet` 即可出 Tiled 可用的 wang set。
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import numpy as np
from PIL import Image

from ..core.action import Action, Context
from ..core.registry import register


_RESAMPLE = {
    "nearest": Image.NEAREST,
    "bilinear": Image.BILINEAR,
    "bicubic": Image.BICUBIC,
    "lanczos": Image.LANCZOS,
}


def _load_rgba(path: str) -> Image.Image:
    """加载图片为 RGBA。path 可能是文件路径或 server 的 file_id；
    server 在 _materialize_input_path 已经把 file_id 解析过了，
    所以这里只需当普通路径处理。"""
    p = Path(str(path)).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"找不到图片: {p}")
    im = Image.open(p)
    im.load()
    return im if im.mode == "RGBA" else im.convert("RGBA")


@register("mask_blend_set")
class MaskBlendSetAction(Action):
    description = (
        "用蒙版混合 foreground + background 两张底图，生成 wang 2-edge tile 集"
        "（默认 16 张，配合 gen_default_masks / load_dir 使用）"
    )
    param_hints = {
        "foreground": {"widget": "filepath"},
        "background": {"widget": "filepath"},
        "resample":   {"enum": ["nearest", "bilinear", "bicubic", "lanczos"]},
        "expected":   {"min": 0, "max": 256, "step": 1},
    }

    def run(
        self,
        ctx: Context,
        foreground: str,
        background: str,
        resample: str = "nearest",
        expected: int = 16,
    ) -> Context:
        masks: Optional[List[Image.Image]] = ctx.extras.get("tiles")
        if not masks:
            raise RuntimeError(
                "[mask_blend_set] ctx.extras['tiles'] 为空。"
                "请先用 gen_default_masks 或 load_dir 准备蒙版。"
            )
        if expected and len(masks) != expected:
            raise RuntimeError(
                f"[mask_blend_set] 期望 {expected} 张蒙版，实际 {len(masks)} 张。"
                "如确实需要不同数量，把 expected 设为 0 跳过这个检查。"
            )

        tile_w, tile_h = masks[0].size
        for i, m in enumerate(masks):
            if m.size != (tile_w, tile_h):
                raise RuntimeError(
                    f"[mask_blend_set] 蒙版 #{i} 尺寸 {m.size} 与首张 "
                    f"{(tile_w, tile_h)} 不一致，所有蒙版必须同尺寸"
                )

        rs = _RESAMPLE.get(resample.lower(), Image.NEAREST)
        fg = _load_rgba(foreground).resize((tile_w, tile_h), rs)
        bg = _load_rgba(background).resize((tile_w, tile_h), rs)

        fg_np = np.asarray(fg, dtype=np.float32)   # (H, W, 4)
        bg_np = np.asarray(bg, dtype=np.float32)

        out_tiles: List[Image.Image] = []
        for m in masks:
            # 蒙版统一成单通道 0..1
            m_l = m.convert("L")
            a = np.asarray(m_l, dtype=np.float32) / 255.0
            a = a[:, :, None]                       # (H, W, 1)
            blended = fg_np * a + bg_np * (1.0 - a)
            out_tiles.append(
                Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8),
                                mode="RGBA")
            )

        ctx.image = out_tiles[-1]  # code 15 = 全 fg 那张当占位
        ctx.extras["tiles"] = out_tiles
        # tile_names 沿用（如果存在），否则补一份默认
        if "tile_names" not in ctx.extras or len(ctx.extras["tile_names"]) != len(out_tiles):
            ctx.extras["tile_names"] = [f"wang_{i:02d}" for i in range(len(out_tiles))]
        print(
            f"[mask_blend_set] {len(out_tiles)} 张 tile, "
            f"tile_size={tile_w}x{tile_h}, resample={resample}"
        )
        return ctx
