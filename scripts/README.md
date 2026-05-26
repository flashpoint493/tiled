# scripts/ — Tiled 资源处理工具集

为 Tiled 项目准备贴图、组装 tileset 的小工具集合。

## 目录结构

```
scripts/
├── pyproject.toml          # 独立 Python 包配置
├── requirements.txt        # 开发期依赖列表
├── tiled_tools/            # 核心包：Action + Pipeline + Web UI
│   ├── core/               #   Action 基类 / Context / Pipeline / 注册表
│   ├── actions/            #   一个文件一个 action
│   ├── docs/               #   Web 帮助文档（随包分发）
│   ├── pipelines/          #   内置 YAML workflow（随包分发，只读）
│   ├── web/                #   单页前端（随包分发，无构建）
│   └── server.py           #   FastAPI 后端（web 模式）
├── split_icons.py          # 旧脚本：从总览图拆图标（仍可用）
├── build_tsx.py            # 旧脚本：把目录组装成 .tsx（仍可用）
├── res/                    # 本仓库示例输入素材
├── output/                 # 本仓库示例产物输出（gitignore）
└── .tiled_tools_runtime/   # web 模式 uploads/outputs（运行时自动创建，gitignore）
```

> 旧脚本 `split_icons.py` / `build_tsx.py` 保留是为了向后兼容；新功能请走
> `tiled_tools` 包，它们后续会被改造成对应 action 的薄包装。

## 安装

开发安装（推荐，直接在本目录调试）：

```bash
pip install -e .
```

或仅安装依赖后用源码运行：

```bash
pip install -r requirements.txt
```

## 设计理念：Action + Pipeline

* **Action**：一个原子操作，例如「正方化画布」「旋转 45°」「按比例缩放」。
  每个 Action 接收一个 `Context`（携带当前图像、元数据、工作目录），返回新的
  `Context`。
* **Pipeline**：把一串 Action 串起来跑。可以写成 YAML 让非编码用户也能改。

这种结构带来的好处：

1. 任意组合：不同任务（topdown→iso、批量切图、生成 sheet…）只是不同的
   Action 序列。
2. 复用：每个 action 都能单独使用、单独测试、单独替换。
3. 易扩展：写个新文件，加一个 `@register("xxx")`，YAML 里就能用。

## 已有 actions

| name | 说明 |
| --- | --- |
| `load` | 从磁盘读图到 ctx.image |
| `save` | 把 ctx.image 写到磁盘（单图） |
| `save_all` | 批量保存上一步的多张产物（消费 `ctx.extras["tiles"]`） |
| `square_canvas` | 把图放进指定画布：默认正方形，也支持 `size=[w,h]` / `width` / `height` 矩形画布 |

| `rotate` | 任意角度旋转，可选 expand |
| `scale` | 缩放，支持非等比 |
| `topdown_to_iso` | 复合：square_canvas + rotate(45) + scale(sy=0.5) + 可选 trim |
| `iso45_tile_spec` | 用下拉预设选择 iso45 最终规格（96/128/256/512/custom） |
| `iso45_fit_tile` | Topdown tile → iso45 菱形 → 放入所选规格 cell |
| `iso_to_topdown` | `topdown_to_iso` 的几何逆（scale + rotate(-45) + trim） |

| `split_3x3` | 把"3×3 循环 tile / auto-tile"图拆成 9 张（NW/N/NE/W/C/E/SW/S/SE） |
| `for_each` | 对上一步产出的多张图批量执行子 pipeline |
| `pack_sheet` | 把 `ctx.extras["tiles"]` 拼成单张 sprite sheet PNG（Tiled 友好） |
| `build_tsx_sheet` | 基于 pack_sheet 的 sheet 生成 Tiled `.tsx`（Based on Tileset Image） |
| `tile_repeat` | 把单张贴图按 N×M 网格平铺成一张大图（验证循环 / 铺地预览） |
| `load_dir` | 从目录批量读图到 `ctx.extras["tiles"]`（读美术蒙版用） |
| `gen_default_masks` | 生成 16 张 wang 2-edge 几何蒙版（过渡素材起稿） |
| `mask_blend_set` | 用 16 张蒙版混合两张底图 → 16 张 wang 2-edge tile |
| `multi_terrain_wang_set` | 从 3+ 张四方连续基础 terrain 生成 scene-source shared tile，并写入 edge/corner/mixed WangSet 元数据 |
| `wang_2edge_compose_map` | 按边匹配 code 矩阵把 16 张 wang tile 拼成完整预览地图 |
| `make_seamless` | 把任意图片变成四方连续（tileable） |


