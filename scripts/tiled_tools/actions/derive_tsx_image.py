# -*- coding: utf-8 -*-
"""derive_tsx_image: derive a Tiled TSX from an existing TSX with a new image.

This is intended for art-polish workflows where the logical tileset stays
isomorphic: tile IDs, tile names, terrain sets, WangSets, and custom properties
come from the base TSX, while only the visual sheet image changes.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

from ..core.action import Action, Context
from ..core.registry import register


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_image(root: ET.Element) -> ET.Element:
    for child in list(root):
        if _local_name(child.tag) == "image":
            return child
    raise ValueError("[derive_tsx_image] source TSX does not contain an <image> element")


def _resolve_output(source_tsx: Path, output: str, image_source: str) -> Path:
    if output and output != "auto":
        output_path = Path(output).expanduser()
        if not output_path.is_absolute():
            output_path = (source_tsx.parent / output_path).resolve()
        return output_path

    image_stem = Path(image_source).stem if image_source else f"{source_tsx.stem}_derived"
    return source_tsx.with_name(f"{image_stem}.tsx")


def _image_size(image_path: str, base_dir: Path) -> Optional[Tuple[int, int]]:
    if not image_path:
        return None
    path = Path(image_path).expanduser()
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"[derive_tsx_image] image_path not found: {path}")
    with Image.open(path) as img:
        return int(img.width), int(img.height)


@register("derive_tsx_image")
class DeriveTsxImageAction(Action):
    description = "从现有 TSX 派生新 TSX，只替换 tileset 名称和 image source/size，保留 WangSet 与 tile name"
    param_hints = {
        "source_tsx": {"widget": "filepath"},
        "image_path": {"widget": "filepath"},
        "output": {"widget": "filepath"},
    }

    def run(
        self,
        ctx: Context,
        source_tsx: str,
        output: str = "auto",
        name: str = "",
        image_source: str = "",
        image_path: str = "",
        image_width: int = 0,
        image_height: int = 0,
    ) -> Context:
        source_file = Path(source_tsx).expanduser().resolve()
        if not source_file.is_file():
            raise FileNotFoundError(f"[derive_tsx_image] source_tsx not found: {source_file}")

        tree = ET.parse(source_file)
        root = tree.getroot()
        image = _find_image(root)

        next_image_source = image_source.strip() or (Path(image_path).name if image_path else image.get("source", ""))
        if not next_image_source:
            raise ValueError("[derive_tsx_image] image_source or image_path is required")

        if name.strip():
            root.set("name", name.strip())

        image.set("source", next_image_source)

        detected_size = _image_size(image_path, source_file.parent)
        width = int(image_width or (detected_size[0] if detected_size else 0))
        height = int(image_height or (detected_size[1] if detected_size else 0))
        if width > 0:
            image.set("width", str(width))
        if height > 0:
            image.set("height", str(height))

        output_file = _resolve_output(source_file, output, next_image_source)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        tree.write(output_file, encoding="UTF-8", xml_declaration=True, short_empty_elements=True)

        ctx.extras["derived_tsx"] = {
            "path": str(output_file),
            "source_tsx": str(source_file),
            "name": root.get("name"),
            "image_source": image.get("source"),
            "image_width": image.get("width"),
            "image_height": image.get("height"),
            "tilecount": root.get("tilecount"),
            "columns": root.get("columns"),
        }
        ctx.meta["last_derived_tsx"] = str(output_file)
        print(
            f"[derive_tsx_image] -> {output_file.name}  "
            f"name={root.get('name')} image={image.get('source')} "
            f"size={image.get('width')}x{image.get('height')} "
            f"tilecount={root.get('tilecount')} columns={root.get('columns')}"
        )
        return ctx
