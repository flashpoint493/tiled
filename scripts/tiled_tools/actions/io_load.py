# -*- coding: utf-8 -*-
"""load: 从磁盘加载图片到 ctx.image，并把来源信息写入 meta。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from ..core.action import Action, Context
from ..core.registry import register


@register("load")
class LoadAction(Action):
    description = "从磁盘读取图片（或 server 上传后的临时 id）"
    param_hints = {
        "path": {"widget": "filepath"},
    }

    def run(self, ctx: Context, path: str | Path) -> Context:
        p = Path(path).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(f"[load] 找不到输入文件: {p}")
        img = Image.open(p).convert("RGBA")
        ctx.meta["source_path"] = p
        ctx.meta["source_size"] = img.size
        # 默认 workdir = 输入文件所在目录，方便 save 写相对路径
        ctx.workdir = p.parent
        print(f"[load] {p}  size={img.size}")
        return ctx.with_image(img)
