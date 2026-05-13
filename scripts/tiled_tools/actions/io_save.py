# -*- coding: utf-8 -*-
"""save: 把 ctx.image 写到磁盘。

参数：
- path     : 输出文件路径。支持相对路径（相对 ctx.workdir）。
- suffix   : 当 path 没显式给时，基于 source_path 加后缀生成，
             例如 source_path = a.png, suffix = "_iso" → a_iso.png。
- format   : 不指定则按扩展名推断；常见 "PNG"、"WEBP"。
- overwrite: 默认 True。False 时若文件存在会跳过。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..core.action import Action, Context
from ..core.registry import register


@register("save")
class SaveAction(Action):
    description = "保存当前图像到磁盘"
    param_hints = {
        "path": {"widget": "filepath"},
        "format": {"enum": ["", "PNG", "WEBP", "JPEG"]},
    }

    def run(
        self,
        ctx: Context,
        path: Optional[str | Path] = None,
        suffix: str = "_out",
        format: Optional[str] = None,
        overwrite: bool = True,
    ) -> Context:
        img = self.require_image(ctx, "save")

        if path is None:
            src = ctx.meta.get("source_path")
            if src is None:
                raise ValueError(
                    "[save] 既没有 path 参数，meta 里也没有 source_path，"
                    "无法推断输出位置。"
                )
            src = Path(src)
            out_path = src.with_name(f"{src.stem}{suffix}{src.suffix}")
        else:
            out_path = Path(path)
            if not out_path.is_absolute():
                # 相对路径默认相对当前进程的 CWD（最符合命令行直觉），
                # 这样 `python -m tiled_tools ... -v output=output/foo.png`
                # 写出的就是 `<cwd>/output/foo.png`。
                out_path = (Path.cwd() / out_path).resolve()

        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.exists() and not overwrite:
            print(f"[save] 已存在且 overwrite=False，跳过: {out_path}")
            return ctx

        save_kwargs = {}
        if format:
            save_kwargs["format"] = format
        img.save(out_path, **save_kwargs)
        ctx.meta["last_saved"] = out_path
        print(f"[save] -> {out_path}  size={img.size}")
        return ctx
