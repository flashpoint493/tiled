# Tiled 实战工作流 Cookbook

6 个典型任务的完整步骤。每个工作流都对应教程里的实战内容，可直接照抄给用户。默认用户已经装了 Tiled（≥ 1.10）。

## 工作流 1：从零建一个新项目

**场景**：用户刚拿到素材，要开始画第一张地图。

```
1. 组织目录（任意项目根下）
   project/
   ├── project.tiled-project   ← 马上要建
   ├── maps/                   ← 所有 .tmj 放这
   ├── tilesets/               ← 所有 .tsj / .tsx 放这
   └── assets/
       ├── tilesets/           ← sheet PNG
       ├── sprites/            ← 散装 PNG（对象、角色）
       └── backgrounds/        ← image layer 用的大图

2. File → New → New Project...
   命名 project.tiled-project 存到项目根
   → 此后 View → Custom Types Editor 才能点开

3. View → Custom Types Editor
   先建 Enum ActorTag: player / enemy / item
   再建 Class Actor: health:int, gravity:float, tag:ActorTag, ...
   （具体字段参考 custom_properties.md）

4. File → New → New Map...
   - Orientation: Orthogonal（或 Isometric，按项目类型）
   - Tile Size: 按素材（16x16 / 32x32 / 64x64）
   - Map Size: 先随便填，后面可以改
   - Tile Layer Format: CSV（最通用）
   - 格式 → 务必 JSON（.tmj）
   另存到 maps/level1.tmj

5. 把 maps/ 与 tilesets/ 的相对关系确认好，之后引用 tileset 才不会失联。
```

## 工作流 2：导入一个 sheet 类 tileset（有动画）

**场景**：素材是一张 sheet PNG，里面既有静态地形又有海浪/水面动画。

```
1. Tileset 面板 → New Tileset...
   - Type: Based on Tileset Image
   - Name: terrain_main
   - Image: assets/tilesets/terrain_main.png
   - Tile Width / Height: 按素材（常见 16 / 32 / 64）
   - Margin / Spacing: 先都填 0，预览不对齐再调
   - Embed in map: 否（保存为独立 .tsj 到 tilesets/）

2. 预览发现错位？
   Tileset → Tileset Properties → Edit Tileset Image
   调 Margin（整张图外边像素数）/ Spacing（tile 之间像素缝）
   常见：margin=1 spacing=1、或 margin=16 spacing=2（动画素材）

3. 设置动画（举例：海浪 tile 有 4 帧）
   a. 先点中 tile set 面板里的目标 tile（比如第 0 号）
   b. View → Tile Animation Editor
   c. 双击第 1 帧 tile（作为第 1 帧自动加入）
   d. 再双击第 2 帧... 直到全加完
   e. 每帧 Duration 默认 100ms；海浪类改 200-300ms 更自然
   f. 必点 Apply
   g. 下一个动画 tile：不要关 Editor！直接在 tileset 面板选新 tile，
      重复 c-f（效率翻倍）

4. Ctrl+S 保存 tileset。
```

## 工作流 3：画一张"带参考图的分层地图"（2D 平台跳跃）

**场景**：用户有 `preview.png` 作为最终效果参考，要在 Tiled 里复刻。出处：`Tiled入门实战`。

```
1. 计算地图尺寸
   如果 preview.png 是 1456x464，tile 是 16x16
   → 地图宽 91，高 29（都除以 16）
   Map → Resize Map...

2. 放参考图到底层做对照
   New Image Layer → 命名 ref
   - Image: preview.png
   - Opacity: 0.5（半透明，方便看到上面画的 tile）

3. 建远景 / 中景（image layer）
   New Image Layer → far
   - Image: 远景 PNG
   - Horizontal Repeat: ✓
   - Parallax Factor: X=0.2, Y=1.0
   New Image Layer → mid
   - Image: 中景 PNG
   - Offset Y: -96（如果需要贴底）
   - Horizontal Repeat: ✓
   - Parallax Factor: X=0.6, Y=1.0

4. 建主图块层 main + 背景图块层 back（都是 Tile Layer）
   - back 放黑色填充、背景装饰（没有碰撞）
   - main 放地面、平台、墙（带碰撞）

   小技巧：沙漠/山洞的大面积背景 → 用 Bucket Fill 前先用 Stamp Brush
   把要填充的区域边界封闭（避免填出去）。

5. 为 main 的所有可碰撞 tile 加 solid 属性
   扳手进入 tileset 编辑模式 → Ctrl 多选所有地面 tile →
   右键 Add Property → name=solid, type=bool, value=true

6. 建对象层 object（Object Layer）
   - 放玩家、敌人、物品（用 Collection 类 tileset 的 sprite）
   - 每个对象 Object Properties: name="player" / "goblin" / "diamond"
   - 可配合 Custom Types Editor 里的 Actor 类填 health 等字段

7. 为角色 sprite 画碰撞盒（可选）
   tileset 编辑模式 → 选 player tile → View → Tile Collision Editor
   玩家用手画（要比视觉小一圈），敌人 / 物品可 Detect Bounding Box 自动

8. Ctrl+S 保存 map。
```

## 工作流 4：用地形集画大面积地面

**场景**：画一片草地 + 悬崖 + 海洋，涉及边界过渡。

