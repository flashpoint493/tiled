# -*- coding: utf-8 -*-
"""build_tsx_sheet：基于 ctx.extras["sheet"] 生成 Tiled 可识别的 .tsx。

与已有的 collection 版 build_tsx.py 的区别：
- build_tsx.py  ：Collection of Images（每 tile 一张独立图，tsx 里用
                  <tile><image source=".."/></tile> 列出所有图）。
- 本 action     ：Based on Tileset Image（一张 sheet 大图 + 网格参数，
                  tsx 顶层 <image source="sheet.png"> + tilewidth/columns/...）。

二者产物都能被 Tiled 直接 File→Open；但后者性能更好、渲染更快，适合
有序的自动图块集、角色帧、iso 拼图等场景。

参数
----
- path        : 输出 .tsx 路径。默认 "auto" = sheet 同名 .tsx。
                web 模式下相对路径会落到 sheet 所在目录，保持 <image source>
                的相对路径就是文件名。
- name        : <tileset name="..."/>，默认 = sheet 文件的 stem。
- tile_names  : 是否给每个 tile 加 <tile id="n"><properties>...
                把 sheet.tile_names（如 NW/N/NE...）写进去做成命名属性。
                默认 True（便于在 Tiled 里通过名字选 tile）。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional
from xml.sax.saxutils import escape as xml_escape

from ..core.action import Action, Context
from ..core.registry import register


TILED_VERSION = "1.11"
TSX_VERSION = "1.10"


@register("build_tsx_sheet")
class BuildTsxSheetAction(Action):
    description = "为 pack_sheet 产出的 sheet 生成 Tiled 可识别的 .tsx"
    param_hints = {
        "path": {"widget": "filepath"},
    }

    def run(
        self,
        ctx: Context,
        path: str = "auto",
        name: Optional[str] = None,
        tile_names: bool = True,
    ) -> Context:
        sheet: Dict[str, Any] = ctx.extras.get("sheet")
        if not sheet:
            raise RuntimeError(
                "[build_tsx_sheet] ctx.extras['sheet'] 为空。"
                "请先放一个 pack_sheet 步骤。"
            )

        sheet_path = Path(sheet["path"]).resolve()
        tile_w = int(sheet["tile_w"])
        tile_h = int(sheet["tile_h"])
        cols = int(sheet["columns"])
        spacing = int(sheet.get("spacing") or 0)
        margin = int(sheet.get("margin") or 0)
        tile_count = int(sheet["tile_count"])
        sheet_w = int(sheet["sheet_w"])
        sheet_h = int(sheet["sheet_h"])
        names = sheet.get("tile_names") or []

        # 解析 tsx 输出位置
        if not path or path == "auto":
            tsx_path = sheet_path.with_suffix(".tsx")
        else:
            tsx_path = Path(path).expanduser()
            if not tsx_path.is_absolute():
                tsx_path = (sheet_path.parent / tsx_path).resolve()
        tsx_path.parent.mkdir(parents=True, exist_ok=True)

        # <image source=".."> 相对 tsx 所在目录
        rel = os.path.relpath(sheet_path, start=tsx_path.parent)
        rel_posix = rel.replace(os.sep, "/")

        tsx_name = name or tsx_path.stem

        lines = []
        lines.append('<?xml version="1.0" encoding="UTF-8"?>')
        attrs = [
            f'version="{TSX_VERSION}"',
            f'tiledversion="{TILED_VERSION}"',
            f'name="{xml_escape(tsx_name)}"',
            f'tilewidth="{tile_w}"',
            f'tileheight="{tile_h}"',
            f'tilecount="{tile_count}"',
            f'columns="{cols}"',
        ]
        if spacing:
            attrs.insert(-1, f'spacing="{spacing}"')
        if margin:
            attrs.insert(-1, f'margin="{margin}"')
        lines.append("<tileset " + " ".join(attrs) + ">")
        lines.append(
            f' <image source="{xml_escape(rel_posix)}" '
            f'width="{sheet_w}" height="{sheet_h}"/>'
        )

        # 为每个 tile 写一个带命名属性的 <tile>，方便在 Tiled 里用名字选
        if tile_names and names:
            for i in range(tile_count):
                label = names[i] if i < len(names) else ""
                if not label:
                    continue
                lines.append(f' <tile id="{i}">')
                lines.append('  <properties>')
                lines.append(
                    f'   <property name="name" value="{xml_escape(str(label))}"/>'
                )
                lines.append('  </properties>')
                lines.append(' </tile>')

        lines.append("</tileset>")
        tsx_xml = "\n".join(lines) + "\n"
        tsx_path.write_text(tsx_xml, encoding="utf-8")

        ctx.extras["tsx"] = {
            "path": str(tsx_path),
            "name": tsx_name,
            "sheet_path": str(sheet_path),
        }
        ctx.meta["last_tsx"] = str(tsx_path)
        print(
            f"[build_tsx_sheet] -> {tsx_path.name}  "
            f"name={tsx_name}  tile={tile_w}x{tile_h}  "
            f"cols={cols}  count={tile_count}"
        )
        return ctx  # 不改 ctx.image
