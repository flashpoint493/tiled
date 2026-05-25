"""make_seamless: 把任意图片变成四方连续（tileable）。

四种方法：

  multiband (推荐，高质量默认)
      和 feather 一样先把图片 roll 半张，让未来的平铺边界来自原图中心区域；
      但融合时使用拉普拉斯金字塔做多频段混合。低频层负责颜色/亮度过渡，
      高频层尽量保留纹理细节，通常比简单 feather 更不容易出现糊边和鬼影。
      对水面、草地、沙地、岩石、雪地等自然材质最通用。

  feather (快速)
      把图片向右下 roll 半张，让原本无缝的边集中到中央十字位置。
      然后用一张"中央十字 alpha mask"把未 roll 的原图叠到中央，
      这样产物的"四周边缘"对应原图的"中心区域"——既然原图中心
      区域是连续的，产物的边自然能无缝循环。
      对纹理素材（沙、草、岩石、布料、水面）速度最快。

  mirror
      把原图与其水平/垂直翻转拼成 2W×2H，再从中心裁回 W×H。
      产物的边缘像素来自镜像位置，必然左右/上下相等 → 0 接缝，
      但有可见对称感。适合"细节非常杂乱、不能容忍模糊"的素材。

  offset_blur
      把图片 roll 半张让接缝集中到中央十字，仅对十字带做高斯模糊，
      再 roll 回来。最朴素，对低频接缝（颜色不均的渐变背景）有效，
      对高频细节会糊掉。

参数：
  method            "multiband" | "feather" | "mirror" | "offset_blur"
  overlap           multiband/feather: 边缘羽化带占图宽/高的比例（0..0.5）
                    典型值 0.20~0.35。值越大融合越自然但中心信息越少。
  levels            multiband: 金字塔层数。典型 4~5，水面可用 5~6。
  blur_radius       offset_blur: 高斯模糊半径（像素）。典型 4..16。
  blur_band         offset_blur: 模糊带占图宽/高的比例。典型 0.15。

输入: ctx.image
输出: ctx.image 替换为四方连续版本（尺寸不变）
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

from ..core.action import Action, Context
from ..core.registry import register


# ---------- feather ----------

def _feather_mask(w: int, h: int, overlap: float) -> np.ndarray:
    """中央十字形 alpha mask（H, W, 1），值域 0..1。

    overlap=0.25 时，中央 ~50% 区域是纯 1（用未 roll 版本），
    向四周线性渐变到 0（用 roll 版本，即把原图中心拉到边的版本）。
    """
    overlap = max(0.01, min(0.49, float(overlap)))
    # 横向：中央高 1，两侧线性降到 0；过渡带宽 = overlap * w
    def axis_mask(n: int) -> np.ndarray:
        m = np.ones(n, dtype=np.float32)
        band = max(1, int(round(n * overlap)))
        # 左右各 band 宽的过渡
        ramp = np.linspace(0.0, 1.0, band, dtype=np.float32)
        m[:band] = ramp
        m[-band:] = ramp[::-1]
        return m

    mx = axis_mask(w)         # (W,)
    my = axis_mask(h)         # (H,)
    # 二维 mask：取 min 形成"中央方形 + 四周渐变" 的十字状区域
    mask2d = np.minimum.outer(my, mx)
    return mask2d[:, :, None]  # (H, W, 1)


def _feather(img: Image.Image, overlap: float) -> Image.Image:
    src = img if img.mode == "RGBA" else img.convert("RGBA")
    a = np.asarray(src, dtype=np.float32)             # (H, W, 4)
    h, w = a.shape[:2]
    # 向右下 roll 半张：原本的左右/上下接缝现在被放到了图像正中央十字位置
    rolled = np.roll(a, shift=(h // 2, w // 2), axis=(0, 1))
    # 中央十字用未偏移的原图（边缘连续），四周用 rolled（产物的边对应原图中心）
    m = _feather_mask(w, h, overlap)                  # (H, W, 1)
    out = a * m + rolled * (1.0 - m)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="RGBA")


# ---------- multiband ----------

def _resize_float(a: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Resize H×W×C float arrays without quantizing intermediate pyramid data."""
    target_w, target_h = size
    if a.shape[1] == target_w and a.shape[0] == target_h:
        return a.copy()

    channels = []
    for i in range(a.shape[2]):
        channel = Image.fromarray(a[:, :, i].astype(np.float32), mode="F")
        channels.append(
            np.asarray(channel.resize((target_w, target_h), resample=Image.BICUBIC), dtype=np.float32)
        )
    return np.stack(channels, axis=2)


