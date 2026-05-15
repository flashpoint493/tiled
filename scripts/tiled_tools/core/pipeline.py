# -*- coding: utf-8 -*-
"""Pipeline：把一串 Action 顺序执行。

YAML 结构示例：
    name: topdown_to_iso
    description: 把 topdown 贴图转成 iso45 视角
    steps:
      - action: load
        params:
          path: ${input}
      - action: square_canvas
      - action: rotate
        params: { angle: 45, expand: true }
      - action: scale
        params: { sy: 0.5 }
      - action: save
        params:
          path: ${output}

变量替换：
  ${var} 会从 Pipeline.run(variables=...) 传进来的字典里取值。
  这样同一份 YAML 可以复用，外部传 input/output 即可。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .action import Context
from .registry import get_action


# 变量占位符语法（向后兼容旧的 ${var}）：
#   ${var}            必填，未提供时报错
#   ${var:default}    可选，默认值 = default（直到 } 之前的所有字符）
#   ${var:-default}   同上，shell 习惯写法
# default 部分会按字符串原样插入，例如 ${output:auto} 等价于字面量 "auto"。
_VAR_PATTERN = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)(?::-?([^}]*))?\}")


def _coerce_default(s: str) -> Any:
    """把 YAML/CLI 里 ${var:default} 中的 default 字符串智能转为合适类型。

    YAML 里写的 ${target:96} 默认值文本是字符串 "96"，但 action 期望的可能
    是 int/float/bool。这里做一次"尽量能转就转"的解析，行为对照 YAML 标量
    自动类型推断的子集（比 ast.literal_eval 更宽容）：

      "96"     -> 96
      "0.5"    -> 0.5
      "true"   -> True
      ""       -> ""        (保留空字符串语义，比如 ${prefix:})
      "auto"   -> "auto"    (无法解析的字符串原样保留)

    若用户在 CLI 用 `-v target=96` 传入，那已经是字符串，会被送入这里同样
    转换 —— 行为统一。
    """
    if s == "":
        return ""
    low = s.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "none", "~"):
        return None
    # int
    try:
        return int(s)
    except ValueError:
        pass
    # float
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _resolve_var(name: str, default: Optional[str], variables: Dict[str, Any]) -> Any:
    if name in variables:
        v = variables[name]
        # CLI 用 `-v target=96` 传进来时也是字符串，统一转一下；
        # 非字符串（数字 / bool / list / dict 等）原样返回。
        if isinstance(v, str):
            return _coerce_default(v)
        return v
    if default is not None:
        return _coerce_default(default)
    raise KeyError(
        f"pipeline 引用了未提供的变量: {name}。"
        f"在 CLI 用 -v {name}=... 传入，或者在 YAML 里写 ${{{name}:默认值}}。"
    )


def _substitute(value: Any, variables: Dict[str, Any]) -> Any:
    """递归地把字符串里的 ${var} / ${var:default} 替换成实际值。"""
    if isinstance(value, str):
        # 整串就是一个 ${...} → 返回原始类型（便于传非字符串的默认）
        m = _VAR_PATTERN.fullmatch(value.strip())
        if m:
            return _resolve_var(m.group(1), m.group(2), variables)
        # 否则按字符串内插
        def _repl(match: "re.Match[str]") -> str:
            return str(_resolve_var(match.group(1), match.group(2), variables))
        return _VAR_PATTERN.sub(_repl, value)
    if isinstance(value, list):
        return [_substitute(v, variables) for v in value]
    if isinstance(value, dict):
        return {k: _substitute(v, variables) for k, v in value.items()}
    return value


@dataclass
class Step:
    action: str
    params: Dict[str, Any]


@dataclass
class Pipeline:
    name: str
    steps: List[Step]
    description: str = ""

    # ---------- 加载 ----------

    @classmethod
    def from_yaml(cls, path: Path) -> "Pipeline":
        try:
            import yaml  # type: ignore
        except ImportError as e:
            raise SystemExit(
                "需要 pyyaml 才能加载 YAML pipeline，请 `pip install pyyaml`"
            ) from e
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Pipeline":
        steps_raw = data.get("steps") or []
        steps = [
            Step(action=s["action"], params=dict(s.get("params") or {}))
            for s in steps_raw
        ]
        return cls(
            name=data.get("name", "pipeline"),
            description=data.get("description", ""),
            steps=steps,
        )

    # ---------- 执行 ----------

    def run(
        self,
        ctx: Optional[Context] = None,
        variables: Optional[Dict[str, Any]] = None,
        verbose: bool = True,
    ) -> Context:
        if ctx is None:
            ctx = Context()
        variables = dict(variables or {})

        for i, step in enumerate(self.steps, start=1):
            action = get_action(step.action)
            params = _substitute(step.params, variables)
            if verbose:
                print(f"[{i}/{len(self.steps)}] {step.action}  params={params}")
            ctx = action.run(ctx, **params)
        return ctx
