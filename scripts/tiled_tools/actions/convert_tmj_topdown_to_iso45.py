# -*- coding: utf-8 -*-
"""convert_tmj_topdown_to_iso45: convert a Tiled JSON map to iso45 metadata.

The action keeps already painted map data unchanged by default. It rewrites
map-level orientation / tile size / tileset source so a topdown authoring map can
be opened as an isometric map when the topdown and iso45 tilesets keep the same
local tile ID order. For maps painted with an older duplicated edge WangSet, the
optional gid_remap=edge_canonical mode also normalizes saved edge candidates.
For scene-source tilesets, gid_remap=iso45_cw rotates shared tile corner labels
from TR,BR,BL,TL to TL,TR,BR,BL before looking up the target tile ID.
"""

from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

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


_AUTO_VALUES = {"", "auto", "context"}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    return int(float(value))


def _resolve_path(ctx: Context, path: str | Path, base: Optional[Path] = None) -> Path:
    p = Path(path).expanduser()
    if p.is_absolute():
        return p.resolve()
    root = base if base is not None else ctx.workdir
    return (root / p).resolve()


def _as_map_source(path: Path, map_dir: Path) -> str:
    return os.path.relpath(path, start=map_dir).replace(os.sep, "/")


def _tileset_matches(ts: Dict[str, Any], wanted: str) -> bool:
    wanted = (wanted or "").strip()
    if wanted.lower() in _AUTO_VALUES:
        return False
    values = [
        str(ts.get("name") or ""),
        str(ts.get("source") or ""),
        Path(str(ts.get("source") or "")).stem,
    ]
    return any(v == wanted for v in values)


def _select_tileset(tilesets: List[Dict[str, Any]], wanted: str) -> int:
    if not tilesets:
        raise ValueError("[convert_tmj_topdown_to_iso45] map.tilesets 为空")

    wanted = (wanted or "").strip()
    if wanted.lower() not in _AUTO_VALUES:
        for index, ts in enumerate(tilesets):
            if _tileset_matches(ts, wanted):
                return index
        raise ValueError(f"[convert_tmj_topdown_to_iso45] 找不到源 tileset: {wanted!r}")

    if len(tilesets) > 1:
        print(
            "[convert_tmj_topdown_to_iso45] source_tileset=auto 且地图含多个 tileset，"
            "默认转换第一个 tileset"
        )
    return 0


def _resolve_target_tileset(ctx: Context, target_tileset: str, map_dir: Path) -> Tuple[Path, str]:
    target = str(target_tileset or "").strip()
    if target.lower() in _AUTO_VALUES:
        target = str(ctx.meta.get("last_tsx") or "")
        if not target:
            extra = ctx.extras.get("tsx") or {}
            target = str(extra.get("path") or "")
    if not target:
        raise ValueError(
            "[convert_tmj_topdown_to_iso45] target_tileset 为空，"
            "请传入目标 iso45 .tsx，或在前序步骤生成 .tsx"
        )

    candidate = Path(target).expanduser()
    if candidate.is_absolute():
        target_path = candidate.resolve()
    else:
        map_relative = (map_dir / candidate).resolve()
        target_path = map_relative if map_relative.is_file() else candidate.resolve()
    if not target_path.is_file():
        raise FileNotFoundError(f"[convert_tmj_topdown_to_iso45] 找不到目标 tileset: {target_path}")
    return target_path, _as_map_source(target_path, map_dir)


def _resolve_source_tileset_path(map_dir: Path, ts: Dict[str, Any]) -> Optional[Path]:
    source = str(ts.get("source") or "").strip()
    if not source:
        return None
    path = (map_dir / source).resolve()
    return path if path.is_file() else None


def _iter_children(parent: ET.Element, name: str) -> Iterable[ET.Element]:
    for child in list(parent):
        if _local_name(child.tag) == name:
            yield child


