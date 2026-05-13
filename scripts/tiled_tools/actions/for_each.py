# -*- coding: utf-8 -*-
"""for_each：把"上一步产生的多张图"丢给一个子 pipeline 批量处理。

为什么需要它
------------
像 split_3x3 这类 action 会一次产出 9 张图（放在 ctx.extras["tiles"]）。
如果想对 9 张都做"topdown_to_iso"，不能直接接一个 topdown_to_iso —— 那个
action 只看 ctx.image，处理的是单张（split_3x3 设的中央块 C）。

for_each 的角色就是：取出 extras["tiles"] 列表，逐张当作 ctx.image，
跑一遍内部的 steps 子 pipeline，把每张的处理结果再收回到 tiles 里。
对外看就是"批量化"。

参数
----
- source : 取哪个 extras key 当输入列表。默认 "tiles"。
- steps  : 子 pipeline，结构与顶层 pipeline 一样，[{action, params}, ...]。
- keep_names : True (默认) 时保留 ctx.extras["tile_names"]，方便 save_all
               按原名（NW/N/NE...）写出。

输出
----
- ctx.image                = 子 pipeline 处理完的最后一张（保持"链最末是单图"
                             的直觉，便于后面再接 save 看一张）
- ctx.extras["tiles"]      = 9 张处理结果
- ctx.extras["tile_names"] = 与原来一致（如果原来有）
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..core.action import Action, Context
from ..core.registry import register, get_action


@register("for_each")
class ForEachAction(Action):
    description = "对上一步产出的多张图批量执行子 pipeline（split_* 后用）"
    param_hints = {
        "source": {"enum": ["tiles"]},
        "steps":  {"widget": "subpipe"},
    }

    def run(
        self,
        ctx: Context,
        source: str = "tiles",
        steps: List[Dict[str, Any]] | None = None,
        keep_names: bool = True,
    ) -> Context:
        steps = steps or []
        tiles = ctx.extras.get(source)
        if not tiles:
            raise RuntimeError(
                f"[for_each] ctx.extras[{source!r}] 为空。"
                f"通常应放在 split_3x3 / split_grid 等会产出多图的 action 之后。"
            )
        if not steps:
            print("[for_each] steps 为空，跳过")
            return ctx

        names = ctx.extras.get("tile_names") if keep_names else None

        out_tiles = []
        for i, tile in enumerate(tiles):
            label = (names[i] if names and i < len(names) else f"#{i + 1}")
            print(f"[for_each] ({i + 1}/{len(tiles)}) tile={label} "
                  f"size={tile.size}")
            # 给每张构造独立的子 ctx：image 设为该 tile，meta/extras 不共享
            # （避免子 pipeline 误读外层 tiles 造成无限递归）
            sub_ctx = Context(
                image=tile,
                meta={**ctx.meta, "for_each_index": i, "for_each_label": label},
                extras={},
                workdir=ctx.workdir,
            )
            for j, step in enumerate(steps, start=1):
                action_name = step.get("action")
                params = dict(step.get("params") or {})
                if action_name in ("for_each",):
                    raise ValueError("[for_each] 暂不支持嵌套 for_each")
                action = get_action(action_name)
                print(f"  [for_each.{i + 1}.{j}] {action_name}  params={params}")
                sub_ctx = action.run(sub_ctx, **params)

            if sub_ctx.image is None:
                raise RuntimeError(
                    f"[for_each] 第 {i + 1} 张处理后 ctx.image 为空，"
                    "子 pipeline 里不要放 save / split 之类会清空主图的 action。"
                )
            out_tiles.append(sub_ctx.image)

        # 收集结果回外层 ctx
        ctx.extras[source] = out_tiles
        if keep_names and names:
            ctx.extras["tile_names"] = list(names)
        ctx.meta["for_each_count"] = len(out_tiles)
        # 主图取最后一张（直觉一致；想取中央块就 split_3x3 之后再做）
        return ctx.with_image(out_tiles[-1])