```
1. 判断地形集类型（参考 terrain_sets.md "Choosing which to use"）
   - 素材有完整的外角 + 内角 + 边 → Mixed
   - 只有边变体 → Edge（最常见，Tiny Sword / Kenney 多属此列）
   - 只有角变体（稀少）→ Corner

2. 建地形集
   扳手进 tileset 编辑模式 → 右下面板 Terrain Sets → New Terrain Set
   选好 Corner / Edge / Mixed → 命名（如 forest_grass）

3. 添加 Terrain
   "+"加地形，命名 grass，指定图标 tile，分配颜色

4. 标记 tile
   选中 grass Terrain 进入标记模式
   - Edge：点击 tile 的边（上下左右）标为 grass
   - Corner：点击 tile 的角（四个角）标为 grass
   - 所有"属于 grass"的边/角都要标；留白=背景

5. 为不同地形重复 3-4
   比如再加 cliff_high、cliff_low、water

6. 使用地形刷 T
   在地图层选中地形 → 在地图上刷
   → 自动选合适的 tile
   → 小范围用 Stamp Brush B 手工修正特殊边角

7. 概率变体增强自然感
   tileset 编辑模式 → 选装饰 tile → Probability=0.05
   回到地图用地形刷 + 工具栏的骰子（Random Mode）
```

## 工作流 5：把 9 张方向 tile 做成 Tiled 能用的 auto-tile

**场景**：用户有一张"3x3 循环 tile"大图（中央可平铺 + 8 个边界 tile）。这是 auto-tile 最常见的素材组织方式。

### 5.1 AI 自动完成路径（推荐）

```
用 scripts/tiled_tools 的 workflow，一条命令产出 sheet + tsx

1. cd scripts && python -m tiled_tools serve --port 8765
2. 浏览器打开 http://localhost:8765/
3. 顶栏下拉选 "3x3_split_then_iso_sheet" 或 "3x3_split_then_iso"
   （前者还会做 iso 化，后者只拆+拼）
4. 上传源图 → ▶ 运行
5. 右下产物面板下载两个文件：
   - grass_iso.png（sheet）
   - grass_iso.tsx（Tiled 可直接打开）
6. 在 Tiled 里 File → Open → 选 tsx → 进入 tileset 编辑模式

细节见 references/scripts-toolkit.md
```

### 5.2 在 Tiled 里配 Edge 地形集

拿到 sheet 后，9 个 tile 的命名是 NW / N / NE / W / C / E / SW / S / SE
（`build_tsx_sheet` 自动把名字写成 tile 的 `name` 属性）：

```
   NW  N  NE
   W   C   E
   SW  S  SE

C 是"全方向都是草"的那块（中央可平铺的 base）
其他 8 块是"某些方向开口"的边界变体

配 Edge 集时：
- grass Terrain 分配到所有 9 块
- C：四条边全部标为 grass（中心满）
- N：只有"下边"标为 grass（北墙边缘，向下延伸草地）
- S：只有"上边"标为 grass
- W：只有"右边"标为 grass
- E：只有"左边"标为 grass
- NW：右边 + 下边 标为 grass（西北外角）
- NE：左边 + 下边
- SW：右边 + 上边
- SE：左边 + 上边

这样地形刷一刷就自动拼出无缝大草地。
```

## 工作流 6：用 World 拼开放世界

**场景**：游戏有 10+ 张小地图，想在编辑时看到相邻地图的衔接。

```
1. 确保每张地图尺寸一致（或至少宽/高规范）
   比如每张 40x23 tiles, 16px 一格 → 640x368 像素

2. View → Show World（勾选）

3. World → New World...
   保存为 maps/world.world

4. 打开 map1.tmj（已在编辑器里）
   World → Add Current Map to World
   默认位置 (0, 0)

5. World → Add Another Map to World...
   选 map2.tmj
   → 在主视图里直接拖到 map1 右边
   Tiled 会自动吸附到相邻位置（需要启用 Snapping）

6. 在编辑单张地图时，World 视图下相邻地图会淡显
   → 修改边界 tile 时可以看到对面，衔接不出错

7. 批量摆放（> 100 张）
   手动打开 .world JSON，用 patterns 字段按命名规则自动布局：
   {
     "maps": [],
     "patterns": [
       {
         "regexp": "map_(\\d+)_(\\d+)\\.tmj",
         "multiplierX": 640,
         "multiplierY": 368,
         "offsetX": 0,
         "offsetY": 0
       }
     ]
   }
   → 文件名 map_3_2.tmj 自动放在 (3*640, 2*368)=(1920, 736)
```

## 通用建议

- **每次保存前先 Ctrl+S 再截图**——Tiled 崩溃虽少见但存在。
- **导出到游戏时**：`File → Export As...` 可以把 .tmj 再导出为别的格式（比如 `.lua` 给 LÖVE、`.json` 拍平给某些引擎）。大多数现代引擎直接读 `.tmj`，不用额外导出。
- **多人协作**：`.tmj` 是 JSON 文本，git 友好。但注意 `.tiled-project` 里的 class/enum 定义会改变整个项目行为，改动时在 PR 里明确说明。
- **性能**：单张 tile 层 > 200x200 开始明显卡，拆成 World 里多张小图。对象层对象数 > 1000 也会卡，用批量工具 / 拆层。
