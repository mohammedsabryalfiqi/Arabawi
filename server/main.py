"""خادم Arabawi: التعرف على الخطوط العربية من الصور + إدارة مكتبة الخطوط.

نقاط API:
  GET  /api/health            حالة الخادم
  GET  /api/storage           حصة التخزين والاستخدام
  GET  /api/fonts             قائمة الخطوط المفهرسة
  POST /api/fonts             رفع خط جديد (multipart: file, license, source, name)
  DELETE /api/fonts/{id}      حذف خط
  GET  /api/ocr/status        حالة محرك التعرف الضوئي
  POST /api/identify          تحليل صورة: تحسين → كلمات → OCR → مطابقة
  GET  /api/preview/{id}.png  معاينة نص مرسم بخط معين
"""
from __future__ import annotations

import hashlib
import io
import os
import time
import uuid

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from . import config, fontstore, matcher, ocr, segment
from .enhance import enhance
from .render import crop_ink, get_renderer

Image.MAX_IMAGE_PIXELS = 40_000_000

app = FastAPI(title="Arabawi — محرك التعرف على الخطوط العربية", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

config.ensure_dirs()


@app.on_event("startup")
def _startup() -> None:
    n = fontstore.scan_inbox()
    if n:
        print(f"[arabawi] التُقط {n} خطًا من صندوق الوارد")


@app.get("/api/health")
def health():
    return {"ok": True, "service": "arabawi", "time": time.time()}


@app.get("/api/storage")
def storage():
    return fontstore.storage_info()


@app.get("/api/fonts")
def fonts():
    return fontstore.list_fonts()


@app.post("/api/fonts")
async def add_font(file: UploadFile = File(...),
                   license: str = Form(""),
                   source: str = Form("مكتبة المالك"),
                   name: str = Form("")):
    data = await file.read()
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, "حجم الملف أكبر من الحد المسموح")
    try:
        rec = fontstore.add_font(data, file.filename or "font.ttf",
                                 license_=license, source=source, display_name=name)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return rec


@app.delete("/api/fonts/{font_id}")
def del_font(font_id: str):
    if not fontstore.delete_font(font_id):
        raise HTTPException(404, "الخط غير موجود")
    return {"ok": True}


@app.get("/api/ocr/status")
def ocr_status():
    return ocr.status()


@app.post("/api/identify")
async def identify(file: UploadFile = File(...),
                   text: str = Form(""),
                   do_enhance: str = Form("1")):
    data = await file.read()
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise HTTPException(400, "ملف صورة غير صالح")
    uid = uuid.uuid4().hex[:10]
    os.makedirs(config.UPLOADS_DIR, exist_ok=True)
    orig_path = os.path.join(config.UPLOADS_DIR, f"{uid}_orig.png")
    img.convert("RGB").save(orig_path)

    enh = enhance(img)
    enh_path = os.path.join(config.UPLOADS_DIR, f"{uid}_enh.png")
    enh["clean"].save(enh_path)

    ocr_out = None
    text_used = (text or "").strip()
    if not text_used:
        ocr_out = ocr.recognize(np.asarray(enh["gray"]))
        if ocr_out:
            text_used = ocr_out["text"].strip()

    # عدد كلمات الجملة المعروف يصحّح التقسيم (بلا تجزئة للحروف)
    target_n = len(text_used.split()) if text_used else None
    seg = segment.segment_words(enh["binary"], target_n=target_n)
    words = seg["words"]

    fonts = fontstore.list_fonts()
    result = None
    if text_used and fonts:
        result = matcher.identify(words, text_used, fonts, top_n=5,
                                  line_mask=enh["binary"])
        for m in result["matches"]:
            m["preview_url"] = preview_url(m["font_id"], text_used)
            _ensure_preview(m["font_id"], text_used)

    return {
        "upload_id": uid,
        "original_url": f"/uploads/{os.path.basename(orig_path)}",
        "enhanced_url": f"/uploads/{os.path.basename(enh_path)}",
        "enhance_meta": enh["meta"],
        "word_count": seg["word_count"],
        "line_count": seg["line_count"],
        "words": [{"box": w["box"], "dots": w["dots"]} for w in words],
        "ocr": ocr_out,
        "text_used": text_used,
        "needs_text": not bool(text_used),
        "matches": result["matches"] if result else [],
        "all_scores": result["all_scores"] if result else {},
        "fonts_in_library": len(fonts),
    }


def preview_url(font_id: str, text: str, h: int = 72) -> str:
    key = hashlib.sha1(f"{font_id}|{text}|{h}".encode()).hexdigest()[:12]
    return f"/previews/{font_id}_{key}.png"


def _preview_path(font_id: str, text: str, h: int = 72) -> str:
    key = hashlib.sha1(f"{font_id}|{text}|{h}".encode()).hexdigest()[:12]
    return os.path.join(config.PREVIEWS_DIR, f"{font_id}_{key}.png")


def _ensure_preview(font_id: str, text: str, h: int = 72) -> None:
    path = _preview_path(font_id, text, h)
    if os.path.exists(path):
        return
    f = fontstore.get_font(font_id)
    if not f:
        return
    try:
        mask = crop_ink(get_renderer(f["path"]).render(text, h, pad=10))
        Image.fromarray(255 - mask * 255).save(path)
    except Exception:
        pass


@app.get("/api/preview/{font_id}.png")
def preview(font_id: str, text: str = "العرباوي", h: int = 72):
    f = fontstore.get_font(font_id)
    if not f:
        raise HTTPException(404, "الخط غير موجود")
    path = _preview_path(font_id, text, h)
    _ensure_preview(font_id, text, h)
    if not os.path.exists(path):
        raise HTTPException(500, "تعذّر الرسم")
    return FileResponse(path, media_type="image/png")


app.mount("/uploads", StaticFiles(directory=config.UPLOADS_DIR), name="uploads")
app.mount("/previews", StaticFiles(directory=config.PREVIEWS_DIR), name="previews")
app.mount("/", StaticFiles(directory=config.WEB_DIR, html=True), name="web")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)
