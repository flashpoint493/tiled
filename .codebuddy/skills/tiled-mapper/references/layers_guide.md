# Layers Guide

Tiled organizes a map into stacked layers, rendered bottom → top. Three kinds
exist; understanding their differences is essential for clean engine import.

## Layer Kinds

### Tile Layer
- Grid-aligned tiles drawn from a tileset.
- The default workhorse for terrain, walls, ladders, foreground props that align to the grid.
- Brush is constrained to the tile grid; you cannot place tiles at sub-tile offsets.

### Object Layer
- Holds free-positioned **objects**: shapes (rect, ellipse, polygon, point, polyline) and tile-objects (insert tile button).
- Each object has a name, type/class, position, size, rotation, custom properties.
- Engine reads object layers for: spawn points, triggers, pickup spawners, NPC paths, custom collision boxes, named markers (`PlayerStart`, `EndOfLevel`, …).
- Snap behavior: configurable via `View → Snapping`. Hold **Ctrl** to bypass snap temporarily.

### Image Layer
- A single image that fills (or repeats across) the map.
- Cannot be drawn into; it is the entire image.
- Primary use: parallax backgrounds, overlay vignettes, fixed reference images while authoring.

## Recommended Layer Stack (platformer)

Bottom → top:

```
ref           image layer  (optional, reference, opacity 0.5)
far           image layer  (parallaxX=0.2, repeatX=true)
mid           image layer  (parallaxX=0.6, repeatX=true, offsetY≈-96)
back          tile layer   (non-collidable scenery)
main          tile layer   (collidable terrain — has solid tiles)
ground2       tile layer   (mid-elevation platforms, optional)
ground3       tile layer   (high-elevation platforms, optional)
object        object layer (player, enemies, items)
deco1         object layer (animated decorations: grass, sheep, torches)
deco2         object layer (foreground decorations rendered above units)
unit          object layer (towers, NPC spawners)
```

Reasoning for `ground1/2/3` split (Tiny Sword case): when the terrain has stacked
elevations, the higher platform tiles need to *cover* the lower platform's top
edge to look natural. Splitting into multiple tile layers keeps occlusion clean
without manual erasing.

## Parallax

In the layer Properties panel for an image (or tile) layer:

| Property | Meaning |
|---|---|
| Parallax Factor X | 1.0 = scrolls with camera, 0.0 = locked to viewport, 0.2 = slow background |
| Parallax Factor Y | usually 1.0 unless camera moves vertically too |
| Repeat X | tile the image horizontally to cover entire map width |
| Repeat Y | tile the image vertically |
| Offset X / Y | shift image by N pixels (useful to align horizon with the ground row) |
| Opacity | 0.0–1.0, semi-transparent layer (great for reference images) |

### Suggested parallax factors

- Sky / very far background: `0.1`–`0.2`
- Distant mountains / hills: `0.3`–`0.4`
- Mid background (trees, buildings): `0.5`–`0.7`
- Near-camera foreground: `1.0` or slightly larger (`1.1`–`1.3` for overlays)

### Vertical alignment trick

When mid-ground art's "floor line" doesn't match the playable terrain row,
drag the image layer down in the canvas (the **Offset** values update live).
Holding Ctrl while dragging snaps to the tile grid. Typical fine values like
`-96` mean "shift image up by 96 px so its floor aligns with playable floor".

## Placing tiles on an object layer

Even though objects normally hold shapes, the **Insert Tile** tool places a tile
as a tile-object (object whose `gid` references a tileset tile). Useful for:
- Doors, gems, keys (decorative-only, no grid required).
- Decorations from a Collection-of-images tileset that don't match the tile grid.
- Items that an engine treats as individual entities rather than world cells.

Always enable Snap-to-Grid for tile-objects unless you specifically need sub-cell
placement (then hold Ctrl).

## Object naming & class

Engines depend on objects having a meaningful identity:
- **Name**: human label, often the role (`player`, `door_to_level2`).
- **Class** (formerly Type): the prefab/component name. Filling Class auto-instantiates the matching custom-property template (see `custom_properties.md`).

Multi-select objects to set Class on many at once.

## Layer Properties Worth Setting

- **Name** — always rename `Tile Layer 1` to something descriptive.
- **Visible** — toggle the eye icon to hide while authoring.
- **Locked** — lock layers you don't want to accidentally edit.
- **Opacity** — drop to 0.5 to dim a layer while painting on top.
- **Tint Color** — quick palette adjustment for things like night versions.
- **Custom Properties** — engine-specific hints (e.g. `parallax: bool`, `collision: bool`).
