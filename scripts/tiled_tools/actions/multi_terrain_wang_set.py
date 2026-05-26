# -*- coding: utf-8 -*-
"""multi_terrain_wang_set: 从多张基础 terrain 贴图生成多地形 wang 规则集。

典型输入：
- 先用 `load_dir` 读取一个目录中的基础地形循环贴图（grass / sand / water ...）
- 然后本 action 按 edge / corner / mixed / both / all 生成组合：
  * edge   : N^4 张（顺序 N/E/S/W）
  * corner : N^4 张（Tiled 原生顺序 TR/BR/BL/TL）
  * mixed  : N^4 张（完整 8 段 wangid，图像复用 corner 形状）
  * both   : 2 * N^4 张（先 edge 后 corner，保留独立图案）
  * all    : N^4 张共享图案，edge/corner/mixed 三个 wangset 指向同一批 tileid

输出：
- `ctx.extras["tiles"]`      : 组合后的 tile 列表（RGBA）
- `ctx.extras["tile_names"]` : 每张 tile 的名字
- `ctx.extras["wang_multisets"]`:
    给 `build_tsx_sheet` 用的泛化 wangset 元数据，可自动写入多 terrain 的
    `<wangsets>` / `<wangcolor>` / `<wangtile>`。

设计目标：
- 不是去穷举“成对过渡”再拆多个 tileset，而是直接生成含 N 个 terrain 的 wangset；
  Tiled 里每条边/每个角都可以指向 1..N 中任意一种 terrain。
- `mode=all` 专门用于同一图案同时参与 Edge Set / Corner Set / Mixed Set，避免
  同图案被复制成三份 tile，导致同一个 tile 不能同时触发三类地形集。
- 美术上这只是一个“通用混合启发式”：角集根据角标签做多材质双线性混合，
  边集按旋转 45° 后的角集逻辑反推。对于 3+ terrain 的复杂交汇，它能保证
  边界连续，但是否完全符合期望造型仍取决于素材风格；必要时可在生成结果上再手工修图。
"""
from __future__ import annotations

from itertools import combinations, permutations, product
from typing import Any, Dict, List, Optional, Sequence, Tuple

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
    """根据 Tiled Edge WangSet 原生顺序 Top/Right/Bottom/Left 生成边权重。

    corner_set 已验证可用，它的核心是四角 one-hot 双线性插值。edge_set 这里
    反推为一张旋转 45° 的 corner_set：Top/Right/Bottom/Left 分别落到旋转
    坐标里的 TL/TR/BR/BL，再复用同样的 smoothstep + 归一化策略。
    """
    ys = np.linspace(0, 1, height, dtype=np.float32)
    xs = np.linspace(0, 1, width, dtype=np.float32)
    y, x = np.meshgrid(ys, xs, indexing="ij")

    extent = min(0.5, max(1e-6, float(half_extent)))
    rx = np.clip((x + y - 1.0 + extent) / (2.0 * extent), 0.0, 1.0)
    ry = np.clip((extent - x + y) / (2.0 * extent), 0.0, 1.0)

    weights = np.zeros((terrain_count, height, width), dtype=np.float32)
    for terrain_idx in range(terrain_count):
        tr = 1.0 if labels[1] == terrain_idx else 0.0
        br = 1.0 if labels[2] == terrain_idx else 0.0
        bl = 1.0 if labels[3] == terrain_idx else 0.0
        tl = 1.0 if labels[0] == terrain_idx else 0.0
        top = tl * (1.0 - rx) + tr * rx
        bottom = bl * (1.0 - rx) + br * rx
        acc = top * (1.0 - ry) + bottom * ry
        weights[terrain_idx] = acc * acc * (3.0 - 2.0 * acc)
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


def _edge_labels_from_corners(labels: Sequence[int]) -> List[int]:
    """从 TR/BR/BL/TL 四角派生 Edge Set 的 Top/Right/Bottom/Left 标签。"""
    mixed = _mixed_labels_from_corners(labels)
    return [mixed[0], mixed[2], mixed[4], mixed[6]]


def _blend_tiles(base_np: np.ndarray, weights: np.ndarray) -> Image.Image:
    blended = np.einsum("thwc,thw->hwc", base_np, weights, optimize=True)
    return Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8), mode="RGBA")


_KIND_SORT_RANK = {
    "shared": 0,
    "edge": 0,
    "corner": 1,
    "mixed": 2,
}


def _rotate_left(values: Sequence[int], amount: int) -> Tuple[int, ...]:
    vals = tuple(int(x) for x in values)
    if not vals:
        return tuple()
    amount = amount % len(vals)
    return vals[amount:] + vals[:amount]


def _bits_to_int(bits: Sequence[int]) -> int:
    value = 0
    for i, bit in enumerate(bits):
        if int(bit):
            value |= 1 << i
    return value


def _canonical_bit_shape(bits: Sequence[int]) -> Tuple[int, int]:
    best_mask = None
    best_rotation = 0
    for rotation in range(len(bits)):
        mask = _bits_to_int(_rotate_left(bits, rotation))
        if best_mask is None or mask < best_mask:
            best_mask = mask
            best_rotation = rotation
    return int(best_mask or 0), best_rotation


def _normalize_pattern(values: Sequence[int]) -> Tuple[int, ...]:
    mapping: Dict[int, int] = {}
    next_id = 0
    normalized: List[int] = []
    for raw in values:
        value = int(raw)
        if value not in mapping:
            mapping[value] = next_id
            next_id += 1
        normalized.append(mapping[value])
    return tuple(normalized)


def _canonical_pattern_shape(labels: Sequence[int]) -> Tuple[Tuple[int, ...], int]:
    best_pattern = None
    best_rotation = 0
    for rotation in range(len(labels)):
        pattern = _normalize_pattern(_rotate_left(labels, rotation))
        if best_pattern is None or pattern < best_pattern:
            best_pattern = pattern
            best_rotation = rotation
    return tuple(best_pattern or ()), best_rotation


def _pair_shape_key(labels: Sequence[int], unique: Tuple[int, int]) -> Tuple[Tuple[Any, ...], int, int, int]:
    foreground = unique[-1]
    bits = tuple(1 if int(value) == foreground else 0 for value in labels)
    count = sum(bits)
    polarity = 0
    shape_bits = bits
    shape_count = count
    if count > len(bits) / 2:
        shape_bits = tuple(1 - bit for bit in bits)
        shape_count = len(bits) - count
        polarity = 1
    canonical_mask, rotation = _canonical_bit_shape(shape_bits)
    return (1, shape_count, canonical_mask), rotation, polarity, _bits_to_int(bits)


