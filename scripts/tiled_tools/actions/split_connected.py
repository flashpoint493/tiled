# -*- coding: utf-8 -*-
"""split_connected：从透明背景 tilesheet 中自动裁出独立贴图。"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Tuple

from PIL import Image

from ..core.action import Action, Context
from ..core.registry import register


Box = Tuple[int, int, int, int]


def _expand_box(box: Box, padding: int, width: int, height: int) -> Box:
    left, top, right, bottom = box
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(width, right + padding),
        min(height, bottom + padding),
    )


def _component_boxes(
    alpha: Image.Image,
    min_alpha: int,
    connectivity: int,
) -> List[Box]:
    width, height = alpha.size
    data = alpha.load()
    visited = bytearray(width * height)

    if connectivity == 4:
        neighbors = ((1, 0), (-1, 0), (0, 1), (0, -1))
    elif connectivity == 8:
        neighbors = (
            (1, 0), (-1, 0), (0, 1), (0, -1),
            (1, 1), (1, -1), (-1, 1), (-1, -1),
        )
    else:
        raise ValueError("[split_connected] connectivity 只能是 4 或 8")

    boxes: List[Box] = []
    for y in range(height):
        row = y * width
        for x in range(width):
            idx = row + x
            if visited[idx] or data[x, y] < min_alpha:
                continue

            visited[idx] = 1
            queue = deque([(x, y)])
            left = right = x
            top = bottom = y

            while queue:
                cx, cy = queue.popleft()
                if cx < left:
                    left = cx
                elif cx > right:
                    right = cx
                if cy < top:
                    top = cy
                elif cy > bottom:
                    bottom = cy

                for dx, dy in neighbors:
                    nx = cx + dx
                    ny = cy + dy
                    if nx < 0 or ny < 0 or nx >= width or ny >= height:
                        continue
                    nidx = ny * width + nx
                    if visited[nidx] or data[nx, ny] < min_alpha:
                        continue
                    visited[nidx] = 1
                    queue.append((nx, ny))

            boxes.append((left, top, right + 1, bottom + 1))

    return boxes


def _sort_boxes(boxes: List[Box], mode: str) -> List[Box]:
    if mode == "row-major":
        return sorted(boxes, key=lambda b: (b[1], b[0], b[3], b[2]))
    if mode == "column-major":
        return sorted(boxes, key=lambda b: (b[0], b[1], b[2], b[3]))
    if mode == "area-desc":
        return sorted(boxes, key=lambda b: (-(b[2] - b[0]) * (b[3] - b[1]), b[1], b[0]))
    raise ValueError(f"[split_connected] 未知 sort: {mode}")


@register("split_connected")
class SplitConnectedAction(Action):
    description = "从透明背景 tilesheet 自动识别连通贴图并裁成多张独立 PNG"
    param_hints = {
        "min_alpha": {"min": 0, "max": 255, "step": 1},
        "min_width": {"min": 1, "step": 1},
        "min_height": {"min": 1, "step": 1},
        "padding": {"min": 0, "step": 1},
        "connectivity": {"enum": [4, 8]},
        "sort": {"enum": ["row-major", "column-major", "area-desc"]},
    }

    def run(
        self,
        ctx: Context,
        min_alpha: int = 1,
        min_width: int = 1,
        min_height: int = 1,
        padding: int = 0,
        connectivity: int = 8,
        sort: str = "row-major",
    ) -> Context:
        img = self.require_image(ctx, "split_connected")
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        min_alpha = max(0, min(255, int(min_alpha)))
        min_width = max(1, int(min_width))
        min_height = max(1, int(min_height))
        padding = max(0, int(padding))
        connectivity = int(connectivity)
        width, height = img.size

        boxes = _component_boxes(img.getchannel("A"), min_alpha, connectivity)
        boxes = [
            box for box in boxes
            if (box[2] - box[0]) >= min_width and (box[3] - box[1]) >= min_height
        ]
        boxes = _sort_boxes(boxes, sort)

        tiles: List[Image.Image] = []
        tile_boxes: List[Dict[str, int]] = []
        tile_names: List[str] = []
        for i, box in enumerate(boxes, start=1):
            crop_box = _expand_box(box, padding, width, height)
            tiles.append(img.crop(crop_box))
            tile_names.append(f"{i:03d}")
            tile_boxes.append({
                "x": crop_box[0],
                "y": crop_box[1],
                "width": crop_box[2] - crop_box[0],
                "height": crop_box[3] - crop_box[1],
            })

        if not tiles:
            raise RuntimeError(
                "[split_connected] 没有找到符合条件的非透明贴图。"
                "请检查图片是否有 alpha 通道，或降低 min_alpha / min_width / min_height。"
            )

        ctx.extras["tiles"] = tiles
        ctx.extras["tile_names"] = tile_names
        ctx.extras["split_connected_boxes"] = tile_boxes
        ctx.meta["split_connected_count"] = len(tiles)
        ctx.meta["split_connected_min_alpha"] = min_alpha
        ctx.meta["split_connected_connectivity"] = connectivity

        print(
            f"[split_connected] 源 {width}x{height} -> {len(tiles)} 张，"
            f" min_alpha={min_alpha} connectivity={connectivity} padding={padding}"
        )
        for name, box in zip(tile_names, tile_boxes):
            print(
                f"  [{name}] x={box['x']} y={box['y']} "
                f"size={box['width']}x{box['height']}"
            )

        return ctx.with_image(tiles[0])
