# -*- coding: utf-8 -*-
"""multi_terrain_wang_set: 从多张基础 terrain 贴图生成多地形 wang 规则集。 

典型输入：
- 先用 `load_dir` 读取一个目录中的基础地形循环贴图（grass / sand / water ...）
- 然后本 action 按 edge / corner / both 生成全部组合：
  * edge   : N^4 张（顺序 N/E/S/W）
  * corner : N^4 张（Tiled 原生顺序 TR/BR/BL/TL）
  * both   : 2 * N^4 张（先 edge 后 corner）

输出：
- `ctx.extras["tiles"]`      : 组合后的 tile 列表（RGBA）
- `ctx.extras["tile_names"]` : 每张 tile 的名字
- `ctx.extras["wang_multisets"]`:
    给 `build_tsx_sheet` 用的泛化 wangset 元数据，可自动写入多 terrain 的
    `<wangsets>` / `<wangcolor>` / `<wangtile>`。

设计目标：
- 不是去穷举“成对过渡”再拆多个 tileset，而是直接生成一个含 N 个 terrain 的
  单一 wangset；Tiled 里每条边/每个角都可以指向 1..N 中任意一种 terrain。
- 美术上这只是一个“通用混合启发式”：边集根据边标签做距离场混合，角集根据角
  标签做多材质双线性混合。对于 3+ terrain 的复杂交汇，它能保证边界连续，但
  是否完全符合期望造型仍取决于素材风格；必要时可在生成结果上再手工修图。
"""
from __future__ import annotations

from itertools import product
from typing import Any, Dict, List, Sequence

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

_DEFAULT_COLORS = [
    "#4caf50", "#c4a000", "#378dc2", "#a855f7",
    "#ef4444", "#f97316", "#14b8a6", "#64748b",
]


def _edge_field(width: int, height: int, edge: str, half_extent: float) -> np.ndarray:
    ys = np.linspace(0, 1, height, dtype=np.float32)
    xs = np.linspace(0, 1, width, dtype=np.float32)
    y, x = np.meshgrid(ys, xs, indexing="ij")
    if edge == "N":
        d = 1.0 - y
    elif edge == "S":
        d = y
    elif edge == "W":
        d = 1.0 - x
    elif edge == "E":
        d = x
    else:
        raise ValueError(edge)
    t = (d - (1.0 - half_extent)) / max(1e-6, float(half_extent))
    return np.clip(t, 0.0, 1.0)


def _corner_field(width: int, height: int, corner: str, half_extent: float) -> np.ndarray:
    ys = np.linspace(0, 1, height, dtype=np.float32)
    xs = np.linspace(0, 1, width, dtype=np.float32)
    y, x = np.meshgrid(ys, xs, indexing="ij")
    if corner == "NW":
        dist = np.sqrt(x * x + y * y)
    elif corner == "NE":
        dist = np.sqrt((1.0 - x) * (1.0 - x) + y * y)
    elif corner == "SE":
        dist = np.sqrt((1.0 - x) * (1.0 - x) + (1.0 - y) * (1.0 - y))
    elif corner == "SW":
        dist = np.sqrt(x * x + (1.0 - y) * (1.0 - y))
    else:
        raise ValueError(corner)
    radius = max(1e-6, float(half_extent) * 2 ** 0.5)
    t = np.clip((radius - dist) / radius, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _parse_target_size(value: Any, name: str) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        value = value.strip().lower()
        if not value or value == "auto":
            return 0
    try:
        size = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"[multi_terrain_wang_set] {name} must be an integer or auto") from exc
    if size < 0:
        raise ValueError(f"[multi_terrain_wang_set] {name} must be >= 0")
    return size


def _normalize_rgba_tiles(
    tiles: Sequence[Image.Image],
    resample: str,
    tile_width: Any = 0,
    tile_height: Any = 0,
) -> tuple[List[Image.Image], int, int]:
    if not tiles:
        raise RuntimeError("[multi_terrain_wang_set] 没有输入基础 terrain 贴图")
    max_width = max(int(t.size[0]) for t in tiles)
    max_height = max(int(t.size[1]) for t in tiles)
    width = _parse_target_size(tile_width, "tile_width") or max_width
    height = _parse_target_size(tile_height, "tile_height") or max_height
    rs = _RESAMPLE.get((resample or "nearest").lower(), Image.NEAREST)
    out: List[Image.Image] = []
    for t in tiles:
        im = t if t.mode == "RGBA" else t.convert("RGBA")
        if im.size != (width, height):
            im = im.resize((width, height), rs)
        out.append(im)
    return out, width, height


def _resolve_names(raw_names: Any, count: int) -> List[str]:
    if isinstance(raw_names, list) and raw_names:
        names = [str(x).strip() for x in raw_names if str(x).strip()]
        if len(names) >= count:
            return names[:count]
    return [f"terrain_{i + 1}" for i in range(count)]


