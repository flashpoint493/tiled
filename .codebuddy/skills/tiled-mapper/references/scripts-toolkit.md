# scripts/tiled_tools 工具链能力速查

本仓库 `scripts/tiled_tools/` 提供了一套 **Action + Pipeline** 框架，把 Tiled 资源准备阶段的常见任务自动化。本文档让另一个 CodeBuddy 实例能快速判断"该用哪条 pipeline"以及"怎么跑"。

> 完整使用文档见 `scripts/README.md`，本文档是给 AI 的决策表。

## 何时使用工具链 vs. 何时教用户在 Tiled 里手工操作

| 场景 | 推荐 |
| --- | --- |
| 一张源图，要切成 9 张 / 16 张 tile | **工具链**（手工切麻烦且容易像素错位） |
| topdown 视角贴图转 iso 45°（菱形） | **工具链** |
| 多张同尺寸 tile 拼成 sprite sheet | **工具链** |
| 批量对一组 tile 做相同处理（旋转、缩放、iso） | **工具链** |
| 生成 Tiled 可识别的 `.tsx`（带网格参数） | **工具链** |
| 在 Tiled 里调地形集 / 动画 / 自定义属性 | **手工**（Tiled 编辑器本身就是为此设计的） |
| 在地图上画对象 / 摆 NPC | **手工** |

**判定法则**：涉及"图像像素处理 + 文件生成"用工具链；涉及"在地图上做决策性布置"用 Tiled。

## 启动方式

工具链有 3 种使用入口，**优先推荐 Web UI**（用户最直观）：

### 1. Web UI（推荐）

```powershell
cd scripts
python -m tiled_tools serve --port 8765
# 浏览器打开 http://localhost:8765/
```

启动日志会列出当前注册的所有 action。界面三栏：
- 左：action 库
- 中：当前 pipeline（拖拽排序）
- 右：原图 / 产物预览 + 日志

顶栏 workflow 下拉里有 12 个内置 workflow（见下文表格），开箱即用；顶栏「批量导入」可一次选择多张图片并自动生成 sheet + `.tsx`。





### 2. CLI 跑 YAML pipeline

```powershell
cd scripts
python -m tiled_tools run pipelines/3x3_split_then_iso_sheet.yaml `
    -v input=path/to/source.png `
    -v sheet_name=grass_iso
```

### 3. CLI 单 action（调试用）

```powershell
python -m tiled_tools quick-iso source.png output.png --y-scale 0.5
python -m tiled_tools list                # 列所有 action
python -m tiled_tools do scale --param sx=2 --param sy=2  # 单步跑
```

## 内置 workflow（pipelines/*.yaml）

| Workflow | 用途 | 产物 |
| --- | --- | --- |
| `topdown_to_iso` | 单张 topdown 贴图 → iso 45° | 1 PNG |
| `iso_to_topdown` | 单张 iso 贴图 → 反推回 topdown（`topdown_to_iso` 的逆） | 1 PNG |
| `3x3_split_then_iso` | 3x3 循环 tile → 切 9 张 → 每张 iso → 散文件 | 9 PNG |
| `3x3_split_then_iso_sheet` | 同上 + 拼 sprite sheet + 生成 Tiled `.tsx` | 1 PNG + 1 TSX |
| `tile_repeat_3x3` | 单张贴图按 3×3 平铺成大图（验证循环 / 铺地预览） | 1 PNG |
| `batch_images_to_tilesheet` | 多张独立图片 / 一个目录 → 拼成单张 tilesheet + `.tsx`（Web 顶栏「批量导入」会自动走这条链路） | 1 PNG + 1 TSX |
| `wang_2edge_set` | 两张底图（foreground/background）→ 16 张过渡 tile + sheet + .tsx（沙↔水 等 edge-style 过渡素材） | 1 PNG + 1 TSX |
| `wang_2edge_corner_set` | 两张底图 → 非 iso 的 32 格 sheet + .tsx；前 16 格 edge、后 16 格 corner，并自动写两个 wangset | 1 PNG + 1 TSX |