def _directional_sort_key(meta: Dict[str, Any]) -> Tuple[Any, ...]:
    labels = tuple(int(x) for x in (meta.get("sort_labels") or []))
    unique = tuple(sorted(set(labels)))
    set_type = str(meta.get("set_type") or "shared")
    set_rank = _KIND_SORT_RANK.get(set_type, 9)
    original_tileid = int(meta.get("tileid") or 0)

    if len(unique) <= 1:
        shape_key: Tuple[Any, ...] = (0,)
        rotation = 0
        polarity = 0
        raw_mask = 0
    elif len(unique) == 2:
        shape_key, rotation, polarity, raw_mask = _pair_shape_key(labels, (unique[0], unique[1]))
    else:
        counts = tuple(sorted((labels.count(value) for value in unique), reverse=True))
        pattern, rotation = _canonical_pattern_shape(labels)
        shape_key = (2, counts, pattern)
        polarity = 0
        raw_mask = 0

    return (
        set_rank,
        len(unique),
        unique,
        shape_key,
        rotation,
        polarity,
        raw_mask,
        labels,
        original_tileid,
    )


_CORNER_POSITIONS = (
    (1, -1),   # TR
    (1, 1),    # BR
    (-1, 1),   # BL
    (-1, -1),  # TL
)
_EDGE_POSITIONS = (
    (0, -1),   # Top
    (1, 0),    # Right
    (0, 1),    # Bottom
    (-1, 0),   # Left
)
_CELL_ROW_MAJOR = (0, 1, 2, 3, 4, 5, 6, 7, 8)
_CELL_CENTER = 4


def _sign_cell(value: float) -> int:
    if value < -0.25:
        return 0
    if value > 0.25:
        return 2
    return 1


def _grid_positions_for_meta(meta: Dict[str, Any]) -> Tuple[Tuple[int, int], ...]:
    set_type = str(meta.get("set_type") or "shared").strip().lower()
    if set_type == "edge":
        return _EDGE_POSITIONS
    return _CORNER_POSITIONS


def _slot_labels(set_type: str, terrain: int, partner: int, cell: int) -> Tuple[int, ...]:
    positions = _EDGE_POSITIONS if set_type == "edge" else _CORNER_POSITIONS
    cell_x = cell % 3 - 1
    cell_y = cell // 3 - 1
    if cell_x == 0 and cell_y == 0:
        return tuple([terrain] * len(positions))

    is_edge_positions = positions == _EDGE_POSITIONS
    labels: List[int] = []
    for pos_x, pos_y in positions:
        if cell_x == 0:
            is_foreign = pos_y == cell_y
        elif cell_y == 0:
            is_foreign = pos_x == cell_x
        elif is_edge_positions:
            is_foreign = pos_x == cell_x or pos_y == cell_y
        else:
            is_foreign = pos_x == cell_x and pos_y == cell_y
        labels.append(partner if is_foreign else terrain)
    return tuple(labels)


def _slot_candidate_key(meta: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        _KIND_SORT_RANK.get(str(meta.get("set_type") or "shared"), 9),
        _representative_sort_key(meta),
    )


def _terrain_grid_info(meta: Dict[str, Any]) -> Dict[str, Any]:
    labels = tuple(int(x) for x in (meta.get("sort_labels") or []))
    positions = _grid_positions_for_meta(meta)
    counts: Dict[int, int] = {}
    for value in labels:
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        anchor = 0
    else:
        anchor = min(counts, key=lambda value: (-counts[value], value))

    foreign_positions = [positions[i] for i, value in enumerate(labels) if int(value) != anchor]
    if not foreign_positions:
        cell = _CELL_CENTER
        avg_x = 0.0
        avg_y = 0.0
    else:
        avg_x = sum(pos[0] for pos in foreign_positions) / len(foreign_positions)
        avg_y = sum(pos[1] for pos in foreign_positions) / len(foreign_positions)
        cell = _sign_cell(avg_y) * 3 + _sign_cell(avg_x)

    unique = tuple(sorted(counts))
    non_anchor_count = len(foreign_positions)
    is_solid = len(unique) <= 1
    is_pair = len(unique) == 2
    other_values = tuple(value for value in unique if value != anchor)
    spread = abs(avg_x) + abs(avg_y)
    original_tileid = int(meta.get("tileid") or 0)

    return {
        "anchor": anchor,
        "cell": cell,
        "labels": labels,
        "unique": unique,
        "non_anchor_count": non_anchor_count,
        "is_solid": is_solid,
        "is_pair": is_pair,
        "other_values": other_values,
        "spread": spread,
        "original_tileid": original_tileid,
    }


def _terrain_grid_sort_key(meta: Dict[str, Any]) -> Tuple[Any, ...]:
    info = meta.get("grid_info") or _terrain_grid_info(meta)
    labels = tuple(int(x) for x in (meta.get("sort_labels") or []))
    cell = int(info["cell"])
    center_penalty = 0 if bool(info["is_solid"]) else 1
    pair_penalty = 0 if bool(info["is_pair"]) else 1
    directional_strength = -float(info["spread"])
    return (
        _KIND_SORT_RANK.get(str(meta.get("set_type") or "shared"), 9),
        int(info["anchor"]),
        cell,
        center_penalty,
        pair_penalty,
        int(info["non_anchor_count"]),
        tuple(info["other_values"]),
        directional_strength,
        labels,
        int(info["original_tileid"]),
    )


def _representative_sort_key(meta: Dict[str, Any]) -> Tuple[Any, ...]:
    info = meta.get("grid_info") or _terrain_grid_info(meta)
    cell = int(info["cell"])
    if cell == _CELL_CENTER:
        desired_count = 0
    elif cell in (1, 3, 5, 7):
        desired_count = 2
    else:
        desired_count = 1
    return (
        0 if bool(info["is_solid"]) else 1,
        0 if bool(info["is_pair"]) else 1,
        abs(int(info["non_anchor_count"]) - desired_count),
        tuple(info["other_values"]),
        -float(info["spread"]),
        tuple(int(x) for x in (meta.get("sort_labels") or [])),
        int(info["original_tileid"]),
    )


def _parse_layout_columns(value: Any, tile_count: int) -> int:
    try:
        columns = int(value or 0)
    except (TypeError, ValueError):
        columns = 0
    if columns > 0:
        return max(1, columns)
    return max(1, int(np.ceil(np.sqrt(max(1, tile_count)))))


