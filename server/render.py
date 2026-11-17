"""محرك رسم النص العربي بتشكيل كامل (harfbuzz + freetype).

لا يعتمد على تقطيع الحروف: التشكيل يتم على مستوى الكلمة/الجملة كاملة عبر
HarfBuzz (الوصل واللزقات والاستبدالات) ثم الرسم عبر FreeType لكل حرف shaped
بموضعه الصحيح، فتخرج الكلمة متصلة كما تُكتب فعلاً.
"""
from __future__ import annotations

import os
from functools import lru_cache

import numpy as np
import uharfbuzz as hb
import freetype as ft

ARABIC_RANGES = ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF),
                 (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))


def is_arabic(text: str) -> bool:
    return any(0x0600 <= ord(ch) <= 0x06FF or 0xFB50 <= ord(ch) <= 0xFEFF for ch in text)


def _glyph_index_ar(ch: str) -> bool:
    o = ord(ch)
    return any(a <= o <= b for a, b in ARABIC_RANGES)


class Renderer:
    """يرسم نصاً عربياً مصفوفًا (shaped) في مصفوفة حبر grayscale."""

    def __init__(self, font_path: str):
        self.font_path = font_path
        self._face = ft.Face(font_path)
        with open(font_path, "rb") as f:
            self._bytes = f.read()
        self._hb_face = hb.Face(self._bytes)
        self.upm = self._face.units_per_EM or 1000

    # ------------------------------------------------------------------
    def shape(self, text: str, pixel_size: int):
        font = hb.Font(self._hb_face)
        font.scale = (pixel_size * 64, pixel_size * 64)
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        if is_arabic(text):
            buf.direction = "RTL"
            buf.script = "Arab"
            buf.language = "ar"
            # الأرقام وحدها تُكتب يسار→يمين حتى داخل نص عربي
            import re as _re
            if _re.fullmatch(r"[\s\d\u0660-\u0669]+", text):
                buf.direction = "LTR"
        hb.shape(font, buf)
        return buf.glyph_infos, buf.glyph_positions

    def render(self, text: str, pixel_size: int = 64, pad: int = 6,
               grayscale: bool = True) -> np.ndarray:
        """يعيد مصفوفة uint8 (ink 0..255) للنص كاملًا كسطر واحد متصل."""
        infos, positions = self.shape(text, pixel_size)
        self._face.set_pixel_sizes(0, pixel_size)
        pieces = []
        pen_x = pen_y = 0
        for info, pos in zip(infos, positions):
            gid = info.codepoint
            gx = pen_x + pos.x_offset
            gy = pen_y + pos.y_offset
            self._face.load_glyph(gid, ft.FT_LOAD_RENDER | ft.FT_LOAD_NO_HINTING)
            glyph = self._face.glyph
            bmp = glyph.bitmap
            if bmp.rows > 0 and bmp.width > 0:
                arr = np.array(bmp.buffer, dtype=np.uint8).reshape(bmp.rows, bmp.pitch)
                arr = arr[:, : bmp.width].copy()
                x = int(round(gx / 64.0)) + glyph.bitmap_left
                y = int(round(gy / 64.0)) - glyph.bitmap_top
                pieces.append((arr, x, y))
            pen_x += pos.x_advance
            pen_y += pos.y_advance
        if not pieces:
            return np.zeros((8, 8), dtype=np.uint8)
        min_x = min(p[1] for p in pieces)
        min_y = min(p[2] for p in pieces)
        max_x = max(p[1] + p[0].shape[1] for p in pieces)
        max_y = max(p[2] + p[0].shape[0] for p in pieces)
        canvas = np.zeros((max_y - min_y + 2 * pad, max_x - min_x + 2 * pad), dtype=np.uint8)
        for arr, x, y in pieces:
            y0, x0 = y - min_y + pad, x - min_x + pad
            region = canvas[y0:y0 + arr.shape[0], x0:x0 + arr.shape[1]]
            np.maximum(region, arr, out=region)
        if not grayscale:
            canvas = (canvas > 127).astype(np.uint8) * 255
        return canvas

    def render_word_images(self, words: list[str], pixel_size: int = 64, pad: int = 4):
        """يرسم كل كلمة على حدة (بدون تقطيع حروف) ويعيد قائمة مصفوفات."""
        return [self.render(w, pixel_size, pad) for w in words]

    # ------------------------------------------------------------------
    def glyph_stats(self, pixel_size: int = 48) -> dict:
        """تحليل المحارف: تغطية + قياسات لكل حرف عربي مدعوم."""
        from fontTools.ttLib import TTFont
        tt = TTFont(self.font_path, fontNumber=0, lazy=True)
        cmap = tt.getBestCmap() or {}
        covered, missing = [], []
        for cp in range(0x0621, 0x064B):
            ch = chr(cp)
            (covered if cp in cmap else missing).append(ch)
        stats = {"covered": len(covered), "missing": len(missing),
                 "coverage": round(len(covered) / (len(covered) + len(missing) or 1), 3),
                 "glyphs_total": len(cmap), "upm": self.upm}
        heights, strokes = [], []
        for ch in covered[:28]:
            mask = self.render(ch, pixel_size, pad=2, grayscale=False)
            ys, xs = np.nonzero(mask)
            if len(ys) == 0:
                continue
            heights.append((ys.max() - ys.min() + 1) / pixel_size)
            from scipy import ndimage
            dt = ndimage.distance_transform_edt(mask > 0)
            strokes.append(float(np.median(dt[dt > 0])) * 2 / pixel_size)
        stats["mean_glyph_height"] = round(float(np.mean(heights)), 3) if heights else 0
        stats["mean_stroke_ratio"] = round(float(np.mean(strokes)), 4) if strokes else 0
        names = _font_names(self.font_path)
        stats.update(names)
        return stats


@lru_cache(maxsize=64)
def _font_names(font_path: str) -> dict:
    from fontTools.ttLib import TTFont
    out = {"family": os.path.splitext(os.path.basename(font_path))[0],
           "style": "Regular", "arabic_name": ""}
    try:
        tt = TTFont(font_path, fontNumber=0, lazy=True)
        name = tt["name"]
        def get(id_):
            r = name.getDebugName(id_)
            return r or ""
        out["family"] = get(16) or get(1) or out["family"]
        out["style"] = get(17) or get(2) or "Regular"
    except Exception:
        pass
    return out


_RENDERERS: dict[str, Renderer] = {}


def get_renderer(font_path: str) -> Renderer:
    key = os.path.abspath(font_path)
    r = _RENDERERS.get(key)
    if r is None:
        r = Renderer(key)
        _RENDERERS[key] = r
    return r


def crop_ink(mask: np.ndarray) -> np.ndarray:
    """يقصّ إلى صندوق الحبر الفعلي."""
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return mask
    return mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