| `wang_2edge_set_iso` | 同 `wang_2edge_set`，但每张过渡 tile 被单独 iso 45° 化，默认最终是 256×256 画布的视觉 tileset sheet；规格由 `iso45_tile_spec.preset` 下拉控制 | 1 PNG + 1 TSX |

| `wang_2edge_set_iso_terrain` | 同 `wang_2edge_set`，但每张 tile 默认放在 256×256 tileset 单元中，同时在 `.tsx` 写入 256×128 isometric grid + tileoffset，适合 Tiled Isometric Terrain Brush；改 preset 时 cell/grid/tileoffset 联动 | 1 PNG + 1 TSX |

| `wang_2edge_corner_set_iso_terrain` | 同时生成完整 Edge Set + Corner Set：前 16 格 edge，后 16 格 corner，并在 `.tsx` 自动写两个 wangset；同样支持规格下拉 | 1 PNG + 1 TSX |


| `wang_2edge_big_iso` | 按边匹配矩阵拼完整 3×3 平面地图，再把整张图整体 iso 45° 化（默认 `lake3`，反转外围 8 格方向，四角都是拐角过渡 tile；不是 0..15 lookup sheet） | 平面图 + 1 PNG |







**最常用是第三个**——一条命令把 auto-tile 素材完全做成 Tiled 可打开的形态。

## Action 速查（18 个）


| Action | 输入 | 输出 | 主要参数 |
| --- | --- | --- | --- |
| `load` | 磁盘 path / web 上传 file_id | `ctx.image` | `path` |
| `save` | `ctx.image` | 磁盘文件 | `path`（`auto` = 自动分配） |
| `save_all` | `ctx.extras["tiles"]` 多张图 | 一组文件 | `dir`, `prefix`, `pattern` |
| `square_canvas` | `ctx.image` | 指定画布（默认正方形，也可矩形） | `anchor`, `size`, `width`, `height`, `background` |

| `rotate` | `ctx.image` | 旋转后的图 | `angle`, `expand`, `resample` |
| `scale` | `ctx.image` | 缩放后的图 | `sx`, `sy`, `factor`, `size` |
| `topdown_to_iso` | `ctx.image` | iso 化的图 | `anchor`, `angle=45`, `y_scale=0.5`, `trim` |
| `iso45_tile_spec` | — | `ctx.meta` 中的 iso45 规格 | `preset=96/128/256/512/custom`（Web 下拉控制最终 cell/grid/tileoffset） |
| `iso45_fit_tile` | `ctx.image` | 按规格放入 cell 的 iso45 tile | `preset=context`, `anchor`, `resample` |
| `iso_to_topdown` | `ctx.image` | 反推回 topdown 的图 | `y_scale=2.0`, `angle=-45`, `pad_before_scale`, `trim`（`topdown_to_iso` 的几何逆） |

| `split_3x3` | `ctx.image` | 9 张 tiles + tile_names | `mode=equal/border`, `border` |
| `for_each` | `ctx.extras["tiles"]` | 批量处理后的 tiles | `source`, `steps`（子 pipeline） |
| `pack_sheet` | `ctx.extras["tiles"]` | sprite sheet PNG + sheet 元数据 | `columns`, `spacing`, `margin`, `tile_w`, `tile_h`, `pad_anchor` |
| `build_tsx_sheet` | `ctx.extras["sheet"]` | Tiled `.tsx` | `name`, `tile_names`（是否写 NW/N/... 命名属性） |
| `tile_repeat` | `ctx.image` | 平铺后的大图 | `cols=3`, `rows=3`, `count`（覆盖 cols/rows）, `gap`, `background`（单图 N×M 复制：验证循环 / 铺地预览） |
| `make_seamless` | `ctx.image` | 四方连续贴图 | `method`, `overlap`, `blur_radius`, `blur_band`（把任意图片变 tileable） |

| `load_dir` | 目录 | `ctx.extras["tiles"]` + `tile_names` | `path`, `pattern="*.png"`, `sort`, `limit`（批量读美术蒙版用） |
| `gen_default_masks` | — | 16 张蒙版（`tiles`） | `size=32`, `half_extent=0.5`（生成 wang 2-edge 几何蒙版） |
| `mask_blend_set` | `ctx.extras["tiles"]`（16 蒙版）+ 两张底图 | 16 张过渡 tile | `foreground`, `background`, `resample`, `expected=16` |
| `wang_2edge_compose_map` | `ctx.extras["tiles"]`（16 张 wang tile） | 边匹配 3×3 / 4×4 预览地图 | `pattern=lake3`, `code_matrix`, `wrap` |