def _read_tsx_info(path: Path) -> Dict[str, Any]:
    root = ET.parse(path).getroot()
    tilecount = int(root.get("tilecount") or 0)
    grid: Dict[str, Any] = {}
    for child in _iter_children(root, "grid"):
        grid = {
            "orientation": str(child.get("orientation") or ""),
            "width": _optional_int(child.get("width")),
            "height": _optional_int(child.get("height")),
        }
        break

    names: Dict[int, str] = {}
    for tile in _iter_children(root, "tile"):
        tile_id = int(tile.get("id") or 0)
        label = None
        for properties in _iter_children(tile, "properties"):
            for prop in _iter_children(properties, "property"):
                if prop.get("name") == "name":
                    label = str(prop.get("value") or "")
                    break
            if label is not None:
                break
        if label is not None:
            names[tile_id] = label

    wangsets: Dict[str, Dict[str, Any]] = {}
    wangset_parents = list(_iter_children(root, "wangsets")) or [root]
    for wangsets_parent in wangset_parents:
        for wangset in _iter_children(wangsets_parent, "wangset"):
            wangset_name = str(wangset.get("name") or "")
            wangset_type = str(wangset.get("type") or "").strip().lower()
            wangset_info = {
                "type": wangset_type,
                "colors": [],
                "tiles": [],
            }
            for color in _iter_children(wangset, "wangcolor"):
                wangset_info["colors"].append({
                    "name": str(color.get("name") or ""),
                    "color": str(color.get("color") or ""),
                })
            for tile in _iter_children(wangset, "wangtile"):
                wangset_info["tiles"].append({
                    "tileid": int(tile.get("tileid") or 0),
                    "wangid": str(tile.get("wangid") or ""),
                })
            wangsets[wangset_name] = wangset_info

    return {
        "path": str(path),
        "tilecount": tilecount,
        "grid": grid,
        "names": names,
        "wangsets": wangsets,
    }


def _compare_tile_names(source: Dict[str, Any], target: Dict[str, Any]) -> List[int]:
    source_names: Dict[int, str] = source.get("names") or {}
    target_names: Dict[int, str] = target.get("names") or {}
    if not source_names or not target_names:
        return []
    ids = sorted(set(source_names) | set(target_names))
    return [tile_id for tile_id in ids if source_names.get(tile_id) != target_names.get(tile_id)]


def _find_wangset(info: Dict[str, Any], wangset_name: str, wangset_type: str) -> Optional[Dict[str, Any]]:
    wangsets: Dict[str, Dict[str, Any]] = info.get("wangsets") or {}
    wanted = str(wangset_name or "").strip()
    if wanted and wanted in wangsets:
        return wangsets[wanted]
    for spec in wangsets.values():
        if str(spec.get("type") or "").strip().lower() == wangset_type:
            return spec
    return None


def _split_shared_tile_name(label: str, terrain_names: List[str]) -> Optional[List[str]]:
    if not label.startswith("shared_"):
        return None
    rest = label[len("shared_"):]
    names = sorted([str(name) for name in terrain_names if str(name)], key=len, reverse=True)

    def consume(value: str, count: int) -> Optional[List[str]]:
        if count == 0:
            return [] if value == "" else None
        for name in names:
            if count == 1 and value == name:
                return [name]
            prefix = name + "_"
            if value.startswith(prefix):
                tail = consume(value[len(prefix):], count - 1)
                if tail is not None:
                    return [name] + tail
        return None

    return consume(rest, 4)


def _edge_labels_from_wangid(wangid: str, terrain_names: List[str]) -> Optional[Tuple[str, str, str, str]]:
    try:
        values = [int(part) for part in str(wangid or "").split(",")]
    except ValueError:
        return None
    if len(values) != 8:
        return None
    labels: List[str] = []
    for index in (0, 2, 4, 6):
        value = values[index]
        if value <= 0 or value > len(terrain_names):
            return None
        labels.append(terrain_names[value - 1])
    return labels[0], labels[1], labels[2], labels[3]


