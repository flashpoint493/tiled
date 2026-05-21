# -*- coding: utf-8 -*-
"""remap_tmj_gids: replace brush tileset GIDs in a Tiled JSON map.

This action consumes the .remap.json produced by brush_remap_tsx. It scans Tiled
JSON map layers, chunk data, and tile objects. Any GID that belongs to the brush
tileset is rewritten to the mapped runtime/source tileset GID while preserving
Tiled flip flags.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.action import Action, Context
from ..core.registry import register


FLIPPED_HORIZONTALLY_FLAG = 0x80000000
FLIPPED_VERTICALLY_FLAG = 0x40000000
FLIPPED_DIAGONALLY_FLAG = 0x20000000
ROTATED_HEXAGONAL_120_FLAG = 0x10000000
GID_FLAG_MASK = (
    FLIPPED_HORIZONTALLY_FLAG
    | FLIPPED_VERTICALLY_FLAG
    | FLIPPED_DIAGONALLY_FLAG
    | ROTATED_HEXAGONAL_120_FLAG
)
GID_VALUE_MASK = ~GID_FLAG_MASK


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _tileset_matches(ts: Dict[str, Any], wanted: str) -> bool:
    wanted = (wanted or "").strip()
    if not wanted:
        return False
    names = [
        str(ts.get("name") or ""),
        Path(str(ts.get("source") or "")).stem,
    ]
    return any(n == wanted for n in names)


def _find_firstgid(tilesets: List[Dict[str, Any]], wanted: str) -> Optional[int]:
    for ts in tilesets:
        if _tileset_matches(ts, wanted):
            return int(ts.get("firstgid", 0))
    return None


def _xml_tileset_matches(ts: ET.Element, wanted: str) -> bool:
    wanted = (wanted or "").strip()
    if not wanted:
        return False
    names = [
        str(ts.get("name") or ""),
        Path(str(ts.get("source") or "")).stem,
    ]
    image = next((child for child in list(ts) if _local_name(child.tag) == "image"), None)
    if image is not None:
        names.append(Path(str(image.get("source") or "")).stem)
    return any(n == wanted for n in names)


def _find_xml_firstgid(tilesets: List[ET.Element], wanted: str) -> Optional[int]:
    for ts in tilesets:
        if _xml_tileset_matches(ts, wanted):
            return int(ts.get("firstgid", "0"))
    return None


def _rewrite_gid(gid: int, brush_firstgid: int, brush_tile_count: int, remap: Dict[int, int]) -> Tuple[int, bool]:
    if not isinstance(gid, int) or gid == 0:
        return gid, False
    flags = gid & GID_FLAG_MASK
    raw = gid & GID_VALUE_MASK
    if raw < brush_firstgid or raw >= brush_firstgid + brush_tile_count:
        return gid, False
    brush_tile_id = raw - brush_firstgid
    target_gid = remap.get(brush_tile_id, 0)
    if target_gid <= 0:
        return 0, True
    return int(target_gid) | flags, True


def _rewrite_data_array(data: List[Any], brush_firstgid: int, brush_tile_count: int, remap: Dict[int, int]) -> Tuple[List[Any], int]:
    changed = 0
    out: List[Any] = []
    for value in data:
        if isinstance(value, int):
            new_value, did_change = _rewrite_gid(value, brush_firstgid, brush_tile_count, remap)
            out.append(new_value)
            if did_change:
                changed += 1
        else:
            out.append(value)
    return out, changed


def _rewrite_layer(layer: Dict[str, Any], brush_firstgid: int, brush_tile_count: int, remap: Dict[int, int]) -> int:
    changed = 0
    if isinstance(layer.get("data"), list):
        layer["data"], n = _rewrite_data_array(layer["data"], brush_firstgid, brush_tile_count, remap)
        changed += n

    for chunk in layer.get("chunks") or []:
        if isinstance(chunk, dict) and isinstance(chunk.get("data"), list):
            chunk["data"], n = _rewrite_data_array(chunk["data"], brush_firstgid, brush_tile_count, remap)
            changed += n

    for obj in layer.get("objects") or []:
        if isinstance(obj, dict) and isinstance(obj.get("gid"), int):
            obj["gid"], did_change = _rewrite_gid(obj["gid"], brush_firstgid, brush_tile_count, remap)
            if did_change:
                changed += 1

    for child in layer.get("layers") or []:
        if isinstance(child, dict):
            changed += _rewrite_layer(child, brush_firstgid, brush_tile_count, remap)
    return changed


def _rewrite_csv_text(text: Optional[str], width: int, brush_firstgid: int, brush_tile_count: int, remap: Dict[int, int]) -> Tuple[str, int]:
    values = [int(x) for x in re.findall(r"-?\d+", text or "")]
    if not values:
        return text or "", 0

    rewritten, changed = _rewrite_data_array(values, brush_firstgid, brush_tile_count, remap)
    if width <= 0:
        return ",".join(str(v) for v in rewritten), changed

    rows = []
    for i in range(0, len(rewritten), width):
        rows.append(",".join(str(v) for v in rewritten[i:i + width]))
    return "\n" + ",\n".join(rows) + "\n", changed


def _rewrite_tmx_data(root: ET.Element, brush_firstgid: int, brush_tile_count: int, remap: Dict[int, int]) -> int:
    changed = 0

    for chunk in root.iter():
        if _local_name(chunk.tag) != "chunk":
            continue
        width = int(chunk.get("width", "0") or 0)
        chunk.text, n = _rewrite_csv_text(chunk.text, width, brush_firstgid, brush_tile_count, remap)
        changed += n

    for data in root.iter():
        if _local_name(data.tag) != "data":
            continue
        encoding = (data.get("encoding") or "").lower()
        if encoding and encoding != "csv":
            continue
        if any(_local_name(child.tag) == "chunk" for child in list(data)):
            continue
        parent_width = int(root.get("width", "0") or 0)
        data.text, n = _rewrite_csv_text(data.text, parent_width, brush_firstgid, brush_tile_count, remap)
        changed += n

    for obj in root.iter():
        if _local_name(obj.tag) != "object" or obj.get("gid") is None:
            continue
        new_gid, did_change = _rewrite_gid(int(obj.get("gid", "0")), brush_firstgid, brush_tile_count, remap)
        if did_change:
            obj.set("gid", str(new_gid))
            changed += 1

    return changed


@register("remap_tmj_gids")
class RemapTmjGidsAction(Action):
    description = "用 brush .remap.json 后处理 Tiled JSON 地图，把 brush GID 替换成源 tileset GID"
    param_hints = {
        "map_path": {"widget": "filepath"},
        "mapping_json": {"widget": "filepath"},
        "output": {"widget": "filepath"},
    }

    def run(
        self,
        ctx: Context,
        map_path: str,
        mapping_json: str,
        output: str = "auto",
        brush_tileset_name: str = "",
        source_tileset_name: str = "",
        source_firstgid: int = 0,
        remove_brush_tileset: bool = True,
        indent: int = 2,
    ) -> Context:
        map_file = Path(map_path).expanduser().resolve()
        mapping_file = Path(mapping_json).expanduser().resolve()
        if not map_file.is_file():
            raise FileNotFoundError(f"[remap_tmj_gids] 找不到地图文件: {map_file}")
        if not mapping_file.is_file():
            raise FileNotFoundError(f"[remap_tmj_gids] 找不到映射 JSON: {mapping_file}")

        mapping = json.loads(mapping_file.read_text(encoding="utf-8"))
        if map_file.suffix.lower() == ".tmx":
            return self._run_tmx(
                ctx=ctx,
                map_file=map_file,
                mapping=mapping,
                output=output,
                brush_tileset_name=brush_tileset_name,
                source_tileset_name=source_tileset_name,
                source_firstgid=source_firstgid,
                remove_brush_tileset=remove_brush_tileset,
            )

        data = json.loads(map_file.read_text(encoding="utf-8"))
        tilesets = data.get("tilesets") or []
        if not isinstance(tilesets, list):
            raise ValueError("[remap_tmj_gids] map.tilesets 必须是数组")

        brush_name = brush_tileset_name or str(mapping.get("name") or "")
        source_name = source_tileset_name or str(mapping.get("source_name") or "")
        brush_firstgid = _find_firstgid(tilesets, brush_name)
        if brush_firstgid is None:
            raise ValueError(f"[remap_tmj_gids] 地图里找不到 brush tileset: {brush_name!r}")

        actual_source_firstgid = int(source_firstgid or 0)
        if actual_source_firstgid <= 0:
            found = _find_firstgid(tilesets, source_name)
            if found is None:
                raise ValueError(f"[remap_tmj_gids] 地图里找不到源 tileset: {source_name!r}")
            actual_source_firstgid = found

        brush_tile_count = int((mapping.get("brush_grid") or {}).get("tile_count") or 0)
        if brush_tile_count <= 0:
            raise ValueError("[remap_tmj_gids] 映射 JSON 缺少 brush_grid.tile_count")

        remap: Dict[int, int] = {}
        for item in mapping.get("mappings") or []:
            brush_tile_id = int(item.get("brush_tile_id"))
            target_tile_id = int(item.get("target_tile_id", -1))
            if target_tile_id >= 0:
                remap[brush_tile_id] = actual_source_firstgid + target_tile_id

        changed = 0
        for layer in data.get("layers") or []:
            if isinstance(layer, dict):
                changed += _rewrite_layer(layer, int(brush_firstgid), brush_tile_count, remap)

        if remove_brush_tileset:
            data["tilesets"] = [ts for ts in tilesets if not _tileset_matches(ts, brush_name)]

        if not output or output == "auto":
            output_file = map_file.with_name(f"{map_file.stem}_runtime{map_file.suffix or '.tmj'}")
        else:
            output_file = Path(output).expanduser()
            if not output_file.is_absolute():
                output_file = (map_file.parent / output_file).resolve()
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(data, ensure_ascii=False, indent=int(indent)), encoding="utf-8")

        ctx.extras["remapped_map"] = {
            "path": str(output_file),
            "changed": changed,
            "brush_tileset": brush_name,
            "brush_firstgid": int(brush_firstgid),
            "source_tileset": source_name,
            "source_firstgid": actual_source_firstgid,
        }
        ctx.meta["last_remapped_map"] = str(output_file)
        print(
            f"[remap_tmj_gids] -> {output_file.name}  changed={changed}  "
            f"brush={brush_name}@{brush_firstgid} source={source_name}@{actual_source_firstgid}"
        )
        return ctx

    def _run_tmx(
        self,
        ctx: Context,
        map_file: Path,
        mapping: Dict[str, Any],
        output: str,
        brush_tileset_name: str,
        source_tileset_name: str,
        source_firstgid: int,
        remove_brush_tileset: bool,
    ) -> Context:
        tree = ET.parse(map_file)
        root = tree.getroot()
        tilesets = [child for child in list(root) if _local_name(child.tag) == "tileset"]

        brush_name = brush_tileset_name or str(mapping.get("name") or "")
        source_name = source_tileset_name or str(mapping.get("source_name") or "")
        brush_firstgid = _find_xml_firstgid(tilesets, brush_name)
        if brush_firstgid is None:
            raise ValueError(f"[remap_tmj_gids] 地图里找不到 brush tileset: {brush_name!r}")

        actual_source_firstgid = int(source_firstgid or 0)
        if actual_source_firstgid <= 0:
            found = _find_xml_firstgid(tilesets, source_name)
            if found is None:
                raise ValueError(f"[remap_tmj_gids] 地图里找不到源 tileset: {source_name!r}")
            actual_source_firstgid = found

        brush_tile_count = int((mapping.get("brush_grid") or {}).get("tile_count") or 0)
        if brush_tile_count <= 0:
            raise ValueError("[remap_tmj_gids] 映射 JSON 缺少 brush_grid.tile_count")

        remap: Dict[int, int] = {}
        for item in mapping.get("mappings") or []:
            brush_tile_id = int(item.get("brush_tile_id"))
            target_tile_id = int(item.get("target_tile_id", -1))
            if target_tile_id >= 0:
                remap[brush_tile_id] = actual_source_firstgid + target_tile_id

        changed = _rewrite_tmx_data(root, int(brush_firstgid), brush_tile_count, remap)

        if remove_brush_tileset:
            for ts in list(root):
                if _local_name(ts.tag) == "tileset" and _xml_tileset_matches(ts, brush_name):
                    root.remove(ts)

        if not output or output == "auto":
            output_file = map_file.with_name(f"{map_file.stem}_runtime{map_file.suffix or '.tmx'}")
        else:
            output_file = Path(output).expanduser()
            if not output_file.is_absolute():
                output_file = (map_file.parent / output_file).resolve()
        output_file.parent.mkdir(parents=True, exist_ok=True)
        tree.write(output_file, encoding="utf-8", xml_declaration=True)

        ctx.extras["remapped_map"] = {
            "path": str(output_file),
            "changed": changed,
            "brush_tileset": brush_name,
            "brush_firstgid": int(brush_firstgid),
            "source_tileset": source_name,
            "source_firstgid": actual_source_firstgid,
        }
        ctx.meta["last_remapped_map"] = str(output_file)
        print(
            f"[remap_tmj_gids] -> {output_file.name}  changed={changed}  "
            f"brush={brush_name}@{brush_firstgid} source={source_name}@{actual_source_firstgid}"
        )
        return ctx
