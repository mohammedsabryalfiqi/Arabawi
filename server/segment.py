"""تقسيم صورة النص إلى كلمات كاملة (بلا تقطيع للحروف).

الحروف العربية متصلة داخل الكلمة، لذا المكوّنات المتصلة ≈ كلمات + نقاط.
ندمج النقاط والمكوّنات القريبة في صندوق كلمة واحدة، ونرتّب الكلمات
من اليمين إلى اليسار، ونحسب عدد الكلمات وعدد الأسطر (الجمل).

إن عُرف عدد كلمات الجملة (من نص OCR أو إدخال المستخدم) نصحّح التقسيم
إليه: دمج أقرب المجموعات أو الشق عند وديان الحبر — فلا تُجزأ الحروف أبدًا
وتبقى الوحدة كلمة/جملة كاملة.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage


def _components(binary: np.ndarray, min_area: int = 6):
    lab, n = ndimage.label(binary, structure=np.ones((3, 3)))
    comps = []
    if n == 0:
        return comps
    areas = ndimage.sum(binary, lab, range(1, n + 1))
    slices = ndimage.find_objects(lab)
    for i, sl in enumerate(slices):
        area = int(areas[i])
        if area < min_area:
            continue
        y0, y1 = sl[0].start, sl[0].stop
        x0, x1 = sl[1].start, sl[1].stop
        comps.append({"id": i + 1, "box": (x0, y0, x1, y1), "area": area,
                      "w": x1 - x0, "h": y1 - y0})
    return comps


def _gap(a: dict, b: dict) -> float:
    """المسافة الأفقية بين صندوقين (سالبة إن تداخلًا)."""
    ax0, _ay0, ax1, _ay1 = a["box"]
    bx0, _by0, bx1, _by1 = b["box"]
    left, right = (a, b) if ax0 < bx0 else (b, a)
    return float(right["box"][0] - left["box"][2])


def _split_group(group: dict, binary: np.ndarray, pieces: int):
    """يشق مجموعة متصلة عند وديان الحبر (أعمدة شبه خالية) داخل صندوقها."""
    x0, y0, x1, y1 = group["box"]
    sub = binary[y0:y1, x0:x1]
    cols = sub.sum(axis=0).astype(np.float64)
    med = max(np.median(cols[cols > 0]) if (cols > 0).any() else 1.0, 1.0)
    valleys = []
    x = 1
    W = len(cols)
    while x < W - 1:
        if cols[x] <= 0.10 * med:
            x2 = x
            while x2 < W - 1 and cols[x2] <= 0.10 * med:
                x2 += 1
            width = x2 - x
            depth = width * (med - cols[x:x2].mean())
            if width >= 1 and 0.08 * W < (x + x2) / 2 < 0.92 * W:
                valleys.append((depth, (x + x2) // 2))
            x = x2
        else:
            x += 1
    valleys.sort(reverse=True)
    cuts = sorted(v[1] for v in valleys[:pieces - 1])
    if not cuts:
        return [group]
    bounds = [0] + cuts + [W]
    out = []
    for i in range(len(bounds) - 1):
        sx0, sx1 = bounds[i], bounds[i + 1]
        if sx1 - sx0 < 2:
            continue
        sub2 = sub[:, sx0:sx1]
        ys, xs = np.nonzero(sub2)
        if len(ys) == 0:
            continue
        by0, by1 = y0 + ys.min(), y0 + ys.max() + 1
        bx0, bx1 = x0 + sx0 + xs.min(), x0 + sx0 + xs.max() + 1
        out.append({"box": (bx0, by0, bx1, by1),
                    "area": int(sub2.sum()),
                    "w": bx1 - bx0, "h": by1 - by0})
    return out or [group]


def segment_words(binary: np.ndarray, target_n: int | None = None) -> dict:
    """يعيد: كلمات (صناديق + عدد النقاط + قناع)، عدد الكلمات، عدد الأسطر.

    target_n: عدد كلمات الجملة إن عُرف (من النص) لتصحيح التقسيم إليه.
    """
    comps = _components(binary)
    if not comps:
        return {"words": [], "word_count": 0, "line_count": 0}

    max_area = max(c["area"] for c in comps)
    bodies0 = [c for c in comps if c["area"] >= 0.15 * max_area] or comps
    med_h = float(np.median([c["h"] for c in bodies0]))

    # المكوّنات النقطية (نقاط الحروف/الهمزات) تُضم لأقرب كلمة
    dots, bodies = [], []
    for c in comps:
        aspect = c["w"] / max(c["h"], 1)
        if c["h"] <= 0.22 * med_h and c["area"] <= 0.9 * (0.22 * med_h) ** 2 and 0.4 < aspect < 2.5:
            dots.append(c)
        else:
            bodies.append(c)
    if not bodies:
        bodies, dots = comps, []

    # دمج أفقي أولي: أجزاء الكلمة الواحدة متقاربة
    bodies.sort(key=lambda c: c["box"][0])
    groups = [dict(b) for b in bodies]
    changed = True
    while changed:
        changed = False
        merged = []
        for g in groups:
            if merged:
                px0, py0, px1, py1 = merged[-1]["box"]
                gx0, gy0, gx1, gy1 = g["box"]
                gap = gx0 - px1
                v_overlap = min(py1, gy1) - max(py0, gy0)
                h_min = min(py1 - py0, gy1 - gy0)
                if gap < 0.30 * med_h and v_overlap > 0.25 * h_min:
                    m = merged[-1]
                    m["box"] = (min(px0, gx0), min(py0, gy0),
                                max(px1, gx1), max(py1, gy1))
                    m["area"] += g["area"]
                    changed = True
                    continue
            merged.append(g)
        groups = merged

    # تصحيح العدد إلى عدد كلمات الجملة المعروف إن وُفر
    if target_n and target_n > 0:
        guard = 0
        while len(groups) > target_n and guard < 40:
            guard += 1
            groups.sort(key=lambda g: g["box"][0])
            best_i, best_cost = 0, 1e18
            for i in range(len(groups) - 1):
                gp = _gap(groups[i], groups[i + 1])
                oy = min(groups[i]["box"][3], groups[i + 1]["box"][3]) - \
                     max(groups[i]["box"][1], groups[i + 1]["box"][1])
                cost = gp - 0.6 * max(oy, 0)
                if cost < best_cost:
                    best_cost, best_i = cost, i
            a, b = groups[best_i], groups[best_i + 1]
            a["box"] = (min(a["box"][0], b["box"][0]), min(a["box"][1], b["box"][1]),
                        max(a["box"][2], b["box"][2]), max(a["box"][3], b["box"][3]))
            a["area"] += b["area"]
            groups.pop(best_i + 1)
        guard = 0
        while len(groups) < target_n and guard < 40:
            guard += 1
            groups.sort(key=lambda g: -g["w"])
            cand = groups[0]
            need = target_n - len(groups) + 1
            pieces = _split_group(cand, binary, need + 1)
            if len(pieces) <= 1:
                break
            groups.remove(cand)
            groups.extend(pieces)

    # ضم النقاط لصندوق الكلمة الأقرب وتوسيع الصندوق ليشملها
    # (حتى يطابق قناع الكلمة الرسمَ الكامل بالنقاط)
    groups.sort(key=lambda g: g["box"][0])
    word_boxes = [list(g["box"]) for g in groups]
    dot_counts = [0] * len(word_boxes)
    for d in dots:
        dx = (d["box"][0] + d["box"][2]) / 2
        dy = (d["box"][1] + d["box"][3]) / 2
        best, bestd = 0, 1e9
        for i, (x0, y0, x1, y1) in enumerate(word_boxes):
            cx = min(max(dx, x0), x1)
            cy = min(max(dy, y0), y1)
            dist = ((dx - cx) ** 2 + (dy - cy) ** 2) ** 0.5
            if dist < bestd:
                bestd, best = dist, i
        if bestd < 1.6 * med_h:
            dot_counts[best] += 1
            bx0, by0, bx1, by1 = word_boxes[best]
            word_boxes[best] = [min(bx0, d["box"][0]), min(by0, d["box"][1]),
                                max(bx1, d["box"][2]), max(by1, d["box"][3])]

    words = []
    for i, box in enumerate(word_boxes):
        x0, y0, x1, y1 = box
        pad = 2
        crop = binary[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad]
        words.append({"box": [int(x0), int(y0), int(x1), int(y1)],
                      "dots": dot_counts[i], "mask": crop,
                      "ink": int(crop.sum())})
    # ترتيب عربي: من اليمين إلى اليسار
    words.sort(key=lambda w: -w["box"][0])

    # الأسطر = تجميع عمودي
    yc = sorted((w["box"][1] + w["box"][3]) / 2 for w in words)
    lines = 1
    for a, b in zip(yc, yc[1:]):
        if b - a > 1.2 * med_h:
            lines += 1

    return {"words": words, "word_count": len(words), "line_count": lines}
