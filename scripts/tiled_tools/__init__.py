# -*- coding: utf-8 -*-
"""tiled_tools：图像处理 / 资源整理工作流工具集。

设计目标：
- 把每一类操作抽象为一个独立的 Action（输入 Context，输出 Context）；
- 所有 Action 可在 Pipeline（YAML）里自由组合；
- 既能以 CLI 单步使用，也能作为库在 Python 里编排。
"""

from .core.action import Action, Context
from .core.pipeline import Pipeline
from .core.registry import register, get_action, available_actions

# 触发 actions 子包的注册副作用
from . import actions  # noqa: F401

__all__ = [
    "Action",
    "Context",
    "Pipeline",
    "register",
    "get_action",
    "available_actions",
]
