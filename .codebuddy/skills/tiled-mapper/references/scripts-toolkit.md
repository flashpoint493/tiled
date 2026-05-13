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

顶栏 workflow 下拉里有 5 个内置 workflow（见下文表格），开箱即用。

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

**最常用是第三个**——一条命令把 auto-tile 素材完全做成 Tiled 可打开的形态。

## Action 速查（13 个）

| Action | 输入 | 输出 | 主要参数 |
| --- | --- | --- | --- |
| `load` | 磁盘 path / web 上传 file_id | `ctx.image` | `path` |
| `save` | `ctx.image` | 磁盘文件 | `path`（`auto` = 自动分配） |
| `save_all` | `ctx.extras["tiles"]` 多张图 | 一组文件 | `dir`, `prefix`, `pattern` |
| `square_canvas` | `ctx.image` | 正方形画布 | `anchor`, `size`, `background` |
| `rotate` | `ctx.image` | 旋转后的图 | `angle`, `expand`, `resample` |
| `scale` | `ctx.image` | 缩放后的图 | `sx`, `sy`, `factor`, `size` |
| `topdown_to_iso` | `ctx.image` | iso 化的图 | `anchor`, `angle=45`, `y_scale=0.5`, `trim` |
| `iso_to_topdown` | `ctx.image` | 反推回 topdown 的图 | `y_scale=2.0`, `angle=-45`, `pad_before_scale`, `trim`（`topdown_to_iso` 的几何逆） |
| `split_3x3` | `ctx.image` | 9 张 tiles + tile_names | `mode=equal/border`, `border` |
| `for_each` | `ctx.extras["tiles"]` | 批量处理后的 tiles | `source`, `steps`（子 pipeline） |
| `pack_sheet` | `ctx.extras["tiles"]` | sprite sheet PNG + sheet 元数据 | `columns`, `spacing`, `margin`, `tile_w`, `tile_h`, `pad_anchor` |
| `build_tsx_sheet` | `ctx.extras["sheet"]` | Tiled `.tsx` | `name`, `tile_names`（是否写 NW/N/... 命名属性） |
| `tile_repeat` | `ctx.image` | 平铺后的大图 | `cols=3`, `rows=3`, `count`（覆盖 cols/rows）, `gap`, `background`（单图 N×M 复制：验证循环 / 铺地预览） |

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
- 没有"目录批处理"模式（拿一个文件夹批量跑同一 workflow）。要批处理多源文件，用 PowerShell / bash 循环 CLI。
