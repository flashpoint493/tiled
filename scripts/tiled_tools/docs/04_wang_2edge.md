# Wang 2-edge 过渡素材专题

> 你有一张四方连续的沙地，想加沙→水过渡。本页讲完整流程。

## 你需要画的东西

| 文件 | 内容 | 数量 |
| --- | --- | --- |
| `sand_tile.png` | 四方连续沙地（你已有） | 1 |
| `water_tile.png` | 四方连续水面 | 1 |
| `masks/mask_00.png ... mask_15.png` | 16 张过渡蒙版（可选） | 16 |

**蒙版可选**——`gen_default_masks` 能自动生成几何蒙版，足够"先验证整条链路通了"。等流程跑通了，再用美术蒙版替换它就行。

## 边码约定（4-bit N E S W）

每个 tile 用 4 bit 描述四条边各是什么 terrain：

| bit 位 | 边 | 1 = | 0 = |
| --- | --- | --- | --- |
| 1 | 北 N | foreground (沙) | background (水) |
| 2 | 东 E | foreground | background |
| 4 | 南 S | foreground | background |
| 8 | 西 W | foreground | background |

```
code  N E S W  含义                可视化（白=沙 黑=水）
─────────────────────────────────────────────────────
  0   0 0 0 0  全水               ████  ████
  1   1 0 0 0  仅北沙             ░░░░  ▒▒░░
  2   0 1 0 0  仅东沙             ████  █▒░░
  3   1 1 0 0  北东沙（凹陆角）    ░░░░  ▒▒░░ (左下水)
 ...
 15   1 1 1 1  全沙               ░░░░  ░░░░
```

按 code 升序排列，刚好凑成 4×4 sheet：

```
 0   1   2   3      水 北水 东水 北东水
 4   5   6   7      南水 …
 8   9  10  11      西水 …
12  13  14  15     …  全沙
```

> **重要**：4×4 排列的顺序就是 Tiled Edge Set 的边码顺序。当前 workflow 会把这些边码直接写进 `.tsx` 的 `<wangsets>`，所以一般不需要再手工逐 tile 标边；打开 tileset 后 Terrain Sets 里会直接出现可用的 Edge Set。


## 蒙版怎么画

**白色区域 = 用 foreground（沙），黑色区域 = 用 background（水），灰度 = 混合**。

每张蒙版的形状对应它的边码——哪条边是沙，那一侧就画白色"渗入" tile 内部。

### 几个典型形状

| code | NESW | 蒙版形状 |
| --- | --- | --- |
| 0 | 水水水水 | 整张黑 |
| 15 | 沙沙沙沙 | 整张白 |
| 1 | 沙水水水 | 上半渐变（上白下黑）|
| 5 | 沙水沙水 | 上下两条沙带，中间水带 |
| 3 | 沙沙水水 | 左下角扇形黑，其余白（凸入水里的沙角）|
| 12 | 水水沙沙 | 左上角扇形白，其余黑（凸入沙里的水角）|

### 接缝匹配原则（最容易翻车的点）

相邻两张 tile 必须**共享边的形状**——具体说：

- `tile A` 的东边 = `tile B` 的西边（如果 A、B 水平相邻）
- `tile A` 的南边 = `tile C` 的北边（如果 C 在 A 下面）

实际操作上，你只要保证**所有蒙版的"北边像素列"长一个样、"东边像素列"长一个样、…**，就一定能拼。最简单的实现：

1. 画 4 张"边沿条"：`north.png`、`east.png`、`south.png`、`west.png`（每张 W×H，但只用边缘那一段，其余先按"沙渗入半张 tile"画好）
2. 每张 tile 蒙版 = 该 tile 各 fg 边对应"边沿条"取 max