def _resolve_colors(raw_colors: Any, count: int) -> List[str]:
    colors: List[str] = []
    if isinstance(raw_colors, list):
        for item in raw_colors:
            s = str(item).strip()
            if s:
                colors.append(s)
    while len(colors) < count:
        colors.append(_DEFAULT_COLORS[len(colors) % len(_DEFAULT_COLORS)])
    return colors[:count]


def _edge_weights(labels: Sequence[int], width: int, height: int, half_extent: float, terrain_count: int) -> np.ndarray:
    """根据 N/E/S/W 边标签生成更干净的边缘权重。

    旧实现把四条边的线性距离场直接归一化，3+ terrain 时会在很大区域
    产生泥状平均色。这里改为“最近边”软分配：每个像素主要继承最近边
    的 terrain，只在两条边的分界附近柔和过渡。
    """
    ys = np.linspace(0, 1, height, dtype=np.float32)
    xs = np.linspace(0, 1, width, dtype=np.float32)
    y, x = np.meshgrid(ys, xs, indexing="ij")

    side_distances = np.stack([
        y,          # Top
        1.0 - x,   # Right
        1.0 - y,   # Bottom
        x,          # Left
    ], axis=0)
    softness = max(1e-6, float(half_extent) * 0.25)
    side_scores = np.exp(-side_distances / softness).astype(np.float32)
    side_scores /= np.clip(side_scores.sum(axis=0, keepdims=True), 1e-6, None)

    weights = np.zeros((terrain_count, height, width), dtype=np.float32)
    for side_idx, terrain_idx in enumerate(labels):
        weights[int(terrain_idx)] += side_scores[side_idx]

    weights = np.power(np.clip(weights, 0.0, 1.0), 1.35)
    denom = np.clip(weights.sum(axis=0, keepdims=True), 1e-6, None)
    return weights / denom


def _corner_weights(labels: Sequence[int], width: int, height: int, terrain_count: int) -> np.ndarray:
    """根据 Tiled Corner WangSet 原生顺序 TR/BR/BL/TL 生成角权重。"""
    ys = np.linspace(0, 1, height, dtype=np.float32)
    xs = np.linspace(0, 1, width, dtype=np.float32)
    y, x = np.meshgrid(ys, xs, indexing="ij")

    weights = np.zeros((terrain_count, height, width), dtype=np.float32)
    for terrain_idx in range(terrain_count):
        tr = 1.0 if labels[0] == terrain_idx else 0.0
        br = 1.0 if labels[1] == terrain_idx else 0.0
        bl = 1.0 if labels[2] == terrain_idx else 0.0
        tl = 1.0 if labels[3] == terrain_idx else 0.0
        top = tl * (1.0 - x) + tr * x
        bottom = bl * (1.0 - x) + br * x
        acc = top * (1.0 - y) + bottom * y
        weights[terrain_idx] = acc * acc * (3.0 - 2.0 * acc)
    denom = np.clip(weights.sum(axis=0, keepdims=True), 1e-6, None)
    return weights / denom


def _mixed_labels_from_corners(labels: Sequence[int]) -> List[int]:
    """从 TR/BR/BL/TL 四角派生 Tiled mixed wangid 的 8 段标签。

    输出顺序遵循 Tiled WangId：Top, TopRight, Right, BottomRight,
    Bottom, BottomLeft, Left, TopLeft。
    """
    tr, br, bl, tl = [int(x) for x in labels]
    top = tl if tl == tr else tr
    right = tr if tr == br else br
    bottom = bl if bl == br else br
    left = tl if tl == bl else bl
    return [top, tr, right, br, bottom, bl, left, tl]


def _blend_tiles(base_np: np.ndarray, weights: np.ndarray) -> Image.Image:
    blended = np.einsum("thwc,thw->hwc", base_np, weights, optimize=True)
    return Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8), mode="RGBA")


