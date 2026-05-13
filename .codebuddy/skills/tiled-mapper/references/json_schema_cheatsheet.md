# JSON Schema Cheatsheet for Engine Integration

Tiled JSON files are the recommended on-disk format. Below are minimal
templates that engines parse. For the exhaustive spec see
`https://doc.mapeditor.org/en/stable/reference/json-map-format/`.

## `.tmj` — Map

```json
{
  "type": "map",
  "version": "1.10",
  "tiledversion": "1.10.2",
  "orientation": "orthogonal",
  "renderorder": "right-down",

  "width": 25,
  "height": 19,
  "tilewidth": 64,
  "tileheight": 64,
  "infinite": false,

  "nextlayerid": 5,
  "nextobjectid": 12,

  "tilesets": [
    { "firstgid": 1,   "source": "../tilesets/tileset.tsj" },
    { "firstgid": 256, "source": "../tilesets/props.tsj" }
  ],

  "layers": [
    {
      "id": 1, "name": "main", "type": "tilelayer",
      "x": 0, "y": 0, "width": 25, "height": 19,
      "opacity": 1, "visible": true,
      "data": [ /* width*height ints (gid; 0 = empty) */ ]
    },
    {
      "id": 2, "name": "object", "type": "objectgroup",
      "x": 0, "y": 0, "opacity": 1, "visible": true,
      "objects": [
        {
          "id": 1, "name": "player",
          "type": "actor",
          "x": 32, "y": 480,
          "width": 32, "height": 32,
          "gid": 257,
          "properties": [
            { "name": "tag", "type": "string", "propertytype": "actor_tag", "value": "player" }
          ]
        }
      ]
    },
    {
      "id": 3, "name": "far", "type": "imagelayer",
      "image": "../assets/bg/far.png",
      "parallaxx": 0.2, "repeatx": true,
      "offsetx": 0, "offsety": 0,
      "opacity": 1, "visible": true
    }
  ],

  "properties": []
}
```

Key fields:
- `tilesets[*].firstgid` — global ID where this tileset's tiles begin in `data` arrays. A tile-layer cell with value `260` belongs to the tileset whose firstgid ≤ 260 (offset = 260 − firstgid).
- `data` for `tilelayer` — flat array of length `width × height`. `0` means empty cell.
- `gid` for tile-objects — same global-ID scheme.
- High bits in gid encode flip flags: `0x80000000` h-flip, `0x40000000` v-flip, `0x20000000` diagonal-flip.

## `.tsj` — Tileset (single image)

```json
{
  "type": "tileset",
  "version": "1.10",
  "name": "tileset",
  "image": "../assets/tileset.png",
  "imagewidth": 512, "imageheight": 512,
  "tilewidth": 64, "tileheight": 64,
  "margin": 0, "spacing": 0,
  "columns": 8,
  "tilecount": 64,

  "tiles": [
    {
      "id": 5,
      "probability": 0.05,
      "properties": [
        { "name": "solid", "type": "bool", "value": true }
      ],
      "objectgroup": {
        "draworder": "index",
        "objects": [
          { "id": 1, "x": 0, "y": 32, "width": 64, "height": 32 }
        ]
      },
      "animation": [
        { "tileid": 5, "duration": 200 },
        { "tileid": 6, "duration": 200 },
        { "tileid": 7, "duration": 200 }
      ]
    }
  ]
}
```

Per-tile features encoded as objects inside `tiles[]`:
- `properties` — inline / class-driven properties.
- `objectgroup` — collision shapes (Tile Collision Editor output).
- `animation` — frame list with durations in ms.

## `.tsj` — Collection of images

Differs from the single-image variant: no top-level `image` / `columns` /
`tilewidth`/`tileheight` constraints. Each tile has its own image.

```json
{
  "type": "tileset",
  "name": "actor",
  "tilewidth": 32, "tileheight": 32,
  "tilecount": 4,
  "tiles": [
    {
      "id": 0,
      "image": "../assets/actor/player.png",
      "imagewidth": 128, "imageheight": 32,
      "x": 0, "y": 0, "width": 32, "height": 32
    }
  ]
}
```

`width` / `height` on a tile crop the source image (the "image rect").

## `.tiled-project` — Project

```json
{
  "automappingRulesFile": "",
  "commands": [],
  "extensionsPath": "extensions",
  "folders": ["."],

  "propertyTypes": [
    {
      "id": 1, "name": "actor_tag", "type": "enum",
      "storageType": "string",
      "values": ["player", "enemy", "item"],
      "valuesAsFlags": false
    },
    {
      "id": 2, "name": "actor", "type": "class",
      "useAs": ["object", "tile"],
      "members": [
        { "name": "health", "type": "int", "value": 100 },
        { "name": "tag", "propertyType": "actor_tag", "value": "enemy" }
      ]
    }
  ]
}
```

## `.world` — World container

```json
{
  "type": "world",
  "maps": [
    { "fileName": "maps/level_0_0.tmj", "x": 0,   "y": 0, "width": 640, "height": 360 }
  ],
  "patterns": [
    {
      "regexp": "maps/level_(?P<x>\\d+)_(?P<y>\\d+)\\.tmj",
      "multiplierX": 640,
      "multiplierY": 360,
      "offsetX": 0, "offsetY": 0
    }
  ]
}
```

## Engine parsing checklist

When integrating a new engine importer:

1. Parse the map; resolve every `tilesets[*].source` to load the referenced `.tsj`.
2. Build a tile lookup keyed by global ID.
3. For each `tilelayer`, iterate `data` and instantiate tiles at `(x*tilewidth, y*tileheight)`, applying flip flags from the high gid bits.
4. For each `objectgroup`, instantiate objects; use `type`/`class` to route to the right prefab; consume `properties` for parameters.
5. For each `imagelayer`, set up parallax and repeat per `parallaxx`/`parallaxy`/`repeatx`/`repeaty`.
6. Per-tile data (collisions, properties, animations) read from the tileset's `tiles[]` array — keyed by local `id` (gid − firstgid).
7. If a `.world` file is present, load its `maps` list (and resolve `patterns` regex) to know how to chain map loads at run time.