`gen_default_masks` 内置就是这个逻辑（用几何渐变），并且会对相邻 fg 边的公共角补圆角渐变（例如 `N+E` 补 `NE` 角），避免 4 个转角只靠直角边带导致过渡生硬。你画美术蒙版时只要保证 16 张里**任意两张共享方向的边沿像素一致**，同时给 `3/6/9/12` 这类拐角 tile 的角落画出连续过渡即可。


## 三种工作流

### 方案 1：纯几何蒙版（30 秒上手）

不画蒙版，直接用 `gen_default_masks` 出几何过渡。**适合**：先验证 Tiled 那边的 terrain set 配置对不对、地形拼接逻辑通不通。

```bash
# CLI
python -m tiled_tools run wang_2edge_set \
    -v fg=sand_tile.png -v bg=water_tile.png -v name=wang_sand_water
```

或 web 端：

1. 顶栏 workflow 下拉选 `wang_2edge_set`
2. 展开 `mask_blend_set` 这一步，看到 `foreground` 和 `background` 两个字段
3. 点 `foreground` 旁的 📎 按钮上传沙地贴图；点 `background` 旁的 📎 上传水面贴图
4. ▶ 运行

产物：`set_xxxx/sheet.png` (128×128) + `set_xxxx/sheet.tsx`，下载两个到同一目录，拖进 Tiled 就能用。

### 方案 2：先用几何蒙版起稿，再美术化

```bash
# step 1: 生成几何蒙版当起稿
python -m tiled_tools run - <<'EOF'   # （示意，实际用 yaml 文件）
steps:
  - action: gen_default_masks
    params: { size: 32, half_extent: 0.5 }
  - action: save_all
    params: { dir: masks_geom, pattern: "mask_{name:02d}.png" }
EOF

# step 2: 美术在 masks_geom/ 上手工修饰每张（贝壳、白沫、参差海岸线）
# 保存到 masks_art/

# step 3: 用美术蒙版做最终 tile set
python -m tiled_tools run wang_2edge_set \
    -v fg=sand_tile.png -v bg=water_tile.png \
    -v mask_dir=masks_art
```

**注意 pipeline 里要把 `gen_default_masks` 换成 `load_dir`**——打开
`wang_2edge_set`，按注释提示切换即可。

### 方案 3：全美术蒙版

跳过几何，直接画 16 张 PNG（建议先在你最熟的工具如 Photoshop / Aseprite 画一张完整的 4×4 sheet 草稿，再切成 16 张）。然后 web 端选 `wang_2edge_set`，把第一步换成 `load_dir`，path 指向你的蒙版目录。

## 非 iso 的完整 Edge Set + Corner Set：`wang_2edge_corner_set`

如果不做 `isometric 45°` 转换，只想用两张四方连续贴图直接得到完整规则集，选 `wang_2edge_corner_set`。

```text
gen_default_masks(mode=both, size=tile_size)
→ mask_blend_set(expected=32)
→ pack_sheet(columns=8)
→ build_tsx_sheet(wang_2edge=true, wang_2corner=true)
```

默认产物：

- `sheet.png`：8×4，共 32 格；前 16 格是 Edge Set，后 16 格是 Corner Set
- `sheet.tsx`：自动写入两个 `<wangset>`：`type="edge"` 和 `type="corner"`
- 默认每格 `256×256`，整张 sheet 是 `2048×1024`

命令行：

```bash
python -m tiled_tools run wang_2edge_corner_set \
    -v fg=sand.png \
    -v bg=water.png \
    -v tile_size=256
```

Web 端：workflow 下拉选 `wang_2edge_corner_set`，给 `mask_blend_set.foreground/background` 上传两张四方连续贴图，直接运行即可。

> 说明：这里的“完整”指完整 Edge Set + Corner Set。Tiled 的 Mixed Set 是 8 个 corner/edge 位置同时参与的 256 组合，当前这条 workflow 不生成 Mixed Set；如果后续确实需要 Mixed Set，需要扩展新的 mask / wangid 生成 action。

## iso 45° 版本：`wang_2edge_set_iso`


