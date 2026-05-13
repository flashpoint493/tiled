---
name: tiled-mapper
description: Tiled 2D 地图编辑器的端到端工作流指南，覆盖 tilesets / layers / terrain sets (corner·edge·mixed) / 动画 / 自定义属性 / World 多地图拼接 / JSON 格式规范，并在合适场景调用本仓库 `scripts/tiled_tools` 自动化处理素材（topdown→iso、3x3 循环 tile 拆分、合成 sprite sheet + `.tsx`）。当用户讨论 Tiled 地图编辑、`.tmj` / `.tsj` / `.tmx` / `.tsx` / `.tiled-project` / `.world` 文件、想用 Tiled 做 2D 关卡、问"tileset / terrain set / auto-tile / wang tile / 自动图块 / 循环 tile / 图块集 / 地形集"、想把素材转成 Tiled 能识别的格式、或在本仓库 `scripts/` 工具链下处理 Tiled 素材时使用此 skill。
---

# Tiled Mapper

## Overview

This skill bundles two things in one place:

1. **Domain knowledge** for the Tiled 2D map editor — concepts, decision criteria, and step-by-step procedures distilled from the project's tutorial notes (`docs/tutorial/`) and official plugin docs (`tiled_integration_plugin_docs/`).
2. **A bridge to the in-repo automation** under `scripts/tiled_tools/` — a pipeline framework with a web UI that turns common asset-prep tasks (topdown→iso, 3x3 auto-tile splitting, sprite sheet + `.tsx` generation) into one-click workflows.

Use the editor knowledge when the user is **editing a map by hand**; use the scripts when the user is **preparing assets before opening Tiled**.

## When to Trigger

Trigger this skill when the user mentions any of:

- Tiled editor / `.tmj` / `.tsj` / `.tmx` / `.tsx` / `.tiled-project` / `.world`
- Tileset, tile layer, object layer, image layer
- Terrain set / corner set / edge set / mixed set / auto-tile / wang tile / 自动图块 / 循环 tile
- Animated tile / 帧动画 / 帧时长
- Custom properties / 自定义属性 / class / enum
- World / 多地图拼接 / 开放世界
- "Topdown to iso", iso/dimetric/45°
- "Sprite sheet for Tiled", "make this image Tiled-friendly"

## Decision Tree

Decide which leg to pursue **before** opening a reference file:

```
User goal
├── Edit a map / understand a Tiled feature
│   → Pick the domain-specific reference file (see "Reference Files" below)
│
├── Prepare assets BEFORE Tiled
│   (topdown→iso, split 3x3, build sheet+tsx, batch images)
│   → references/scripts-toolkit.md   (pick a pipeline + run it)
│
├── Integrate Tiled output into an engine
│   → references/json_schema_cheatsheet.md (parse .tmj/.tsj/.world)
│
└── A mix of the above
    → start with scripts-toolkit.md for asset prep
    → then the relevant editor reference
    → finally json_schema_cheatsheet.md for engine import
```

When the choice is unclear, ask one targeted question — for example: "Is the source already in Tiled-friendly shape, or do we need to convert / cut images first?"

## How to Use This Skill

Follow this rhythm for any Tiled-related request:

1. **Classify the request** using the decision tree above. State the chosen branch in one sentence to the user.
2. **Load the relevant reference file(s)** with `read_file`. Reference files are kept lean (each < 6k words) so reading a full file is fine; do **not** pre-load everything.
3. **For asset-prep tasks, prefer the in-repo pipeline over manual steps.** `references/scripts-toolkit.md` maps each common task to a ready-made YAML workflow or action chain. Running the web UI (`python -m tiled_tools serve --port 8765`) is usually the fastest path.
4. **For editor tasks, give concrete UI paths.** Tiled's menus are stable; cite exact menu items (e.g., "View → Tile Animation Editor", "Map → Map Properties") rather than vague descriptions. The reference files contain these verbatim.
5. **For terrain confusion (corner vs. edge vs. mixed),** always consult `references/terrain_sets.md` before recommending — picking the wrong terrain type is the single most common Tiled mistake and the tutorial set explicitly warns about it.
6. **For engine integration**, read `references/json_schema_cheatsheet.md` — it has concrete JSON shapes for `.tmj`, `.tsj`, `.tiled-project`, `.world`, plus a parser checklist.

## Key Project Conventions

These conventions come from `docs/tutorial/` (especially the 入门实战 and 初级实战 series). Keep new artifacts consistent:

- **File format**: prefer JSON (`.tmj` / `.tsj` / `.tiled-project`) over the legacy XML (`.tmx` / `.tsx`). Modern engines parse JSON more easily. Note: the `scripts/tiled_tools` `build_tsx_sheet` action currently emits XML `.tsx`; if the user needs JSON, open the produced `.tsx` in Tiled and `File → Save As…` a `.tsj`.
- **Folder layout**:

  ```
  project/
  ├── project.tiled-project
  ├── maps/              (.tmj)
  ├── tilesets/          (.tsj)
  └── assets/            (PNGs referenced from tilesets)
      ├── tilesets/
      ├── sprites/
      └── backgrounds/
  ```

  Always create a Tiled **project** at the workspace root so custom properties can be reused across maps.
