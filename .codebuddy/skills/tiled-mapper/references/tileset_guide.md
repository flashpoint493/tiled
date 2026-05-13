# Tileset Guide

Tiled supports two kinds of tilesets. Choose deliberately — they encode very
different assumptions about the source art.

## 1. Based on a Tileset Image

A single PNG/JPG laid out as a regular grid. Best for terrain sheets where every
tile shares the same width/height (e.g. `tileset.png`, `Desert.png`).

### Required fields
- **Image**: path to the PNG. Tiled stores it relative to the `.tsj` file.
- **Tile Width / Tile Height**: must match the art's true cell size (16/32/64 are most common). Wrong values lead to a beautifully fractal but unusable tileset.
- **Margin**: pixels around the *entire* image before the first tile starts. Often 0 or 1.
- **Spacing**: pixels between adjacent tiles. Often 0, but many art packs use 1 or 2 pixels of separator (commonly black or transparent) to avoid bleeding.

### Diagnostic recipe: "tiles look offset"

If the visible tile boundaries don't align with the artwork's actual cells,
the cause is *always* one of: wrong tile size, wrong margin, wrong spacing.

Procedure:
1. Open the source PNG in any image viewer that shows pixel coordinates.
2. Identify the first real pixel of the first tile (top-left). Distance from `(0,0)` = `margin`.
3. Identify the first pixel of the second tile to the right. Distance from end-of-first-tile to start-of-second-tile = `spacing`.
4. Tile size = pixel size of one cell's actual artwork.
5. In Tiled, enter tileset edit mode → `Tileset → Tileset Properties` → `Image` row → **Edit…**. Punch in the values. Tiles snap into place when correct.

### Editing afterwards

Most fields (tile width, margin, spacing) start as read-only after creation.
Click the **Edit Image** button to unlock. After editing, save with Ctrl+S.

## 2. Collection of Images

A tileset built from multiple independent PNGs. Best for:
- Props with irregular sizes (houses, trees, crates).
- Actors / enemies / items where each sprite is its own file.
- Sprite atlases where each tile-cell holds one frame.

### Adding images
Drag files into the tileset view. Each image becomes a tile. They may be different sizes — Tiled handles this gracefully.

### Image rect (cropping out a single frame from a strip)

If a single source PNG actually contains multiple frames laid horizontally (e.g.
a frog with idle + jump = two frames side-by-side, total 160×41 px for 4 frames),
the imported tile appears as one wide image.

To split it into per-frame tiles, edit the tile's **Image Rect** properties so
the rect covers only one frame:

| Property | Value |
|---|---|
| `image rect x` | 0 |
| `image rect y` | 0 |
| `image rect width` | source_width / frame_count |
| `image rect height` | full frame height |

For the foxy player (32×32 frames in a 128×32 strip): width=32, height=32.

For Sunny Land items (5 frames, 75×15): width=15, height=15.

### Object placement implications

Image-collection tiles do not snap to a grid by default when placed on object
layers. Enable `View → Snapping → Snap to Grid` for clean placement; **Ctrl**
temporarily disables snapping.

## Common Art Packs (notes)

### Sunny Land (Ansimuz)
- Tile size 16×16.
- Main `tileset.png` is a single-image tileset.
- `props/` has individual PNGs → collection of images.
- Player `foxy.png`: 32×32 frames.
- Frog `frog.png`: needs idle + jump merged (use any "image stitch" tool, then `image rect width = 32, height = 32`).
- Item PNGs (cherry, gem): 15×15 frames inside 75×15 strips.

### Tiny Sword (Pixel Frog)
- Tile size 64×64.
- Reference map sized 1600×1216 → map 25 cols × 19 rows.
- Terrain art lacks complete inner-corner pieces → use **Edge Set**, not Corner Set.
- Some cliff art only joins horizontally → make a separate simplified Edge Set with only the relevant left/right transitions.
- Water-meets-cliff art at the bottom has built-in animation frames → set them up via the Tile Animation Editor.

## Saving

Always save as **`.tsj`** (JSON). The legacy `.tsx` (XML) format works but is
gradually being phased out across the ecosystem.

```
project/
  tilesets/
    tileset.tsj       # main terrain
    props.tsj         # buildings, trees, crates (collection)
    actor.tsj         # player + enemies (collection)
    item.tsj          # pickups (collection)
```

## Probability (per-tile random weight)

In tileset edit mode, the Properties panel shows a **Probability** field for the
selected tile. Default `1`. Use small values (`0.01`–`0.05`) for rare props so
that random mode scatters them sparsely while base terrain stays common.

## Custom properties on tiles

Two systems coexist:
- **Inline properties** (free-form key→value) — add via right-click in the Properties pane.
- **Class properties** (templates from Custom Types Editor) — set the tile's **Type/Class**; defined members appear pre-filled.

Use class-based templates for anything that the engine consumes (e.g. `solid:bool`),
so that names and types are guaranteed consistent across the project.

## Collision shapes

Each tile can carry one or more **collision shapes** authored in the Tile
Collision Editor (toolbar button while in tileset edit mode). Shapes are saved
inside the tileset file and ride along with every map placement.

Quick recipes:
- Full-tile collider with `solid` property — no shape needed; engine uses tile bounds.
- Auto-fit sprite collider — Tile Collision Editor → right-click select arrow → **Detect Bounding Box**.
- Smaller-than-sprite player collider — draw a manual rectangle covering torso + feet.
- Slopes / spikes / partial — draw a polygon matching the visible danger or surface.