### Context 通道（设计核心）

- `ctx.image`：单图通道。`load` 写入，`save` / `square_canvas` / `rotate` / `scale` / `topdown_to_iso` 读写。
- `ctx.extras["tiles"]`：多图通道。`split_3x3` 写入 9 张，`for_each` 读写（批量改写），`save_all` / `pack_sheet` 消费。
- `ctx.extras["tile_names"]`：与 tiles 平行的名字列表。`split_3x3` 写 `[NW,N,NE,W,C,E,SW,S,SE]`，一路透传到 `build_tsx_sheet` 写成 tile 的 `name` 属性。
- `ctx.extras["sheet"]`：`pack_sheet` 写入的 sheet 规格（path / tile_w / tile_h / columns / rows / spacing / margin / tile_count），`build_tsx_sheet` 消费。

## 常见 pipeline 配方

### 配方 A：topdown 贴图 → iso 45°（单张）

```yaml
steps:
  - { action: load, params: { path: ${input} } }
  - action: topdown_to_iso
    params:
      anchor: bottom-center   # 站立物用 bottom-center；地面 tile 用 center
      y_scale: 0.5            # 2:1 dimetric；真 60° iso 用 0.5774
      trim: true
  - { action: save, params: { path: ${output:auto} } }
```

### 配方 A2：iso → topdown（反向，`topdown_to_iso` 的几何逆）

适用于"还原自己生成的 iso"或"把第三方 iso 资产反推 footprint"。

```yaml
steps:
  - { action: load, params: { path: ${input} } }
  - action: iso_to_topdown
    params:
      y_scale: 2.0            # dimetric 反算；60° 真等距用 1.7321
      angle: -45              # 与正向 +45 对称
      resample: bicubic       # 像素风改 nearest
      trim: true
      pad_before_scale: 0     # 输入紧贴画布边时设 > 0（如 8 / 16）
  - { action: save, params: { path: ${output:auto} } }
```

闭环验证已通过：128×128 topdown → iso → topdown 还原到 132×132（仅旋转
padding 多出 4px），主要色块、方向标记完整保留。

### 配方 A3：单图 N×M 平铺（验证循环 / 铺地预览）

用户上传一张贴图，想直接看"如果把它当循环 tile 重复 N×M 次会是什么效果"，
或者要把单 tile 拼成大块给美术看成品：

```yaml
steps:
  - { action: load, params: { path: ${input} } }
  - action: tile_repeat
    params:
      cols: 3
      rows: 3
      gap: 0              # 验证无缝循环用 0；想看清单格边界设 1
      # count: 5          # 便捷写法，等价 cols=rows=5
  - { action: save, params: { path: ${output:auto} } }
```

注意：这是**机械复制**，每格图都一样。如果用户实际上有一组 3×3 auto-tile
（9 张不同方位 tile），他要的可能是"按邻居关系挑边角拼"，那是另一个还没
实现的能力（roadmap 里的 `tile_repeat_autotile`），需要先和用户澄清。

### 配方 A4：Wang 2-edge 过渡素材（沙↔水等）

用户说"我有一张四方连续沙地，想加沙→水过渡"——这是经典 wang 2-edge
（Edge Set 的标准制作方式，行业里叫 RPG Maker A2 / 2-edge wang tile）。

**边码约定**：4-bit `N E S W`（bit 1=北, 2=东, 4=南, 8=西），bit=1 代表
foreground terrain（默认 sand）。0..15 共 16 张 tile，排成 4×4 sheet。