def _gaussian_pyramid(a: np.ndarray, levels: int) -> list[np.ndarray]:
    pyr = [a]
    for _ in range(1, levels):
        h, w = pyr[-1].shape[:2]
        if w <= 1 and h <= 1:
            break
        pyr.append(_resize_float(pyr[-1], (max(1, w // 2), max(1, h // 2))))
    return pyr


def _laplacian_pyramid(gauss: list[np.ndarray]) -> list[np.ndarray]:
    pyr = []
    for i in range(len(gauss) - 1):
        h, w = gauss[i].shape[:2]
        up = _resize_float(gauss[i + 1], (w, h))
        pyr.append(gauss[i] - up)
    pyr.append(gauss[-1])
    return pyr


def _reconstruct_laplacian(pyr: list[np.ndarray]) -> np.ndarray:
    out = pyr[-1]
    for i in range(len(pyr) - 2, -1, -1):
        h, w = pyr[i].shape[:2]
        out = _resize_float(out, (w, h)) + pyr[i]
    return out


def _edge_guard_mask(w: int, h: int) -> np.ndarray:
    """Outer-ring mask used to keep final borders anchored to the rolled image."""
    max_band = max(1, min(w, h) // 8)
    band = max(1, min(8, max_band))

    def axis_mask(n: int) -> np.ndarray:
        m = np.ones(n, dtype=np.float32)
        b = min(band, max(1, n // 2))
        ramp = 0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, b, dtype=np.float32))
        m[:b] = ramp
        m[-b:] = ramp[::-1]
        return m

    mask2d = np.minimum.outer(axis_mask(h), axis_mask(w))
    return mask2d[:, :, None]


def _multiband(img: Image.Image, overlap: float, levels: int) -> Image.Image:
    src = img if img.mode == "RGBA" else img.convert("RGBA")
    a = np.asarray(src, dtype=np.float32)
    h, w = a.shape[:2]
    levels = max(1, min(8, int(levels)))

    rolled = np.roll(a, shift=(h // 2, w // 2), axis=(0, 1))
    mask = _feather_mask(w, h, overlap)

    ga = _gaussian_pyramid(a, levels)
    gb = _gaussian_pyramid(rolled, len(ga))
    gm = [np.clip(m, 0.0, 1.0) for m in _gaussian_pyramid(mask, len(ga))]

    la = _laplacian_pyramid(ga)
    lb = _laplacian_pyramid(gb)
    blended = [pa * m + pb * (1.0 - m) for pa, pb, m in zip(la, lb, gm)]
    out = _reconstruct_laplacian(blended)

    # 多频段重建会在最外圈产生少量低频泄漏；最终用很窄的边界 guard
    # 把四周重新锚定到 rolled，确保 tile_repeat 验证时边界仍然稳定。
    edge_guard = _edge_guard_mask(w, h)
    out = out * edge_guard + rolled * (1.0 - edge_guard)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="RGBA")


# ---------- mirror ----------

def _mirror(img: Image.Image) -> Image.Image:
    src = img if img.mode == "RGBA" else img.convert("RGBA")
    w, h = src.size
    # 2W × 2H 大图：左上原图、右上水平翻、左下垂直翻、右下双翻
    big = Image.new("RGBA", (w * 2, h * 2), (0, 0, 0, 0))
    big.paste(src, (0, 0))
    big.paste(src.transpose(Image.FLIP_LEFT_RIGHT), (w, 0))
    big.paste(src.transpose(Image.FLIP_TOP_BOTTOM), (0, h))
    big.paste(src.transpose(Image.ROTATE_180), (w, h))
    # 从中心裁 W×H：这样产物的左右边是同一镜像位置的像素（无缝）
    return big.crop((w // 2, h // 2, w // 2 + w, h // 2 + h))


# ---------- offset_blur ----------

def _offset_blur(img: Image.Image, radius: float, band: float) -> Image.Image:
    src = img if img.mode == "RGBA" else img.convert("RGBA")
    a = np.asarray(src, dtype=np.float32)
    h, w = a.shape[:2]
    # roll 半张让接缝集中到中央十字
    rolled = np.roll(a, shift=(h // 2, w // 2), axis=(0, 1))
    rolled_im = Image.fromarray(np.clip(rolled, 0, 255).astype(np.uint8), mode="RGBA")
    blurred = rolled_im.filter(ImageFilter.GaussianBlur(radius=max(0.1, float(radius))))
    b = np.asarray(blurred, dtype=np.float32)

    # 十字形 mask：中央水平带 + 中央垂直带 = 1，其余 = 0；过渡处羽化
    bw = max(1, int(round(w * float(band))))
    bh = max(1, int(round(h * float(band))))
    def band_alpha(n: int, bsz: int) -> np.ndarray:
        # 中央 bsz 宽的钟形（cosine），两端 0
        center = n // 2
        idx = np.arange(n) - center
        out = np.clip(1.0 - np.abs(idx) / bsz, 0.0, 1.0)
        # 平滑一下（cos 上升）
        return 0.5 - 0.5 * np.cos(out * np.pi)
    vert = band_alpha(h, bh)[:, None]                 # (H, 1)
    horiz = band_alpha(w, bw)[None, :]                # (1, W)
    cross = np.maximum(vert + horiz * 0, vert) + 0    # （沿用 vert）
    cross = np.maximum(np.broadcast_to(vert, (h, w)),
                       np.broadcast_to(horiz, (h, w)))  # (H, W)
    cross = cross[:, :, None]

    mixed = b * cross + rolled * (1.0 - cross)
    # roll 回来还原方向
    out = np.roll(mixed, shift=(-(h // 2), -(w // 2)), axis=(0, 1))
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="RGBA")


# ---------- action ----------

@register("make_seamless")
class MakeSeamlessAction(Action):
    description = (
        "把任意图片变成四方连续（tileable）。四种 method 各有取舍："
        "multiband=高质量/默认；feather=快速通用；mirror=零接缝但有对称感；"
        "offset_blur=对低频接缝有效。"
    )
    param_hints = {
        "method": {"enum": ["multiband", "feather", "mirror", "offset_blur"]},
        "overlap": {"min": 0.05, "max": 0.49, "step": 0.01},
        "levels": {"min": 1, "max": 8, "step": 1},
        "blur_radius": {"min": 0.5, "max": 64.0, "step": 0.5},
        "blur_band": {"min": 0.05, "max": 0.49, "step": 0.01},
    }

    def run(
        self,
        ctx: Context,
        method: str = "multiband",
        overlap: float = 0.30,
        levels: int = 5,
        blur_radius: float = 8.0,
        blur_band: float = 0.15,
    ) -> Context:
        img = self.require_image(ctx, "make_seamless")
        method = (method or "multiband").lower()
        w, h = img.size

        if method == "multiband":
            result = _multiband(img, overlap, levels)
        elif method == "feather":
            result = _feather(img, overlap)
        elif method == "mirror":
            result = _mirror(img)
        elif method == "offset_blur":
            result = _offset_blur(img, blur_radius, blur_band)
        else:
            raise ValueError(
                f"[make_seamless] 未知 method: {method!r}（应为 multiband/feather/mirror/offset_blur）"
            )

        ctx.image = result
        ctx.extras["make_seamless"] = {
            "method": method,
            "overlap": overlap,
            "levels": levels,
            "blur_radius": blur_radius,
            "blur_band": blur_band,
            "size": result.size,
        }
        print(f"[make_seamless] {w}x{h} -> {result.size[0]}x{result.size[1]}  method={method}")
        return ctx