def _edge_fit_score(corner_labels: List[str], edge_labels: Tuple[str, str, str, str]) -> Tuple[int, int, int, Tuple[str, ...]]:
    tr, br, bl, tl = corner_labels
    top, right, bottom, left = edge_labels
    edge_values = {top, right, bottom, left}
    mismatch = sum([
        tr != top,
        tr != right,
        br != right,
        br != bottom,
        bl != bottom,
        bl != left,
        tl != left,
        tl != top,
    ])
    foreign = sum(1 for value in (tr, br, bl, tl) if value not in edge_values)
    return mismatch, foreign, len(set((tr, br, bl, tl))), (tr, br, bl, tl)


def _build_edge_canonical_map(
    source_info: Dict[str, Any],
    target_info: Dict[str, Any],
    wangset_name: str,
) -> Dict[int, int]:
    source_wangset = _find_wangset(source_info, wangset_name, "edge")
    if source_wangset is None:
        raise ValueError("[convert_tmj_topdown_to_iso45] 源 tileset 找不到 edge WangSet")

    terrain_names = [str(item.get("name") or "") for item in (source_wangset.get("colors") or [])]
    terrain_names = [name for name in terrain_names if name]
    if not terrain_names:
        raise ValueError("[convert_tmj_topdown_to_iso45] edge WangSet 缺少 wangcolor name")

    source_names: Dict[int, str] = source_info.get("names") or {}
    target_names: Dict[int, str] = target_info.get("names") or {}
    target_by_name = {name: tile_id for tile_id, name in target_names.items() if name}

    groups: Dict[str, List[Tuple[int, List[str], Tuple[str, str, str, str]]]] = {}
    for entry in source_wangset.get("tiles") or []:
        tile_id = int(entry.get("tileid") or 0)
        label = source_names.get(tile_id) or ""
        corner_labels = _split_shared_tile_name(label, terrain_names)
        edge_labels = _edge_labels_from_wangid(str(entry.get("wangid") or ""), terrain_names)
        if corner_labels is None or edge_labels is None:
            continue
        groups.setdefault(str(entry.get("wangid") or ""), []).append((tile_id, corner_labels, edge_labels))

    local_map: Dict[int, int] = {}
    for items in groups.values():
        best_tile_id, best_labels, best_edges = min(
            items,
            key=lambda item: _edge_fit_score(item[1], item[2]),
        )
        best_name = source_names.get(best_tile_id) or ""
        target_tile_id = target_by_name.get(best_name, best_tile_id)
        for tile_id, _labels, _edges in items:
            local_map[tile_id] = target_tile_id
    return local_map


def _terrain_names_from_info(info: Dict[str, Any], wangset_name: str = "") -> List[str]:
    wangsets: Dict[str, Dict[str, Any]] = info.get("wangsets") or {}
    candidates: List[Dict[str, Any]] = []
    wanted = str(wangset_name or "").strip()
    if wanted and wanted in wangsets:
        candidates.append(wangsets[wanted])
    candidates.extend(spec for name, spec in wangsets.items() if name != wanted)

    for spec in candidates:
        names = [str(item.get("name") or "") for item in (spec.get("colors") or [])]
        names = [name for name in names if name]
        if names:
            return names
    raise ValueError("[convert_tmj_topdown_to_iso45] tileset 缺少可用于解析 shared tile name 的 wangcolor name")


def _rotate_shared_tile_name(label: str, terrain_names: List[str], mode: str) -> str:
    corner_labels = _split_shared_tile_name(label, terrain_names)
    if corner_labels is None:
        return label

    if mode == "iso45_cw":
        mapped = [corner_labels[3], corner_labels[0], corner_labels[1], corner_labels[2]]
    else:
        raise ValueError(f"[convert_tmj_topdown_to_iso45] 未知 tile name rotation mode: {mode!r}")
    return "shared_" + "_".join(mapped)