```yaml
steps:
  # 方案 A（最快）：用几何蒙版
  - action: gen_default_masks
    params: { size: ${tile_size:32}, half_extent: 0.5 }  # 自动生成边带 + 拐角圆角过渡

  # 方案 B（量产）：换成自己画的蒙版目录
  # - action: load_dir
  #   params: { path: ${mask_dir}, pattern: "mask_*.png", limit: 16 }

  - action: mask_blend_set
    params:
      foreground: ${fg}     # sand_tile.png
      background: ${bg}     # water_tile.png
      resample: nearest     # 像素美术必须
  - action: pack_sheet
    params: { columns: 4, spacing: 0, margin: 0, path: auto }
  - action: build_tsx_sheet
    params: { name: ${name:wang_sand_water}, tile_names: true }
```

**Tiled 这边**：把产物 `.tsx` 拖进 Tiled 后，Terrain Sets 面板里会已有自动生成的 **Edge Set**（写在 `<wangsets>` 里）。通常只需要改 terrain 名称 / 颜色并开始刷，不需要在透明 padding 很多的 sheet 上手工逐 tile 标边。


### 配方 A5：Wang 2-edge 过渡素材 + iso 45° 视角（规格下拉控制）

和 A4 输入完全一致，但每张过渡 tile 被 iso 化成菱形并放在 `N×N` 正方形画布中。
`N` 由 `iso45_tile_spec.preset` 控制，Web 里是下拉菜单（96 / 128 / 256 / 512 / custom）；默认 `256` 表示菱形 footprint 为 `256×128`。

```yaml
steps:
  - { action: gen_default_masks, params: { size: ${tile_size:32}, half_extent: 0.5 } }
  - { action: mask_blend_set, params: { foreground: ${fg}, background: ${bg}, resample: nearest } }
  - { action: iso45_tile_spec, params: { preset: ${spec:256} } }
  - action: for_each
    params:
      source: tiles
      steps:
        - action: iso45_fit_tile
          params:
            preset: context
            anchor: ${anchor:bottom-center}
            resample: bicubic
            background: [0, 0, 0, 0]
  - { action: pack_sheet, params: { columns: 4, path: auto } }
  - { action: build_tsx_sheet, params: { name: ${name:wang_2edge_iso}, tile_names: true } }
```

**默认尺寸**：`spec=256` → 每张 tile 256×256 画布，4×4 sheet = 1024×1024。
要改成 128×128 或 512×512：Web 改 `iso45_tile_spec.preset` 下拉，CLI 传 `-v spec=128/512`。

**注意**：默认 tsx orientation 是普通方块。要用作真正的 Tiled isometric
地图 tileset，优先使用 `wang_2edge_set_iso_terrain`，它会自动写入 isometric grid / tileoffset。


### 配方 B：3x3 循环 tile → 9 张散文件

```yaml
steps:
  - { action: load, params: { path: ${input} } }
  - { action: split_3x3, params: { mode: equal } }
  - action: save_all
    params:
      dir: ${output_dir:auto}
      prefix: ${prefix:tile}
      pattern: "{prefix}_{name}.png"   # name = NW/N/NE...
```

### 配方 C：3x3 拆分 + 每张 iso + 拼 sheet + tsx（最完整）

```yaml
steps:
  - { action: load, params: { path: ${input} } }
  - { action: split_3x3, params: { mode: equal } }
  - action: for_each
    params:
      source: tiles
      steps:
        - action: topdown_to_iso
          params:
            anchor: center
            y_scale: 0.5
            trim: false   # 批量场景 trim=false 才能尺寸一致
  - action: pack_sheet
    params:
      path: ${sheet_name:sheet}.png
      columns: 3
      spacing: 0
      margin: 0
  - action: build_tsx_sheet
    params:
      name: ${name:grass_iso}
      tile_names: true   # 把 NW/N/NE... 写成 tile property
```

### 配方 D：纯批量缩放

```yaml
steps:
  - { action: load, params: { path: ${input} } }
  - { action: split_3x3, params: { mode: equal } }
  - action: for_each
    params:
      source: tiles
      steps:
        - action: scale
          params: { factor: 2, resample: nearest }   # 像素风用 nearest
  - { action: save_all, params: { dir: ${output_dir:auto} } }
```

## 关键参数提示

### `topdown_to_iso.anchor`

- **角色 / 树木 / 站立物件**：`bottom-center`（脚下中心是世界坐标参考）
- **地面 tile**：`center`（中心对称）
- **房屋顶部装饰**：`top-center`

