"""load_dir: 从目录批量加载图片到 ctx.extras["tiles"]。

典型用途：
  读 16 张美术画好的蒙版给 mask_blend_set 用。

参数：
  path: 目录路径（绝对，或相对当前 CWD）
  pattern: glob 模式，默认 "*.png"
  sort: 是否按文件名排序（默认 True，保证顺序稳定）
  limit: 最多读多少张（0 = 不限）

输出：
  ctx.extras["tiles"] = [PIL.Image, ...]
  ctx.extras["tile_names"] = [文件 stem, ...]
  ctx.image 设为第 0 张当占位
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from PIL import Image

from ..core.action import Action, Context
from ..core.registry import register


@register("load_dir")
class LoadDirAction(Action):
    description = "从目录批量加载图片到 ctx.extras['tiles']（按文件名排序）"
    param_hints = {
        "path": {"widget": "filepath"},
        "limit": {"min": 0, "max": 256, "step": 1},
    }

    def run(
        self,
        ctx: Context,
        path: str,
        pattern: str = "*.png",
        sort: bool = True,
        limit: int = 0,
    ) -> Context:
        d = Path(str(path)).expanduser()
        if not d.is_absolute():
            d = (Path.cwd() / d).resolve()
        if not d.is_dir():
            raise FileNotFoundError(f"[load_dir] 目录不存在: {d}")

        files = [p for p in d.glob(pattern) if p.is_file()]
        if sort:
            files.sort(key=lambda p: p.name)
        if limit and limit > 0:
            files = files[:limit]
        if not files:
            raise RuntimeError(
                f"[load_dir] {d} 中没有匹配 {pattern!r} 的图片"
            )

        tiles: List[Image.Image] = []
        names: List[str] = []
        for f in files:
            im = Image.open(f)
            im.load()  # 立刻读到内存，避免后续句柄问题
            tiles.append(im)
            names.append(f.stem)

        ctx.image = tiles[0]
        ctx.extras["tiles"] = tiles
        ctx.extras["tile_names"] = names
        ctx.extras["load_dir"] = {"path": str(d), "count": len(tiles)}
        print(f"[load_dir] {d}  匹配 {pattern!r}  共 {len(tiles)} 张")
        return ctx