@register("multi_terrain_wang_set")
class MultiTerrainWangSetAction(Action):
    description = "从多张基础 terrain 贴图生成多 terrain 的 edge/corner/mixed wang tileset"
    param_hints = {
        "mode": {"enum": ["edge", "corner", "mixed", "both", "all"]},
        "half_extent": {"min": 0.1, "max": 1.0, "step": 0.05},
        "resample": {"enum": ["nearest", "bilinear", "bicubic", "lanczos"]},
        "expected": {"min": 0, "max": 16, "step": 1},
        "tile_width": {"min": 0, "step": 1},
        "tile_height": {"min": 0, "step": 1},
    }
    def run(
        self,
        ctx: Context,
        mode: str = "both",
        half_extent: float = 0.5,
        resample: str = "nearest",
        expected: int = 0,
        tile_width: Any = 0,
        tile_height: Any = 0,
        terrain_names: Any = None,
        terrain_colors: Any = None,
        edge_wangset_name: str = "edge_set",
        corner_wangset_name: str = "corner_set",
        mixed_wangset_name: str = "mixed_set",
    ) -> Context:
        source_tiles = ctx.extras.get("tiles") or []
        if not source_tiles:
            raise RuntimeError(
                "[multi_terrain_wang_set] ctx.extras['tiles'] 为空。"
                "请先用 load_dir 读取基础 terrain 贴图目录。"
            )
        if expected and len(source_tiles) != int(expected):
            raise RuntimeError(
                f"[multi_terrain_wang_set] 期望 {expected} 张基础 terrain，实际 {len(source_tiles)} 张。"
            )

        mode = (mode or "both").lower()
        if mode not in ("edge", "corner", "mixed", "both", "all"):
            raise ValueError("[multi_terrain_wang_set] mode 应为 edge / corner / mixed / both / all")
        include_edge = mode in ("edge", "both", "all")
        include_corner = mode in ("corner", "both", "all")
        include_mixed = mode in ("mixed", "all")

        base_tiles, width, height = _normalize_rgba_tiles(
            source_tiles,
            resample,
            tile_width=tile_width,
            tile_height=tile_height,
        )
        terrain_count = len(base_tiles)
        if terrain_count < 2:
            raise RuntimeError("[multi_terrain_wang_set] 至少需要 2 张基础 terrain 贴图")
        if terrain_count > 6:
            raise RuntimeError("[multi_terrain_wang_set] 当前建议 terrain 数量不超过 6")

        names = _resolve_names(terrain_names or ctx.extras.get("tile_names"), terrain_count)
        colors = _resolve_colors(terrain_colors, terrain_count)
        base_np = np.asarray([np.asarray(t, dtype=np.float32) for t in base_tiles], dtype=np.float32)

        out_tiles: List[Image.Image] = []
        out_names: List[str] = []
        wang_multisets: List[Dict[str, Any]] = []
        offset = 0
        combos = list(product(range(terrain_count), repeat=4))

        if include_edge:
            edge_entries: List[Dict[str, Any]] = []
            for idx, labels in enumerate(combos):
                weights = _edge_weights(labels, width, height, float(half_extent), terrain_count)
                out_tiles.append(_blend_tiles(base_np, weights))
                out_names.append(
                    "edge_" + "_".join(names[i] for i in labels)
                )
                edge_entries.append({"tileid": offset + idx, "wang": list(labels)})
            wang_multisets.append({
                "name": edge_wangset_name,
                "type": "edge",
                "icon_tileid": offset,
                "terrains": [
                    {"name": names[i], "color": colors[i], "tile": offset + i * (terrain_count ** 3 + terrain_count ** 2 + terrain_count + 1)}
                    for i in range(terrain_count)
                ],
                "tiles": edge_entries,
            })
            offset += len(combos)

        if include_corner:
            corner_entries: List[Dict[str, Any]] = []
            for idx, labels in enumerate(combos):
                weights = _corner_weights(labels, width, height, terrain_count)
                out_tiles.append(_blend_tiles(base_np, weights))
                out_names.append(
                    "corner_" + "_".join(names[i] for i in labels)
                )
                corner_entries.append({"tileid": offset + idx, "wang": list(labels)})
            wang_multisets.append({
                "name": corner_wangset_name,
                "type": "corner",
                "icon_tileid": offset,
                "terrains": [
                    {"name": names[i], "color": colors[i], "tile": offset + i * (terrain_count ** 3 + terrain_count ** 2 + terrain_count + 1)}
                    for i in range(terrain_count)
                ],
                "tiles": corner_entries,
            })
            offset += len(combos)

        if include_mixed:
            mixed_entries: List[Dict[str, Any]] = []
            for idx, labels in enumerate(combos):
                weights = _corner_weights(labels, width, height, terrain_count)
                out_tiles.append(_blend_tiles(base_np, weights))
                out_names.append(
                    "mixed_" + "_".join(names[i] for i in labels)
                )
                mixed_entries.append({
                    "tileid": offset + idx,
                    "wang": _mixed_labels_from_corners(labels),
                })
            wang_multisets.append({
                "name": mixed_wangset_name,
                "type": "mixed",
                "icon_tileid": offset,
                "terrains": [
                    {"name": names[i], "color": colors[i], "tile": offset + i * (terrain_count ** 3 + terrain_count ** 2 + terrain_count + 1)}
                    for i in range(terrain_count)
                ],
                "tiles": mixed_entries,
            })
            offset += len(combos)

        ctx.image = out_tiles[-1]
        ctx.extras["tiles"] = out_tiles
        ctx.extras["tile_names"] = out_names
        ctx.extras["wang_multisets"] = wang_multisets
        ctx.extras["multi_terrain_wang"] = {
            "mode": mode,
            "terrain_count": terrain_count,
            "combo_count": terrain_count ** 4,
            "tile_count": len(out_tiles),
            "terrain_names": names,
            "terrain_colors": colors,
            "tile_size": [width, height],
        }
        print(
            f"[multi_terrain_wang_set] terrains={terrain_count} mode={mode} "
            f"combos={terrain_count ** 4} out_tiles={len(out_tiles)} tile={width}x{height}"
        )
        return ctx
