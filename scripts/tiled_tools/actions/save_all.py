# -*- coding: utf-8 -*-
"""save_all：把 ctx.extras["tiles"] 里的多张图批量保存。

适用任何"上一步产出多张图"的 action（split_3x3、未来的 split_grid…）。

参数
----
- dir       : 输出目录。绝对路径直接用；相对路径 web 模式下走当前工作目录的运行时 outputs。
              CLI 模式下相对 cwd。默认 None = 直接放到 ctx.workdir。
- prefix    : 文件名前缀。例如 prefix="grass" 会得到 grass_NW.png 等。
              默认空 = 用 source_path.stem 当前缀；都没有就用 "tile"。
- pattern   : 文件名模板。可用占位符：{prefix} {name} {idx} {idx2}。
              默认 "{prefix}_{name}.png"，例如 "grass_NW.png"。
              没有 tile_names 时换成用 idx，例如 "grass_001.png"。
- format    : 不指定按扩展名推断。
- overwrite : 默认 True。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ..core.action import Action, Context
from ..core.registry import register


@register("save_all")
class SaveAllAction(Action):
    description = "批量保存上一步产生的多张图（消费 ctx.extras['tiles']）"
    param_hints = {
        "dir": {"widget": "filepath"},
        "format": {"enum": ["", "PNG", "WEBP", "JPEG"]},
    }

    def run(
        self,
        ctx: Context,
        dir: Optional[str] = None,
        prefix: str = "",
        pattern: str = "{prefix}_{name}.png",
        format: Optional[str] = None,
        overwrite: bool = True,
    ) -> Context:
        tiles = ctx.extras.get("tiles")
        if not tiles:
            raise RuntimeError(
                "[save_all] ctx.extras['tiles'] 为空。"
                "请先放一个会产出多图的 action（如 split_3x3）。"
            )
        names = ctx.extras.get("tile_names") or []

        # 解析输出目录
        if dir:
            out_dir = Path(dir).expanduser()
            if not out_dir.is_absolute():
                # 走 cwd 而不是 workdir，和 SaveAction 保持一致的直觉
                out_dir = (Path.cwd() / out_dir).resolve()
        else:
            out_dir = ctx.workdir
        out_dir.mkdir(parents=True, exist_ok=True)

        # 解析前缀
        eff_prefix = prefix
        if not eff_prefix:
            src = ctx.meta.get("source_path")
            eff_prefix = Path(src).stem if src else "tile"

        save_kwargs = {}
        if format:
            save_kwargs["format"] = format

        saved: List[Path] = []
        for i, img in enumerate(tiles):
            name = names[i] if i < len(names) else f"{i + 1:03d}"
            filename = pattern.format(
                prefix=eff_prefix,
                name=name,
                idx=i + 1,
                idx2=f"{i + 1:02d}",
            )
            out_path = out_dir / filename

            if out_path.exists() and not overwrite:
                print(f"[save_all] 跳过已存在: {out_path.name}")
                continue
            img.save(out_path, **save_kwargs)
            saved.append(out_path)
            print(f"[save_all] -> {out_path.name}  size={img.size}")

        ctx.extras["saved_paths"] = saved
        ctx.meta["last_saved_all"] = saved
        print(f"[save_all] 共保存 {len(saved)} 张到 {out_dir}")
        return ctx
