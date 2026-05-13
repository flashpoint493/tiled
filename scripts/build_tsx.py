# -*- coding: utf-8 -*-
"""
把一个目录下的 PNG 批量组织成 Tiled 的"多图片集合图块集"（Collection of Images），
产出一个可直接在 Tiled 里 `File -> Open` 打开的 .tsx 文件。

关键点（与 Tiled 文档对齐）：
- Collection of Images 的 TSX 里，顶层 <tileset> 没有 <image>；
  每个 <tile> 内部自带 <image source="..." width=".." height=".."/>。
- <tileset> 的 tilewidth/tileheight 在该类型下代表"集合中最大 tile 宽/高"。
- columns 固定写 0（Collection of Images 的约定）。
- <image source="..."> 使用相对于 .tsx 文件所在目录的路径，便于整个目录搬迁。

常用例子：
    # 最简单：扫描目录里所有 png，生成同名 tsx
    python build_tsx.py --input output/tileset_origin_01 --name oriental_dungeon

    # 过滤掉过小的碎片（比如 LOGO 文字抠出来的小块）
    python build_tsx.py -i output/tileset_origin_01 -n oriental_dungeon \
        --min-width 40 --min-height 40

    # 指定输出目录（.tsx 和 PNG 会是同一个目录关系）
    python build_tsx.py -i output/tileset_origin_01 -n oriental_dungeon \
        --out-dir output
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import List, Tuple
from xml.sax.saxutils import escape as xml_escape

from PIL import Image


TILED_VERSION = "1.11"
TSX_VERSION = "1.10"


def _read_size(p: Path) -> Tuple[int, int]:
    with Image.open(p) as im:
        return im.size  # (w, h)


def ensure_png(path: Path) -> Path:
    """
    若传入的不是 PNG/WEBP（例如 JPEG），就转码成同目录、同名的 PNG 并返回新路径。
    Tiled 的 Collection of Images 支持多种格式，但统一成 PNG 对透明处理和跨工具兼容最稳。
    """
    if path.suffix.lower() in (".png", ".webp"):
        return path
    new_path = path.with_suffix(".png")
    with Image.open(path) as im:
        im.convert("RGBA").save(new_path)
    print(f"[转码] {path.name} -> {new_path.name}")
    return new_path


def collect_tiles(
    src_dir: Path,
    min_width: int,
    min_height: int,
    exts: Tuple[str, ...] = (".png", ".webp"),
) -> List[Tuple[Path, int, int]]:
    """扫描 src_dir 下的图片，返回 [(path, w, h), ...]，按文件名自然排序。"""
    files = sorted(
        [p for p in src_dir.iterdir() if p.is_file() and p.suffix.lower() in exts],
        key=lambda p: p.name.lower(),
    )
    tiles: List[Tuple[Path, int, int]] = []
    skipped = 0
    for p in files:
        # 跳过调试图
        if p.name.startswith("_debug"):
            continue
        try:
            w, h = _read_size(p)
        except Exception as e:
            print(f"[警告] 跳过无法读取的文件 {p.name}: {e}")
            continue
        if w < min_width or h < min_height:
            skipped += 1
            continue
        tiles.append((p, w, h))
    if skipped:
        print(f"[过滤] 忽略过小图片 {skipped} 张（min {min_width}x{min_height}）")
    return tiles


def build_tsx_xml(
    name: str,
    tiles: List[Tuple[Path, int, int]],
    tsx_path: Path,
) -> str:
    """生成 TSX 的 XML 字符串。"""
    max_w = max((w for _, w, _ in tiles), default=1)
    max_h = max((h for _, _, h in tiles), default=1)
    tile_count = len(tiles)

    tsx_dir = tsx_path.resolve().parent
    lines: List[str] = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(
        f'<tileset version="{TSX_VERSION}" tiledversion="{TILED_VERSION}" '
        f'name="{xml_escape(name)}" tilewidth="{max_w}" tileheight="{max_h}" '
        f'tilecount="{tile_count}" columns="0">'
    )
    # 让 Tiled 在面板里按网格摆出图标（仅影响显示）
    lines.append(' <grid orientation="orthogonal" width="1" height="1"/>')

    for tile_id, (img_path, w, h) in enumerate(tiles):
        rel = os.path.relpath(img_path.resolve(), start=tsx_dir)
        # 统一用正斜杠，跨平台友好
        rel_posix = rel.replace(os.sep, "/")
        lines.append(f' <tile id="{tile_id}">')
        lines.append(
            f'  <image width="{w}" height="{h}" source="{xml_escape(rel_posix)}"/>'
        )
        lines.append(" </tile>")

    lines.append("</tileset>")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(
        description="把一个目录的 PNG 组装成 Tiled 的多图片集合 .tsx"
    )
    ap.add_argument("--input", "-i", required=True,
                    help="包含若干 PNG 的目录（通常是 split_icons.py 的产物）")
    ap.add_argument("--name", "-n", required=True,
                    help="图块集名字，也是 .tsx 的文件名")
    ap.add_argument("--out-dir", "-o", default=None,
                    help="输出目录（默认与 --input 同目录，便于相对路径最短）")
    ap.add_argument("--min-width", type=int, default=0,
                    help="小于该宽度的图片会被忽略（过滤 LOGO/文字碎片用）")
    ap.add_argument("--min-height", type=int, default=0,
                    help="小于该高度的图片会被忽略")
    ap.add_argument("--extra", action="append", default=[],
                    help="额外加入的图片文件，可重复指定；"
                         "非 PNG/WEBP 会自动转码为 PNG。"
                         "默认插入到 tile 列表最前（tile id=0）。"
                         "常见用法：把整张原始大图作为参考 tile 放最前。")
    ap.add_argument("--extra-position", choices=["front", "back"], default="front",
                    help="--extra 的插入位置，front 放最前，back 放最后（默认 front）")
    args = ap.parse_args()

    src_dir = Path(args.input).resolve()
    if not src_dir.is_dir():
        raise SystemExit(f"输入目录不存在: {src_dir}")

    out_dir = Path(args.out_dir).resolve() if args.out_dir else src_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    tsx_path = out_dir / f"{args.name}.tsx"

    tiles = collect_tiles(src_dir, args.min_width, args.min_height)

    # 处理 --extra：逐个转码成 PNG 并读尺寸
    extras: List[Tuple[Path, int, int]] = []
    for raw in args.extra:
        ep = Path(raw).resolve()
        if not ep.is_file():
            print(f"[警告] --extra 文件不存在，已跳过: {ep}")
            continue
        ep = ensure_png(ep)
        try:
            w, h = _read_size(ep)
        except Exception as e:
            print(f"[警告] --extra 无法读取 {ep.name}: {e}")
            continue
        extras.append((ep, w, h))

    # 避免 extra 与扫描结果重复（按绝对路径去重）
    if extras:
        existing = {p.resolve() for p, _, _ in tiles}
        extras = [t for t in extras if t[0].resolve() not in existing]

    if extras:
        if args.extra_position == "front":
            tiles = extras + tiles
        else:
            tiles = tiles + extras
        print(f"[加入] --extra {len(extras)} 张 "
              f"({'最前' if args.extra_position == 'front' else '最后'})")

    if not tiles:
        raise SystemExit("没有可用的图片，已退出")

    xml = build_tsx_xml(args.name, tiles, tsx_path)
    tsx_path.write_text(xml, encoding="utf-8")

    print(f"[完成] 写出 {tsx_path}")
    print(f"       tile 数量: {len(tiles)}")
    print(f"       最大 tile 尺寸: "
          f"{max(w for _, w, _ in tiles)}x"
          f"{max(h for _, _, h in tiles)}")
    print("在 Tiled 中使用：File -> Open... 选择该 .tsx 即可加载为多图片集合图块集。")


if __name__ == "__main__":
    main()
