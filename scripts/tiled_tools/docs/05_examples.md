# 输入 / 输出案例

> 本页示例使用仓库 `scripts/res/` 下的两张素材：`T_Ground_Sand.png` 与 `T_Ground_Water.png`。为了让帮助手册加载更快，文档内展示的是缩小到 256px 的示范输入，实际 workflow 可以直接处理原始 1024×1024 PNG。

## 示例输入素材

| Sand foreground | Water background |
| --- | --- |
| ![sand input](/docs-assets/examples/sand_input_256.png) | ![water input](/docs-assets/examples/water_input_256.png) |

Web 端操作：

1. 单图 workflow：点顶栏 **上传图片**，选择 `scripts/res/T_Ground_Sand.png`。
2. 双图 workflow：加载 `wang_*` workflow 后，分别点 `foreground` / `background` 字段旁的 **📎**，上传 sand 与 water。
3. 批量 workflow：点顶栏 **批量导入**，一次选择两张图。

---

## 单图转换类 workflow

### `topdown_to_iso`

把一张 topdown 方形贴图旋转 45° 并压缩高度，得到 2:1 dimetric / iso 预览。

| 输入 | 输出 |
| --- | --- |
| ![topdown input](/docs-assets/examples/sand_input_256.png) | ![topdown to iso output](/docs-assets/examples/topdown_to_iso_sand.png) |

CLI 等价命令：

```bash
python -m tiled_tools run topdown_to_iso \
  -v input=res/T_Ground_Sand.png \
  -v output=output/sand_iso.png
```

推荐参数：地面 tile 使用 `anchor=center`；人物/物件默认 `bottom-center` 更合适。

### `iso_to_topdown`

把 iso 45° 图反推回 topdown footprint，常用于估算菱形图块对应的平面占地。

| 输入 iso | 输出 topdown |
| --- | --- |
| ![iso input](/docs-assets/examples/topdown_to_iso_sand.png) | ![iso to topdown output](/docs-assets/examples/iso_to_topdown_sand.png) |

CLI 等价命令：

```bash
python -m tiled_tools run iso_to_topdown \
  -v input=output/sand_iso.png \
  -v output=output/sand_topdown_back.png
```

### `tile_repeat_3x3`

把单张贴图平铺成 3×3，用来肉眼检查循环接缝。

| 输入 | 3×3 平铺验证 |
| --- | --- |
| ![tile repeat input](/docs-assets/examples/sand_input_256.png) | ![tile repeat output](/docs-assets/examples/tile_repeat_3x3_sand.png) |

如果你只想看格子边界，可把 `gap` 改为 `1`。

### `make_seamless`

把普通纹理处理成四方连续，并额外输出 3×3 验证图。适合沙、草、岩石、雪、水面等材质。

| 原图 | 无缝单图 | 3×3 验证 |
| --- | --- | --- |
| ![make seamless input](/docs-assets/examples/sand_input_256.png) | ![make seamless output](/docs-assets/examples/make_seamless_sand.png) | ![make seamless repeat output](/docs-assets/examples/make_seamless_sand_3x3.png) |

参数建议：

- `method=feather`：纹理类默认推荐。
- `method=mirror`：接缝要求极低但可接受镜像感。
- `method=offset_blur`：低频渐变背景。

---

## 3×3 / tileset 类 workflow

### `3x3_split_then_iso`

把一张 3×3 循环 tile 切成 `NW/N/NE/W/C/E/SW/S/SE` 九张，再分别转换成 iso。

| 3×3 输入 | 输出示例：中心 C | 输出示例：北 N | 输出示例：东 E |
| --- | --- | --- | --- |
| ![3x3 input](/docs-assets/examples/sand_3x3_input_255.png) | ![split C](/docs-assets/examples/3x3_split_then_iso_sand/sand_iso_C.png) | ![split N](/docs-assets/examples/3x3_split_then_iso_sand/sand_iso_N.png) | ![split E](/docs-assets/examples/3x3_split_then_iso_sand/sand_iso_E.png) |

