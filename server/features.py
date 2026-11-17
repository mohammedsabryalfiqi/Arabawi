"""سمات شكلية على مستوى الكلمة (لا على مستوى الحرف) لمطابقة الخطوط.

لكل قناع كلمة نستخرج: صورة معيارية، إسقاطات أفقية/رأسية، سماكة الضربة،
نمط النقاط (عدد + مواضع نسبية)، عدد العيون/الحلقات (الثقوب)، نسبة العرض.
المطابقة = متوسط مرجّح لتشابه هذه السمات بين كلمة الصورة وكلمة مرسمّة بالخط.
"""
from __future__ import annotations

import numpy as np
from PIL import Image
from scipy import ndimage

GRID = (128, 32)          # (عرض، ارتفاع) للصورة المعيارية
PROF_H, PROF_V = 64, 24   # دقة الإسقاطات


def _resize_mask(mask: np.ndarray, size) -> np.ndarray:
    img = Image.fromarray((mask * 255).astype(np.uint8))
    img = img.resize(size, Image.BILINEAR)
    return np.asarray(img, dtype=np.float32) / 255.0


def extract(mask: np.ndarray) -> dict:
    """mask: uint8/bool قناع الحبر مقصوصًا لصندوق الحبر."""
    m = (mask > 0).astype(np.uint8)
    ys, xs = np.nonzero(m)
    if len(ys) == 0:
        return {"empty": True}
    h = ys.max() - ys.min() + 1
    w = xs.max() - xs.min() + 1
    norm = _resize_mask(m, GRID)
    rows = m.sum(axis=1).astype(np.float64)
    cols = m.sum(axis=0).astype(np.float64)
    hprof = _norm_prof(np.interp(np.linspace(0, len(rows) - 1, PROF_V),
                                 np.arange(len(rows)), rows))
    vprof = _norm_prof(np.interp(np.linspace(0, len(cols) - 1, PROF_H),
                                 np.arange(len(cols)), cols))
    dt = ndimage.distance_transform_edt(m)
    stroke = float(np.median(dt[dt > 0])) * 2 / max(h, 1)
    holes = _count_holes(m)
    dots = _dot_pattern(m)
    baseline = float(np.argmax(rows)) / max(len(rows), 1)
    return {
        "empty": False,
        "aspect": w / max(h, 1),
        "norm": norm,
        "hprof": hprof,
        "vprof": vprof,
        "stroke": stroke,
        "holes": holes,
        "dots": dots,
        "baseline": baseline,
        "density": float(m.sum()) / max(w * h, 1),
    }


def _norm_prof(p: np.ndarray) -> np.ndarray:
    s = p.sum()
    return p / s if s > 0 else p


def _count_holes(m: np.ndarray) -> int:
    filled = ndimage.binary_fill_holes(m)
    holes = filled & ~m.astype(bool)
    lab, n = ndimage.label(holes)
    if n == 0:
        return 0
    sizes = ndimage.sum(holes, lab, range(1, n + 1))
    return int((sizes >= 4).sum())


def _dot_pattern(m: np.ndarray) -> dict:
    lab, n = ndimage.label(m, structure=np.ones((3, 3)))
    if n == 0:
        return {"count": 0, "rel": []}
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    total = sizes.sum()
    ys, xs = np.nonzero(m)
    H = ys.max() - ys.min() + 1
    W = xs.max() - xs.min() + 1
    rel = []
    cnt = 0
    for i, sl in enumerate(ndimage.find_objects(lab)):
        a = sizes[i]
        hh = sl[0].stop - sl[0].start
        ww = sl[1].stop - sl[1].start
        if a < 0.03 * total and a >= 4 and 0.4 < ww / max(hh, 1) < 2.5 and hh < 0.4 * H:
            cnt += 1
            cy = ((sl[0].start + sl[0].stop) / 2 - ys.min()) / H
            cx = ((sl[1].start + sl[1].stop) / 2 - xs.min()) / W
            rel.append((round(cx, 2), round(cy, 2)))
    rel.sort(key=lambda t: -t[0])  # ترتيب عربي يمين→يسار
    return {"count": cnt, "rel": rel[:12]}


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    a = a.ravel().astype(np.float64)
    b = b.ravel().astype(np.float64)
    ma, mb = a.mean(), b.mean()
    da, db = a - ma, b - mb
    denom = (np.linalg.norm(da) * np.linalg.norm(db))
    return float(da @ db / denom) if denom > 1e-9 else 0.0


def _dots_sim(d1: dict, d2: dict) -> float:
    c1, c2 = d1["count"], d2["count"]
    if c1 == 0 and c2 == 0:
        return 1.0
    score = 1.0 - abs(c1 - c2) / max(c1, c2, 1)
    r1, r2 = d1["rel"], d2["rel"]
    if r1 and r2:
        k = min(len(r1), len(r2))
        d = np.mean([abs(r1[i][0] - r2[i][0]) + abs(r1[i][1] - r2[i][1]) for i in range(k)])
        score *= max(0.0, 1.0 - d)
    return float(max(0.0, score))


def similarity(f1: dict, f2: dict) -> float:
    """تشابه 0..1 بين سمتي كلمتين."""
    if f1.get("empty") or f2.get("empty"):
        return 0.0
    s_img = max(0.0, _corr(f1["norm"], f2["norm"]))
    s_prof = 0.5 * max(0.0, _corr(f1["hprof"], f2["hprof"])) + \
             0.5 * max(0.0, _corr(f1["vprof"], f2["vprof"]))
    s_stroke = float(np.exp(-2.2 * abs(np.log(max(f1["stroke"], 1e-4) / max(f2["stroke"], 1e-4)))))
    s_dots = _dots_sim(f1["dots"], f2["dots"])
    s_holes = 1.0 if f1["holes"] == f2["holes"] else max(0.0, 1.0 - abs(f1["holes"] - f2["holes"]) * 0.35)
    s_aspect = float(np.exp(-1.5 * abs(np.log(f1["aspect"] / max(f2["aspect"], 1e-4)))))
    s_base = float(np.exp(-6.0 * abs(f1["baseline"] - f2["baseline"])))
    return (0.34 * s_img + 0.18 * s_prof + 0.12 * s_stroke + 0.14 * s_dots +
            0.10 * s_holes + 0.06 * s_aspect + 0.06 * s_base)


def detail(f1: dict, f2: dict) -> dict:
    if f1.get("empty") or f2.get("empty"):
        return {}
    return {
        "shape": round(max(0.0, _corr(f1["norm"], f2["norm"])), 3),
        "profiles": round(0.5 * max(0.0, _corr(f1["hprof"], f2["hprof"])) +
                          0.5 * max(0.0, _corr(f1["vprof"], f2["vprof"])), 3),
        "stroke": round(float(np.exp(-2.2 * abs(np.log(max(f1["stroke"], 1e-4) /
                                                        max(f2["stroke"], 1e-4))))), 3),
        "dots": round(_dots_sim(f1["dots"], f2["dots"]), 3),
        "holes": round(1.0 if f1["holes"] == f2["holes"] else
                       max(0.0, 1.0 - abs(f1["holes"] - f2["holes"]) * 0.35), 3),
    }