查看实时列表：

```bash
python -m tiled_tools list
```

## 用法

### Web 端（推荐）

```bash
python -m tiled_tools serve --port 8765
# 浏览器打开 http://localhost:8765/
```

界面三栏：
- 左侧：所有 action 的卡片，点击或拖到中间。
- 中间：当前 pipeline，每步可展开改参数、上下排序、删除。
- 右侧：原图预览 / 产物预览（多张时自动 3x3 网格） / 执行日志。

顶栏支持 **workflow** 持久化：
- 下拉条：列出已保存的 user workflow 和内置的 builtin（包内 `tiled_tools/pipelines/*.yaml`）。
- 选择即加载到中间面板；可直接修改后再次保存（同名覆盖）。
- 「★ 存为 workflow」会问你 id（落盘文件名）和显示名，存到当前工作目录的 `workflows/<id>.json`。
- 「🗑」删除当前选中的 user workflow（builtin 不能删）。

操作：
1. 点「上传图片」选一张本地贴图（自动填到 `load.path`）。
2. 如果是多张独立 PNG 要组成 tilesheet，点「批量导入」一次选择多张图，Web 会自动拼成 sheet + `.tsx` 并运行。
3. 选一个内置 workflow 起步，或自己拼。常用模板：
   - `topdown_to_iso`：单图直接 iso 化。
   - `3x3_split_then_iso`：3×3 循环 tile → 拆 9 张 → 每张 iso → 批量保存。
   - `batch_images_to_tilesheet`：目录/批量图片 → sheet + `.tsx`。
   - `multi_tiletype_corner_set` / `multi_tiletype_corner_set_iso45_matrix`：多 terrain scene-source sheet + edge/corner/mixed `.tsx`。
   - `project_color_merge_iso45`：项目专用流程，一次生成 topdown authoring 源图和 iso45 Tiled 版本。
4. 点「▶ 运行」或按 `Ctrl+Enter`。产物在右下，可下载。


### 合成 sprite sheet + Tiled tsx

Tiled 支持两种 tileset：

1. **Collection of Images**（旧脚本 `build_tsx.py` 做的）：每个 tile 一张独立 PNG，
   tsx 里用 `<tile><image source=".."/></tile>` 一个一个列。尺寸可以参差。
2. **Based on Tileset Image**（`pack_sheet` + `build_tsx_sheet` 做的）：一张 sheet 大图
   + 网格参数。所有 tile 尺寸必须一致，但性能好、Tiled 里渲染更流畅，
   也是循环 tile / 角色帧 / iso 拼图的标准格式。

web 端内置 workflow `3x3_split_then_iso_sheet` 就是第 2 种的一条龙：

```
load → split_3x3 → for_each[topdown_to_iso] → pack_sheet → build_tsx_sheet
```

跑完产物面板里会看到两个文件：`grass_iso.png` + `grass_iso.tsx`（在同一子目录）。
两个一起下载，放到任意目录，双击 tsx 用 Tiled 打开即可。

`build_tsx_sheet` 默认会把 `NW/N/NE/W/C/E/SW/S/SE` 写成每个 tile 的 `name` 属性，
方便在 Tiled 的 Tile Properties 里直接根据方位找到对应 tile。

### `for_each`：批量处理多张图

`split_3x3` 这类 action 一次产 9 张图（放在 `ctx.extras["tiles"]`）。如果要对
9 张都做 iso 化，不能直接接 `topdown_to_iso`（它只看主图 `ctx.image`），
而应用 `for_each` 包起来：

```
load → split_3x3 → for_each(steps=[topdown_to_iso]) → save_all
```

`for_each` 的 `steps` 字段在前端长成一个内嵌的小 pipeline 编辑器，
可以加多步（例如 `scale → topdown_to_iso → rotate`）。

### API（前端就靠这几条；写脚本/插件也能直接调）

| 路由 | 说明 |
| --- | --- |
| `GET /api/actions` | 列出所有 action 的 schema |
| `POST /api/upload` | multipart 上传单张图片，返回 `file_id` |
| `POST /api/upload-batch` | multipart 批量上传图片，返回 `dir_id` 与文件列表，供 `load_dir` 使用 |
| `POST /api/run` | body `{pipeline:[...], variables:{...}}`，跑完返回 `outputs` 与日志 |