def _build_tile_name_rotation_map(
    source_info: Dict[str, Any],
    target_info: Dict[str, Any],
    wangset_name: str,
    mode: str,
) -> Dict[int, int]:
    terrain_names = _terrain_names_from_info(source_info, wangset_name)
    source_names: Dict[int, str] = source_info.get("names") or {}
    target_names: Dict[int, str] = target_info.get("names") or {}
    target_by_name = {name: tile_id for tile_id, name in target_names.items() if name}

    local_map: Dict[int, int] = {}
    missing: List[Tuple[int, str, str]] = []
    for tile_id, label in source_names.items():
        if not label:
            continue
        target_label = _rotate_shared_tile_name(label, terrain_names, mode)
        target_tile_id = target_by_name.get(target_label)
        if target_tile_id is None:
            missing.append((tile_id, label, target_label))
            continue
        local_map[tile_id] = target_tile_id

    if missing:
        preview = "; ".join(
            f"{tile_id}:{label}->{target_label}"
            for tile_id, label, target_label in missing[:8]
        )
        raise ValueError(
            "[convert_tmj_topdown_to_iso45] gid_remap=iso45_cw 找不到目标 tile name："
            f"missing={len(missing)} first=[{preview}]"
        )
    return local_map


def _remap_gid_value(value: Any, firstgid: int, upper_gid: Optional[int], local_map: Dict[int, int]) -> Tuple[Any, bool]:
    if not isinstance(value, int) or value == 0:
        return value, False
    raw = value & GID_VALUE_MASK
    if raw < firstgid:
        return value, False
    if upper_gid is not None and raw >= upper_gid:
        return value, False
    local_id = raw - firstgid
    mapped = local_map.get(local_id)
    if mapped is None:
        return value, False
    new_value = firstgid + int(mapped) + (value & GID_FLAG_MASK)
    return new_value, new_value != value


def _remap_layer_gids(layer: Dict[str, Any], firstgid: int, upper_gid: Optional[int], local_map: Dict[int, int]) -> int:
    changed = 0
    data = layer.get("data")
    if isinstance(data, list):
        new_data = []
        for value in data:
            new_value, did_change = _remap_gid_value(value, firstgid, upper_gid, local_map)
            changed += 1 if did_change else 0
            new_data.append(new_value)
        layer["data"] = new_data

    for chunk in layer.get("chunks") or []:
        if not isinstance(chunk, dict) or not isinstance(chunk.get("data"), list):
            continue
        new_chunk_data = []
        for value in chunk["data"]:
            new_value, did_change = _remap_gid_value(value, firstgid, upper_gid, local_map)
            changed += 1 if did_change else 0
            new_chunk_data.append(new_value)
        chunk["data"] = new_chunk_data

    for obj in layer.get("objects") or []:
        if isinstance(obj, dict) and "gid" in obj:
            new_value, did_change = _remap_gid_value(obj.get("gid"), firstgid, upper_gid, local_map)
            changed += 1 if did_change else 0
            obj["gid"] = new_value

    for child in layer.get("layers") or []:
        if isinstance(child, dict):
            changed += _remap_layer_gids(child, firstgid, upper_gid, local_map)
    return changed


def _remap_map_gids(data: Dict[str, Any], firstgid: int, upper_gid: Optional[int], local_map: Dict[int, int]) -> int:
    changed = 0
    for layer in data.get("layers") or []:
        if isinstance(layer, dict):
            changed += _remap_layer_gids(layer, firstgid, upper_gid, local_map)
    return changed


def _iter_layer_gids(layer: Dict[str, Any]) -> Iterable[int]:
    data = layer.get("data")
    if isinstance(data, list):
        for value in data:
            if isinstance(value, int):
                yield value

    for chunk in layer.get("chunks") or []:
        if not isinstance(chunk, dict):
            continue
        chunk_data = chunk.get("data")
        if isinstance(chunk_data, list):
            for value in chunk_data:
                if isinstance(value, int):
                    yield value

    for obj in layer.get("objects") or []:
        if isinstance(obj, dict) and isinstance(obj.get("gid"), int):
            yield int(obj["gid"])

    for child in layer.get("layers") or []:
        if isinstance(child, dict):
            yield from _iter_layer_gids(child)


def _used_local_ids(data: Dict[str, Any], firstgid: int, upper_gid: Optional[int]) -> List[int]:
    out = set()
    for layer in data.get("layers") or []:
        if not isinstance(layer, dict):
            continue
        for gid in _iter_layer_gids(layer):
            if gid == 0:
                continue
            raw = gid & GID_VALUE_MASK
            if raw < firstgid:
                continue
            if upper_gid is not None and raw >= upper_gid:
                continue
            out.add(raw - firstgid)
    return sorted(out)


