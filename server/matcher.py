"""مطابقة الخط: مقارنة كلمات الصورة بكلمات مرسمّة بكل خط في المكتبة.

لا تقطيع للحروف: المقارنة على مستوى الكلمة كاملة (والجملة كاملة كسطر).
لكل خط نرسم كلمة النص المرشَّح (بتشكيل HarfBuzz كامل) بعدة مقاسات حول
ارتفاع كلمة الصورة، ونحسب تشابه السمات، ثم نرتّب الخطوط بثقة مئوية.
"""
from __future__ import annotations

import numpy as np

from . import features as F
from .render import get_renderer, crop_ink

SIZE_FACTORS = (0.94, 1.0, 1.06)


def _word_features_cache_key(font_id: str, word: str, px: int) -> str:
    return f"{font_id}|{word}|{px}"


_FEAT_CACHE: dict[str, dict] = {}


def _render_features(font_path: str, font_id: str, word: str, target_h: int) -> dict:
    """يرسم الكلمة بحيث يطابق ارتفاع حبرها ارتفاع كلمة الصورة (حلّ بمسحيتين)."""
    key = _word_features_cache_key(font_id, word, target_h)
    f = _FEAT_CACHE.get(key)
    if f is None:
        r = get_renderer(font_path)
        mask = crop_ink(r.render(word, max(12, target_h), pad=4, grayscale=False))
        h0 = mask.shape[0]
        if h0 > 4 and abs(h0 - target_h) > 2:
            em2 = int(round(max(12, target_h) * target_h / h0))
            mask = crop_ink(r.render(word, em2, pad=4, grayscale=False))
            h1 = mask.shape[0]
            if h1 > 4 and abs(h1 - target_h) > 2:
                em3 = int(round(em2 * target_h / h1))
                mask = crop_ink(r.render(word, em3, pad=4, grayscale=False))
        f = F.extract(mask)
        if len(_FEAT_CACHE) > 4000:
            _FEAT_CACHE.clear()
        _FEAT_CACHE[key] = f
    return f


def _line_features(font_path: str, font_id: str, text: str, target_h: int) -> dict:
    key = f"LINE|{font_id}|{text}|{target_h}"
    f = _FEAT_CACHE.get(key)
    if f is None:
        r = get_renderer(font_path)
        mask = crop_ink(r.render(text, max(16, target_h), pad=6, grayscale=False))
        h0 = mask.shape[0]
        if h0 > 4 and abs(h0 - target_h) > 2:
            em2 = int(round(max(16, target_h) * target_h / h0))
            mask = crop_ink(r.render(text, em2, pad=6, grayscale=False))
        f = F.extract(mask)
        if len(_FEAT_CACHE) > 4000:
            _FEAT_CACHE.clear()
        _FEAT_CACHE[key] = f
    return f


def identify(words: list[dict], text: str, fonts: list[dict],
             line_mask: np.ndarray | None = None, top_n: int = 5) -> dict:
    """words: كلمات الصورة مرتبة يمين→يسار. text: النص المنطقي للجملة.

    line_mask: قناع الجملة كاملة (اختياري) لإضافة درجة تشابه على مستوى
    السطر كله — يلتقط إيقاع الوصل والمسافات بين الكلمات.
    """
    logical = text.split()
    rtl = logical  # الترتيب المنطقي للنص العربي = ترتيب العرض يمين→يسار
    qline, qline_h = None, 0
    if line_mask is not None:
        lm = crop_ink(line_mask)
        if lm.size and lm.sum() > 0:
            qline = F.extract(lm)
            qline_h = lm.shape[0]
    results = []
    for font in fonts:
        if font.get("status") != "ready":
            continue
        per_word, weights, details = [], [], []
        n = min(len(words), len(rtl))
        for k in range(n):
            q = words[k]
            qmask = q["mask"]
            qf = F.extract(crop_ink(qmask))
            if qf.get("empty"):
                continue
            qh = q["box"][3] - q["box"][1]
            best, best_detail = -1.0, {}
            for fac in SIZE_FACTORS:
                pf = _render_features(font["path"], font["id"], rtl[k],
                                      max(12, int(qh * fac)))
                s = F.similarity(qf, pf)
                if s > best:
                    best, best_detail = s, F.detail(qf, pf)
            per_word.append(best)
            weights.append(max(q["ink"], 1))
            details.append(best_detail)
        count_penalty = 1.0
        if logical and len(words) != len(logical):
            count_penalty = 0.85 ** abs(len(words) - len(logical))
        if per_word:
            word_score = float(np.average(per_word, weights=weights))
        else:
            word_score = 0.0
        score = word_score
        if qline is not None and not qline.get("empty") and logical:
            lf = _line_features(font["path"], font["id"], text, qline_h)
            s_line = F.similarity(qline, lf)
            score = 0.85 * word_score + 0.15 * s_line
        score *= count_penalty
        results.append({"font": font, "score": score,
                        "words": [round(s, 3) for s in per_word],
                        "detail": details})

    results.sort(key=lambda r: -r["score"])
    top = results[:top_n]
    matches = []
    for i, r in enumerate(top):
        conf = int(round(100 * min(max(r["score"], 0.0), 1.0)))
        margin = (r["score"] - top[i + 1]["score"]) if i + 1 < len(top) else 0.0
        matches.append({
            "rank": i + 1,
            "font_id": r["font"]["id"],
            "name": r["font"]["name"],
            "family": r["font"]["family"],
            "style": r["font"]["style"],
            "license": r["font"]["license"],
            "source": r["font"]["source"],
            "score": round(r["score"], 4),
            "confidence": conf,
            "margin": round(margin, 4),
            "word_scores": r["words"],
            "detail": r["detail"],
        })
    return {"matches": matches, "all_scores": {r["font"]["name"]: round(r["score"], 4)
                                               for r in results}}