和 `wang_2edge_set` 一模一样的输入（两张底图 + 蒙版），但**每张 wang tile 都
会被 iso 化成菱形并标准化到 256×256 正方形画布**（菱形宽 96 高 48 贴底，上方留
48px 透明边给"高度"空间）—— 这就是 Tiled isometric 模式的标准 tile 形态。

```
普通版产物 (wang_2edge_set):        iso 版产物 (wang_2edge_set_iso):
┌──┬──┬──┬──┐                       ┌────┬────┬────┬────┐
├──┼──┼──┤                          │    │    │    │    │     ← 每张 256×256 画布
├──┼──┼──┤                          │ ◇  │ ◇  │ ◇  │ ◇  │       下半是 256×128 菱形（贴底）
└──┴──┴──┘                          │    │    │    │    │       上半 48px 透明给立绘 / 高物体
                                    │ ◇  │ ◇  │ ◇  │ ◇  │
4×4 平面 sheet                      └────┴────┴────┴────┘
（32×32 tile → 128×128）            4×4 iso sheet (默认 1024×1024)
```

**为什么默认贴底？** iso 视角下菱形是地面 footprint，上方留白用来放角色立绘
或高物体（树、塔楼）。这样：
- 角色站在 tile 上时直接画在画布顶部，无需手算偏移
- Tile 之间切换 / 替换时世界坐标参考点保持一致

想要居中对齐？传 `-v anchor=center`。

**画布尺寸可配置**——通过 `target` / `half_target` 两个变量控制：

```bash
# 默认 256×256 画布，菱形贴底
python -m tiled_tools run wang_2edge_set_iso -v fg=sand.png -v bg=water.png

# 改成 128×128
python -m tiled_tools run wang_2edge_set_iso \
    -v fg=sand.png -v bg=water.png -v target=128 -v half_target=64

# 改成 64×64（紧凑版）+ 居中对齐
... -v target=64 -v half_target=32 -v anchor=center
```

Web 端跑时如果想改 target / anchor，先 ▶ 跑一次拿到默认产物，再编辑左侧
`for_each` 下嵌套的 `square_canvas.anchor` 字段即可。

**注意 1**：产物 tsx 默认是普通方块 tile orientation，仅视觉是 iso。如果要
用作真正的 Tiled isometric 地图 tileset，**在 Tiled 里手动改**：
Edit Tileset → Orientation 改为 Isometric，Tile Width 保持 96，Tile Height
改为 48（菱形外接矩形高，不是画布高）。

**注意 2**：默认参数下 16 张 tile **完全同尺寸** 256×256，菱形贴底对齐，sheet
网格完美对齐。这是通过 workflow 里以下设计实现的：
- `topdown_to_iso.trim = false` —— 不裁透明边，保证形状一致
- `scale.size = [target, half_target]` —— 精确缩放到菱形外接尺寸
- `square_canvas.size = target, anchor = bottom-center` —— 上方补透明边到正方形画布

### 使用步骤

1. 顶栏 workflow 下拉选 `wang_2edge_set_iso`
2. 找到 `mask_blend_set` 步骤，点 `foreground` 旁的 📎 上传沙地，`background` 旁的 📎 上传水面
3. ▶ 运行
4. 右下产物：`sheet_xxxx/sheet.png` (1024×1024) + `sheet.tsx`

## 真正用于 Isometric Terrain Brush：`wang_2edge_set_iso_terrain`

如果目标是在 Tiled 的 **Isometric Map** 里用 Terrain Brush 刷地形，优先用 `wang_2edge_set_iso_terrain`。它和 `wang_2edge_set_iso` 的区别是：

```text
wang_2edge_set_iso:
每格 N×N 透明画布，菱形可贴底 —— 适合视觉 tileset / 物件垫底

wang_2edge_set_iso_terrain:
每格仍是 N×N tileset 单元，方便在 Tileset 编辑器里框选/标记；
但内部 isometric grid 是 N×N/2 —— 适合 Tiled Isometric Terrain Brush
```

