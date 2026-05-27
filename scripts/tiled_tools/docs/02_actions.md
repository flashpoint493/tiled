# Action 速查

> 当前共 **26 个 action**。每个都是单一职责的"算子"，可任意串联。

>
> 命名约定：动词在前，`_` 分隔；处理多张图的 action 名字里通常含 `_all` / `_set` / `_dir`。

## I/O 类

| Action | 输入 | 输出 | 主要参数 |
| --- | --- | --- | --- |
| `load` | path | `ctx.image` | `path`（file_id 或磁盘路径） |
| `load_dir` | 目录路径 | `ctx.extras["tiles"]` + `tile_names` | `path`, `pattern="*.png"`, `sort`, `limit` |
| `save` | `ctx.image` | 1 张 PNG | `path`（`auto` = 自动分配 file_id） |
| `save_all` | `ctx.extras["tiles"]` | 多张 PNG | `dir`, `prefix`, `pattern="{prefix}_{name}.png"` |

## 单图变换类

| Action | 主要参数 | 说明 |
| --- | --- | --- |
| `square_canvas` | `anchor`, `size`, `width`, `height`, `background` | 把图放进指定画布：默认正方形，也支持矩形画布 |

| `rotate` | `angle`, `expand`, `resample`, `background` | 任意角度旋转 |
| `scale` | `sx`, `sy`, `factor`, `size`, `resample` | 缩放（支持非等比） |
| `topdown_to_iso` | `anchor=bottom-center`, `angle=45`, `y_scale=0.5`, `trim` | 复合：`square + rotate + scale` |
| `iso45_tile_spec` | `preset=96/128/256/512/custom` | 用 Web 下拉选择 iso45 最终 cell/grid/tileoffset 规格 |
| `iso45_fit_tile` | `preset=context`, `anchor`, `resample` | Topdown tile → iso45 菱形 → 放入所选规格 cell |
| `iso_to_topdown` | `y_scale=2.0`, `angle=-45`, `pad_before_scale`, `trim` | `topdown_to_iso` 的几何逆 |

| `tile_repeat` | `cols=3`, `rows=3`, `count`, `gap`, `background` | 单图 N×M 平铺（验证循环 / 铺地预览） |
| `make_seamless` | `method`, `overlap`, `levels`, `blur_radius`, `blur_band` | 把任意图片变成四方连续（tileable） |


## 多图 / 集合类

| Action | 输入 | 输出 | 主要参数 |
| --- | --- | --- | --- |
| `split_3x3` | `ctx.image` | 9 张 tiles + 方位 `tile_names` | `mode=equal/border`, `border` |
| `split_connected` | 透明背景 `ctx.image` | 多张 tiles + `001/002/...` `tile_names` | `min_alpha`, `min_width`, `min_height`, `padding`, `connectivity`, `sort` |
| `for_each` | `ctx.extras["tiles"]` | 同上但每张被处理过 | `source=tiles`, `steps`（嵌套子 pipeline） |
| `pack_sheet` | `ctx.extras["tiles"]` | 1 张 sheet PNG + `ctx.extras["sheet"]` | `columns`, `spacing`, `margin`, `tile_w`, `tile_h` |
| `build_tsx_sheet` | `ctx.extras["sheet"]` | Tiled `.tsx` | `name`, `tile_names`（是否写方位命名属性） |

## Tiled 结构文件类

| Action | 输入 | 输出 | 主要参数 |
| --- | --- | --- | --- |
| `derive_tsx_image` | 已有 `.tsx` + 新 image | 派生 `.tsx` | `source_tsx`, `output`, `name`, `image_source`, `image_path` |
| `brush_remap_tsx` | runtime tileset + brush variants tileset | brush `.tsx` + `.remap.json` | `source_tsx`, `variants_tsx`, `output` |
| `remap_tmj_gids` | `.tmj/.tmx` + `.remap.json` | 替换 GID 后的地图 | `map_path`, `mapping_json`, `output` |
| `convert_tmj_topdown_to_iso45` | topdown `.tmj` + iso45 `.tsx` | iso45 `.tmj` | `map_path`, `target_tileset`, `gid_remap` |
| `tileset_to_iso45_matrix` | 已排好的 topdown tileset sheet | tile id 顺序不变的 iso45 sheet | `tile_width`, `tile_height`, `columns`, `tile_count`, `preset` |

`derive_tsx_image` 适合美术重绘同构 sheet 的情况：它只替换 tileset 名称和 `<image>` 元数据，不改 tile name、properties、WangSet。

## Wang 2-edge / 过渡素材类

| Action | 主要参数 | 说明 |
| --- | --- | --- |
| `gen_default_masks` | `size=32`, `half_extent=0.5` | 生成 16 张几何蒙版（4-bit NESW 边码） |
| `mask_blend_set` | `foreground`, `background`, `resample`, `expected=16` | 用蒙版混合两张底图 → 16 张过渡 tile |
| `wang_2edge_compose_map` | `pattern=lake3`, `code_matrix`, `wrap` | 按边匹配 code 矩阵把 16 张 wang tile 拼成完整预览地图 |



## Context 通道（设计核心）

理解 action 怎么串联，看这张图：

```
            ctx.image              ctx.extras
            (单图)                 ──────────────────
load        ↓ 设                  
rotate      ↓ 读 写
split_3x3   ↓ 设为中央             tiles=[9 张]
                                    tile_names=[NW..SE]
split_conn  ↓ 设为第 1 张           tiles=[识别到的多张]
                                    tile_names=[001..]
for_each    └ 每张当 image 跑子 ↘  tiles 被替换为处理后
gen_masks   ↓ 设最后一张占位       tiles=[16 蒙版]
                                    tile_names=[mask_00..]
mask_blend  ↓ 设最后一张占位       tiles=[16 合成 tile]
pack_sheet  ↓ 设为 sheet PNG       sheet={path, tile_w, ...}
build_tsx                          消费 sheet → 写 tsx
save        └ 写一张 ↗
save_all    └ 写全部 tiles ↗
```

**关键约定**：
- `ctx.image` 永远是"当前主图"。
- `ctx.extras["tiles"]` 是"当前有一组图"的通道，任何会输出多张的 action 都写它，
  任何能消费多张的 action 都读它。**新 action 想接入只要遵守这俩约定，无需改任何旧代码**。
- `ctx.extras["tile_names"]` 是与 tiles 平行的名字列表，一路透传到 `save_all` /
  `build_tsx_sheet`，最终在 Tiled 里能按方位/语义名找到 tile。

## 添加新 action 的最小成本

```python
# scripts/tiled_tools/actions/my_action.py
from ..core.action import Action, Context
from ..core.registry import register

@register("my_action")
class MyAction(Action):
    description = "做点什么"
    param_hints = {"factor": {"min": 0.0, "max": 10.0}}
    def run(self, ctx: Context, factor: float = 1.0) -> Context:
        img = self.require_image(ctx, "my_action")
        # ... 处理 img ...
        ctx.image = result
        return ctx
```

再在 `actions/__init__.py` 加一行 `from . import my_action`。

**前端表单、CLI 子命令、workflow YAML 全部自动可用，零额外工作量。**
