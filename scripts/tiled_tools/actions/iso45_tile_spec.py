# -*- coding: utf-8 -*-
"""iso45_tile_spec / iso45_fit_tile：用一个预设控制 iso45 最终产物规格。"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ..core.action import Action, Context
from ..core.registry import register
from .canvas_square import SquareCanvasAction, _ANCHORS
from .scale import ScaleAction
from .topdown_to_iso import TopdownToIsoAction


_SPEC_KEY = "iso45_tile_spec"
_PRESET_SIZES = {
    "96": 96,
    "128": 128,
    "256": 256,
    "512": 512,
}
_PRESET_ENUM = ["context", "96", "128", "256", "512", "custom"]


def _as_int(value: Any, minimum: int = 1) -> Optional[int]:
    if value is None or value == "":
        return None
    return max(minimum, int(float(value)))



def _make_square_spec(side: int, preset: str) -> Dict[str, int | str]:
    grid_h = max(1, int(round(side / 2)))
    return {
        "preset": preset,
        "cell_width": side,
        "cell_height": side,
        "footprint_width": side,
        "footprint_height": grid_h,
        "grid_width": side,
        "grid_height": grid_h,
        "tileoffset_x": 0,
        "tileoffset_y": max(0, int(round((side - grid_h) / 2))),
    }


def resolve_iso45_tile_spec(
    ctx: Optional[Context] = None,
    preset: Any = "context",
    cell_size: Optional[int] = None,
    cell_width: Optional[int] = None,
    cell_height: Optional[int] = None,
    footprint_width: Optional[int] = None,
    footprint_height: Optional[int] = None,
    grid_width: Optional[int] = None,
    grid_height: Optional[int] = None,
    tileoffset_x: Optional[int] = None,
    tileoffset_y: Optional[int] = None,
) -> Dict[str, int | str]:
    """解析 iso45 单格规格。

    预设约定：cell 为 N×N，iso footprint / Tiled grid 为 N×N/2，
    tileoffset.y 为 (cell_h - grid_h) / 2。
    """
    p = str(preset or "context").strip().lower()
    context_spec = None
    if ctx is not None:
        context_spec = ctx.meta.get(_SPEC_KEY)

    if p == "context" and context_spec:
        spec: Dict[str, int | str] = dict(context_spec)
    else:
        if p == "context":
            p = "256"
        side = _as_int(cell_size)
        if p in _PRESET_SIZES:
            side = _PRESET_SIZES[p]
        elif p != "custom":
            # 兼容前端/CLI 把 enum 数字转成 int 后再传进来。
            try:
                side = int(float(p))
                p = str(side)
            except ValueError as exc:
                raise ValueError(f"[iso45_tile_spec] 未知 preset: {preset!r}") from exc
        if side is None:
            side = _as_int(cell_width) or _as_int(grid_width) or 256
        spec = _make_square_spec(side, p)

    # 显式参数可覆盖 preset，主要用于 custom。
    side_override = _as_int(cell_size)
    if side_override is not None:
        spec.update(_make_square_spec(side_override, str(spec.get("preset") or "custom")))

    overrides = {
        "cell_width": cell_width,
        "cell_height": cell_height,
        "footprint_width": footprint_width,
        "footprint_height": footprint_height,
        "grid_width": grid_width,
        "grid_height": grid_height,
        "tileoffset_x": tileoffset_x,
        "tileoffset_y": tileoffset_y,
    }
    for key, value in overrides.items():
        parsed = _as_int(value, minimum=0 if key.startswith("tileoffset_") else 1)
        if parsed is not None:
            spec[key] = parsed


    # grid 默认跟 footprint 一致；tileoffset 默认根据 cell/grid 自动推导。
    spec["grid_width"] = int(spec.get("grid_width") or spec["footprint_width"])
    spec["grid_height"] = int(spec.get("grid_height") or spec["footprint_height"])
    if tileoffset_y is None:
        spec["tileoffset_y"] = max(0, int(round((int(spec["cell_height"]) - int(spec["grid_height"])) / 2)))
    if tileoffset_x is None:
        spec["tileoffset_x"] = int(spec.get("tileoffset_x") or 0)
    return spec


@register("iso45_tile_spec")
class Iso45TileSpecAction(Action):
    description = "选择 iso45 最终单格规格（Web 下拉：96 / 128 / 256 / 512 / custom）"
    param_hints = {
        "preset": {"enum": _PRESET_ENUM[1:]},
        "cell_size": {"min": 1, "step": 1},
        "cell_width": {"min": 1, "step": 1},
        "cell_height": {"min": 1, "step": 1},
        "footprint_width": {"min": 1, "step": 1},
        "footprint_height": {"min": 1, "step": 1},
        "grid_width": {"min": 1, "step": 1},
        "grid_height": {"min": 1, "step": 1},
        "tileoffset_x": {"step": 1},
        "tileoffset_y": {"step": 1},
    }

    def run(
        self,
        ctx: Context,
        preset: str = "256",
        cell_size: Optional[int] = None,
        cell_width: Optional[int] = None,
        cell_height: Optional[int] = None,
        footprint_width: Optional[int] = None,
        footprint_height: Optional[int] = None,
        grid_width: Optional[int] = None,
        grid_height: Optional[int] = None,
        tileoffset_x: Optional[int] = None,
        tileoffset_y: Optional[int] = None,
    ) -> Context:
        spec = resolve_iso45_tile_spec(
            ctx,
            preset=preset,
            cell_size=cell_size,
            cell_width=cell_width,
            cell_height=cell_height,
            footprint_width=footprint_width,
            footprint_height=footprint_height,
            grid_width=grid_width,
            grid_height=grid_height,
            tileoffset_x=tileoffset_x,
            tileoffset_y=tileoffset_y,
        )
        ctx.meta[_SPEC_KEY] = spec
        print(
            "[iso45_tile_spec] "
            f"cell={spec['cell_width']}x{spec['cell_height']}  "
            f"footprint={spec['footprint_width']}x{spec['footprint_height']}  "
            f"grid={spec['grid_width']}x{spec['grid_height']}  "
            f"offset={spec['tileoffset_x']},{spec['tileoffset_y']}"
        )
        return ctx


@register("iso45_fit_tile")
class Iso45FitTileAction(Action):
    description = "Topdown tile → iso45 菱形 → 按 iso45_tile_spec 放入最终 cell"
    param_hints = {
        "preset": {"enum": _PRESET_ENUM},
        "anchor": {"enum": sorted(_ANCHORS)},
        "resample": {"enum": ["nearest", "bilinear", "bicubic", "lanczos"]},
        "background": {"widget": "rgba"},
        "cell_size": {"min": 1, "step": 1},
        "cell_width": {"min": 1, "step": 1},
        "cell_height": {"min": 1, "step": 1},
        "footprint_width": {"min": 1, "step": 1},
        "footprint_height": {"min": 1, "step": 1},
    }

    def run(
        self,
        ctx: Context,
        preset: str = "context",
        anchor: str = "center",
        resample: str = "bicubic",
        cell_size: Optional[int] = None,
        cell_width: Optional[int] = None,
        cell_height: Optional[int] = None,
        footprint_width: Optional[int] = None,
        footprint_height: Optional[int] = None,
        background: Tuple[int, int, int, int] = (0, 0, 0, 0),
    ) -> Context:
        spec = resolve_iso45_tile_spec(
            ctx,
            preset=preset,
            cell_size=cell_size,
            cell_width=cell_width,
            cell_height=cell_height,
            footprint_width=footprint_width,
            footprint_height=footprint_height,
        )
        ctx.meta[_SPEC_KEY] = spec
        ctx = TopdownToIsoAction().run(
            ctx,
            anchor="center",
            angle=45,
            y_scale=0.5,
            expand=True,
            resample=resample,
            trim=False,
            background=background,
        )
        ctx = ScaleAction().run(
            ctx,
            size=(int(spec["footprint_width"]), int(spec["footprint_height"])),
            resample=resample,
        )
        ctx = SquareCanvasAction().run(
            ctx,
            size=[int(spec["cell_width"]), int(spec["cell_height"])],
            anchor=anchor,
            background=background,
        )
        return ctx