规格由 `iso45_tile_spec.preset` 控制，Web 里会显示为下拉菜单：`96 / 128 / 256 / 512 / custom`。默认 `256` 时会在 `.tsx` 中写入：

```xml
<tileoffset x="0" y="64"/>
<grid orientation="isometric" width="256" height="128"/>
```

命令行：

```bash
python -m tiled_tools run wang_2edge_set_iso_terrain \
    -v fg=sand.png \
    -v bg=water.png \
    -v spec=256
```

默认产物是 `1024×1024` sheet（4×4，每格 `256×256`），但 terrain grid 是 `256×128`；如果 `-v spec=128`，则变成每格 `128×128`、grid `128×64`、tileoffset.y `32`。

Tiled 中配套：

1. New Map：`Orientation=Isometric`，`Tile Width=N`，`Tile Height=N/2`（默认 256 / 128）
2. 打开生成的 `.tsx`（tileset 单元是 `N×N`，不是 `N×N/2`）
3. 确认 Tileset Properties 里 `Orientation=Isometric`、`Grid Width=N`、`Grid Height=N/2`
4. Terrain Sets 面板里应已经有自动生成的 **Edge Set**，直接选择 terrain 在地图上刷即可


如果你想手动改 terrain 名称 / 颜色，可以在已有 Edge Set 上改，不必在透明 padding 的 cell 上重新逐格标边。



## 同时包含 Edge Set + Corner Set：`wang_2edge_corner_set_iso_terrain`

如果你希望一个 tileset 里同时包含完整 **边缘集** 和 **转角集**，用 `wang_2edge_corner_set_iso_terrain`。

它会生成 32 个 tile：

```text
0..15   = Edge Set（边码 N/E/S/W）
16..31  = Corner Set（角码 TL/TR/BR/BL）
```

并在 `.tsx` 里自动写入两个 wangset：

```xml
<wangset name="edge_set" type="edge" ...>
<wangset name="corner_set" type="corner" ...>
```

命令行：

```bash
python -m tiled_tools run wang_2edge_corner_set_iso_terrain \
    -v fg=sand.png \
    -v bg=water.png
```

默认产物是 `2048×1024` sheet（8×4，每格 `256×256`），内部 grid 仍是 `256×128`；同样可通过 `iso45_tile_spec.preset` 下拉或 `-v spec=128/512` 改规格。打开 `.tsx` 后 Terrain Sets 面板里会同时有 Edge Set 和 Corner Set，不需要在透明 cell 上手工标边。


## 3 种甚至更多 terrain：`multi_tiletype_corner_set`

上面的 `wang_2edge_set` / `wang_2edge_corner_set` 本质上都是**二地形**规则：

- 每条边只有 `foreground / background` 两种取值
- 每个角只有 `foreground / background` 两种取值
- 所以 edge 是 `2^4 = 16`，corner 也是 `2^4 = 16`

一旦你要做 `grass / sand / water` 这种 **3 种 terrain 混合**，或者更多类型，继续按“成对生成多个二地形 tileset”会遇到两个问题：

- **规则不统一**：`grass↔sand`、`sand↔water`、`grass↔water` 分散在多个 tileset，地图上不好一起刷
- **三岔/四岔交汇缺失**：成对过渡只能表达 A/B，不能在同一 tile 上同时表达 A/B/C

为此新增了 `multi_tiletype_corner_set` workflow：

```text
load_dir(读取基础 terrain 目录)
→ multi_terrain_wang_set(mode=both)
→ pack_sheet
→ build_tsx_sheet
```

它的核心思路是：

- 目录里的每张基础循环贴图代表一种 terrain
- 直接生成一个**单一的多 terrain wangset**，而不是拆成多个二地形 tileset
- 对于 N 种 terrain：
  - Edge Set 数量 = `N^4`
  - Corner Set 数量 = `N^4`
  - 两者一起 = `2 * N^4`