| `GET /api/file/<id>` | 预览/下载 uploads 或 outputs 里的文件 |
| `GET /api/workflows` | 列出所有 workflow（user + builtin yaml） |
| `GET /api/workflows/<id>` | 取一个 workflow（builtin 用 `yaml:<stem>` 形式） |
| `POST /api/workflows` | 保存 workflow（覆盖同名） |
| `DELETE /api/workflows/<id>` | 删除 user workflow |

### 0) 3×3 循环 tile 拆分

适用于"中央块自身可平铺，外圈 8 块用于边界过渡"的 auto-tile / wang tile 素材。
在 web 端把 pipeline 拼成：

```
load → split_3x3 → save_all
```

跑完右侧产物面板会用 3×3 网格展示 9 张子贴图（NW/N/NE/W/C/E/SW/S/SE），
每张可点击下载。

参数：
- `mode = equal`（默认）：源图均分 3 等份。最常用。
- `mode = border` + `border = N`：外圈厚度 = N 像素，中心占剩余。常用于像素美术
  规格化的素材（如「边框 16，中央 32」）。

链式用法：`split_3x3` 会把**中央块 C** 设为 `ctx.image`，所以可以直接接
`topdown_to_iso` 把中央块 iso 化，再接 `save`：

```
load → split_3x3 → topdown_to_iso → save
```

### 1) Topdown → Iso 45°（命令行最快）

最快：

```bash
python -m tiled_tools quick-iso res/grass_topdown.png output/grass_iso.png
```

可选参数：

```bash
python -m tiled_tools quick-iso input.png output.png \
    --anchor center \         # 地面 tile 用 center；人物/物件用 bottom-center
    --y-scale 0.5774 \        # 真 60° iso；2:1 dimetric 用 0.5（默认）
    --resample nearest \      # 像素风用 nearest 保硬边
    --no-trim                 # 保留旋转后的整张正方形画布，不裁透明
```

走 YAML：

```bash
python -m tiled_tools run topdown_to_iso \
    -v input=res/grass_topdown.png \
    -v output=output/grass_iso.png
```

YAML 里随便改步骤、加步骤都可以，例如想在 iso 化前做一次 2x 上采样，只要插一行：

```yaml
steps:
  - { action: load,  params: { path: ${input} } }
  - { action: scale, params: { factor: 2, resample: nearest } }   # 新增
  - { action: topdown_to_iso, params: { anchor: bottom-center } }
  - { action: save,  params: { path: ${output} } }
```

### 1.5) Iso → Topdown（反向）

`topdown_to_iso` 的几何逆，用来还原资产或把第三方 iso 资产反推 footprint：

```bash
python -m tiled_tools quick-topdown iso_input.png topdown_out.png \
    --y-scale 2.0 \           # dimetric 反算用 2.0（默认）；60° 真等距用 1.7321
    --resample nearest \      # 像素风务必 nearest
    --pad 16                  # 输入紧贴画布边时加点 padding，避免角被裁
```

走内置 workflow：`iso_to_topdown`，web 端下拉里也能直接选到。

闭环验证（topdown → iso → topdown）已经在测试里跑通：128×128 输入经过一次往返
回到 132×132（正方形误差 0），主要色块和方向都保留。

### 1.6) 单图 N×M 平铺（验证循环 / 铺地预览）

把一张贴图复制成 N×M 的大图，最常用的两个用途：

1. **验证循环 tile 是否真无缝**：拼 3×3 看接缝。如果中央和外圈拼接处没有
   可见竖/横/十字裂缝，就说明这张图能正确循环。
2. **给美术做"铺地"成品预览**：一张地面 tile 拼 5×5，直接看大块效果。

```bash
python -m tiled_tools run tile_repeat_3x3 \
    -v input=res/grass.png -v output=output/grass_3x3.png
```

参数：
- `cols` / `rows`：分别控制 X / Y 方向数量（默认 3 / 3）
- `count`：便捷写法，等价于 `cols=rows=count`（如 `count=5` 即 5×5）
- `gap`：tile 之间的像素间隔，默认 0；想看清单格边界可设 1
- `background`：留 gap 时透出的底色，默认透明

Web 端下拉里直接选 `tile_repeat_3x3` 即可，上传一张图后改改参数就行。

### 1.7) Wang 2-edge 过渡素材（沙↔水 等）

你有一张四方连续的沙地，想加入沙→水过渡怎么办？这就是经典的
"wang 2-edge tile" 需求（也叫 RPG Maker 的 A2 格式）。

