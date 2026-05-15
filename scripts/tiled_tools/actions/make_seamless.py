"""make_seamless: 把任意图片变成四方连续（tileable）。

三种方法：

  feather (推荐)
      把图片向右下 roll 半张，让原本无缝的边集中到中央十字位置。
      然后用一张"中央十字 alpha mask"把未 roll 的原图叠到中央，
      这样产物的"四周边缘"对应原图的"中心区域"——既然原图中心
      区域是连续的，产物的边自然能无缝循环。
      对纹理素材（沙、草、岩石、布料、水面）效果最好。

  mirror
      把原图与其水平/垂直翻转拼成 2W×2H，再从中心裁回 W×H。
      产物的边缘像素来自镜像位置，必然左右/上下相等 → 0 接缝，
      但有可见对称感。适合"细节非常杂乱、不能容忍模糊"的素材。

  offset_blur
      把图片 roll 半张让接缝集中到中央十字，仅对十字带做高斯模糊，
      再 roll 回来。最朴素，对低频接缝（颜色不均的渐变背景）有效，
      对高频细节会糊掉。

参数：
  method            "feather" | "mirror" | "offset_blur"
  overlap           feather: 边缘羽化带占图宽/高的比例（0..0.5）
                    典型值 0.20~0.35。值越大融合越自然但中心信息越少。
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
        "把任意图片变成四方连续（tileable）。三种 method 各有取舍："
        "feather=最自然/通用；mirror=零接缝但有对称感；"
        "offset_blur=对低频接缝有效。"
    )
    param_hints = {
        "method": {"enum": ["feather", "mirror", "offset_blur"]},
        "overlap": {"min": 0.05, "max": 0.49, "step": 0.01},
        "blur_radius": {"min": 0.5, "max": 64.0, "step": 0.5},
        "blur_band": {"min": 0.05, "max": 0.49, "step": 0.01},
    }

    def run(
        self,
        ctx: Context,
        method: str = "feather",
        overlap: float = 0.25,
        blur_radius: float = 8.0,
        blur_band: float = 0.15,
    ) -> Context:
        img = self.require_image(ctx, "make_seamless")
        method = (method or "feather").lower()
        w, h = img.size

        if method == "feather":
            result = _feather(img, overlap)
        elif method == "mirror":
            result = _mirror(img)
        elif method == "offset_blur":
            result = _offset_blur(img, blur_radius, blur_band)
        else:
            raise ValueError(
                f"[make_seamless] 未知 method: {method!r}（应为 feather/mirror/offset_blur）"
            )

        ctx.image = result
        ctx.extras["make_seamless"] = {
            "method": method,
            "overlap": overlap,
            "size": result.size,
        }
        print(f"[make_seamless] {w}x{h} -> {result.size[0]}x{result.size[1]}  method={method}")
        return ctx