例如：

| terrain 数 | edge | corner | 总数 |
| --- | ---: | ---: | ---: |
| 3 | 81 | 81 | 162 |
| 4 | 256 | 256 | 512 |
| 5 | 625 | 625 | 1250 |

### 什么时候适合用它

- 你确实需要在**同一个 tileset / 同一个 terrain set**里支持 3 种以上材料混刷
- 你的基础素材都是四方连续贴图，允许通过程序化混合来生成边界
- 你能接受“大量组合 tile”带来的 sheet 体积增长

### 什么时候不要硬上

- 如果只是 `sand → shallow → deep` 的分层海岸，而且实际不会在同一格里出现三向交汇，**多个二地形 tileset 仍然更轻量**
- 如果某些三岔路口需要**高度定制的手工美术形状**，程序化混合只能作为起稿，不会完全替代手绘
- 当 terrain 超过 4 种时，通常更建议按主题拆成多个 tileset，否则 sheet 会非常大

### 输入约定

把基础 terrain 图放进一个目录，按文件名排序作为 terrain 顺序，例如：

```text
terrains/
├── 01_grass.png
├── 02_sand.png
└── 03_water.png
```

默认：

- 文件 stem 会作为 terrain 名称写进 `.tsx`
- 颜色会自动分配；如果需要更准确的名称/颜色，可后续继续扩展 action 参数

### 命令行

```bash
python -m tiled_tools run multi_tiletype_corner_set \
    -v terrain_dir=terrains \
    -v name=grass_sand_water \
    -v columns=18
```

### Web 端

1. 先用顶栏 **批量导入** 把多张基础 terrain 图上传到同一个目录
2. 选择 workflow：`multi_tiletype_corner_set`
3. 把第一步 `load_dir.path` 改成批量导入得到的目录 id（如 `batch_ab12cd34`）
4. ▶ 运行，下载生成的 `sheet.png` 与 `.tsx`

### 结果解释

生成的 `.tsx` 里会有：

- 一个多 terrain 的 `edge_set`
- 一个多 terrain 的 `corner_set`
- 每个 `<wangcolor>` 对应一种 terrain（不再是只有 background / foreground 两种）
- 每个 `<wangtile>` 的 `wangid` 会直接写 4 个位置各自属于哪一种 terrain

也就是说，**这不是 Mixed Set 的 8 位置建模**，而是把现有 Edge Set / Corner Set 从“二值”推广到了“多值”。这正适合探索 3 种甚至更多 tile 类型共存时的规则集 workflow。


## 整张 3×3 大图整体 iso 化：`wang_2edge_big_iso`



如果你不想看到 16 个“小菱形 tile”各自摆在 sheet 里，而是希望先得到一张完整的 3×3 大图，再把这整张图整体转成 iso，用 `wang_2edge_big_iso`。


两者区别：

```text
wang_2edge_set_iso:
16 张 tile → 每张单独 iso 化 → 拼成 4×4 iso tileset

wang_2edge_big_iso:
16 张 tile → 按边匹配矩阵取 9 张拼成完整 3×3 平面地图 → 整张图 topdown_to_iso → 1 张完整 iso 大图
```

关键点：`wang_2edge_set` 的 4×4 sheet 是 **lookup 表**（code 0..15），不是一张可连续铺开的地图。相邻 code 的 E/W、N/S 边不一定一致，所以直接整体 iso 会像“角度方向错了”。`wang_2edge_big_iso` 改用 `wang_2edge_compose_map`，默认 `pattern=lake3`，会按下面这种边匹配 code 矩阵取 tile：

```text
9  1  3
8  0  2
12 4  6
```

这个 3×3 矩阵的四个角分别是 `9/3/12/6`，都是拐角过渡 tile，不再用纯色死角。它相当于 `island3` 的反相版本，适合你看到“外围 8 格方向反了”时使用；如果你希望 foreground 在中间、background 在外圈，则把 `pattern` 改成 `island3`。



