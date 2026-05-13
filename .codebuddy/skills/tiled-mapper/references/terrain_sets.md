# Terrain Sets: Corner, Edge, Mixed

Terrain sets are Tiled's auto-tiling system. They let the user paint a single
"material" (grass, sand, stone) and have Tiled pick the right edge/corner tile
automatically based on what neighbors are present.

There are three variants. The differences matter — picking the wrong one wastes
hours.

## Conceptual model

Every tile is broken into smaller regions that the terrain system inspects:

| Set | Region model | Inspects |
|---|---|---|
| Corner | 4 corner quadrants per tile | the 4 corners |
| Edge | 4 edges (top/right/bottom/left) per tile | the 4 sides |
| Mixed | Corners + edges (8 regions total) | both sides and corners |

When painting, Tiled looks at the regions of the affected tile *and* the regions
of the neighbors that touch those regions, then picks the tileset tile whose
recorded regions best match.

## Minimum draw unit and step width

| Set | Min draw unit | Step width | What that means |
|---|---|---|---|
| Corner | 4 cells (2×2 area) | 2 cells | Each click affects a 2×2 block; brush advances in 2-cell increments |
| Edge | 2 cells (1×2 line) | 1 cell | Each click affects a 1×2 strip; brush advances 1 cell at a time |
| Mixed | 1 cell | 1 cell | Finest control — single tile at a time |

This explains why Corner sets feel "chunky" while Edge sets feel like drawing
roads.

## Choosing which to use

Inspect the source art:

1. **Are all 16 corner combinations available?** (full inner corner + outer corner + T-junctions + full fill). → Corner Set is the right default.
2. **Only edge tiles + fill?** (top edge, bottom edge, left/right edges, plus fill — no clean corner pieces). → Edge Set. The Tiny Sword pack is the canonical example.
3. **Both, with rich transition variety?** → Mixed Set is richest, but it requires the most complete art.

When uncertain, pick one, paint a test patch on the map, and look for:
- Black/missing tiles → set kind doesn't fit; switch.
- Visible seams between same-material tiles → set kind doesn't fit.
- Result matches the reference image → keep going.

## Why Corner sets can fail on Tiny Sword

Tiny Sword provides only a horizontal strip of grass-on-dirt transitions: no
"inner corner" tile, no "concave corner" tile. A Corner Set wants to pick a tile
whose top-right quadrant is grass and top-left quadrant is dirt, but no such
tile exists in the strip. The painter sees missing pieces.

An Edge Set only asks: "does my top edge join grass to dirt?" The strip has
exactly that, so painting works — even if the result is one cell wide. Wider
fills are obtained by manually painting the *interior* fill with the fill tile.

## Why Edge sets can still paint wide terrain

People often hear "Edge sets paint roads" and assume the result is always one
cell wide. Not quite. The minimum brush is 1×2, but the *interior* of a large
filled area can be drawn with a "fill" tile (a tile whose edges are all the same
material). The terrain brush will pick that interior tile automatically when
all four neighbors are the same material.

So: paint the perimeter with the terrain brush (Edge set fills 1-cell-wide ledges);
then bucket-fill the interior with the plain interior tile (or use the terrain
brush again over the interior — Tiled picks the all-same-material tile).

## Creating a terrain set, step by step

### Step 1 — Enter tileset edit mode
Click the wrench icon next to the tileset. The terrain panel appears.

### Step 2 — Add a new terrain set
At the bottom of the Terrain Sets panel, click the **+** dropdown:
- New Corner Set
- New Edge Set
- New Mixed Set

Name it (e.g. `grass`, `cliff`, `road`).

### Step 3 — Add terrains (materials)
Inside a set, click the **+ Add Terrain** button. For each material:
- Name (`grass`, `dirt`, `stone`).
- Color (visual identifier; appears in the painting tools).
- Optional icon (a chosen tile from the tileset).

A typical grass-vs-dirt set has 2 terrains; a beach scene might have 3 (sand, grass, water).

### Step 4 — Paint terrain into each tile

Select a terrain in the panel. The cursor becomes the terrain brush. Click
inside individual tiles in the tileset (not on the map yet):

- **Corner set**: click a corner quadrant to mark "this corner is grass". Repeat for the 4 corners of each tile.
- **Edge set**: click an edge to mark "this side is grass". Repeat for 4 sides per tile.
- **Mixed set**: edges + corners, both visible in the tile preview.

Mark the **fill tile** by painting all corners (Corner) or all edges (Edge/Mixed) with the same terrain. This is the tile used for interior fill.

### Step 5 — Repeat for every variant tile

If the art provides 3 grass-fill tiles (slight variations), mark all 3 the same
way and assign each a probability (`0.7`, `0.2`, `0.1`) for natural randomization.

### Step 6 — Paint on the map

In the map, select the terrain brush tool, pick the target terrain in the panel,
and paint on a tile layer. Tiled auto-picks the right tile.

## Special cases

### Cliff: horizontal-only Edge Set

When the art only has left/right transitions (no top/bottom corner pieces),
create an Edge Set and only paint the left and right edges with the cliff
terrain. Tiled will refuse to pick a tile if vertical neighbors don't match,
but for a horizontal-only fence/cliff that's exactly what you want.

### Layered platforms: multiple terrain sets

A map with light grass on top, dark grass below, and stone cliffs benefits from
multiple sets — one per material family:
- Set 1: `light_floor` (grass terrains).
- Set 2: `night_floor` (dark variants).
- Set 3: `night_high` (highest elevation, sometimes a separate art family).
- Set 4: `cliff` (horizontal cliff Edge Set).

This keeps terrain brushes from accidentally picking the wrong material when
materials are visually similar.

### Combining with probability

In tileset edit mode, select a tile and set its **Probability** value. The
terrain brush will then randomize across all tiles that satisfy the requested
material pattern, weighted by probability. Combine with multi-tile fill variants
for naturally-varied terrain.

## When *not* to use terrain sets

- Tiny one-off scenes — manual placement is faster.
- Highly bespoke transitions that the art doesn't generalize (e.g. a unique tower base). Place those manually after the terrain pass.
- Object-layer placements (tile-objects don't participate in terrain rules).

## Workflow tip

When painting a real map:
1. Block in the broad shapes with the terrain brush on dedicated layers (`main`, `ground2`, `ground3`).
2. Identify mismatches: orphan islands, water-vs-cliff joints, unusual corners.
3. Switch to the stamp brush and manually replace those cells.
4. Iterate while comparing to the reference image.
