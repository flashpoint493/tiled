"""wang_2edge_compose_map: 把 16 张 wang 2-edge tile 拼成一张边匹配的预览地图。

注意：`pack_sheet(columns=4)` 生成的是 tileset lookup sheet，顺序是 code 0..15，
相邻格子并不保证 N/E/S/W 边相等，所以视觉上会出现方向错乱。

本 action 的目标不同：它把 16 张 tile 当作“素材库”，按一个有效的 code 矩阵
取用，保证相邻 tile 的共享边匹配，适合后续整体 topdown_to_iso 做大图预览。
"""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

from PIL import Image

from ..core.action import Action, Context
from ..core.registry import register


# code 约定：bit0=N, bit1=E, bit2=S, bit3=W，1=foreground，0=background。
# island3 的四个角分别是 6/12/3/9，都是“拐角过渡 tile”，不再用 0 填死角。
_PRESETS = {
    "island3": [
        [6, 14, 12],
        [7, 15, 13],
        [3, 11, 9],
    ],
    # island3 的反相：适合 foreground=水、background=沙 时做一块水塘。
    "lake3": [
        [9, 1, 3],
        [8, 0, 2],
        [12, 4, 6],
    ],
    # island4 保留给需要更大中心区域的预览；四个外角是纯 background。
    "island4": [
        [0, 4, 4, 0],
        [6, 15, 15, 12],
        [3, 15, 15, 9],
        [0, 1, 1, 0],
    ],
    # island4 的反相。
    "lake4": [
        [15, 11, 11, 15],
        [9, 0, 0, 3],
        [12, 0, 0, 6],
        [15, 14, 14, 15],
    ],
    # 原始 lookup 顺序，仅用于对照；它不是边匹配地图。
    "lookup4": [
        [0, 1, 2, 3],
        [4, 5, 6, 7],
        [8, 9, 10, 11],
        [12, 13, 14, 15],
    ],
}



def _parse_code_matrix(value: Any) -> Optional[List[List[int]]]:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        rows = []
        for row in value.replace(";", "/").split("/"):
            row = row.strip()
            if not row:
                continue
            rows.append([int(x.strip()) for x in row.replace(",", " ").split()])
        return rows or None
    if isinstance(value, list):
        if not value:
            return None
        if all(isinstance(x, int) for x in value):
            # 一维列表优先按正方形切，方便 JSON 写法：[6,14,12,7,15,13,3,11,9]
            side = int(len(value) ** 0.5)
            if side * side == len(value):
                return [list(map(int, value[i:i + side])) for i in range(0, len(value), side)]
            if len(value) % 4 != 0:
                raise ValueError("code_matrix 一维列表长度必须是平方数或 4 的倍数")
            return [list(map(int, value[i:i + 4])) for i in range(0, len(value), 4)]

        return [[int(x) for x in row] for row in value]
    raise TypeError(f"无法识别 code_matrix: {value!r}")


def _validate_edges(codes: List[List[int]], wrap: bool) -> None:
    rows = len(codes)
    cols = len(codes[0]) if rows else 0
    if rows == 0 or cols == 0:
        raise ValueError("code_matrix 不能为空")
    if any(len(r) != cols for r in codes):
        raise ValueError("code_matrix 每行列数必须一致")
    for y, row in enumerate(codes):
        for x, code in enumerate(row):
            if code < 0 or code > 15:
                raise ValueError(f"code_matrix[{y}][{x}]={code}，应在 0..15")

    check_cols = cols if wrap else cols - 1
    for y in range(rows):
        for x in range(check_cols):
            a = codes[y][x]
            b = codes[y][(x + 1) % cols]
            if ((a >> 1) & 1) != ((b >> 3) & 1):
                raise ValueError(
                    f"水平边不匹配: ({y},{x}) E != ({y},{(x + 1) % cols}) W"
                )

    check_rows = rows if wrap else rows - 1
    for y in range(check_rows):
        for x in range(cols):
            a = codes[y][x]
            b = codes[(y + 1) % rows][x]
            if ((a >> 2) & 1) != (b & 1):
                raise ValueError(
                    f"垂直边不匹配: ({y},{x}) S != ({(y + 1) % rows},{x}) N"
                )


@register("wang_2edge_compose_map")
class Wang2EdgeComposeMapAction(Action):
    description = "按边匹配 code 矩阵把 16 张 wang 2-edge tile 拼成一张完整预览地图"
    param_hints = {
        "pattern": {"enum": sorted(_PRESETS)},
        "background": {"widget": "rgba"},
    }

    def run(
        self,
        ctx: Context,
        pattern: str = "lake3",


        code_matrix: Optional[Any] = None,
        wrap: bool = True,
        background: Tuple[int, int, int, int] = (0, 0, 0, 0),
    ) -> Context:
        tiles = ctx.extras.get("tiles")
        if not tiles or len(tiles) < 16:
            raise RuntimeError(
                "[wang_2edge_compose_map] 需要 ctx.extras['tiles'] 至少包含 16 张 tile。"
                "请先运行 gen_default_masks/load_dir + mask_blend_set。"
            )

        codes = _parse_code_matrix(code_matrix)
        if codes is None:
            key = (pattern or "lake3").lower()


            if key not in _PRESETS:
                raise ValueError(
                    f"[wang_2edge_compose_map] 未知 pattern: {pattern!r}，"
                    f"可选 {sorted(_PRESETS)}"
                )
            codes = [row[:] for row in _PRESETS[key]]
        _validate_edges(codes, wrap=wrap)

        # 统一 tile 尺寸。这里不缩放，只把小图 pad 到最大尺寸，避免像素损失。
        rgba_tiles: List[Image.Image] = []
        tile_w = max(t.size[0] for t in tiles[:16])
        tile_h = max(t.size[1] for t in tiles[:16])
        bg = self.normalize_color(background, channels=4)
        for t in tiles[:16]:
            im = t if t.mode == "RGBA" else t.convert("RGBA")
            if im.size == (tile_w, tile_h):
                rgba_tiles.append(im)
            else:
                canvas = Image.new("RGBA", (tile_w, tile_h), bg)
                canvas.alpha_composite(im, dest=(0, 0))
                rgba_tiles.append(canvas)

        rows = len(codes)
        cols = len(codes[0])
        out = Image.new("RGBA", (cols * tile_w, rows * tile_h), bg)
        for y, row in enumerate(codes):
            for x, code in enumerate(row):
                out.alpha_composite(rgba_tiles[code], dest=(x * tile_w, y * tile_h))

        ctx.extras["wang_2edge_map"] = {
            "pattern": pattern,
            "codes": codes,
            "tile_w": tile_w,
            "tile_h": tile_h,
            "cols": cols,
            "rows": rows,
            "wrap": wrap,
        }
        print(
            f"[wang_2edge_compose_map] pattern={pattern} "
            f"grid={cols}x{rows} tile={tile_w}x{tile_h} wrap={wrap}"
        )
        return ctx.with_image(out)
