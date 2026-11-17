"""تحسين صورة النص العربي قبل التحليل.

خطوات: تدرّج رمادي → تقدير الخلفية وتطبيعها → تمدد تباين → إزالة ضجيج
وسيط → تعتيم/تنعيم → ثَتْننة (Otsu) → تصحيح ميل → غلق مورفولوجي خفيف.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

MAX_SIDE = 1600


def _otsu(gray: np.ndarray) -> int:
    hist, _ = np.histogram(gray, bins=256, range=(0, 256))
    hist = hist.astype(np.float64)
    total = hist.sum()
    sum_all = (hist * np.arange(256)).sum()
    sum_b = w_b = 0.0
    best_t, best_var = 127, -1.0
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
        if var > best_var:
            best_var, best_t = var, t
    return int(best_t)


def _deskew_angle(binary: np.ndarray) -> float:
    best_angle, best_score = 0.0, -1.0
    ys, xs = np.nonzero(binary)
    if len(ys) < 50:
        return 0.0
    for angle in np.arange(-8, 8.01, 1.0):
        rot = ndimage.rotate(binary, angle, order=0, mode="constant", cval=0)
        rows = rot.sum(axis=1).astype(np.float64)
        score = rows.var()
        if score > best_score:
            best_score, best_angle = score, float(angle)
    # ضبط أدق حول الأفضل
    for angle in np.arange(best_angle - 0.8, best_angle + 0.81, 0.4):
        rot = ndimage.rotate(binary, angle, order=0, mode="constant", cval=0)
        rows = rot.sum(axis=1).astype(np.float64)
        score = rows.var()
        if score > best_score:
            best_score, best_angle = score, float(angle)
    return best_angle


def enhance(img: Image.Image) -> dict:
    """يعيد قاموسًا فيه الصورة المحسّنة (رمادية + ثنائية) وبيانات العملية."""
    img = img.convert("L")
    w, h = img.size
    scale = min(1.0, MAX_SIDE / max(w, h))
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)

    # تقدير الخلفية وتطبيع الإضاءة
    bg = img.filter(ImageFilter.GaussianBlur(radius=25))
    arr = np.asarray(img, dtype=np.float32)
    b = np.asarray(bg, dtype=np.float32)
    norm = np.clip(arr / np.maximum(b, 1.0), 0.0, 1.6)
    norm = norm / max(norm.max(), 1e-6)
    g = (norm * 255).astype(np.uint8)

    # تمدد تباين بالنسب المئوية
    lo, hi = np.percentile(g, (0.5, 99.5))
    if hi - lo < 8:
        lo, hi = g.min(), max(g.max(), lo + 8)
    g = np.clip((g.astype(np.float32) - lo) * (255.0 / max(hi - lo, 1e-6)), 0, 255).astype(np.uint8)

    # إزالة ضجيج وسيط + تنعيم خفيف
    g = ndimage.median_filter(g, size=3)
    g_img = Image.fromarray(g).filter(ImageFilter.SMOOTH)
    g = np.asarray(g_img, dtype=np.uint8)

    thr = _otsu(g)
    binary = (g < thr).astype(np.uint8)  # الحبر = 1
    # إن كان الحبر أقلية واضحة نعكس
    if binary.mean() > 0.5:
        binary = 1 - binary

    angle = _deskew_angle(binary)
    if abs(angle) > 0.05:
        binary = (ndimage.rotate(binary, angle, order=1, mode="constant", cval=0) > 0.5).astype(np.uint8)
        g = ndimage.rotate(g, angle, order=1, mode="constant", cval=255).astype(np.uint8)

    # فتح خفيف لإزالة نقط الضجيج فقط إن وُجدت فعليًا (بلا غلق يشوّه الرفيع)
    lab_n, n_cnt = ndimage.label(binary)
    if n_cnt:
        sizes = ndimage.sum(binary, lab_n, range(1, n_cnt + 1))
        tiny = int((sizes <= 3).sum())
        if tiny > max(3, int(0.05 * n_cnt)):
            binary = ndimage.binary_opening(binary, structure=np.ones((2, 2))).astype(np.uint8)

    gray_out = Image.fromarray((1 - binary) * 255)
    return {
        "gray": Image.fromarray(g),
        "binary": binary,
        "clean": gray_out,
        "meta": {"threshold": thr, "deskew_deg": round(angle, 2),
                 "size": gray_out.size},
    }
