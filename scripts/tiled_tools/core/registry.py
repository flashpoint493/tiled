# -*- coding: utf-8 -*-
"""Action 注册表。

用法：
    @register("rotate")
    class RotateAction(Action):
        ...

之后在 Pipeline / CLI 里通过名字 "rotate" 找到该类。
"""

from __future__ import annotations

from typing import Dict, List, Type

from .action import Action


_REGISTRY: Dict[str, Type[Action]] = {}


def register(name: str):
    """装饰器：把一个 Action 子类注册到全局表里。"""
    def _wrap(cls: Type[Action]) -> Type[Action]:
        if not issubclass(cls, Action):
            raise TypeError(f"{cls} 不是 Action 子类")
        cls.name = name
        if name in _REGISTRY:
            raise ValueError(f"Action 名字重复: {name}")
        _REGISTRY[name] = cls
        return cls
    return _wrap


def get_action(name: str) -> Action:
    if name not in _REGISTRY:
        raise KeyError(
            f"未知 action: {name}。可用列表: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[name]()


def available_actions() -> List[str]:
    return sorted(_REGISTRY)