def _next_firstgid(tilesets: List[Dict[str, Any]], firstgid: int) -> Optional[int]:
    values = []
    for ts in tilesets:
        value = int(ts.get("firstgid") or 0)
        if value > firstgid:
            values.append(value)
    return min(values) if values else None


def _infer_tile_size(
    ctx: Context,
    target_info: Dict[str, Any],
    map_tile_width: Any,
    map_tile_height: Any,
) -> Tuple[int, int]:
    explicit_w = _optional_int(map_tile_width)
    explicit_h = _optional_int(map_tile_height)

    grid = target_info.get("grid") or {}
    grid_w = _optional_int(grid.get("width"))
    grid_h = _optional_int(grid.get("height"))

    spec = ctx.meta.get("iso45_tile_spec") or {}
    spec_w = _optional_int(spec.get("grid_width"))
    spec_h = _optional_int(spec.get("grid_height"))

    width = explicit_w or grid_w or spec_w or 256
    height = explicit_h or grid_h or spec_h or max(1, int(round(width / 2)))
    return int(width), int(height)


@register("convert_tmj_topdown_to_iso45")
class ConvertTmjTopdownToIso45Action(Action):
    description = "Topdown .tmj → iso45 .tmj（保留 layer data，只更新地图元数据和 tileset 引用）"
    param_hints = {
        "map_path": {"widget": "filepath"},
        "target_tileset": {"widget": "filepath"},
        "output": {"widget": "filepath"},
        "source_tileset": {"widget": "text"},
        "orientation": {"enum": ["isometric"]},
        "renderorder": {"enum": ["right-down", "right-up", "left-down", "left-up"]},
        "gid_remap": {"enum": ["none", "edge_canonical", "iso45_cw"]},
        "gid_remap_wangset": {"widget": "text"},
        "map_tile_width": {"min": 1, "step": 1},
        "map_tile_height": {"min": 1, "step": 1},
        "indent": {"min": 0, "step": 1},
    }

    def run(
        self,
        ctx: Context,
        map_path: str = "",
        target_tileset: str = "context",
        output: str = "auto",
        source_tileset: str = "auto",
        orientation: str = "isometric",
        renderorder: str = "right-down",
        map_tile_width: Optional[int] = None,
        map_tile_height: Optional[int] = None,
        tiledversion: str = "",
        check_tile_names: bool = True,
        strict_tile_names: bool = True,
        gid_remap: str = "none",
        gid_remap_wangset: str = "edge_set",
        indent: int = 1,
    ) -> Context:
        if not str(map_path or "").strip():
            print("[convert_tmj_topdown_to_iso45] map_path 为空，跳过")
            return ctx

        map_file = _resolve_path(ctx, map_path)
        if not map_file.is_file():
            raise FileNotFoundError(f"[convert_tmj_topdown_to_iso45] 找不到地图文件: {map_file}")

        data = json.loads(map_file.read_text(encoding="utf-8"))
        tilesets = data.get("tilesets") or []
        if not isinstance(tilesets, list):
            raise ValueError("[convert_tmj_topdown_to_iso45] map.tilesets 必须是数组")

        target_path, target_source = _resolve_target_tileset(ctx, target_tileset, map_file.parent)
        target_info = _read_tsx_info(target_path)
        selected_index = _select_tileset(tilesets, source_tileset)
        selected_tileset = dict(tilesets[selected_index])
        firstgid = int(selected_tileset.get("firstgid") or 1)
        source_path = _resolve_source_tileset_path(map_file.parent, selected_tileset)
        source_info = _read_tsx_info(source_path) if source_path else {"tilecount": 0, "names": {}}

        diffs: List[int] = []
        if check_tile_names and source_path:
            diffs = _compare_tile_names(source_info, target_info)
            if diffs:
                preview = ", ".join(str(i) for i in diffs[:12])
                message = (
                    "[convert_tmj_topdown_to_iso45] 源/目标 tileset 的 tile name 不同构，"
                    f"diff_count={len(diffs)} first=[{preview}]"
                )
                if strict_tile_names:
                    raise ValueError(message)
                print(message)
            elif (source_info.get("names") or {}) and (target_info.get("names") or {}):
                print("[convert_tmj_topdown_to_iso45] tile name check: OK")

        source_tilecount = int(source_info.get("tilecount") or 0)
        target_tilecount = int(target_info.get("tilecount") or 0)
        upper_gid = _next_firstgid(tilesets, firstgid)
        if upper_gid is None:
            count = source_tilecount or target_tilecount
            upper_gid = firstgid + count if count > 0 else None
        used_local_ids = _used_local_ids(data, firstgid, upper_gid)
        if target_tilecount > 0 and used_local_ids:
            max_local = max(used_local_ids)
            if max_local >= target_tilecount:
                raise ValueError(
                    "[convert_tmj_topdown_to_iso45] 地图使用的 local tile id 超出目标 tileset 范围："
                    f"max_used={max_local} target_tilecount={target_tilecount}"
                )

        gid_remap_mode = str(gid_remap or "none").strip().lower()
        remapped_gids = 0
        if gid_remap_mode not in ("", "none"):
            if gid_remap_mode not in ("edge_canonical", "iso45_cw"):
                raise ValueError(f"[convert_tmj_topdown_to_iso45] 未知 gid_remap: {gid_remap!r}")
            if not source_path:
                raise ValueError(f"[convert_tmj_topdown_to_iso45] gid_remap={gid_remap_mode} 需要源 tileset source")
            if gid_remap_mode == "edge_canonical":
                local_map = _build_edge_canonical_map(source_info, target_info, gid_remap_wangset)
            else:
                local_map = _build_tile_name_rotation_map(source_info, target_info, gid_remap_wangset, gid_remap_mode)
            remapped_gids = _remap_map_gids(data, firstgid, upper_gid, local_map)
            print(
                f"[convert_tmj_topdown_to_iso45] gid_remap={gid_remap_mode} "
                f"map_entries={len(local_map)} changed_gids={remapped_gids}"
            )

        tile_w, tile_h = _infer_tile_size(ctx, target_info, map_tile_width, map_tile_height)

        selected_tileset["firstgid"] = firstgid
        selected_tileset["source"] = target_source
        tilesets[selected_index] = selected_tileset

        data["orientation"] = str(orientation or "isometric")
        data["renderorder"] = str(renderorder or "right-down")
        data["tilewidth"] = tile_w
        data["tileheight"] = tile_h
        data["tilesets"] = tilesets
        if str(tiledversion or "").strip():
            data["tiledversion"] = str(tiledversion).strip()

        if not output or output == "auto":
            output_file = map_file.with_name(f"{map_file.stem}_iso45{map_file.suffix or '.tmj'}")
        else:
            output_file = Path(output).expanduser()
            if not output_file.is_absolute():
                output_file = (map_file.parent / output_file).resolve()
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=int(indent)),
            encoding="utf-8",
        )

        result = {
            "path": str(output_file),
            "source_map": str(map_file),
            "source_tileset": str(source_path or selected_tileset.get("source") or ""),
            "target_tileset": str(target_path),
            "target_source": target_source,
            "firstgid": firstgid,
            "used_tiles": len(used_local_ids),
            "tilewidth": tile_w,
            "tileheight": tile_h,
            "name_diffs": len(diffs),
            "gid_remap": gid_remap_mode or "none",
            "remapped_gids": remapped_gids,
        }
        ctx.extras["converted_tmj_iso45"] = result
        ctx.meta["last_tmj"] = str(output_file)
        ctx.meta["last_iso45_tmj"] = str(output_file)
        print(
            f"[convert_tmj_topdown_to_iso45] -> {output_file.name}  "
            f"tile={tile_w}x{tile_h}  tileset={target_source}  used_tiles={len(used_local_ids)}  "
            f"remapped_gids={remapped_gids}"
        )
        return ctx
