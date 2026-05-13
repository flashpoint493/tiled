# Worlds (Multi-Map Containers)

A `.world` file glues many independent maps into a single, browseable world.
It is **not** a new map format — just a small JSON list of (map path, x, y,
width, height) records that Tiled uses to render neighbors next to the
currently-edited map.

## When to use

- Open-world or sprawling Metroidvania designs split into chunks.
- Scrolling RPG with seamless cross-room visuals.
- Any time the playable area exceeds what a single Tiled map can comfortably
  hold (or what your engine can stream in one shot).
- When edges of adjacent maps must match — seeing both maps side-by-side while
  editing eliminates seam errors.

If the game only has 1–3 independent levels with no shared edges, skip worlds —
they add overhead without benefit.

## Creating a world

1. `View → Show World` (toggle on).
2. `World → New World…`. Save as `name.world` near the `maps/` folder.
3. Open one of the maps; `World → Add Current Map to World`.
4. Drag-position the map in the world view, or set explicit coordinates in the
   World Properties panel.
5. Repeat for each additional map.
6. Save with `Ctrl+S` on the world file (the world has its own dirty marker).

## World tool

The **World tool** in the toolbar (a small grid icon) operates on the world
view rather than a single map. Active tool features:
- Drag maps to reposition.
- Add maps from the file browser.
- Snap-to-grid based on the world's own grid size.

## File schema (`.world` JSON)

```json
{
  "maps": [
    { "fileName": "maps/level_0_0.tmj", "x": 0,    "y": 0,    "width": 640, "height": 360 },
    { "fileName": "maps/level_1_0.tmj", "x": 640,  "y": 0,    "width": 640, "height": 360 },
    { "fileName": "maps/level_0_1.tmj", "x": 0,    "y": 360,  "width": 640, "height": 360 }
  ],
  "type": "world",
  "onlyShowAdjacentMaps": false
}
```

- `fileName` — path to the `.tmj`/`.tmx`, relative to the `.world` file.
- `x`, `y` — top-left position of the map in world coordinates (pixels).
- `width`, `height` — map dimensions (pixels). Should match the map's actual size.
- `onlyShowAdjacentMaps` — when true, only render neighbors of the open map.

The engine can read this JSON directly to know which map to load when the player
crosses a world boundary at world-space `(px, py)`.

## Pattern Match (auto-place hundreds of maps)

For very large projects (e.g. `map_03_07.tmj`, `map_03_08.tmj`, …) Tiled
supports **Pattern Match** in the World Properties:

- **Map name pattern**: a regex with named groups `x` and `y`, e.g.
  `map_(?P<x>\d+)_(?P<y>\d+)\.tmj`.
- **Multiplier**: the world-space pixel size of one grid step (e.g. `640` if
  every map is 640 px wide and y-step is the same).
- **Offset**: optional shift to align with a non-zero origin.

Tiled scans the project folder, matches files, and positions them
automatically. Files added or renamed later are picked up the next time the
world refreshes.

### Example

```json
{
  "patterns": [
    {
      "regexp": "maps/level_(?P<x>\\d+)_(?P<y>\\d+)\\.tmj",
      "multiplierX": 640,
      "multiplierY": 360,
      "offsetX": 0,
      "offsetY": 0
    }
  ],
  "type": "world"
}
```

This is ideal for procedurally-organized worlds. Manual `maps` entries and
patterns can coexist in the same file.

## Editing across maps

With the world open, dragging the camera across a map boundary scrolls into the
neighbor. The neighbor renders read-only (greyed slightly), but switching focus
to it (click the neighbor's title) makes it editable. Painting near a border
can now use the *visible* tiles of the neighbor as alignment reference.

## Caveats

- The world doesn't merge maps; each map remains a separate file. Tilesets are
  not deduplicated across maps automatically.
- Object IDs are local per map. The engine that reads multiple maps must scope
  IDs by map filename.
- World coordinates use pixels, not tiles. When maps differ in tile size, plan
  the world layout carefully.

## Quick recipe

```text
project/
  world.world
  maps/
    level_0_0.tmj   (640×360)
    level_1_0.tmj   (640×360)
    level_2_0.tmj   (640×360)
```

`world.world` content:

```json
{
  "type": "world",
  "maps": [
    { "fileName": "maps/level_0_0.tmj", "x": 0,    "y": 0, "width": 640, "height": 360 },
    { "fileName": "maps/level_1_0.tmj", "x": 640,  "y": 0, "width": 640, "height": 360 },
    { "fileName": "maps/level_2_0.tmj", "x": 1280, "y": 0, "width": 640, "height": 360 }
  ]
}
```

Open `world.world` in Tiled with `View → Show World` enabled, then edit any of
the three maps with the others visible as neighbors.
