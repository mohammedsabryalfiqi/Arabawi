"""طبقة التعرف الضوئي على النص العربي (OCR) — محركات قابلة للتبديل.

المحرك المدعوم: EasyOCR (نموذج arabic + كاشف CRAFT). تُحمّل النماذج من
مجسد data/easyocr_models عبر أداة tools/fetch_ocr_models.py على الخادم
الفعلي. إن غابت النماذج أو تعذّر تحميل المحرك يعمل النظام بلا OCR مع
إتاحة إدخال النص يدويًا في الواجهة (مع بقاء عدّ الكلمات تلقائيًا).
"""
from __future__ import annotations

import os
import threading

import numpy as np

from . import config

_LOCK = threading.Lock()
_STATE = {"reader": None, "error": None, "checked": False}

NEEDED = ("arabic.pth", "craft_mlt_25k.pth")


def models_present() -> bool:
    return all(os.path.exists(os.path.join(config.MODELS_DIR, n)) for n in NEEDED)


def status() -> dict:
    with _LOCK:
        if _STATE["reader"] is not None:
            return {"engine": "easyocr", "ready": True, "models": list(NEEDED)}
        err = _STATE["error"]
    return {
        "engine": "easyocr",
        "ready": False,
        "models": list(NEEDED),
        "models_present": models_present(),
        "reason": err or ("النماذج غير منزّلة — شغّل tools/fetch_ocr_models.py على الخادم"
                          if not models_present() else None),
        "fallback": "إدخال النص يدويًا في الواجهة",
    }


def _load_reader():
    if _STATE["checked"]:
        return _STATE["reader"]
    with _LOCK:
        if _STATE["checked"]:
            return _STATE["reader"]
        _STATE["checked"] = True
        if not models_present():
            _STATE["error"] = "models missing"
            return None
        try:
            import easyocr  # يستورد torch — يتطلب مكتبات CPU stubs إن لزم
            _STATE["reader"] = easyocr.Reader(
                ["ar"], gpu=False, verbose=False,
                model_storage_directory=config.MODELS_DIR,
                download_enabled=False)
        except Exception as e:  # pragma: no cover
            _STATE["error"] = f"{type(e).__name__}: {e}"
            _STATE["reader"] = None
        return _STATE["reader"]


def recognize(gray: np.ndarray) -> dict | None:
    """gray: مصفوفة uint8 رمادية للصورة المحسّنة. يعيد نصًا وثقة وأسطرًا."""
    reader = _load_reader()
    if reader is None:
        return None
    try:
        raw = reader.readtext(gray, detail=1, paragraph=False)
    except Exception:
        return None
    if not raw:
        return {"text": "", "confidence": 0.0, "lines": []}
    items = []
    for box, text, conf in raw:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        items.append({"box": [min(xs), min(ys), max(xs), max(ys)],
                      "text": text.strip(), "conf": float(conf)})
    # تجميع الأسطر ثم ترتيب عربي (يمين→يسار) داخل السطر
    items.sort(key=lambda it: it["box"][1])
    lines: list[list[dict]] = []
    for it in items:
        placed = False
        for line in lines:
            ly = (line[0]["box"][1] + line[0]["box"][3]) / 2
            iy = (it["box"][1] + it["box"][3]) / 2
            if abs(ly - iy) < 0.6 * max(it["box"][3] - it["box"][1], 1):
                line.append(it)
                placed = True
                break
        if not placed:
            lines.append([it])
    out_lines = []
    for line in lines:
        line.sort(key=lambda it: -it["box"][0])  # RTL
        out_lines.append({
            "text": " ".join(w["text"] for w in line if w["text"]),
            "confidence": round(sum(w["conf"] for w in line) / len(line), 3),
            "box": line[0]["box"],
        })
    text = " ".join(l["text"] for l in out_lines)
    conf = round(sum(l["confidence"] for l in out_lines) / len(out_lines), 3) if out_lines else 0.0
    return {"text": text, "confidence": conf, "lines": out_lines}