CLI 等价命令：

```bash
python -m tiled_tools run 3x3_split_then_iso \
  -v input=res/T_Ground_Sand.png \
  -v output_dir=output/sand_3x3_iso \
  -v prefix=sand
```

### `3x3_split_then_iso_sheet`

在上一个 workflow 的基础上，把 9 张 iso tile 拼成 3×3 sheet，并生成 Tiled 可打开的 `.tsx`。

| 3×3 输入 | Sheet PNG |
| --- | --- |
| ![3x3 sheet input](/docs-assets/examples/sand_3x3_input_255.png) | ![3x3 sheet output](/docs-assets/examples/3x3_split_then_iso_sheet_sand/sand_iso_sheet.png) |

产物：

- [下载示例 `sand_iso_sheet.tsx`](/docs-assets/examples/3x3_split_then_iso_sheet_sand/sand_iso_sheet.tsx)
- `tile_names=true` 会把 `NW/N/NE/W/C/E/SW/S/SE` 写进 tile 属性，方便在 Tiled 中识别。

### `tileset_to_iso45_matrix`

把整张 tileset sheet 按格切开，逐格转成 iso，再按原 tile id 顺序拼回矩阵。适合“地图仍按旧 tile id 走，但视角改成 iso”的迁移。

| 输入 sheet | 输出 iso matrix |
| --- | --- |
| ![tileset matrix input](/docs-assets/examples/sand_3x3_input_255.png) | ![tileset matrix output](/docs-assets/examples/tileset_to_iso45_matrix_sand.png) |

CLI 等价命令示例：

```bash
python -m tiled_tools run tileset_to_iso45_matrix \
  -v input=res/T_Ground_Sand.png \
  -v output=output/sand_iso_matrix.png \
  -v tile_width=256 -v tile_height=256 -v columns=4 -v spec=256
```

### `batch_images_to_tilesheet`

把多张独立图片按文件名顺序组成 Tiled tilesheet，并生成 `.tsx`。

| 批量输入 | 输出 sheet |
| --- | --- |
| Sand + Water 两张图 | ![batch sheet output](/docs-assets/examples/batch_images_to_tilesheet_examples/examples_sheet.png) |

产物：

- [下载示例 `examples_sheet.tsx`](/docs-assets/examples/batch_images_to_tilesheet_examples/examples_sheet.tsx)

Web 端最快方式：点顶栏 **批量导入**，一次选择多张图片，工具会自动上传、生成 pipeline 并运行。

### `tilesheet_split_connected`

把一张透明背景 tilesheet 反向裁成多张独立 PNG。它不是按固定网格切，而是按 alpha 连通区域识别：每一团彼此相连的非透明像素会被裁成一张图，并按从上到下、从左到右命名为 `001/002/...`。

CLI 等价命令：

```bash
python -m tiled_tools run tilesheet_split_connected \
  -v input=res/items_sheet.png \
  -v output_dir=output/items \
  -v prefix=item
```

常用参数：

- `min_alpha`：默认 `1`，alpha 大于等于该值才算有效像素。
- `min_width` / `min_height`：过滤透明图里的小噪点。
- `padding`：给每张裁剪结果额外保留透明边。
- `connectivity`：默认 `8`，斜角接触也算同一张；改成 `4` 时只按上下左右连接。

注意：两个 sprite 如果非透明像素已经接触，会被识别为同一个组件；这种情况需要先在原图中留透明间隔。

---

## Wang / Terrain 过渡类 workflow

下面所有示例都使用：

- `foreground = T_Ground_Sand.png`
- `background = T_Ground_Water.png`

### `wang_2edge_set`

生成 16 格 Edge Set 过渡 tilesheet，并写入 Tiled Wang Edge Set 元数据。

| 输出 sheet |
| --- |
| ![wang edge output](/docs-assets/examples/wang_2edge_set_examples/wang_2edge_set.png) |

产物：

- [下载示例 `wang_2edge_set.tsx`](/docs-assets/examples/wang_2edge_set_examples/wang_2edge_set.tsx)