命令行：


```bash
python -m tiled_tools run wang_2edge_big_iso \
    -v fg=sand.png \
    -v bg=water.png \
    -v target=288 \
    -v half_target=144 \
    -v pattern=lake3

```

`pattern` 可选：

| pattern | 用途 |
| --- | --- |
| `lake3` | 默认；3×3 反向环，适合修正“外围 8 格方向反了”的结果 |
| `island3` | `lake3` 反相；foreground 在中间、background 在外圈 |

| `island4` | 4×4 更大中心区，但四个外角是纯 background |
| `lake4` | `island4` 反相 |
| `lookup4` | 原始 code 0..15 顺序，仅用于对照，不保证边匹配 |

默认产物：


- `flat_output`：未 iso 的 3×3 平面图（默认 `256×256`，当 `tile_size=32`）
- `output`：整体 iso 后的大图，默认放进 `768×768` 透明画布，下半是 `768×384` 的完整菱形图


> 注意：这个产物适合美术预览、mock-up、或作为 Object Layer 上的一张大图使用；它不是可逐格刷地形的 Edge Set tileset。要 Tiled terrain brush，仍用 `wang_2edge_set` / `wang_2edge_set_iso`。

## 大块水域怎么不显得机械？


`wang_2edge_set` 输出的 tile #0（全水）只有 1 张。大片水域铺起来视觉太规整。三种解法（**素材层面而非 Tiled 层面**）：

| 解法 | 难度 | 怎么做 |
| --- | --- | --- |
| 多变体 | ★ | 画 2-3 张外观略不同的"全水" tile，导入 tsx 后手工加入 terrain set 的同一 terrain | 
| 动画 | ★★ | 画 4-6 帧波纹序列，在 Tiled 用 Tile Animation Editor 配到 #0 | 
| 装饰层 | ★★★ | 单独一层 object layer，散几个浪花/反光（不进 terrain set） | 

## 多级过渡（深水/浅水/沙）

一条 wang_2edge_set 只能搞两个 terrain 间的过渡。如果你要"沙→浅水→深水"三层：

```
集合 A: sand    ↔ shallow    → 16 tiles
集合 B: shallow ↔ deep       → 16 tiles
共享 1 张 shallow 循环 tile，所以总共 1 + 14 + 1 + 14 + 1 = 31 tile
```

每个集合都用一次 `wang_2edge_set`，分别命名 `coast.tsx` 和 `deep.tsx`，在 Tiled 同一张地图上叠两层 terrain set 使用即可。

## 细节装饰物（贝壳/礁石/海星等）

**不要塞进 terrain set**，它们应该是装饰物：

1. 单独一个 tileset，类型选 **Collection of Images**（每个细节 1 张独立 PNG）
2. 在地图加一层 `Object Layer`，命名如 `decor_beach`
3. 装饰物以 object 形式自由放置（不受格子约束，可缩放旋转）
4. 想要"靠岸才出现贝壳"自动撒点 → 用 Tiled 的 Automapping，或运行时游戏自己生成

## 完整端到端示例（一行命令）

```bash
cd scripts

# 假设：sand.png 和 water.png 都是 32x32 的四方连续 tile
python -m tiled_tools run wang_2edge_set \
    -v fg=res/sand.png \
    -v bg=res/water.png \
    -v tile_size=32 \
    -v name=wang_sand_water
```

完成后：
```
.tiled_tools_runtime/outputs/sheet_xxxxxxxx/
├── sheet.png   128x128，4x4 wang 2-edge set
└── sheet.tsx   Tiled tileset 文件
```

拖 `.tsx` 进 Tiled 后，Terrain Sets 面板里会已有自动生成的 Edge Set。你可以直接改 terrain 名称 / 颜色并开始刷；不需要按 4×4 sheet 手工逐 tile 标边。


