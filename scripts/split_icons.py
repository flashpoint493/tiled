# -*- coding: utf-8 -*-
"""
一键抠图脚本：把"一张大图里整齐排列了多个图标"的总览图，
拆分成一个图标一个 PNG，输出到 output/<原图名>/ 子文件夹里。

支持两种模式：
1) auto  : 连通域自动抠图（默认）。利用 alpha 通道（或指定背景色）做二值化，
           然后用形态学膨胀 + 连通区域标记把每个图标抠出来。
2) grid  : 网格切分。当图标在画面里整齐排成 R 行 × C 列时使用；脚本会先把
           大图等分 R*C 份，再在每个格子内部按非背景像素裁紧 bbox。
           对"整齐排列"来说这是最稳的方式。

依赖：
    pip install pillow numpy scipy

常用例子：
    # 默认：处理 PNG/ 目录下所有图，输出到 output/
    python split_icons.py

    # 透明背景的总览图，图标内部有缝隙时把膨胀调大
    python split_icons.py --dilate 8 --min-area 800

    # 白底（非透明）的总览图：把白色当背景剔除
    python split_icons.py --bg-color 255,255,255 --bg-tol 15

    # 网格模式：把单张图按 8 行 × 6 列切，再裁紧每格
    python split_icons.py --mode grid --grid 8x6 --only "wall 01.png"

    # 调试模式：在输出目录里多保存一张 _debug.png（红框标出识别到的每个图标）
    python split_icons.py --debug
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage


# ----------------------------- 工具函数 -----------------------------

def load_rgba(src_path: Path) -> np.ndarray:
    """读取图片并强制转换为 RGBA。"""
    img = Image.open(src_path).convert("RGBA")
    return np.array(img)


def build_foreground_mask(
    arr: np.ndarray,
    alpha_thresh: int,
    bg_color: Optional[Tuple[int, int, int]],
    bg_tol: int,
) -> np.ndarray:
    """
    构造前景掩码（True = 图标像素，False = 背景）。

    - 若图本身有 alpha 通道，alpha > alpha_thresh 的视为前景。
    - 若指定了 --bg-color，则同时把 RGB 与背景色差距 <= bg_tol 的像素也判为背景，
      用于处理"白底"或其他纯色底的总览图。
    """
    alpha = arr[:, :, 3]
    mask = alpha > alpha_thresh

    if bg_color is not None:
        rgb = arr[:, :, :3].astype(np.int16)
        bg = np.array(bg_color, dtype=np.int16).reshape(1, 1, 3)
        # 与背景色的最大通道差
        diff = np.max(np.abs(rgb - bg), axis=2)
        not_bg = diff > bg_tol
        mask = mask & not_bg

    return mask


def order_by_grid(items, row_tol_factor: float = 0.5):
    """
    按"先从上到下、同一行再从左到右"对图标排序。
    items: list of (cy, cx, h, payload)
    """
    if not items:
        return []
    avg_h = float(np.mean([it[2] for it in items]))
    row_tol = max(avg_h * row_tol_factor, 8.0)

    items_sorted = sorted(items, key=lambda it: it[0])
    rows: list[list] = []
    cur_row: list = []
    cur_y: Optional[float] = None
    for it in items_sorted:
        cy = it[0]
        if cur_y is None or abs(cy - cur_y) <= row_tol:
            cur_row.append(it)
            cur_y = cy if cur_y is None else (cur_y + cy) / 2.0
        else:
            rows.append(cur_row)
            cur_row = [it]
            cur_y = cy
    if cur_row:
        rows.append(cur_row)

    ordered = []
    for row in rows:
        row.sort(key=lambda it: it[1])  # 行内按 cx 排序
        ordered.extend(row)
    return ordered


def save_icon(
    arr: np.ndarray,
    region_mask: np.ndarray,
    out_path: Path,
    padding: int,
) -> bool:
    """
    根据 region_mask 从原图中裁出该图标并保存为透明 PNG。
    region_mask 必须是与 arr 同尺寸的布尔数组。
    """
    if not region_mask.any():
        return False

    ys, xs = np.where(region_mask)
    y0 = max(int(ys.min()) - padding, 0)
    y1 = min(int(ys.max()) + 1 + padding, arr.shape[0])
    x0 = max(int(xs.min()) - padding, 0)
    x1 = min(int(xs.max()) + 1 + padding, arr.shape[1])

    crop = arr[y0:y1, x0:x1].copy()
    sub_mask = region_mask[y0:y1, x0:x1]
    # 把不属于本图标的像素（包括邻居图标、网格线）alpha 置 0
    crop[~sub_mask, 3] = 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(crop, mode="RGBA").save(out_path)
    return True


# ----------------------------- 模式 1：连通域 -----------------------------

def split_auto(
    src_path: Path,
    out_dir: Path,
    alpha_thresh: int,
    bg_color: Optional[Tuple[int, int, int]],
    bg_tol: int,
    dilate: int,
    min_area: int,
    padding: int,
    debug: bool,
) -> int:
    arr = load_rgba(src_path)
    fg = build_foreground_mask(arr, alpha_thresh, bg_color, bg_tol)
    if not fg.any():
        print(f"[跳过] {src_path.name}: 没有检测到前景，"
              f"如果这是白底图请加 --bg-color 255,255,255")
        return 0

    # 膨胀，让同一图标内部细缝合并
    fg_dil = ndimage.binary_dilation(fg, iterations=dilate) if dilate > 0 else fg

    # 8 邻接连通区域
    structure = np.ones((3, 3), dtype=bool)
    labels, num = ndimage.label(fg_dil, structure=structure)
    if num == 0:
        print(f"[跳过] {src_path.name}: 未检测到连通区域")
        return 0

    slices = ndimage.find_objects(labels)
    items = []
    for idx, sl in enumerate(slices, start=1):
        if sl is None:
            continue
        ys, xs = sl
        area = int(np.sum(labels[ys, xs] == idx))
        if area < min_area:
            continue
        cy = (ys.start + ys.stop) / 2.0
        cx = (xs.start + xs.stop) / 2.0
        h = ys.stop - ys.start
        items.append((cy, cx, h, (idx, ys, xs)))

    if not items:
        print(f"[跳过] {src_path.name}: 过滤后没有有效图标 (--min-area 调小试试)")
        return 0

    ordered = order_by_grid(items)

    out_dir.mkdir(parents=True, exist_ok=True)
    base = src_path.stem
    saved = 0
    debug_boxes: list[Tuple[int, int, int, int]] = []
    for i, (_, _, _, (idx, _ys, _xs)) in enumerate(ordered, start=1):
        # 真实区域 = 该 label ∩ 原始（未膨胀）前景
        region = (labels == idx) & fg
        if not region.any():
            continue
        out_path = out_dir / f"{base}_{i:03d}.png"
        if save_icon(arr, region, out_path, padding):
            saved += 1
            ys2, xs2 = np.where(region)
            debug_boxes.append((int(xs2.min()), int(ys2.min()),
                                int(xs2.max()), int(ys2.max())))

    if debug:
        save_debug(arr, debug_boxes, out_dir / f"_debug_{base}.png")

    print(f"[完成] {src_path.name} -> {out_dir} （{saved} 个图标）")
    return saved


# ----------------------------- 模式 2：网格 -----------------------------

def split_grid(
    src_path: Path,
    out_dir: Path,
    rows: int,
    cols: int,
    alpha_thresh: int,
    bg_color: Optional[Tuple[int, int, int]],
    bg_tol: int,
    min_area: int,
    padding: int,
    debug: bool,
) -> int:
    arr = load_rgba(src_path)
    H, W = arr.shape[:2]
    fg = build_foreground_mask(arr, alpha_thresh, bg_color, bg_tol)

    cell_h = H / rows
    cell_w = W / cols

    out_dir.mkdir(parents=True, exist_ok=True)
    base = src_path.stem
    saved = 0
    debug_boxes: list[Tuple[int, int, int, int]] = []

    for r in range(rows):
        for c in range(cols):
            y0 = int(round(r * cell_h))
            y1 = int(round((r + 1) * cell_h))
            x0 = int(round(c * cell_w))
            x1 = int(round((c + 1) * cell_w))

            cell_mask_full = np.zeros_like(fg)
            cell_mask_full[y0:y1, x0:x1] = fg[y0:y1, x0:x1]
            area = int(cell_mask_full.sum())
            if area < min_area:
                continue

            i = r * cols + c + 1
            out_path = out_dir / f"{base}_{i:03d}.png"
            if save_icon(arr, cell_mask_full, out_path, padding):
                saved += 1
                ys2, xs2 = np.where(cell_mask_full)
                debug_boxes.append((int(xs2.min()), int(ys2.min()),
                                    int(xs2.max()), int(ys2.max())))

    if debug:
        # 网格模式下额外把网格线也画出来
        save_debug(arr, debug_boxes, out_dir / f"_debug_{base}.png",
                   grid=(rows, cols))

    print(f"[完成] {src_path.name} -> {out_dir} （{saved} 个图标，"
          f"网格 {rows}×{cols}）")
    return saved


# ----------------------------- 调试可视化 -----------------------------

def save_debug(
    arr: np.ndarray,
    boxes: list[Tuple[int, int, int, int]],
    out_path: Path,
    grid: Optional[Tuple[int, int]] = None,
):
    """把识别到的每个图标用红框画在原图上，方便人工检查。"""
    img = Image.fromarray(arr, mode="RGBA").convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    if grid is not None:
        rows, cols = grid
        H, W = arr.shape[:2]
        for r in range(1, rows):
            y = int(round(r * H / rows))
            draw.line([(0, y), (W, y)], fill=(0, 255, 255, 200), width=1)
        for c in range(1, cols):
            x = int(round(c * W / cols))
            draw.line([(x, 0), (x, H)], fill=(0, 255, 255, 200), width=1)

    for i, (x0, y0, x1, y1) in enumerate(boxes, start=1):
        draw.rectangle([x0, y0, x1, y1], outline=(255, 0, 0, 255), width=2)
        draw.text((x0 + 2, y0 + 2), str(i), fill=(255, 0, 0, 255))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(img, overlay).save(out_path)


# ----------------------------- 入口 -----------------------------

def parse_color(s: str) -> Tuple[int, int, int]:
    parts = [int(x) for x in s.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            f"--bg-color 需要 R,G,B 三个数字，例如 255,255,255；得到: {s}"
        )
    return tuple(parts)  # type: ignore[return-value]


def parse_grid(s: str) -> Tuple[int, int]:
    s = s.lower().replace("×", "x")
    if "x" not in s:
        raise argparse.ArgumentTypeError(
            f"--grid 必须形如 RxC，例如 8x6；得到: {s}"
        )
    r, c = s.split("x")
    return int(r), int(c)


def main():
    ap = argparse.ArgumentParser(
        description="把多图标总览图拆成单个图标 PNG"
    )
    ap.add_argument("--input", "-i", default="PNG", help="输入目录")
    ap.add_argument("--output", "-o", default="output", help="输出根目录")
    ap.add_argument("--mode", choices=["auto", "grid"], default="auto",
                    help="auto: 连通域自动抠图；grid: 按网格均分")
    ap.add_argument("--grid", type=parse_grid, default=None,
                    help="grid 模式下的行列数，形如 8x6（行x列）")
    ap.add_argument("--only", default=None,
                    help="只处理某个文件名（文件名包含该字符串即匹配）")

    ap.add_argument("--alpha-thresh", type=int, default=10,
                    help="alpha 大于该值视为前景 (默认 10)")
    ap.add_argument("--bg-color", type=parse_color, default=None,
                    help="若图是不透明背景，把这个颜色当背景剔除，"
                         "格式 R,G,B（如白底用 255,255,255）")
    ap.add_argument("--bg-tol", type=int, default=15,
                    help="--bg-color 的容差（默认 15）")

    ap.add_argument("--dilate", type=int, default=3,
                    help="auto 模式：膨胀次数。图标被切成多块时调大；"
                         "邻居图标粘连时调小 (默认 3)")
    ap.add_argument("--min-area", type=int, default=400,
                    help="过滤小于该像素数的碎片 (默认 400)")
    ap.add_argument("--padding", type=int, default=2,
                    help="每个图标四周保留的 padding 像素 (默认 2)")
    ap.add_argument("--debug", action="store_true",
                    help="同时输出 _debug_xxx.png，红框标出识别到的图标")

    args = ap.parse_args()

    in_dir = Path(args.input).resolve()
    out_root = Path(args.output).resolve()
    if not in_dir.is_dir():
        raise SystemExit(f"输入目录不存在: {in_dir}")

    files = sorted([p for p in in_dir.iterdir()
                    if p.suffix.lower() in (".png", ".webp")])
    if args.only:
        files = [p for p in files if args.only in p.name]
    if not files:
        raise SystemExit(f"{in_dir} 下没有可处理的图片")

    if args.mode == "grid" and args.grid is None:
        raise SystemExit("grid 模式需要同时指定 --grid，例如 --grid 8x6")

    print(f"输入: {in_dir}")
    print(f"输出: {out_root}")
    print(f"模式: {args.mode}")
    if args.bg_color is not None:
        print(f"背景色剔除: RGB={args.bg_color} 容差={args.bg_tol}")
    print(f"共 {len(files)} 张图待处理\n")

    total = 0
    for p in files:
        sub = out_root / p.stem
        if args.mode == "auto":
            total += split_auto(
                p, sub,
                alpha_thresh=args.alpha_thresh,
                bg_color=args.bg_color,
                bg_tol=args.bg_tol,
                dilate=args.dilate,
                min_area=args.min_area,
                padding=args.padding,
                debug=args.debug,
            )
        else:
            r, c = args.grid
            total += split_grid(
                p, sub, rows=r, cols=c,
                alpha_thresh=args.alpha_thresh,
                bg_color=args.bg_color,
                bg_tol=args.bg_tol,
                min_area=args.min_area,
                padding=args.padding,
                debug=args.debug,
            )

    print(f"\n全部完成，共导出 {total} 个图标到 {out_root}")


if __name__ == "__main__":
    main()