### `topdown_to_iso.y_scale`

- `0.5`：标准 2:1 dimetric（业界最常用，也是 RPG Maker / Pixar）
- `0.5774`：真 60° 等距（数学上精确，但 1 像素 = 半像素，像素风会糊）
- `0.866`：30° 仰视

### `pack_sheet.columns`

- 9 张 → 自动选 3（最常见）
- 其他 → 自动选 `ceil(sqrt(n))`
- 想要"一长条" → 显式指定 `columns=9`（行数会变 1）

### `split_3x3.mode`

- `equal`：源图等分 3 份，最常用。
- `border`：外圈厚度 = `border` 像素，中心吃剩。适合像素美术明确规定"边框 16，中央 32"的素材。

## 变量占位符

YAML 里 `${var}` 与 `${var:default}` 都支持：

| 占位符 | web UI 行为 | CLI 行为 |
| --- | --- | --- |
| `${input}` | 自动填上传文件的 file_id | 必填 `-v input=path` |
| `${output:auto}` | 走 auto（server 自动分配 file_id） | 默认 `auto`，可 `-v output=...` |
| `${output_dir:auto}` | 同上 | 同上 |
| `${prefix:}` | 默认空字符串 → `save_all` 用源文件 stem | 同上 |

变量缺失时报错会提示"在 CLI 用 `-v xxx=...` 传入，或者在 YAML 里写 `${xxx:默认值}`"。

## 产物路径约定（web 模式）

- 上传：`.web_runtime/uploads/up_<uuid>.png`
- 单图产物：`.web_runtime/outputs/out_<uuid>.png`
- 多图产物：`.web_runtime/outputs/set_<uuid>/<prefix>_<name>.png`
- sheet + tsx：`.web_runtime/outputs/sheet_<uuid>/<name>.png` + `<name>.tsx`（同目录，相对路径有效）

`.web_runtime/` 在 `scripts/.gitignore` 里，不会污染版本控制。

## 与 Tiled 衔接的关键点

1. **下载产物时，sheet 和 tsx 必须放同目录**——tsx 里的 `<image source>` 是相对路径。
2. **tsx 名字属性可在 Tiled 里看到**：进入 tileset 编辑模式，点 tile → 右侧 Properties 面板就有 `name: NW`。
3. **配地形集**时按方位约定（`NW/N/NE/W/C/E/SW/S/SE`）在 Tiled 里标 Edge 集的边；具体参考 `terrain_sets.md`。
4. 工具链当前只产 XML 形态的 `.tsx`，**不产 `.tsj` JSON**。如果用户的引擎需要 JSON，让他们在 Tiled 里 `File → Export As...` 导出一遍。

## 扩展新 action（给 AI 自己看的）

```python
# scripts/tiled_tools/actions/my_action.py
from ..core.action import Action, Context
from ..core.registry import register

@register("my_action")
class MyAction(Action):
    description = "一句话说清楚做什么"
    param_hints = {
        "mode": {"enum": ["a", "b"]},     # 前端自动渲染下拉
        "factor": {"min": 0, "step": 0.1}, # 前端 number input 的约束
    }

    def run(self, ctx: Context, mode: str = "a", factor: float = 1.0) -> Context:
        img = self.require_image(ctx, "my_action")
        # ... 处理
        return ctx.with_image(new_img)
```

然后在 `scripts/tiled_tools/actions/__init__.py` 加一行 `from . import my_action`，重启 server，Web UI 自动出现这个 action 卡片。**完全无需改前后端代码**——`Action.param_schema()` 反射机制会处理。

## 已知局限

- 工具链产物 tsx 是 XML，不是 JSON（与教程推荐的 `.tsj` 不一致）。若需要 JSON：用 Tiled 打开 tsx → `File → Save As...` → 选 JSON 格式。
- `for_each` 暂不支持嵌套（显式拒绝）。批量处理需要嵌套时考虑写一个新复合 action。
- Web 顶栏「批量导入」只负责把多张独立图片组成一个 tilesheet；还不是“对一个目录里的每张源图分别跑同一 workflow”的通用目录批处理。


