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
- grid_orientation / grid_width / grid_height:
                可选写入 <grid orientation="isometric" width="..." height="..."/>，
                让 Tiled 在 tileset 编辑器里正确显示 isometric terrain overlay。
- tileoffset_x / tileoffset_y:
                可选写入 <tileoffset x="..." y="..."/>。isometric tile 图像单元
                高于 map grid 时常用 y=(tileheight-gridheight)/2。
- wang_2edge / wang_2corner:
                可选自动写入 Edge Set / Corner Set 的 <wangsets> 元数据，避免在透明
                padding 很多的 isometric sheet 上手工逐 tile 标边。
- wang_transform:
                方向转换。`none` 适合 topdown sheet；`iso45_ccw` 适合经过
                topdown_to_iso(angle=45) 的 sheet。





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


def _transform_edge_code(code: int, transform: str) -> int:
    """转换 edge code 方向。

    原始 mask code 是 topdown 图像的 N/E/S/W。经过 topdown_to_iso(angle=45)
    后，视觉方向映射到 Tiled isometric 逻辑方向为：
      old E -> Top, old S -> Right, old W -> Bottom, old N -> Left
    """
    transform = (transform or "none").lower()
    if transform in ("", "none"):
        return code
    if transform in ("iso45", "iso45_ccw"):
        new_code = 0
        if code & 2: new_code |= 1   # old E -> Top
        if code & 4: new_code |= 2   # old S -> Right
        if code & 8: new_code |= 4   # old W -> Bottom
        if code & 1: new_code |= 8   # old N -> Left
        return new_code
    if transform == "opposite":
        new_code = 0
        if code & 4: new_code |= 1
        if code & 8: new_code |= 2
        if code & 1: new_code |= 4
        if code & 2: new_code |= 8
        return new_code
    raise ValueError(f"[build_tsx_sheet] 未知 wang_transform: {transform}")


def _transform_corner_code(code: int, transform: str) -> int:
    """转换 corner code 方向。原始 bit=TL/TR/BR/BL。"""
    transform = (transform or "none").lower()
    if transform in ("", "none"):
        return code
    if transform in ("iso45", "iso45_ccw"):
        new_code = 0
        if code & 2: new_code |= 1   # old TR -> Tiled TL
        if code & 4: new_code |= 2   # old BR -> Tiled TR
        if code & 8: new_code |= 4   # old BL -> Tiled BR
        if code & 1: new_code |= 8   # old TL -> Tiled BL
        return new_code
    if transform == "opposite":
        new_code = 0
        if code & 4: new_code |= 1
        if code & 8: new_code |= 2
        if code & 1: new_code |= 4
        if code & 2: new_code |= 8
        return new_code
    raise ValueError(f"[build_tsx_sheet] 未知 wang_transform: {transform}")


def _wang_2edge_id(code: int, background: int = 1, foreground: int = 2) -> str:
    """把 4-bit N/E/S/W code 转成 Tiled wangid 的 8 位序列。"""
    top = foreground if code & 1 else background
    right = foreground if code & 2 else background
    bottom = foreground if code & 4 else background
    left = foreground if code & 8 else background
    return f"{top},0,{right},0,{bottom},0,{left},0"


def _wang_2corner_id(code: int, background: int = 1, foreground: int = 2) -> str:
    """把 4-bit TL/TR/BR/BL code 转成 Tiled wangid 的 8 位序列。"""
    tl = foreground if code & 1 else background
    tr = foreground if code & 2 else background
    br = foreground if code & 4 else background
    bl = foreground if code & 8 else background
    return f"0,{tr},0,{br},0,{bl},0,{tl}"



@register("build_tsx_sheet")