def _terrain_grid_order(order_meta: List[Dict[str, Any]], terrain_count: int, layout_columns: Any) -> List[int]:
    tile_count = len(order_meta)
    if tile_count <= 0:
        return []
    columns = _parse_layout_columns(layout_columns, tile_count)
    block_width = 3
    block_height = 3
    blocks_per_row = max(1, columns // block_width)

    enriched: List[Dict[str, Any]] = []
    by_anchor_cell: Dict[Tuple[int, int], List[int]] = {}
    for index, meta in enumerate(order_meta):
        item = dict(meta)
        item["grid_info"] = _terrain_grid_info(item)
        enriched.append(item)
        info = item["grid_info"]
        by_anchor_cell.setdefault((int(info["anchor"]), int(info["cell"])), []).append(index)

    used: set[int] = set()
    positioned: Dict[int, int] = {}

    for terrain_index in range(max(0, int(terrain_count))):
        partner = (terrain_index + 1) % max(1, int(terrain_count))
        block_row = terrain_index // blocks_per_row
        block_col = terrain_index % blocks_per_row
        for cell in _CELL_ROW_MAJOR:
            exact_candidates = []
            for idx, item in enumerate(enriched):
                if idx in used:
                    continue
                set_type = str(item.get("set_type") or "shared").strip().lower()
                if tuple(int(x) for x in (item.get("sort_labels") or [])) == _slot_labels(set_type, terrain_index, partner, cell):
                    exact_candidates.append(idx)
            candidates = exact_candidates or [
                idx for idx in by_anchor_cell.get((terrain_index, cell), []) if idx not in used
            ]
            if not candidates:
                continue
            chosen = min(candidates, key=lambda idx: _slot_candidate_key(enriched[idx]))
            cell_row = cell // block_width
            cell_col = cell % block_width
            target_pos = (block_row * block_height + cell_row) * columns + block_col * block_width + cell_col
            if target_pos >= tile_count or target_pos in positioned:
                continue
            positioned[target_pos] = chosen
            used.add(chosen)

    remaining = [idx for idx in range(tile_count) if idx not in used]
    remaining.sort(key=lambda idx: _terrain_grid_sort_key(enriched[idx]))
    remaining_iter = iter(remaining)

    order: List[int] = []
    for pos in range(tile_count):
        if pos in positioned:
            order.append(positioned[pos])
        else:
            order.append(next(remaining_iter))
    return order


def _frame_slot_labels(set_type: str, terrain: int, partner: int, row: int, col: int) -> Tuple[int, ...]:
    positions = _EDGE_POSITIONS if set_type == "edge" else _CORNER_POSITIONS
    labels: List[int] = []
    for pos_x, pos_y in positions:
        sample_x = col + 0.5 + pos_x * 0.5
        sample_y = row + 0.5 + pos_y * 0.5
        is_inside_center = 1.0 <= sample_x <= 4.0 and 1.0 <= sample_y <= 4.0
        labels.append(terrain if is_inside_center else partner)
    return tuple(labels)


_JUNCTION_REPEAT_POSITION_RANK = {
    (0, 3): 0,  # top side: TR + TL
    (0, 1): 1,  # right side: TR + BR
    (1, 2): 2,  # bottom side: BR + BL
    (2, 3): 3,  # left side: BL + TL
    (0, 2): 4,  # diagonal: TR + BL
    (1, 3): 5,  # diagonal: BR + TL
}


def _permutation_rank(values: Sequence[int], choices: Sequence[int]) -> int:
    target = tuple(int(x) for x in values)
    for rank, perm in enumerate(permutations(tuple(int(x) for x in choices))):
        if perm == target:
            return rank
    return 0


def _junction_slot_for_labels(labels: Sequence[int], combo: Sequence[int]) -> Optional[Tuple[int, int]]:
    labels_tuple = tuple(int(x) for x in labels)
    combo_tuple = tuple(int(x) for x in combo)
    if len(labels_tuple) != 4 or tuple(sorted(set(labels_tuple))) != combo_tuple:
        return None

    if len(combo_tuple) == 3:
        counts = {value: labels_tuple.count(value) for value in combo_tuple}
        repeated_values = [value for value, count in counts.items() if count == 2]
        if len(repeated_values) != 1:
            return None
        repeated = repeated_values[0]
        repeated_positions = tuple(i for i, value in enumerate(labels_tuple) if value == repeated)
        shape_col = _JUNCTION_REPEAT_POSITION_RANK.get(repeated_positions)
        if shape_col is None:
            return None
        singleton_positions = [i for i in range(4) if i not in repeated_positions]
        singleton_values = tuple(labels_tuple[i] for i in singleton_positions)
        expected_singletons = tuple(value for value in combo_tuple if value != repeated)
        singleton_order = 0 if singleton_values == expected_singletons else 1
        row = combo_tuple.index(repeated) * 2 + singleton_order
        return row, shape_col

    if len(combo_tuple) == 4:
        first = labels_tuple[0]
        row = combo_tuple.index(first)
        remaining_choices = tuple(value for value in combo_tuple if value != first)
        col = _permutation_rank(labels_tuple[1:], remaining_choices)
        return row, col

    return None


def _visual_frame_name(
    base_name: str,
    terrain_names: Sequence[str],
    terrain: int,
    partner: int,
    row: int,
    col: int,
) -> str:
    terrain_name = terrain_names[terrain] if 0 <= terrain < len(terrain_names) else f"terrain_{terrain + 1}"
    partner_name = terrain_names[partner] if 0 <= partner < len(terrain_names) else f"terrain_{partner + 1}"
    return f"visual_{terrain_name}_to_{partner_name}_{row}_{col}_{base_name}"


def _terrain_display_name(terrain_names: Sequence[str], terrain: int) -> str:
    return terrain_names[terrain] if 0 <= terrain < len(terrain_names) else f"terrain_{terrain + 1}"


def _visual_junction_name(
    base_name: str,
    terrain_names: Sequence[str],
    combo: Sequence[int],
    row: int,
    col: int,
) -> str:
    combo_name = "_".join(_terrain_display_name(terrain_names, int(value)) for value in combo)
    return f"visual_junction_{combo_name}_{row}_{col}_{base_name}"


def _semantic_pair_hint_labels(
    first: int,
    second: int,
    orientation: str,
    row: int,
    col: int,
    width: int,
    height: int,
) -> Tuple[int, ...]:
    labels: List[int] = []
    horizontal = orientation == "horizontal"
    split = (float(width) if horizontal else float(height)) / 2.0
    for pos_x, pos_y in _CORNER_POSITIONS:
        sample_x = col + 0.5 + pos_x * 0.5
        sample_y = row + 0.5 + pos_y * 0.5
        value = sample_x if horizontal else sample_y
        labels.append(first if value < split else second)
    return tuple(labels)


def _semantic_junction_visual_labels(combo: Sequence[int], row: int, col: int) -> Optional[Tuple[int, ...]]:
    values = tuple(int(value) for value in combo)
    if len(values) == 3:
        a, b, c = values
        if row < 3:
            if col < 3:
                return (a, a, a, a)
            if col < 9:
                return _semantic_pair_hint_labels(a, b, "horizontal", row, col - 3, 6, 3)
            return (b, b, b, b)
        if col < 3:
            return _semantic_pair_hint_labels(a, c, "vertical", row - 3, col, 3, 6)
        if col >= 9:
            return _semantic_pair_hint_labels(b, c, "vertical", row - 3, col - 9, 3, 6)
        return None

    if len(values) == 4:
        a, b, c, d = values
        if row < 3:
            if col < 3:
                return (a, a, a, a)
            if col < 9:
                return _semantic_pair_hint_labels(a, b, "horizontal", row, col - 3, 6, 3)
            return (b, b, b, b)
        if row < 9:
            if col < 3:
                return _semantic_pair_hint_labels(a, c, "vertical", row - 3, col, 3, 6)
            if col >= 9:
                return _semantic_pair_hint_labels(b, d, "vertical", row - 3, col - 9, 3, 6)
            return None
        if col < 3:
            return (c, c, c, c)
        if col < 9:
            return _semantic_pair_hint_labels(c, d, "horizontal", row - 9, col - 3, 6, 3)
        return (d, d, d, d)

    return None


def _find_tile_by_labels(
    order_meta: Sequence[Dict[str, Any]],
    labels: Sequence[int],
    preferred_set_types: Optional[Sequence[str]] = None,
) -> Optional[int]:
    target = tuple(int(value) for value in labels)
    candidates = [
        index for index, item in enumerate(order_meta)
        if tuple(int(x) for x in (item.get("sort_labels") or [])) == target
    ]
    if not candidates:
        return None
    if preferred_set_types:
        preferred = {str(value).strip().lower() for value in preferred_set_types}
        preferred_candidates = [
            index for index in candidates
            if str(order_meta[index].get("set_type") or "shared").strip().lower() in preferred
        ]
        if preferred_candidates:
            candidates = preferred_candidates
    return min(candidates, key=lambda index: _slot_candidate_key(order_meta[index]))


def _corner_left_edge(labels: Sequence[int]) -> Tuple[int, int]:
    return int(labels[3]), int(labels[2])


def _corner_right_edge(labels: Sequence[int]) -> Tuple[int, int]:
    return int(labels[0]), int(labels[1])


def _corner_top_context_labels(labels: Sequence[int]) -> Tuple[int, int, int, int]:
    tr, _br, _bl, tl = [int(value) for value in labels]
    return tr, tr, tl, tl


def _corner_bottom_context_labels(labels: Sequence[int]) -> Tuple[int, int, int, int]:
    _tr, br, bl, _tl = [int(value) for value in labels]
    return br, br, bl, bl


def _corner_left_context_labels(labels: Sequence[int]) -> Tuple[int, int, int, int]:
    _tr, _br, bl, tl = [int(value) for value in labels]
    return tl, bl, bl, tl


def _corner_right_context_labels(labels: Sequence[int]) -> Tuple[int, int, int, int]:
    tr, br, _bl, _tl = [int(value) for value in labels]
    return tr, br, br, tr


def _junction_scene_sort_key(labels: Sequence[int], combo: Sequence[int]) -> Tuple[Any, ...]:
    slot = _junction_slot_for_labels(labels, combo)
    if slot is None:
        return (999, tuple(int(value) for value in labels))
    row, col = slot
    return (row, col, tuple(int(value) for value in labels))


def _junction_target_labels(combo: Sequence[int]) -> List[Tuple[int, int, int, int]]:
    combo_tuple = tuple(int(value) for value in combo)
    targets = [
        tuple(int(value) for value in labels)
        for labels in product(combo_tuple, repeat=4)
        if tuple(sorted(set(int(value) for value in labels))) == combo_tuple
    ]
    targets.sort(key=lambda labels: _junction_scene_sort_key(labels, combo_tuple))
    return targets


def _junction_euler_sequences(
    combo: Sequence[int],
    targets: Sequence[Tuple[int, int, int, int]],
) -> List[List[Tuple[int, int, int, int]]]:
    adjacency: Dict[Tuple[int, int], List[Tuple[Tuple[int, int], Tuple[int, int, int, int]]]] = {}
    for labels in targets:
        start = _corner_left_edge(labels)
        end = _corner_right_edge(labels)
        adjacency.setdefault(start, []).append((end, labels))
        adjacency.setdefault(end, adjacency.get(end, []))

    for edges in adjacency.values():
        edges.sort(key=lambda item: _junction_scene_sort_key(item[1], combo), reverse=True)

    sequences: List[List[Tuple[int, int, int, int]]] = []
    while True:
        starts = [vertex for vertex, edges in adjacency.items() if edges]
        if not starts:
            break
        start = min(starts)
        stack: List[Tuple[Tuple[int, int], Optional[Tuple[int, int, int, int]]]] = [(start, None)]
        path: List[Tuple[int, int, int, int]] = []
        while stack:
            vertex, incoming = stack[-1]
            edges = adjacency.get(vertex) or []
            if edges:
                next_vertex, labels = edges.pop()
                stack.append((next_vertex, labels))
                continue
            _vertex, labels = stack.pop()
            if labels is not None:
                path.append(labels)
        path.reverse()
        if path:
            sequences.append(path)

    sequences.sort(key=lambda sequence: _junction_scene_sort_key(sequence[0], combo))
    return sequences


def _junction_scene_strips(
    combo: Sequence[int],
    max_targets_per_strip: int,
) -> List[List[Tuple[int, int, int, int]]]:
    targets = _junction_target_labels(combo)
    sequences = _junction_euler_sequences(combo, targets)
    width = max(1, int(max_targets_per_strip))
    strips: List[List[Tuple[int, int, int, int]]] = []
    for sequence in sequences:
        for offset in range(0, len(sequence), width):
            strip = sequence[offset:offset + width]
            if strip:
                strips.append(strip)
    return strips


def _remap_wang_multisets(wang_multisets: List[Dict[str, Any]], old_to_new: Dict[int, int]) -> None:
    for spec in wang_multisets:
        if "icon_tileid" in spec:
            old_icon = int(spec.get("icon_tileid") or 0)
            spec["icon_tileid"] = old_to_new.get(old_icon, old_icon)
        for terrain in spec.get("terrains") or []:
            old_tile = int(terrain.get("tile") or 0)
            terrain["tile"] = old_to_new.get(old_tile, old_tile)
        for entry in spec.get("tiles") or []:
            old_tileid = int(entry.get("tileid") or 0)
            entry["tileid"] = old_to_new.get(old_tileid, old_tileid)
        spec["tiles"] = sorted(spec.get("tiles") or [], key=lambda entry: int(entry.get("tileid") or 0))


def _apply_terrain_scene_source_layout(
    out_tiles: List[Image.Image],
    out_names: List[str],
    order_meta: List[Dict[str, Any]],
    wang_multisets: List[Dict[str, Any]],
    terrain_count: int,
    layout_columns: Any = 0,
    terrain_names: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    tile_count = len(out_tiles)
    if tile_count <= 0:
        return {"mode": "terrain_scene_source", "changed": False}
    if len(order_meta) != tile_count:
        raise RuntimeError("[multi_terrain_wang_set] tile 排序元数据数量与 tile 数量不一致")

    names = list(terrain_names or [])
    columns = max(15, _parse_layout_columns(layout_columns, tile_count))
    pair_block_width = 5
    pair_block_height = 5
    pair_blocks_per_row = max(1, min(max(1, int(terrain_count) - 1), columns // pair_block_width))
    old_tiles = list(out_tiles)
    old_names = list(out_names)
    old_meta = [dict(item) for item in order_meta]

    used_old: set[int] = set()
    positioned: Dict[int, Dict[str, Any]] = {}
    reserved_max_pos = -1
    block_index = 0

    for terrain_index in range(max(0, int(terrain_count))):
        for partner in range(max(0, int(terrain_count))):
            if partner == terrain_index:
                continue
            block_row = block_index // pair_blocks_per_row
            block_col = block_index % pair_blocks_per_row
            reserved_max_pos = max(reserved_max_pos, ((block_row + 1) * pair_block_height) * columns - 1)
            for row in range(pair_block_height):
                for col in range(pair_block_width):
                    exact_candidates: List[int] = []
                    for idx, item in enumerate(old_meta):
                        set_type = str(item.get("set_type") or "shared").strip().lower()
                        labels = tuple(int(x) for x in (item.get("sort_labels") or []))
                        if labels == _frame_slot_labels(set_type, terrain_index, partner, row, col):
                            exact_candidates.append(idx)
                    if not exact_candidates:
                        continue
                    unused_candidates = [idx for idx in exact_candidates if idx not in used_old]
                    chosen = min(unused_candidates or exact_candidates, key=lambda idx: _slot_candidate_key(old_meta[idx]))
                    is_duplicate = chosen in used_old
                    if not is_duplicate:
                        used_old.add(chosen)
                    target_pos = (block_row * pair_block_height + row) * columns + block_col * pair_block_width + col
                    positioned[target_pos] = {
                        "old_idx": chosen,
                        "duplicate": is_duplicate,
                        "terrain": terrain_index,
                        "partner": partner,
                        "row": row,
                        "col": col,
                    }
            block_index += 1

    pair_section_rows = int(np.ceil(block_index / pair_blocks_per_row)) * pair_block_height if block_index else 0
    scene_row = pair_section_rows + 1
    scene_block_count = 0
    scene_source_tiles = 0
    scene_context_tiles = 0
    scene_rows_used = 0
    if pair_section_rows:
        reserved_max_pos = max(reserved_max_pos, pair_section_rows * columns - 1)
    max_targets_per_scene = max(1, columns - 2)

    def place_scene_tile(
        target_pos: int,
        labels: Sequence[int],
        combo: Sequence[int],
        scene_index: int,
        scene_local_row: int,
        scene_local_col: int,
        context_kind: str,
    ) -> None:
        nonlocal scene_source_tiles, scene_context_tiles
        source_idx = _find_tile_by_labels(old_meta, labels, preferred_set_types=("shared", "corner"))
        if source_idx is None:
            return
        is_source = context_kind == "source"
        is_duplicate = (not is_source) or source_idx in used_old
        if is_source and not is_duplicate:
            used_old.add(source_idx)
            scene_source_tiles += 1
        else:
            scene_context_tiles += 1
        entry: Dict[str, Any] = {
            "old_idx": source_idx,
            "duplicate": is_duplicate,
            "scene": True,
            "combo": tuple(int(value) for value in combo),
            "strip": scene_index,
            "row": scene_local_row,
            "col": scene_local_col,
            "context_kind": context_kind,
        }
        if is_duplicate:
            combo_name = "_".join(_terrain_display_name(names, int(value)) for value in combo)
            entry["visual_name"] = (
                f"visual_scene_{combo_name}_{scene_index}_{scene_local_row}_{scene_local_col}_{context_kind}_"
                f"{old_names[source_idx]}"
            )
        positioned[target_pos] = entry

    def place_junction_scene(
        strip: Sequence[Tuple[int, int, int, int]],
        combo: Sequence[int],
        scene_index: int,
        top_row: int,
    ) -> int:
        if not strip:
            return 0
        center_row_labels = [
            _corner_left_context_labels(strip[0]),
            *[tuple(int(value) for value in labels) for labels in strip],
            _corner_right_context_labels(strip[-1]),
        ]
        scene_rows = [
            [_corner_top_context_labels(labels) for labels in center_row_labels],
            center_row_labels,
            [_corner_bottom_context_labels(labels) for labels in center_row_labels],
        ]
        scene_width = len(center_row_labels)
        if scene_width > columns:
            raise RuntimeError(
                f"[multi_terrain_wang_set] junction scene width {scene_width} exceeds layout columns {columns}"
            )
        start_col = max(0, (columns - scene_width) // 2)
        for local_row, row_labels in enumerate(scene_rows):
            for local_col, labels in enumerate(row_labels):
                if local_row == 1 and 0 < local_col < scene_width - 1:
                    context_kind = "source"
                elif local_row == 1 and local_col == 0:
                    context_kind = "left_context"
                elif local_row == 1 and local_col == scene_width - 1:
                    context_kind = "right_context"
                elif local_row == 0:
                    context_kind = "top_context"
                else:
                    context_kind = "bottom_context"
                place_scene_tile(
                    (top_row + local_row) * columns + start_col + local_col,
                    labels,
                    combo,
                    scene_index,
                    local_row,
                    local_col,
                    context_kind,
                )
        return scene_width

    for unique_count in (3, 4):
        for combo in combinations(range(max(0, int(terrain_count))), unique_count):
            strips = _junction_scene_strips(combo, max_targets_per_scene)
            for strip in strips:
                if not strip:
                    continue
                reserved_max_pos = max(reserved_max_pos, (scene_row + 3) * columns - 1)
                scene_width = place_junction_scene(
                    strip,
                    combo,
                    scene_block_count,
                    scene_row,
                )
                scene_block_count += 1
                scene_rows_used += 3
                scene_row += 4
                reserved_max_pos = max(
                    reserved_max_pos,
                    scene_row * columns - 1,
                    (scene_row - 2) * columns + min(columns, scene_width) - 1,
                )

    remaining = [idx for idx in range(tile_count) if idx not in used_old]
    remaining.sort(key=lambda idx: _terrain_grid_sort_key(old_meta[idx]))
    remaining_iter = iter(remaining)

    new_tiles: List[Image.Image] = []
    new_names: List[str] = []
    new_meta: List[Dict[str, Any]] = []
    old_to_new: Dict[int, int] = {}
    max_frame_pos = max(max(positioned) if positioned else -1, reserved_max_pos)

    def append_spacer(pos: int) -> None:
        new_tileid = len(new_tiles)
        size = old_tiles[0].size
        new_tiles.append(Image.new("RGBA", size, (0, 0, 0, 0)))
        new_names.append(f"visual_spacer_{new_tileid}")
        new_meta.append({
            "tileid": new_tileid,
            "layout_pos": pos,
            "visual_placeholder": True,
            "spacer": True,
        })

    def append_canonical(old_idx: int, pos: Optional[int] = None) -> None:
        new_tileid = len(new_tiles)
        old_to_new[old_idx] = new_tileid
        new_tiles.append(old_tiles[old_idx])
        new_names.append(old_names[old_idx])
        item = dict(old_meta[old_idx])
        item["old_tileid"] = old_idx
        item["tileid"] = new_tileid
        if pos is not None:
            item["layout_pos"] = pos
        new_meta.append(item)

    def append_visual(entry: Dict[str, Any], pos: int) -> None:
        old_idx = int(entry["old_idx"])
        new_tileid = len(new_tiles)
        new_tiles.append(old_tiles[old_idx].copy())
        visual_name = entry.get("visual_name")
        if visual_name:
            new_names.append(str(visual_name))
        elif bool(entry.get("scene")):
            combo = tuple(int(value) for value in (entry.get("combo") or ()))
            combo_name = "_".join(_terrain_display_name(names, int(value)) for value in combo)
            new_names.append(
                f"visual_scene_{combo_name}_{entry.get('strip')}_{entry.get('row')}_{entry.get('col')}_"
                f"{entry.get('context_kind', 'context')}_{old_names[old_idx]}"
            )
        else:
            new_names.append(
                _visual_frame_name(
                    old_names[old_idx],
                    names,
                    int(entry["terrain"]),
                    int(entry["partner"]),
                    int(entry["row"]),
                    int(entry["col"]),
                )
            )
        item = dict(old_meta[old_idx])
        item["old_tileid"] = old_idx
        item["source_tileid"] = old_idx
        item["tileid"] = new_tileid
        item["layout_pos"] = pos
        item["visual_placeholder"] = True
        if bool(entry.get("scene")):
            item["scene_context"] = entry.get("context_kind")
        new_meta.append(item)

    for pos in range(max_frame_pos + 1):
        entry = positioned.get(pos)
        if entry is None:
            append_spacer(pos)
        elif bool(entry.get("duplicate")):
            append_visual(entry, pos)
        else:
            append_canonical(int(entry["old_idx"]), pos)

    for old_idx in remaining_iter:
        append_canonical(old_idx)

    missing = [idx for idx in range(tile_count) if idx not in old_to_new]
    if missing:
        raise RuntimeError(
            f"[multi_terrain_wang_set] terrain_scene_source 未能映射 {len(missing)} 个原始 tile"
        )

    out_tiles[:] = new_tiles
    out_names[:] = new_names
    _remap_wang_multisets(wang_multisets, old_to_new)

    return {
        "mode": "terrain_scene_source",
        "changed": True,
        "old_to_new": old_to_new,
        "tiles": new_meta,
        "visual_placeholders": len(new_tiles) - tile_count,
        "layout_columns": columns,
        "frame_block": [pair_block_width, pair_block_height],
        "frame_center": [3, 3],
        "scene_patch": [columns, 3],
        "scene_blocks": scene_block_count,
        "junction_blocks": scene_block_count,
        "scene_rows": scene_rows_used,
        "scene_source_tiles": scene_source_tiles,
        "scene_context_tiles": scene_context_tiles,
    }


def _apply_terrain_pair_frame_layout(
    out_tiles: List[Image.Image],
    out_names: List[str],
    order_meta: List[Dict[str, Any]],
    wang_multisets: List[Dict[str, Any]],
    terrain_count: int,
    layout_columns: Any = 0,
    terrain_names: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    tile_count = len(out_tiles)
    if tile_count <= 0:
        return {"mode": "terrain_pair_frame", "changed": False}
    if len(order_meta) != tile_count:
        raise RuntimeError("[multi_terrain_wang_set] tile 排序元数据数量与 tile 数量不一致")

    names = list(terrain_names or [])
    columns = max(12, _parse_layout_columns(layout_columns, tile_count))
    block_width = 5
    block_height = 5
    blocks_per_row = max(1, min(max(1, int(terrain_count) - 1), columns // block_width))
    old_tiles = list(out_tiles)
    old_names = list(out_names)
    old_meta = [dict(item) for item in order_meta]

    used_old: set[int] = set()
    positioned: Dict[int, Dict[str, Any]] = {}
    reserved_max_pos = -1
    block_index = 0

    for terrain_index in range(max(0, int(terrain_count))):
        for partner in range(max(0, int(terrain_count))):
            if partner == terrain_index:
                continue
            block_row = block_index // blocks_per_row
            block_col = block_index % blocks_per_row
            reserved_max_pos = max(reserved_max_pos, ((block_row + 1) * block_height) * columns - 1)
            for row in range(block_height):
                for col in range(block_width):
                    exact_candidates: List[int] = []
                    for idx, item in enumerate(old_meta):
                        set_type = str(item.get("set_type") or "shared").strip().lower()
                        labels = tuple(int(x) for x in (item.get("sort_labels") or []))
                        if labels == _frame_slot_labels(set_type, terrain_index, partner, row, col):
                            exact_candidates.append(idx)
                    if not exact_candidates:
                        continue
                    unused_candidates = [idx for idx in exact_candidates if idx not in used_old]
                    chosen = min(unused_candidates or exact_candidates, key=lambda idx: _slot_candidate_key(old_meta[idx]))
                    is_duplicate = chosen in used_old
                    if not is_duplicate:
                        used_old.add(chosen)
                    target_pos = (block_row * block_height + row) * columns + block_col * block_width + col
                    positioned[target_pos] = {
                        "old_idx": chosen,
                        "duplicate": is_duplicate,
                        "terrain": terrain_index,
                        "partner": partner,
                        "row": row,
                        "col": col,
                    }
            block_index += 1

    junction_block_width = 12
    junction_center_row = 3
    junction_center_col = 3
    junction_center_size = 6
    triple_junction_block_height = 9
    quad_junction_block_height = 12
    pair_section_rows = int(np.ceil(block_index / blocks_per_row)) * block_height if block_index else 0
    junction_blocks_per_row = max(1, columns // junction_block_width)
    junction_block_count = 0
    junction_row_start = pair_section_rows
    junction_col_slot = 0
    junction_row_height = 0

    for unique_count in (3, 4):
        for combo in combinations(range(max(0, int(terrain_count))), unique_count):
            junction_block_height = triple_junction_block_height if unique_count == 3 else quad_junction_block_height
            if junction_col_slot >= junction_blocks_per_row:
                junction_row_start += junction_row_height
                junction_col_slot = 0
                junction_row_height = 0
            block_row = junction_row_start
            block_col = junction_col_slot * junction_block_width
            junction_row_height = max(junction_row_height, junction_block_height)
            reserved_max_pos = max(
                reserved_max_pos,
                (block_row + junction_block_height) * columns - 1,
            )

            for row in range(junction_block_height):
                for col in range(junction_block_width):
                    in_center = (
                        junction_center_row <= row < junction_center_row + junction_center_size
                        and junction_center_col <= col < junction_center_col + junction_center_size
                    )
                    if in_center:
                        continue
                    visual_labels = _semantic_junction_visual_labels(combo, row, col)
                    if visual_labels is None:
                        continue
                    source_idx = _find_tile_by_labels(old_meta, visual_labels)
                    if source_idx is None:
                        continue
                    target_pos = (block_row + row) * columns + block_col + col
                    if target_pos in positioned:
                        continue
                    positioned[target_pos] = {
                        "old_idx": source_idx,
                        "duplicate": True,
                        "visual_name": _visual_junction_name(
                            old_names[source_idx],
                            names,
                            combo,
                            row,
                            col,
                        ),
                        "junction_visual": True,
                        "combo": tuple(combo),
                        "row": row,
                        "col": col,
                    }

            for idx, item in enumerate(old_meta):
                if idx in used_old:
                    continue
                labels = tuple(int(x) for x in (item.get("sort_labels") or []))
                slot = _junction_slot_for_labels(labels, combo)
                if slot is None:
                    continue
                slot_row, slot_col = slot
                target_pos = (
                    (block_row + junction_center_row + slot_row) * columns
                    + block_col + junction_center_col + slot_col
                )
                if target_pos in positioned:
                    continue
                used_old.add(idx)
                positioned[target_pos] = {
                    "old_idx": idx,
                    "duplicate": False,
                    "junction": True,
                    "combo": tuple(combo),
                    "row": junction_center_row + slot_row,
                    "col": junction_center_col + slot_col,
                }
            junction_col_slot += 1
            junction_block_count += 1

    remaining = [idx for idx in range(tile_count) if idx not in used_old]
    remaining.sort(key=lambda idx: _terrain_grid_sort_key(old_meta[idx]))
    remaining_iter = iter(remaining)

    new_tiles: List[Image.Image] = []
    new_names: List[str] = []
    new_meta: List[Dict[str, Any]] = []
    old_to_new: Dict[int, int] = {}
    max_frame_pos = max(max(positioned) if positioned else -1, reserved_max_pos)

    def append_spacer(pos: int) -> None:
        new_tileid = len(new_tiles)
        size = old_tiles[0].size
        new_tiles.append(Image.new("RGBA", size, (0, 0, 0, 0)))
        new_names.append(f"visual_spacer_{new_tileid}")
        new_meta.append({
            "tileid": new_tileid,
            "layout_pos": pos,
            "visual_placeholder": True,
            "spacer": True,
        })

    def append_canonical(old_idx: int, pos: Optional[int] = None) -> None:
        new_tileid = len(new_tiles)
        old_to_new[old_idx] = new_tileid
        new_tiles.append(old_tiles[old_idx])
        new_names.append(old_names[old_idx])
        item = dict(old_meta[old_idx])
        item["old_tileid"] = old_idx
        item["tileid"] = new_tileid
        if pos is not None:
            item["layout_pos"] = pos
        new_meta.append(item)

    def append_visual(entry: Dict[str, Any], pos: int) -> None:
        old_idx = int(entry["old_idx"])
        new_tileid = len(new_tiles)
        new_tiles.append(old_tiles[old_idx].copy())
        visual_name = entry.get("visual_name")
        if visual_name:
            new_names.append(str(visual_name))
        else:
            new_names.append(
                _visual_frame_name(
                    old_names[old_idx],
                    names,
                    int(entry["terrain"]),
                    int(entry["partner"]),
                    int(entry["row"]),
                    int(entry["col"]),
                )
            )
        item = dict(old_meta[old_idx])
        item["old_tileid"] = old_idx
        item["source_tileid"] = old_idx
        item["tileid"] = new_tileid
        item["layout_pos"] = pos
        item["visual_placeholder"] = True
        new_meta.append(item)

    for pos in range(max_frame_pos + 1):
        entry = positioned.get(pos)
        if entry is None:
            append_spacer(pos)
        elif bool(entry.get("duplicate")):
            append_visual(entry, pos)
        else:
            append_canonical(int(entry["old_idx"]), pos)

    for old_idx in remaining_iter:
        append_canonical(old_idx)

    missing = [idx for idx in range(tile_count) if idx not in old_to_new]
    if missing:
        raise RuntimeError(
            f"[multi_terrain_wang_set] terrain_pair_frame 未能映射 {len(missing)} 个原始 tile"
        )

    out_tiles[:] = new_tiles
    out_names[:] = new_names
    _remap_wang_multisets(wang_multisets, old_to_new)

    return {
        "mode": "terrain_pair_frame",
        "changed": True,
        "old_to_new": old_to_new,
        "tiles": new_meta,
        "visual_placeholders": len(new_tiles) - tile_count,
        "layout_columns": columns,
        "frame_block": [block_width, block_height],
        "frame_center": [3, 3],
        "junction_block": [junction_block_width, quad_junction_block_height],
        "junction_triple_block": [junction_block_width, triple_junction_block_height],
        "junction_quad_block": [junction_block_width, quad_junction_block_height],
        "junction_center": [junction_center_size, junction_center_size],
        "junction_blocks": junction_block_count,
    }


def _apply_layout_order(
    out_tiles: List[Image.Image],
    out_names: List[str],
    order_meta: List[Dict[str, Any]],
    wang_multisets: List[Dict[str, Any]],
    layout_order: str,
    terrain_count: int,
    layout_columns: Any = 0,
    terrain_names: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    mode = (layout_order or "terrain_scene_source").strip().lower()
    if mode in ("", "none", "generation", "original"):
        return {"mode": mode or "generation", "changed": False}
    if len(order_meta) != len(out_tiles):
        raise RuntimeError("[multi_terrain_wang_set] tile 排序元数据数量与 tile 数量不一致")

    if mode in ("terrain_scene_source", "scene_source", "source_scene", "junction_scene", "authoring_scene"):
        return _apply_terrain_scene_source_layout(
            out_tiles,
            out_names,
            order_meta,
            wang_multisets,
            terrain_count,
            layout_columns=layout_columns,
            terrain_names=terrain_names,
        )
    if mode in ("terrain_pair_frame", "pair_frame", "terrain_frame", "frame"):
        return _apply_terrain_pair_frame_layout(
            out_tiles,
            out_names,
            order_meta,
            wang_multisets,
            terrain_count,
            layout_columns=layout_columns,
            terrain_names=terrain_names,
        )
    if mode in ("terrain_grid", "grid", "nine_grid", "ninegrid", "directional"):
        order = _terrain_grid_order(order_meta, terrain_count, layout_columns)
        applied_mode = "terrain_grid"
    elif mode in ("directional_flat", "directional_groups", "directional_grouped"):
        order = sorted(range(len(out_tiles)), key=lambda index: _directional_sort_key(order_meta[index]))
        applied_mode = "directional_flat"
    else:
        raise ValueError(
            "[multi_terrain_wang_set] layout_order 应为 terrain_scene_source / terrain_pair_frame / terrain_grid / directional_flat / generation / none"
        )

    identity = list(range(len(out_tiles)))
    changed = order != identity
    if not changed:
        return {"mode": applied_mode, "changed": False}

    old_to_new = {old: new for new, old in enumerate(order)}
    out_tiles[:] = [out_tiles[old] for old in order]
    out_names[:] = [out_names[old] for old in order]

    _remap_wang_multisets(wang_multisets, old_to_new)

    ordered_meta = []
    for new_tileid, old_tileid in enumerate(order):
        item = dict(order_meta[old_tileid])
        item["old_tileid"] = old_tileid
        item["tileid"] = new_tileid
        ordered_meta.append(item)

    return {
        "mode": applied_mode,
        "changed": True,
        "old_to_new": old_to_new,
        "tiles": ordered_meta,
    }


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
        "layout_order": {"enum": ["terrain_scene_source", "terrain_pair_frame", "terrain_grid", "directional", "directional_flat", "generation", "none"]},
        "layout_columns": {"min": 0, "step": 1},
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
        layout_order: str = "terrain_scene_source",
        layout_columns: Any = 0,
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
        order_meta: List[Dict[str, Any]] = []
        wang_multisets: List[Dict[str, Any]] = []
        offset = 0
        combos = list(product(range(terrain_count), repeat=4))
        solid_tile_stride = terrain_count ** 3 + terrain_count ** 2 + terrain_count + 1

        def terrain_defs(base_offset: int) -> List[Dict[str, Any]]:
            return [
                {"name": names[i], "color": colors[i], "tile": base_offset + i * solid_tile_stride}
                for i in range(terrain_count)
            ]

        def add_output_tile(tile: Image.Image, tile_name: str, set_type: str, labels: Sequence[int]) -> int:
            tileid = len(out_tiles)
            out_tiles.append(tile)
            out_names.append(tile_name)
            order_meta.append({
                "tileid": tileid,
                "set_type": set_type,
                "sort_labels": [int(x) for x in labels],
            })
            return tileid

        if mode == "all":
            edge_entries: List[Dict[str, Any]] = []
            corner_entries: List[Dict[str, Any]] = []
            mixed_entries: List[Dict[str, Any]] = []
            for idx, labels_tuple in enumerate(combos):
                labels = list(labels_tuple)
                weights = _corner_weights(labels, width, height, terrain_count)
                tileid = add_output_tile(
                    _blend_tiles(base_np, weights),
                    "shared_" + "_".join(names[i] for i in labels),
                    "shared",
                    labels,
                )
                edge_entries.append({"tileid": tileid, "wang": _edge_labels_from_corners(labels)})
                corner_entries.append({"tileid": tileid, "wang": labels})
                mixed_entries.append({
                    "tileid": tileid,
                    "wang": _mixed_labels_from_corners(labels),
                })
            wang_multisets.extend([
                {
                    "name": edge_wangset_name,
                    "type": "edge",
                    "icon_tileid": 0,
                    "terrains": terrain_defs(0),
                    "tiles": edge_entries,
                },
                {
                    "name": corner_wangset_name,
                    "type": "corner",
                    "icon_tileid": 0,
                    "terrains": terrain_defs(0),
                    "tiles": corner_entries,
                },
                {
                    "name": mixed_wangset_name,
                    "type": "mixed",
                    "icon_tileid": 0,
                    "terrains": terrain_defs(0),
                    "tiles": mixed_entries,
                },
            ])
            offset = len(combos)
        else:
            if include_edge:
                edge_entries: List[Dict[str, Any]] = []
                for idx, labels in enumerate(combos):
                    weights = _edge_weights(labels, width, height, float(half_extent), terrain_count)
                    tileid = add_output_tile(
                        _blend_tiles(base_np, weights),
                        "edge_" + "_".join(names[i] for i in labels),
                        "edge",
                        labels,
                    )
                    edge_entries.append({"tileid": tileid, "wang": list(labels)})
                wang_multisets.append({
                    "name": edge_wangset_name,
                    "type": "edge",
                    "icon_tileid": offset,
                    "terrains": terrain_defs(offset),
                    "tiles": edge_entries,
                })
                offset += len(combos)

            if include_corner:
                corner_entries: List[Dict[str, Any]] = []
                for idx, labels in enumerate(combos):
                    weights = _corner_weights(labels, width, height, terrain_count)
                    tileid = add_output_tile(
                        _blend_tiles(base_np, weights),
                        "corner_" + "_".join(names[i] for i in labels),
                        "corner",
                        labels,
                    )
                    corner_entries.append({"tileid": tileid, "wang": list(labels)})
                wang_multisets.append({
                    "name": corner_wangset_name,
                    "type": "corner",
                    "icon_tileid": offset,
                    "terrains": terrain_defs(offset),
                    "tiles": corner_entries,
                })
                offset += len(combos)

            if include_mixed:
                mixed_entries: List[Dict[str, Any]] = []
                for idx, labels in enumerate(combos):
                    weights = _corner_weights(labels, width, height, terrain_count)
                    tileid = add_output_tile(
                        _blend_tiles(base_np, weights),
                        "mixed_" + "_".join(names[i] for i in labels),
                        "mixed",
                        labels,
                    )
                    mixed_entries.append({
                        "tileid": tileid,
                        "wang": _mixed_labels_from_corners(labels),
                    })
                wang_multisets.append({
                    "name": mixed_wangset_name,
                    "type": "mixed",
                    "icon_tileid": offset,
                    "terrains": terrain_defs(offset),
                    "tiles": mixed_entries,
                })
                offset += len(combos)

        order_info = _apply_layout_order(
            out_tiles,
            out_names,
            order_meta,
            wang_multisets,
            layout_order,
            terrain_count,
            layout_columns=layout_columns,
            terrain_names=names,
        )
        if order_info.get("changed"):
            print(
                f"[multi_terrain_wang_set] layout_order={order_info.get('mode')} "
                f"reordered {len(out_tiles)} tiles"
            )

        ctx.image = out_tiles[-1]
        ctx.extras["tiles"] = out_tiles
        ctx.extras["tile_names"] = out_names
        ctx.extras["wang_multisets"] = wang_multisets
        ctx.extras["tile_order"] = order_info.get("tiles") or []
        ctx.extras["multi_terrain_wang"] = {
            "mode": mode,
            "terrain_count": terrain_count,
            "combo_count": terrain_count ** 4,
            "tile_count": len(out_tiles),
            "terrain_names": names,
            "terrain_colors": colors,
            "tile_size": [width, height],
            "layout_order": order_info.get("mode"),
            "layout_reordered": bool(order_info.get("changed")),
            "layout_columns": int(order_info.get("layout_columns") or _parse_layout_columns(layout_columns, len(out_tiles))),
            "layout_visual_placeholders": int(order_info.get("visual_placeholders") or 0),
            "layout_junction_blocks": int(order_info.get("junction_blocks") or 0),
        }
        print(
            f"[multi_terrain_wang_set] terrains={terrain_count} mode={mode} "
            f"combos={terrain_count ** 4} out_tiles={len(out_tiles)} tile={width}x{height}"
        )
        return ctx