### `wang_2edge_corner_set`

一次生成 Edge Set + Corner Set，共 32 格，适合 orthogonal/topdown 地图。

| 输出 sheet |
| --- |
| ![wang edge corner output](/docs-assets/examples/wang_2edge_corner_set_examples/wang_2edge_corner_set.png) |

产物：

- [下载示例 `wang_2edge_corner_set.tsx`](/docs-assets/examples/wang_2edge_corner_set_examples/wang_2edge_corner_set.tsx)

### `wang_2edge_set_iso`

先生成 16 格 edge 过渡 tile，再逐格 iso 化并拼成 4×4 sheet。适合视觉预览或普通 iso tileset。

| 输出 iso sheet |
| --- |
| ![wang iso output](/docs-assets/examples/wang_2edge_set_iso_examples/wang_2edge_set_iso.png) |

产物：

- [下载示例 `wang_2edge_set_iso.tsx`](/docs-assets/examples/wang_2edge_set_iso_examples/wang_2edge_set_iso.tsx)

### `wang_2edge_set_iso_terrain`

为 Tiled Isometric Terrain Brush 准备的 Edge Set 版本。`.tsx` 会写入 isometric grid 和 tile offset。

| 输出 terrain sheet |
| --- |
| ![wang iso terrain output](/docs-assets/examples/wang_2edge_set_iso_terrain_examples/wang_2edge_set_iso_terrain.png) |

产物：

- [下载示例 `wang_2edge_set_iso_terrain.tsx`](/docs-assets/examples/wang_2edge_set_iso_terrain_examples/wang_2edge_set_iso_terrain.tsx)

在 Tiled 中新建地图时使用：`Orientation=Isometric`，`Tile Width=N`，`Tile Height=N/2`。示例图用 `N=128` 生成，默认 workflow 是 `N=256`。

### `wang_2edge_corner_set_iso_terrain`

同时生成 isometric Edge Set + Corner Set，共 32 格，适合需要边和角都自动刷的复杂地形。

| 输出 terrain sheet |
| --- |
| ![wang corner iso terrain output](/docs-assets/examples/wang_2edge_corner_set_iso_terrain_examples/wang_2edge_corner_set_iso_terrain.png) |

产物：

- [下载示例 `wang_2edge_corner_set_iso_terrain.tsx`](/docs-assets/examples/wang_2edge_corner_set_iso_terrain_examples/wang_2edge_corner_set_iso_terrain.tsx)

### `wang_2edge_big_iso`

先按边匹配规则拼出一张完整 3×3 平面图，再把整张图整体 iso 化。它是美术 mock-up / 大装饰图，不是逐格 terrain brush。

| 平面 3×3 | 整体 iso 大图 |
| --- | --- |
| ![wang big flat](/docs-assets/examples/wang_2edge_big_iso_examples/wang_2edge_big_flat.png) | ![wang big iso](/docs-assets/examples/wang_2edge_big_iso_examples/wang_2edge_big_iso.png) |

---

## 辅助 / 后处理 workflow

### `brush_variants_remap_tsx`

用途：当你有一套 runtime tileset，又有一套更大的“画刷 variants tileset”时，按 tile 主色生成可在 Tiled 中编辑的 brush `.tsx`，并输出 `.remap.json`。之后导出地图时，配合 `remap_tmj_gids` 把 brush GID 替换回 runtime GID。

这个 workflow 需要两张结构化 tileset，不适合只用 sand/water 单张纹理演示。Web 端使用时在 `source` 与 `brush` 字段旁点 **📎** 上传对应 tileset。

### `remap_tmj_gids`

用途：读取 `.tmj` / `.tmx` 地图和 `.remap.json`，把 brush tileset 的 GID 替换回 runtime tileset 的 GID。它是导出后的后处理步骤，不消费 PNG。

典型链路：

```text
brush_variants_remap_tsx → 在 Tiled 中用 brush tileset 编辑地图 → remap_tmj_gids → 得到运行时地图
```