class BuildTsxSheetAction(Action):
    description = "为 pack_sheet 产出的 sheet 生成 Tiled 可识别的 .tsx"
    param_hints = {
        "path": {"widget": "filepath"},
        "grid_orientation": {"enum": ["", "orthogonal", "isometric"]},
        "grid_width": {"min": 1, "step": 1},
        "grid_height": {"min": 1, "step": 1},
        "tileoffset_x": {"step": 1},
        "tileoffset_y": {"step": 1},
        "background_color": {"widget": "color"},
        "foreground_color": {"widget": "color"},
        "wang_transform": {"enum": ["none", "iso45_ccw", "opposite"]},
    }


    def run(

        self,
        ctx: Context,
        path: str = "auto",
        name: Optional[str] = None,
        tile_names: bool = True,
        grid_orientation: str = "",
        grid_width: Optional[int] = None,
        grid_height: Optional[int] = None,
        tileoffset_x: Optional[int] = None,
        tileoffset_y: Optional[int] = None,
        wang_2edge: bool = False,
        wang_2corner: bool = False,
        wangset_name: str = "Terrains",
        corner_wangset_name: str = "Corners",
        background_name: str = "background",
        foreground_name: str = "foreground",
        background_color: str = "#378dc2",
        foreground_color: str = "#c4a000",
        background_tile: int = 0,
        foreground_tile: int = 15,
        edge_offset: int = 0,
        corner_offset: int = 16,
        wang_transform: str = "none",
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
        if tileoffset_x is not None or tileoffset_y is not None:
            ox = int(tileoffset_x or 0)
            oy = int(tileoffset_y or 0)
            lines.append(f' <tileoffset x="{ox}" y="{oy}"/>')
        grid_orientation = (grid_orientation or "").strip().lower()

        if grid_orientation:
            if grid_orientation not in ("orthogonal", "isometric"):
                raise ValueError(
                    "[build_tsx_sheet] grid_orientation 应为 '' / orthogonal / isometric"
                )
            gw = int(grid_width) if grid_width else tile_w
            gh = int(grid_height) if grid_height else tile_h
            lines.append(
                f' <grid orientation="{xml_escape(grid_orientation)}" '
                f'width="{gw}" height="{gh}"/>'
            )
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

        if wang_2edge or wang_2corner:
            bg_tile = max(0, min(tile_count - 1, int(background_tile)))
            fg_tile = max(0, min(tile_count - 1, int(foreground_tile)))
            lines.append(" <wangsets>")
            if wang_2edge:
                eo = int(edge_offset)
                if tile_count < eo + 16:
                    raise RuntimeError("[build_tsx_sheet] wang_2edge=true 需要 edge_offset 后至少 16 个 tile")
                lines.append(
                    f'  <wangset name="{xml_escape(wangset_name)}" type="edge" tile="{fg_tile}">'
                )
                lines.append(
                    f'   <wangcolor name="{xml_escape(background_name)}" '
                    f'color="{xml_escape(background_color)}" tile="{bg_tile}" probability="1"/>'
                )
                lines.append(
                    f'   <wangcolor name="{xml_escape(foreground_name)}" '
                    f'color="{xml_escape(foreground_color)}" tile="{fg_tile}" probability="1"/>'
                )
                for code in range(16):
                    mapped = _transform_edge_code(code, wang_transform)
                    lines.append(
                        f'   <wangtile tileid="{eo + code}" wangid="{_wang_2edge_id(mapped)}"/>'
                    )

                lines.append("  </wangset>")
            if wang_2corner:
                co = int(corner_offset)
                if tile_count < co + 16:
                    raise RuntimeError("[build_tsx_sheet] wang_2corner=true 需要 corner_offset 后至少 16 个 tile")
                lines.append(
                    f'  <wangset name="{xml_escape(corner_wangset_name)}" type="corner" tile="{co + 15}">'
                )
                lines.append(
                    f'   <wangcolor name="{xml_escape(background_name)}" '
                    f'color="{xml_escape(background_color)}" tile="{co}" probability="1"/>'
                )
                lines.append(
                    f'   <wangcolor name="{xml_escape(foreground_name)}" '
                    f'color="{xml_escape(foreground_color)}" tile="{co + 15}" probability="1"/>'
                )
                for code in range(16):
                    mapped = _transform_corner_code(code, wang_transform)
                    lines.append(
                        f'   <wangtile tileid="{co + code}" wangid="{_wang_2corner_id(mapped)}"/>'
                    )

                lines.append("  </wangset>")
            lines.append(" </wangsets>")

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