- **Layer names in English**: layer names eventually become string keys in engine code. Avoid Chinese identifiers. A typical platformer stack top-to-bottom: `object` / `main` / `back` / `mid` / `far` / `ref` — see `references/layers_guide.md` for the full pattern.
- **Collision marking**: use a custom property `solid: bool = true` on collidable tiles (both tileset styles support this), or draw collision shapes in the **Tile Collision Editor**. Either is parseable; pick one and be consistent.
- **Object-layer entities** (player, enemies, pickups) should each get a `name` (e.g. `player`, `goblin`, `diamond`) and a `class` pointing at a Custom Types template like `actor` — see `references/custom_properties.md`.

## Reference Files

All reference files sit under `references/`. Load them on demand; do not pre-load.

| File | When to load |
| --- | --- |
| `tileset_guide.md` | Creating / debugging a tileset — "sheet" vs. "collection", margin/spacing diagnostics, image-rect cropping, per-tile probability and collision. |
| `layers_guide.md` | Layer types (tile / object / image), platformer layer stack, parallax factors, offsets, image-rect tile placement on object layers. |
| `terrain_sets.md` | **Read this first** whenever the user mentions terrain, auto-tile, wang tile, corner / edge / mixed sets, or asks why their terrain brush looks wrong. Contains the art-driven decision procedure. |
| `custom_properties.md` | Tiled projects, class/enum/nested-class definition, where classes can be applied, and the `.tiled-project` JSON shape. |
| `worlds.md` | `.world` files, world tool, Pattern Match auto-placement, caveats. |
| `json_schema_cheatsheet.md` | Engine-side integration — concrete JSON for `.tmj` / `.tsj` / `.tiled-project` / `.world`, global-ID / firstgid / flip-flag math, parser checklist. |
| `workflows.md` | Step-by-step cookbooks for real tasks: new project setup, tileset + animation import, multi-layer scene authoring, terrain set painting, 3x3 auto-tile, World assembly. Cross-references the other files as it goes. |
| `scripts-toolkit.md` | The user has raw images and needs to convert them before Tiled — topdown→iso, 3x3 split, batch processing, sheet packing, `.tsx` generation. Documents the web UI at `http://localhost:8765/` and the three built-in workflows. |

## Bundled Scripts & Assets

### `scripts/` — validation & sizing helpers

Standalone Python 3.8+ utilities (stdlib only; `Pillow` optional for non-PNG images). Use them to cut down on manual math and catch common mistakes early.

| Script | Purpose |
| --- | --- |
| `calc_map_size.py <image> <tile_size> [--tile-height N]` | Compute `Width` × `Height` (in tiles) for the New Map dialog from a reference image. Warns when the image doesn't divide evenly. |
| `validate_map.py <map.tmj>` | Sanity-check a saved JSON map: verify each `tilesets[*].source` resolves, every non-zero gid falls inside a referenced tileset, objects have names + class, and flag layer/object/property names that contain CJK characters (which break many engines). Exit codes: `0` clean, `1` errors, `2` warnings only. |
| `tileset_audit.py <tileset.tsj>` | Inspect a `.tsj` — geometry, animations, collision shapes, probabilities, per-tile custom properties, terrain sets. Warns when `columns × tilewidth + spacings + margins` disagrees with `imagewidth` (the single most common margin/spacing bug). |

These are distinct from the heavier-weight `scripts/tiled_tools/` pipeline framework in the repo root (see `references/scripts-toolkit.md` for that). Think of the bundled scripts here as read-only linters; use the repo-level toolkit for actual image transformation.

### `assets/` — reusable starter files

Copy these into the user's project when bootstrapping:

| Asset | Purpose |
| --- | --- |
| `project_template.tiled-project` | Ready-to-use Tiled project with `actor` / `item` / `trigger` / `sound` classes and an `actor_tag` enum (`player` / `enemy` / `item`) pre-defined. Rename to match the game. |
| `world_template.world` | Minimal 3-map `.world` JSON, edit the `maps[]` entries to taste. |
| `README.md` | Recommended on-disk project layout (maps/ / tilesets/ / assets/ separation). |

## Anti-Patterns

Avoid these — each is a real pitfall mentioned in the tutorial set:

- **Setting tile animations on the wrong tile.** Always click the target tile in the tileset panel *first*, then open `View → Tile Animation Editor`. Otherwise frames bind to whatever was previously selected.
- **Importing a tileset with wrong margin / spacing.** When tiles look offset, open the tileset's image properties and set `margin` / `spacing` to match the source PNG's grid (commonly `0,0`, `1,1`, or `2,2`). See `tileset_guide.md` for the diagnostic procedure.
- **Using a corner terrain set on assets that only provide edge variants.** Symptom: large flat areas paint fine but corners glitch / leave black holes. Switch to an edge set (or mixed, if the asset has both corner *and* edge tiles). Tiny Sword is the canonical edge-only case.
- **Hand-cutting 3x3 auto-tile assets.** When the user has "a single image with a 3x3 grid for auto-tile", do NOT cut by hand — use `scripts/tiled_tools`'s `split_3x3` action followed by `pack_sheet` + `build_tsx_sheet`. See `scripts-toolkit.md`.
- **Saving custom properties without creating a Tiled project first.** The Custom Types Editor only enables once a `.tiled-project` exists. Create the project first via `File → New → New Project…`.
- **Naming layers in Chinese / non-ASCII.** Layer names become string keys in the shipped map file; engine code breaks on mojibake. Stick to English identifiers.
