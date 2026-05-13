# -*- coding: utf-8 -*-
"""统一 CLI 入口。

子命令：
  list                     列出所有已注册 action
  run <pipeline.yaml>      运行 YAML pipeline，-v key=value 传变量
  do <action> [--k v ...]  跑单个 action（快速验证用）

例子：
  # 跑 pipeline
  python -m tiled_tools.cli run pipelines/topdown_to_iso.yaml \
      -v input=res/grass.png -v output=output/grass_iso.png

  # 单独跑一个 action 链：load + topdown_to_iso + save
  python -m tiled_tools.cli quick-iso res/grass.png output/grass_iso.png

  # 看看现在有哪些 action
  python -m tiled_tools.cli list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

from .core.action import Context
from .core.pipeline import Pipeline
from .core.registry import available_actions, get_action


def _parse_kv(items: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for raw in items or []:
        if "=" not in raw:
            raise SystemExit(f"变量需要 key=value 格式，得到: {raw}")
        k, v = raw.split("=", 1)
        out[k.strip()] = v
    return out


def cmd_list(_args: argparse.Namespace) -> int:
    print("已注册 actions:")
    for n in available_actions():
        print(f"  - {n}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    pipeline_path = Path(args.pipeline).resolve()
    if not pipeline_path.is_file():
        raise SystemExit(f"找不到 pipeline: {pipeline_path}")
    pipeline = Pipeline.from_yaml(pipeline_path)
    variables = _parse_kv(args.var or [])
    print(f"== 运行 pipeline: {pipeline.name} ==")
    if pipeline.description:
        print(f"   {pipeline.description}")
    pipeline.run(variables=variables, verbose=True)
    print("== 完成 ==")
    return 0


def cmd_quick_iso(args: argparse.Namespace) -> int:
    """便捷子命令：一条龙做 topdown -> iso。等价于跑 pipelines/topdown_to_iso.yaml"""
    pipeline = Pipeline.from_dict({
        "name": "quick_iso",
        "steps": [
            {"action": "load", "params": {"path": "${input}"}},
            {"action": "topdown_to_iso", "params": {
                "anchor": args.anchor,
                "angle": args.angle,
                "y_scale": args.y_scale,
                "resample": args.resample,
                "trim": not args.no_trim,
            }},
            {"action": "save", "params": {"path": "${output}"}},
        ],
    })
    pipeline.run(variables={"input": args.input, "output": args.output})
    return 0


def cmd_do(args: argparse.Namespace) -> int:
    """跑单个 action。参数通过 --param key=value 传，value 自动尝试 JSON 解析。"""
    import json

    action = get_action(args.action)
    params: Dict[str, Any] = {}
    for raw in args.param or []:
        if "=" not in raw:
            raise SystemExit(f"--param 需要 key=value，得到: {raw}")
        k, v = raw.split("=", 1)
        try:
            params[k] = json.loads(v)
        except json.JSONDecodeError:
            params[k] = v
    ctx = Context()
    action.run(ctx, **params)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import main as serve_main
    print(f"启动 tiled_tools web: http://{args.host}:{args.port}/")
    serve_main(host=args.host, port=args.port, reload=args.reload)
    return 0


def cmd_quick_topdown(args: argparse.Namespace) -> int:
    """便捷子命令：iso → topdown 一条龙。topdown_to_iso 的逆。"""
    pipeline = Pipeline.from_dict({
        "name": "quick_topdown",
        "steps": [
            {"action": "load", "params": {"path": "${input}"}},
            {"action": "iso_to_topdown", "params": {
                "y_scale": args.y_scale,
                "angle": args.angle,
                "resample": args.resample,
                "trim": not args.no_trim,
                "pad_before_scale": args.pad,
            }},
            {"action": "save", "params": {"path": "${output}"}},
        ],
    })
    pipeline.run(variables={"input": args.input, "output": args.output})
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="tiled_tools",
                                 description="Tiled 资源处理工作流工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="列出所有 action").set_defaults(func=cmd_list)

    p_run = sub.add_parser("run", help="运行 YAML pipeline")
    p_run.add_argument("pipeline", help="pipeline YAML 文件路径")
    p_run.add_argument("-v", "--var", action="append", default=[],
                       help="给 pipeline 传变量，形式 key=value，可重复")
    p_run.set_defaults(func=cmd_run)

    p_iso = sub.add_parser("quick-iso", help="便捷：topdown -> iso 一条龙")
    p_iso.add_argument("input", help="输入贴图路径")
    p_iso.add_argument("output", help="输出贴图路径")
    p_iso.add_argument("--anchor", default="bottom-center",
                       help="正方化时的锚点（默认 bottom-center）")
    p_iso.add_argument("--angle", type=float, default=45.0)
    p_iso.add_argument("--y-scale", type=float, default=0.5,
                       dest="y_scale", help="高度压缩比例（默认 0.5）")
    p_iso.add_argument("--resample", default="bicubic",
                       choices=["nearest", "bilinear", "bicubic", "lanczos"])
    p_iso.add_argument("--no-trim", action="store_true",
                       help="保留旋转后的整张正方形画布，不裁透明边")
    p_iso.set_defaults(func=cmd_quick_iso)

    p_top = sub.add_parser("quick-topdown",
                           help="便捷：iso -> topdown 一条龙（quick-iso 的逆）")
    p_top.add_argument("input", help="输入 iso 贴图路径")
    p_top.add_argument("output", help="输出 topdown 贴图路径")
    p_top.add_argument("--y-scale", type=float, default=2.0, dest="y_scale",
                       help="高度反向缩放因子（默认 2.0 = dimetric 的逆；"
                            "60° 真等距用 1.7321）")
    p_top.add_argument("--angle", type=float, default=-45.0,
                       help="反向旋转角度（默认 -45）")
    p_top.add_argument("--resample", default="bicubic",
                       choices=["nearest", "bilinear", "bicubic", "lanczos"])
    p_top.add_argument("--no-trim", action="store_true",
                       help="保留旋转后的整张画布，不裁透明边")
    p_top.add_argument("--pad", type=int, default=0,
                       help="拉伸前先在四周加多少像素 padding（输入紧贴边缘时建议>0）")
    p_top.set_defaults(func=cmd_quick_topdown)

    p_do = sub.add_parser("do", help="单步跑某个 action（调试用）")
    p_do.add_argument("action", help="action 名字，可用 list 子命令查看")
    p_do.add_argument("--param", action="append", default=[],
                      help="key=value，value 支持 JSON（如 [1,2] / true）")
    p_do.set_defaults(func=cmd_do)

    p_srv = sub.add_parser("serve", help="启动 web 端（FastAPI + 单页前端）")
    p_srv.add_argument("--host", default="127.0.0.1")
    p_srv.add_argument("--port", type=int, default=8765)
    p_srv.add_argument("--reload", action="store_true", help="开发模式热重载")
    p_srv.set_defaults(func=cmd_serve)

    return ap


def main(argv: List[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
