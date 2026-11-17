#!/usr/bin/env python3
"""توليد بطاقة «أفضل ٥ خطوط» بنفس تصميم بطاقة المقارنة المرجعية،
لكن بخطوط عربية بالكامل وبدون أي نص إنجليزي (حتى الأرقام هندية).

الخرج: assets/top5_arabic_fonts.png
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)

from server.render import get_renderer, crop_ink  # noqa: E402

INBOX = os.path.join(ROOT, "data", "fonts_inbox")
OUT = os.path.join(ROOT, "assets", "top5_arabic_fonts.png")

W, H = 820, 1160
BG = (236, 228, 218)
HEAD = (59, 42, 35)
PANEL = (247, 242, 234)
PANEL2 = (243, 236, 225)
CROP = (236, 225, 207)
INK = (64, 48, 42)
MUTED = (138, 122, 108)
GOLD = (201, 151, 63)
CHIP = (232, 217, 195)
CHIP_TX = (122, 92, 61)
LINE = (201, 184, 164)
NAVY = (29, 35, 51)

AR = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def ar(s: str) -> str:
    return s.translate(AR)


def font(name):
    return os.path.join(INBOX, name)


UI = font("cairo__Cairo_slnt,wght_.ttf")

ROWS = [
    ("أميري",    "amiri__Amiri-Regular.ttf",        "رخصة حرة", "مكتبة المالك"),
    ("ريم كوفي", "reemkufi__ReemKufi_wght_.ttf",    "رخصة حرة", "خطوط جوجل"),
    ("لاليزار",  "lalezar__Lalezar-Regular.ttf",    "رخصة حرة", "خطوط جوجل"),
    ("ميرزا",    "mirza__Mirza-Regular.ttf",        "رخصة حرة", "مكتبة المالك"),
    ("رقاص",     "rakkas__Rakkas-Regular.ttf",      "رخصة حرة", "خطوط جوجل"),
]
WORD = "العرباوي"
CROP_FONT = font("marhey__Marhey_wght_.ttf")


def put_text(img: Image.Image, xy, text, fpath, px, fill, anchor="right"):
    """يرسم نصًا عربيًا مصفوفًا ويلصقه ملوّنًا. anchor: right/center/left."""
    mask = crop_ink(get_renderer(fpath).render(text, px, pad=4))
    rgba = np.zeros((*mask.shape, 4), dtype=np.uint8)
    rgba[..., 0], rgba[..., 1], rgba[..., 2] = fill
    rgba[..., 3] = mask
    patch = Image.fromarray(rgba, "RGBA")
    x, y = xy
    w, h = patch.size
    if anchor == "right":
        x = x - w
    elif anchor == "center":
        x = x - w // 2
    img.alpha_composite(patch, (int(x), int(y)))
    return w, h


def dashed_rounded(img, box, radius, color, dash=7, gap=5, width=2):
    mask = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle(box, radius=radius, outline=255, width=width)
    a = np.asarray(mask).astype(bool)
    ys, xs = np.nonzero(a)
    keep = ((xs + ys) // dash) % (1 + gap // dash + 1) < 1 + (dash - gap) // dash
    # نمط شرطات على المحيط
    keep = ((xs + ys) % (dash + gap)) < dash
    a2 = np.zeros_like(a)
    a2[ys[keep], xs[keep]] = True
    overlay = np.zeros((*a2.shape, 4), dtype=np.uint8)
    overlay[..., :3] = color
    overlay[..., 3] = a2 * 255
    img.alpha_composite(Image.fromarray(overlay, "RGBA"))


def pill(img, xy, text, fpath, px, fg, bg=None, outline=None, pad_x=14):
    x, y = xy  # أعلى يمين الحبة
    tw = crop_ink(get_renderer(fpath).render(text, px, pad=2)).shape[1]
    th = px
    w = tw + pad_x * 2
    h = th + 12
    d = ImageDraw.Draw(img)
    if bg or outline:
        d.rounded_rectangle([x - w, y, x, y + h], radius=h // 2,
                            fill=bg, outline=outline, width=1)
    put_text(img, (x - pad_x, y + 6), text, fpath, px, fg)
    return w, h


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    img = Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(img)

    # ---------------- الترويسة (من اليمين) ----------------
    d.rectangle([0, 0, W, 100], fill=HEAD)
    put_text(img, (W - 40, 16), "ع", font("arefruqaa__ArefRuqaa-Regular.ttf"), 62, (216, 169, 78))
    put_text(img, (W - 104, 22), "العرباوي", UI, 30, (243, 233, 220))
    put_text(img, (W - 104, 64), "مقارنة الخطوط", UI, 14, (217, 198, 174))
    pw = crop_ink(get_renderer(UI).render("أفضل ٥", 14, pad=2)).shape[1] + 28
    pill(img, (36 + pw, 30), "أفضل ٥", UI, 14, (232, 211, 174), outline=(202, 168, 124))

    # ---------------- الإطار الخارجي ----------------
    dashed_rounded(img, (30, 122, W - 30, H - 26), 26, LINE)
    d.rounded_rectangle((38, 130, W - 38, H - 34), radius=20, fill=PANEL)

    # ---------------- لوحة القصاصة الأصلية ----------------
    d.rounded_rectangle((52, 146, W - 52, 312), radius=16, fill=CROP)
    put_text(img, (W - 70, 162), "القصاصة الأصلية", UI, 13, MUTED)
    # صندوق القصاصة الأبيض
    cw, ch = 460, 108
    cx0 = (W - cw) // 2
    d.rounded_rectangle((cx0, 186, cx0 + cw, 186 + ch), radius=10, fill=(246, 247, 249))
    px = 74
    ww = crop_ink(get_renderer(CROP_FONT).render(WORD, px, pad=2)).shape[1]
    if ww > cw - 40:
        px = int(px * (cw - 40) / ww)
    put_text(img, (W // 2, 202), WORD, CROP_FONT, px, NAVY, anchor="center")
    put_text(img, (W - 70, 288), f'التعرف الضوئي: «{WORD}» · {ar("100")}٪', UI, 12, MUTED)

    # ---------------- الصفوف الخمسة ----------------
    y = 330
    row_h = 132
    for i, (name, ffile, lic, src) in enumerate(ROWS, 1):
        d.rounded_rectangle((52, y, W - 52, y + row_h), radius=16, fill=PANEL2)
        # شريحة الترتيب (يمين)
        d.rounded_rectangle((W - 112, y + 16, W - 68, y + 54), radius=10, fill=CHIP)
        put_text(img, (W - 76, y + 22), ar(f"{i:02d}"), UI, 17, CHIP_TX, anchor="right")
        # الاسم + شارة الرخصة
        nw, _ = put_text(img, (W - 132, y + 18), name, UI, 19, INK, anchor="right")
        pill(img, (W - 132 - nw - 16, y + 20), lic, UI, 11, CHIP_TX, bg=(238, 226, 205))
        # شارة المصدر يسار
        sw = crop_ink(get_renderer(UI).render(src, 11, pad=2)).shape[1] + 28
        pill(img, (68 + sw, y + 20), src, UI, 11, CHIP_TX, bg=(238, 226, 205))
        # معاينة الكلمة بالخط
        put_text(img, (W - 132, y + 52), WORD, font(ffile), 62, (63, 43, 35), anchor="right")
        y += row_h + 14

    # ---------------- التذييل ----------------
    put_text(img, (W - 60, H - 66), "أسماء الخطوط + معاينات حية · نُرسل أي ملف خط عند الطلب",
             UI, 12, MUTED)

    img.convert("RGB").save(OUT, quality=95)
    print("saved", OUT)


if __name__ == "__main__":
    main()
