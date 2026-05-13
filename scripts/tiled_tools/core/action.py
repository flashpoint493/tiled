# -*- coding: utf-8 -*-
"""Action 基类与 Context 数据结构。

Context 在 pipeline 各步之间流动，承载：
- image    : 当前主图（PIL.Image，模式统一为 RGBA）。
             有些 action（比如 split_*）会暂时把 image 置 None，
             转为往 extras 里塞多张产物。
- extras   : 额外产物字典，key 由 action 自行约定。例如 split_connected
             会写入 extras["tiles"] = [Path, ...]。
- meta     : 任意元数据（尺寸、角度、来源路径……）。供后续 action 读取。
- workdir  : 默认输出根目录；save 类 action 不显式给路径时用它。

每个 Action 子类必须：
1. 类属性 name：在 YAML/CLI 里使用的名字。
2. 实现 run(ctx, **params) -> Context。

可选：
- 类属性 description：用于前端展示。
- 类属性 param_hints：覆盖某个参数的 schema（enum / min / max / widget）。
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, get_args, get_origin

from PIL import Image


@dataclass
class Context:
    image: Optional[Image.Image] = None
    extras: Dict[str, Any] = field(default_factory=dict)
    meta: Dict[str, Any] = field(default_factory=dict)
    workdir: Path = field(default_factory=lambda: Path.cwd())

    def with_image(self, img: Optional[Image.Image]) -> "Context":
        """返回替换了 image 的新 Context（meta/extras/workdir 共享引用，
        因为它们通常是希望累积的状态）。"""
        return Context(image=img, extras=self.extras, meta=self.meta,
                       workdir=self.workdir)


class Action:
    """所有 Action 的基类。子类至少要覆盖 name 与 run。"""

    name: str = ""
    description: str = ""

    # 子类可在这里给某些参数加额外约束，例如：
    #   param_hints = {"resample": {"enum": ["nearest", "bilinear", ...]}}
    # 这些 hint 会合并到自动反射出来的 schema 里，前端用它生成下拉/滑块。
    param_hints: Dict[str, Dict[str, Any]] = {}

    def run(self, ctx: Context, **params: Any) -> Context:
        raise NotImplementedError

    # ---- 给子类用的小工具 ----

    @staticmethod
    def require_image(ctx: Context, action_name: str) -> Image.Image:
        if ctx.image is None:
            raise RuntimeError(
                f"[{action_name}] 需要一张图像作为输入，但 ctx.image 为空。"
                "请先在 pipeline 里加一个 load 步骤，或者上一步没有产出图。"
            )
        return ctx.image

    @staticmethod
    def normalize_color(value: Any, channels: int = 4) -> tuple:
        """把各种来源（tuple/list/#RRGGBB/#RRGGBBAA/"r,g,b,a"）统一成 tuple。

        PIL 的 Image.new/rotate 等只接受 int 或 tuple，不吃 list；前端通过
        JSON 传过来的默认是 list，必须转一下。
        """
        if value is None:
            return (0,) * channels
        if isinstance(value, tuple):
            return value
        if isinstance(value, list):
            return tuple(int(v) for v in value)
        if isinstance(value, str):
            s = value.strip()
            # #RRGGBB / #RRGGBBAA
            if s.startswith("#"):
                hx = s[1:]
                if len(hx) in (6, 8):
                    parts = [int(hx[i:i + 2], 16) for i in range(0, len(hx), 2)]
                    while len(parts) < channels:
                        parts.append(255)
                    return tuple(parts[:channels])
            # "r,g,b,a"
            if "," in s:
                parts = [int(x.strip()) for x in s.split(",") if x.strip() != ""]
                return tuple(parts)
        if isinstance(value, int):
            return (value,) * channels
        raise TypeError(f"无法识别的颜色值: {value!r}")

    # ---- 反射 schema：给前端用 ----

    @classmethod
    def param_schema(cls) -> List[Dict[str, Any]]:
        """通过 inspect.signature(cls.run) 反射出参数列表。

        每个参数返回：
          { name, type, default, required, enum?, hint? }

        type 取值（前端按这个画控件）：
          - "string" / "number" / "integer" / "boolean"
          - "tuple"   （比如 background 是 (R,G,B,A)）
          - "any"
        """
        sig = inspect.signature(cls.run)
        out: List[Dict[str, Any]] = []
        for pname, param in sig.parameters.items():
            if pname in ("self", "ctx", "params"):
                continue
            if param.kind in (inspect.Parameter.VAR_POSITIONAL,
                              inspect.Parameter.VAR_KEYWORD):
                continue

            entry: Dict[str, Any] = {
                "name": pname,
                "type": _type_name(param.annotation),
                "required": param.default is inspect.Parameter.empty,
            }
            if param.default is not inspect.Parameter.empty:
                entry["default"] = _jsonable(param.default)

            hint = cls.param_hints.get(pname)
            if hint:
                entry.update(hint)

            out.append(entry)
        return out

    @classmethod
    def describe(cls) -> Dict[str, Any]:
        return {
            "name": cls.name,
            "description": cls.description or (cls.__doc__ or "").strip().split("\n")[0],
            "params": cls.param_schema(),
        }


# ---- 工具函数 ----

def _type_name(annotation: Any) -> str:
    if annotation is inspect.Parameter.empty:
        return "any"
    # 处理 Optional[X] / Union[X, None]
    origin = get_origin(annotation)
    if origin is not None:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return _type_name(args[0])
        # tuple[int, int, int, int] 之类
        if origin in (tuple,):
            return "tuple"
        return "any"

    if annotation is bool:
        return "boolean"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    if annotation is str:
        return "string"
    return "any"


def _jsonable(value: Any) -> Any:
    """把 default 转成 JSON 能序列化的形式。"""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (tuple, list)):
        return [_jsonable(v) for v in value]
    return str(value)
