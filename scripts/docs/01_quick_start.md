# 快速开始

> 30 秒上手 tiled_tools web 端。

## 三栏布局

```
顶栏：[workflow ▼] [存] [删]  |  [上传] [▶ 运行] [💾 导出] [📂 导入] [清空] [📖 帮助]
─────────────────────────────────────────────────────────────────
左：Action 库     │  中：Pipeline 编辑器       │  右：预览 + 日志
                  │                              │
  load            │  1. load                     │  原图预览
  rotate          │     path = up_xxx.png        │  ──────
  scale           │                              │  产物预览
  topdown_to_iso  │  2. topdown_to_iso           │  （多张时网格）
  split_3x3       │     anchor = bottom-center   │  ──────
  ...             │     y_scale = 0.5            │  执行日志
                  │                              │
                  │  3. save                     │
                  │     path = auto              │
```

## 基本流程

1. 点 **「上传图片」** 选一张本地贴图，自动填到 `load.path`。
2. 顶栏 **workflow 下拉** 选一个内置模板（推荐第一次用这个），或左侧点 action 自己拼。
3. 改改参数（每个步骤可展开），按 **▶ 运行** 或 `Ctrl+Enter`。
4. 右下产物面板会显示输出，多张时点任一张可下载。
5. 觉得参数好用？点 **「★ 存为 workflow」** 给它取名保存，下次直接下拉里选。

## 多个输入图怎么上传？

有些 workflow（比如 `wang_2edge_set`）需要两张以上的输入图——一张 foreground（沙）
一张 background（水）。顶栏的「上传图片」只能填 `load.path` 一个字段，所以多图
用法是：

> **每个需要图片路径的字段旁边都有一个 📎 按钮，点它上传即可**。

例如 `wang_2edge_set`：
- `mask_blend_set.foreground` 旁边 📎 → 传 `sand.png`
- `mask_blend_set.background` 旁边 📎 → 传 `water.png`
- 之后 ▶ 运行

📎 按钮上传后会直接把 `file_id` 填进文本框，你能看到类似 `up_0e6b1be62ab6.png`
的值。手工粘贴 file_id 或绝对路径也都能工作。

## 一次导入多张图组成 tilesheet

顶栏点 **「批量导入」**，一次选择多张图片。工具会自动：

```text
上传到 batch_xxxx/ → load_dir → pack_sheet → build_tsx_sheet → 运行
```

右侧产物会同时出现 sheet PNG 和 `.tsx`。两个文件放同目录，Tiled 可直接打开 `.tsx`。

## 内置 workflow 选哪个？


| 想做什么？ | 选这个 |
| --- | --- |
| 把 topdown 贴图变成 iso 45° 视角 | `topdown_to_iso` |
| 把 iso 资产反推回 topdown | `iso_to_topdown` |
| 拿到一张 3×3 循环 tile，想拆成 9 张方位 tile | `3x3_split_then_iso` |
| 同上 + 自动拼成 Tiled tileset (.tsx) | `3x3_split_then_iso_sheet` |
| 验证我的循环 tile 是不是真的无缝 | `tile_repeat_3x3` |
| 多张独立图片组成一张 Tiled tilesheet | 顶栏「批量导入」或 `batch_images_to_tilesheet` |
| **沙↔水 之类的过渡素材（wang 2-edge）** | `wang_2edge_set` |
| Isometric 地图里要用 Terrain Brush 刷沙↔水 | `wang_2edge_set_iso_terrain` |



## 占位符 `${var}` / `${var:default}`

YAML workflow 里看到 `${input}` / `${output:auto}` 这些，意思是：
- `${input}` —— 必填的输入，web 端会被自动填成你上传的 file_id。
- `${output:auto}` —— 可选，默认值 `auto` 让 server 自动分配产物文件名。
- `${name:wang_2edge}` —— 给个默认显示名，不填也能跑。

加载 workflow 时前端会把这些 `${...}` 自动展开成合适的实际值，**你看到的总是
可直接运行的具体值，而不是天书**。

## 快捷键

| 键 | 作用 |
| --- | --- |
| `Ctrl + Enter` | 运行当前 pipeline |
| `Ctrl + S` | 存为 workflow（弹窗） |
| `Esc` | 关闭帮助弹层 |

## 出问题怎么排查？

1. **运行报错** → 看右下日志，每步 `[name] params={...}` 会清楚显示。
2. **改了代码不生效** → server 不会自动重载。`Ctrl+C` 重启，或起服务时加 `--reload`。
3. **浏览器看到旧 UI** → `Ctrl+F5` 硬刷。
