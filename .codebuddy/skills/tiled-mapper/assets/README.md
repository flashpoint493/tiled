# Project Layout Template

Use this as the on-disk skeleton when starting a new Tiled project. Adapt
folder names to taste, but keep the separation between maps, tilesets, and
raw art — this is what most engines (and tutorials) assume.

```
my_game/
├── project.tiled-project        # copy assets/project_template.tiled-project here
├── world.world                  # optional, only if using multi-map worlds
├── maps/
│   ├── level1.tmj
│   ├── level2.tmj
│   └── ...
├── tilesets/
│   ├── tileset.tsj              # main terrain (single-image)
│   ├── props.tsj                # buildings, trees (collection of images)
│   ├── actor.tsj                # player + enemies (collection)
│   └── item.tsj                 # pickups (collection)
└── assets/
    ├── bg/
    │   ├── far.png              # parallax distant
    │   └── mid.png              # parallax mid
    ├── tileset.png              # source for the main tileset
    ├── props/                   # individual prop PNGs
    ├── actor/                   # individual character sheets
    └── item/                    # individual item PNGs
```

## What the skill provides in this `assets/` folder

- `project_template.tiled-project` — a ready-to-use Tiled project file with
  pre-defined `actor`, `item`, `trigger`, `sound` classes and an `actor_tag`
  enum (player / enemy / item). Copy it into the project root, rename to
  match your game.
- `world_template.world` — a minimal multi-map world JSON.

To apply:

1. Create the directories above.
2. Copy `project_template.tiled-project` → `my_game/project.tiled-project`.
3. Open it in Tiled (`File → Open Project…`).
4. Start creating maps / tilesets as usual; the property templates are
   immediately available.