完整 16 张 tile 的边码约定（4-bit N E S W）、蒙版画法、和
Tiled Edge Set 绑定步骤详见 web 端 **📖 帮助 → Wang 2-edge 专题**。
最简形态：

```bash
python -m tiled_tools run wang_2edge_set \
    -v fg=sand_tile.png \
    -v bg=water_tile.png \
    -v name=wang_sand_water
```

产物：一张 4×4 sheet PNG + 一份 Tiled `.tsx`，**用几何蒙版自动生成**
（16 张蒙版由 `gen_default_masks` 出，包含边带和拐角圆角过渡）。`.tsx` 会自动写入 Edge Set 的 `<wangsets>` 元数据，所以不用手工逐格标边；之后用
`load_dir` 换成美术蒙版即可量产。

如果要非 iso 但同时包含完整 Edge Set + Corner Set，用 `wang_2edge_corner_set`：两张四方连续贴图 → 32 格 8×4 sheet + 自动写两个 wangset 的 `.tsx`。默认每格 `256×256`，可用 `-v tile_size=128/512` 调整。

需要 iso 45° 视角的版本？有两种：


- `wang_2edge_set_iso`：每张过渡 tile 单独 iso 化，再拼 4×4 iso sheet；默认每格是 256×256 透明画布，适合视觉 tileset / 物件垫底。规格由 `iso45_tile_spec.preset` 下拉控制（96/128/256/512/custom）。
- `wang_2edge_set_iso_terrain`：默认每格是 256×256 tileset 单元（方便框选/标记），但 `.tsx` 写入 256×128 isometric grid + tileoffset，适合真正在 Tiled Isometric Map 里用 Terrain Brush；改 preset 时 cell/grid/tileoffset 会联动。

- `wang_2edge_corner_set_iso_terrain`：生成 32 格 sheet，前 16 格是完整 Edge Set，后 16 格是完整 Corner Set，并在 `.tsx` 自动写入两个地形集；同样支持规格下拉。


- `wang_2edge_big_iso`：按边匹配矩阵先拼一张完整 3×3 平面地图，再把整张图整体 iso 化，适合美术预览 / mock-up / 一张大装饰图。默认 `lake3` 会反转外围 8 格方向，四角都是拐角过渡 tile，不是简单的 0..15 lookup sheet。






完整说明见 web 端 **📖 帮助 → Wang 2-edge 专题**。


### 2) 在 Python 里直接编排

```python
from tiled_tools import Pipeline, Context
from tiled_tools.core.pipeline import Step

pipe = Pipeline(name="demo", steps=[
    Step("load",            {"path": "in.png"}),
    Step("square_canvas",   {"anchor": "bottom-center"}),
    Step("rotate",          {"angle": 45}),
    Step("scale",           {"sy": 0.5}),
    Step("save",            {"path": "out.png"}),
])
pipe.run()
```

### 3) 单步调试某个 action

```bash
python -m tiled_tools do scale --param sx=2 --param sy=2
```

## 扩展：新增一个 action

1. 在 `tiled_tools/actions/` 下新建 `xxx.py`：

   ```python
   from ..core.action import Action, Context
   from ..core.registry import register

   @register("blur")
   class BlurAction(Action):
       def run(self, ctx: Context, radius: float = 2.0) -> Context:
           img = self.require_image(ctx, "blur")
           from PIL import ImageFilter
           return ctx.with_image(img.filter(ImageFilter.GaussianBlur(radius)))
   ```

2. 在 `tiled_tools/actions/__init__.py` 里加一行 `from . import xxx`，
   触发装饰器副作用。

3. 之后在任何 YAML 或 CLI 里都能用 `blur` 这个名字了。

## 路线图（待办）

* [ ] 把 `split_icons.py` 拆成 `split_connected` / `split_grid` 两个 action。
* [ ] 把旧 `build_tsx.py`（collection 版）包成 `build_tsx_collection` action。
* [ ] Web 端：目录批量模式（一个文件夹批量跑同一 workflow）。
* [ ] Web 端：每步独立预览（点中间任意一步看到当时的 ctx.image）。
* [ ] Web 端：颜色选择器替换"R,G,B,A"文本框。
* [ ] `for_each` 支持嵌套（当前显式拒绝）。
* [ ] `pack_sheet` 支持按 `tile_names` 顺序重排（用户可自定义顺序）。
