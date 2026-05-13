# Custom Properties (Project-Scoped Templates)

Tiled's Custom Types system lets the project define reusable **classes** and
**enums** that any object, tile, or map property can adopt. This eliminates
typos, missing fields, and inconsistent data structures across a project.

## Prerequisite: a Tiled project

Custom Types live in the project file (`.tiled-project`). Without an active
project, the Custom Types Editor is disabled.

To create one: `File → New → New Project…`. Save the `.tiled-project` next to
the `maps/` and `tilesets/` folders.

Tip: pin the project as the workspace by reopening it via `File → Open Project…`.
Closing Tiled with a project open preserves the link.

## Opening the editor

`View → Custom Types Editor` (some versions: `Edit → Preferences → Custom Types`).
A side panel lists existing classes and enums, with **+** buttons to add new ones.

## Defining a class

A class is a named bag of typed properties. Common use cases:
- `actor` — anything with `health`, `tag`, sounds, gravity.
- `enemy` extends `actor` with `damage`, `patrol_speed`.
- `item` — with `value`, `pickup_sound`.
- `trigger` — with `target_map`, `target_x`, `target_y`.

### Steps
1. **+ Add → Class**.
2. Name it (`actor`).
3. Set `Used By` to the surfaces this class can apply to (e.g. *Object*, *Tile*, *Map*, *Tile Layer*, …). Limiting scope prevents accidentally applying `actor` to a Map.
4. **+ Add Member** for each property:
   - **Name**: `health`, `gravity`, `animation`, `sound`, `tag`, …
   - **Type**: pick one — `bool`, `int`, `float`, `string`, `color`, `file`, `object`, an existing class (nested), or an enum.
   - **Default value**: pre-filled when the class is applied.

### Example: `actor` class

| Member | Type | Default |
|---|---|---|
| `animation` | `string` | `"idle"` |
| `gravity` | `float` | `980.0` |
| `health` | `int` | `100` |
| `sound` | class `sound` (nested) | (sub-defaults) |
| `tag` | enum `actor_tag` | `enemy` |

Applying `actor` to an object instantly shows all 5 properties in the
Properties panel, pre-filled with defaults.

## Defining an enum

An enum constrains a property to a fixed list of values. The editor shows a
dropdown instead of a free-text input — typos become impossible.

### Steps
1. **+ Add → Enum**.
2. Name it (`actor_tag`).
3. Add string values (`player`, `enemy`, `item`).
4. Configure storage:
   - `Values As`: `string` (most engines) or `int`.
   - `Values As Flags`: enable when an enum represents bit flags (e.g. damage types).

### Example: `actor_tag`

```
values: [player, enemy, item]
storage: string
```

## Nested classes

A class member can itself be of class type. Use this when a sub-record makes
sense (e.g. an `actor` has a small `sound` record bundling jump/hurt/death
files).

### Example: `sound` class

| Member | Type | Default |
|---|---|---|
| `jump` | `file` | `""` |
| `hurt` | `file` | `""` |
| `death` | `file` | `""` |

Then in `actor`, add member `sound: sound`. The Properties panel collapses the
sound block into a sub-tree.

## Applying a class

### To an object on an object layer
Select the object → Properties panel → **Class** field → pick `actor`. All
class members appear; override what differs.

To set the class for many objects at once: multi-select (Shift / Ctrl click) →
set Class once.

### To a tile in a tileset
Tileset edit mode → select tile → Properties panel → **Class** field.

### To the map itself
Map menu → Map Properties → **Class** field.

## How it's stored

`project.tiled-project` is plain JSON. The relevant section:

```json
{
  "propertyTypes": [
    {
      "id": 1,
      "name": "actor_tag",
      "type": "enum",
      "storageType": "string",
      "values": ["player", "enemy", "item"],
      "valuesAsFlags": false
    },
    {
      "id": 2,
      "name": "sound",
      "type": "class",
      "useAs": ["property"],
      "members": [
        { "name": "jump",  "type": "file", "value": "" },
        { "name": "hurt",  "type": "file", "value": "" },
        { "name": "death", "type": "file", "value": "" }
      ]
    },
    {
      "id": 3,
      "name": "actor",
      "type": "class",
      "useAs": ["object", "tile"],
      "members": [
        { "name": "animation", "type": "string", "value": "idle" },
        { "name": "gravity",   "type": "float",  "value": 980.0 },
        { "name": "health",    "type": "int",    "value": 100 },
        { "name": "sound",     "propertyType": "sound" },
        { "name": "tag",       "propertyType": "actor_tag", "value": "enemy" }
      ]
    }
  ]
}
```

The map and tileset JSON files refer to these by name when they store property
values on actual objects/tiles.

## Cross-engine usage

Most engines that consume Tiled data (Godot, LDtk import shims, custom C++/Rust
parsers) read the same JSON. Standardizing classes at the project level means:
- Engine code can validate that every `player` actor has the expected fields.
- Designers cannot accidentally introduce `Health` vs `health` typos.
- The IDE-like dropdown for enums (`tag`) prevents nonsense values.

## When to refactor properties into a class

If three or more objects share the same property name and type, promote it to a
class member. Future objects will inherit defaults; legacy objects still keep
their values but now display in a consistent layout.
