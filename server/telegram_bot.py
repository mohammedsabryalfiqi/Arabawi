"""بوت تيليجرام للعرباوي — يعمل داخل نفس عملية الخادم (خيط مستقل).

• المالك وحده (ARABAWI_OWNER_TG_ID، افتراضيًا 5231453921) يرفع الخطوط:
  يرسل ملفات الخطوط أو ملف zip في المحادثة → استلام فوري وفهرسة في الخلفية.
• أي خط يُضاف من موقع الدومين يصل للبوت تلقائيًا (نفس المخزن + إشعار للمالك).
• أزرار لوحة: تحليل صورة خط / المكتبة / التخزين / حالة المحرك (+ دليل الرفع للمالك).
• نتيجة التحليل تصل خلال ثوانٍ (بحد أقصى ~٢٠ ثانية) مع معاينة حية:
  الصورة المحسّنة + معاينات مرسومة لأفضل الخطوط.
"""
from __future__ import annotations

import asyncio
import io
import os
import threading
import time
import zipfile

from . import config

_APP = None
_LOOP = None
_STATE: dict[int, dict] = {}

AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"


def ar(n) -> str:
    return str(n).translate(str.maketrans("0123456789", AR_DIGITS))


# ---------------------------------------------------------------- لوحة المفاتيح
def main_keyboard(owner: bool):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows = [
        [InlineKeyboardButton("🔍 تحليل صورة خط", callback_data="analyze"),
         InlineKeyboardButton("📖 المكتبة", callback_data="library")],
        [InlineKeyboardButton("💾 التخزين", callback_data="storage"),
         InlineKeyboardButton("📊 حالة المحرك", callback_data="status")],
    ]
    if owner:
        rows.append([InlineKeyboardButton("📤 دليل رفع الخطوط (للمالك)", callback_data="upload")])
    return InlineKeyboardMarkup(rows)


def _is_owner(update) -> bool:
    u = update.effective_user
    return bool(u) and u.id == config.OWNER_TG_ID


# ---------------------------------------------------------------- الأوامر
async def cmd_start(update, context):
    owner = _is_owner(update)
    txt = ("👋 أهلًا بك في بوت *العرباوي*!\n"
           "عرّف الخط العربي من صورة كلمة أو جملة كاملة — بلا تقطيع للحروف.\n"
           "• أرسل صورة الكلمة/الجملة مباشرة للتحليل.\n")
    if owner:
        txt += ("• *أنت المالك*: أرسل ملفات الخطوط (ttf/otf/woff/woff2/ttc) أو ملف zip "
                "في هذه المحادثة لتُفهرَس في الخلفية وتُضاف للمكتبة وللبوت تلقائيًا.\n")
    txt += "اختر من الأزرار بالأسفل 👇"
    await update.message.reply_text(txt, parse_mode="Markdown",
                                    reply_markup=main_keyboard(owner))


async def cmd_help(update, context):
    await cmd_start(update, context)


async def cmd_storage(update, context):
    from . import fontstore
    s = fontstore.storage_info()
    await update.message.reply_text(
        f"💾 التخزين\nالمستخدم: {s['used_gb']} ج.ب من حصة {ar(s['quota_gb'])} ج.ب\n"
        f"متبقي الحصة: {s['free_gb']} ج.ب · حرّ القرص: {s['disk_free_gb']} ج.ب\n"
        f"الخطوط المفهرسة: {ar(s['font_count'])}")


async def cmd_fonts(update, context):
    from . import fontstore
    fonts = fontstore.list_fonts()
    if not fonts:
        await update.message.reply_text("المكتبة فارغة بعد.")
        return
    names = "، ".join(f["name"] for f in fonts[:15])
    more = f" … و{ar(len(fonts) - 15)} أخرى" if len(fonts) > 15 else ""
    await update.message.reply_text(f"📖 المكتبة ({ar(len(fonts))} خطًا):\n{names}{more}")


async def cmd_status(update, context):
    from . import ocr
    st = ocr.status()
    line = "✅ محرك OCR جاهز" if st["ready"] else "⚠️ محرك OCR غير مفعّل (الإدخال اليدوي متاح)"
    await update.message.reply_text(f"📊 حالة المحرك\n{line}\nالمحرك: {st['engine']}")


# ---------------------------------------------------------------- الأزرار
async def on_button(update, context):
    q = update.callback_query
    await q.answer()
    data = q.data
    msg = q.message
    if data == "analyze":
        _STATE[update.effective_chat.id] = {"step": "await_photo"}
        await msg.reply_text("📷 أرسل الآن صورة الكلمة أو الجملة العربية "
                             "(جملة كاملة — لا تُجزئ الحروف).")
    elif data == "library":
        from . import fontstore
        fonts = fontstore.list_fonts()
        names = "، ".join(f["name"] for f in fonts[:15]) or "لا خطوط بعد"
        more = f" … و{ar(len(fonts) - 15)} أخرى" if len(fonts) > 15 else ""
        await msg.reply_text(f"📖 المكتبة ({ar(len(fonts))} خطًا):\n{names}{more}")
    elif data == "storage":
        from . import fontstore
        s = fontstore.storage_info()
        await msg.reply_text(
            f"💾 المستخدم {s['used_gb']} ج.ب من {ar(s['quota_gb'])} ج.ب · "
            f"متبقي {s['free_gb']} ج.ب · الخطوط {ar(s['font_count'])}")
    elif data == "status":
        from . import ocr
        st = ocr.status()
        await msg.reply_text("✅ OCR جاهز" if st["ready"] else
                             "⚠️ OCR غير مفعّل — يمكن إدخال نص الجملة يدويًا")
    elif data == "upload":
        if not _is_owner(update):
            await msg.reply_text("🔒 هذا الخيار للمالك فقط.")
            return
        await msg.reply_text(
            "📤 ارفع الخطوط بإرسالها هنا مباشرة:\n"
            "• ملفات ttf / otf / woff / woff2 / ttc\n"
            "• أو ملف zip يحتوي عدة خطوط\n"
            "سيتم الاستلام فورًا والفهرسة في الخلفية، وتُضاف للمكتبة وللموقع تلقائيًا.")


# ---------------------------------------------------------------- التحليل
async def on_photo(update, context):
    msg = update.message
    chat_id = update.effective_chat.id
    photo = msg.photo[-1]
    ack = await msg.reply_text(" تم الاستلام — جارٍ تحسين الصورة وتقسيم الكلمات… "
                               "(النتيجة خلال ~٢٠ ثانية)")
    f = await photo.get_file()
    ba = await f.download_as_bytearray()
    data = bytes(ba)

    loop = asyncio.get_running_loop()
    prep = await loop.run_in_executor(None, _prepare, data)
    if prep is None:
        await ack.edit_text("❌ تعذّر قراءة الصورة.")
        return
    if prep["text"]:
        await _finish_analysis(ack, msg, prep, prep["text"])
    else:
        _STATE[chat_id] = {"step": "await_text", "prep": prep}
        await ack.edit_text(
            f"🔢 عُثر على {ar(prep['word_count'])} كلمة في {ar(prep['line_count'])} سطر.\n"
            "محرك OCR غير مفعّل هنا: اكتب نص الجملة كما في الصورة لإتمام التحليل.")


async def on_text(update, context):
    chat_id = update.effective_chat.id
    st = _STATE.get(chat_id)
    if not st or st.get("step") != "await_text":
        return
    _STATE.pop(chat_id, None)
    ack = await update.message.reply_text("⏳ جارٍ مطابقة الخطوط… (النتيجة خلال ~٢٠ ثانية)")
    await _finish_analysis(ack, update.message, st["prep"], update.message.text.strip())


async def _finish_analysis(ack, msg, prep: dict, text: str):
    t0 = time.time()
    loop = asyncio.get_running_loop()
    res = await loop.run_in_executor(None, _identify, prep, text)
    dt = time.time() - t0
    if not res["matches"]:
        await ack.edit_text("❌ لا نتائج — تأكد أن المكتبة غير فارغة وأن النص صحيح.")
        return
    lines = [f"✅ النتيجة بعد {ar(round(dt + prep['prep_dt'], 1))} ثانية — "
             f"الكلمات: {ar(res['word_count'])} · الأسطر: {ar(res['line_count'])}", ""]
    for m in res["matches"]:
        lines.append(f"{ar(m['rank'])}) {m['name']} — ثقة {ar(m['confidence'])}٪ "
                     f"({m['license']} · {m['source']})")
    await ack.edit_text("\n".join(lines))
    # معاينة حية: الصورة المحسّنة ثم معاينات مرسومة لأفضل ٣
    try:
        await msg.reply_photo(photo=prep["enh_bytes"],
                              caption="🖼️ الصورة بعد التحسين (تنظيف + تعتيم + تصحيح ميل)")
    except Exception:
        pass
    media = []
    from telegram import InputMediaPhoto
    for m in res["matches"][:3]:
        p = res["previews"].get(m["font_id"])
        if p:
            media.append(InputMediaPhoto(media=p, caption=f"{m['name']} — {ar(m['confidence'])}٪"
                                         if len(media) == 0 else None))
    if media:
        try:
            await msg.reply_media_group(media=media)
        except Exception:
            for m in media:
                await msg.reply_photo(photo=m.media)


def _prepare(data: bytes) -> dict | None:
    """تحسين + تقسيم + OCR إن توفر. يعمل في خيط عامل."""
    try:
        import numpy as np
        from PIL import Image
        from . import ocr, segment
        from .enhance import enhance
        img = Image.open(io.BytesIO(data))
        img.load()
        t0 = time.time()
        enh = enhance(img)
        enh_buf = io.BytesIO()
        enh["clean"].save(enh_buf, format="PNG")
        ocr_out = ocr.recognize(np.asarray(enh["gray"]))
        text = (ocr_out["text"].strip() if ocr_out else "")
        seg = segment.segment_words(enh["binary"],
                                    target_n=len(text.split()) if text else None)
        return {"binary": enh["binary"], "words": seg["words"],
                "word_count": seg["word_count"], "line_count": seg["line_count"],
                "text": text, "ocr": ocr_out, "enh_bytes": enh_buf.getvalue(),
                "prep_dt": time.time() - t0}
    except Exception:
        return None


def _identify(prep: dict, text: str) -> dict:
    from . import fontstore, matcher
    fonts = fontstore.list_fonts()
    seg = segment_retarget(prep, text)
    result = matcher.identify(seg["words"], text, fonts, top_n=5,
                              line_mask=prep["binary"])
    previews = {}
    for m in result["matches"]:
        previews[m["font_id"]] = _preview_bytes(m["font_id"], text)
    return {"matches": result["matches"], "word_count": seg["word_count"],
            "line_count": seg["line_count"], "previews": previews}


def segment_retarget(prep: dict, text: str) -> dict:
    from . import segment
    n = len(text.split())
    if n and n != prep["word_count"]:
        return segment.segment_words(prep["binary"], target_n=n)
    return {"words": prep["words"], "word_count": prep["word_count"],
            "line_count": prep["line_count"]}


def _preview_bytes(font_id: str, text: str, h: int = 72):
    from PIL import Image
    from . import fontstore
    from .render import crop_ink, get_renderer
    f = fontstore.get_font(font_id)
    if not f:
        return None
    try:
        mask = crop_ink(get_renderer(f["path"]).render(text, h, pad=10))
        buf = io.BytesIO()
        Image.fromarray(255 - mask * 255).save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


# ---------------------------------------------------------------- رفع الخطوط (للمالك)
async def on_document(update, context):
    msg = update.message
    doc = msg.document
    name = (doc.file_name or "").lower()
    if not name.endswith((".ttf", ".otf", ".woff", ".woff2", ".ttc", ".zip")):
        return
    if not _is_owner(update):
        await msg.reply_text("🔒 رفع الخطوط عبر تيليجرام متاح للمالك فقط.\n"
                             "يمكن لأي أحد إضافة الخطوط من موقع الدومين.")
        return
    ack = await msg.reply_text("📥 تم الاستلام — جارٍ الفهرسة وتحليل المحارف في الخلفية…")
    f = await doc.get_file()
    ba = await f.download_as_bytearray()
    data = bytes(ba)
    asyncio.get_running_loop().create_task(_ingest_background(ack, data, name))


async def _ingest_background(ack, data: bytes, name: str):
    loop = asyncio.get_running_loop()
    added, dups, fails = [], [], []
    items = []
    if name.endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for info in z.infolist():
                    if info.is_dir():
                        continue
                    ext = os.path.splitext(info.filename)[1].lower()
                    if ext in config.ALLOWED_FONT_EXT:
                        items.append((os.path.basename(info.filename), z.read(info)))
        except zipfile.BadZipFile:
            await ack.edit_text("❌ ملف zip تالف.")
            return
    else:
        items = [(name, data)]
    if not items:
        await ack.edit_text("❌ لا ملفات خطوط صالحة داخل الحزمة.")
        return
    await ack.edit_text(f"📦 {ar(len(items))} ملف خط — جارٍ التحليل والفهرسة…")
    for fname, blob in items:
        try:
            from . import fontstore as _fs
            rec = await asyncio.to_thread(
                _fs.add_font, blob, fname,
                license_="مكتبة المالك", source="تيليجرام — المالك")
            added.append(rec["name"])
        except ValueError as e:
            if "مسبقًا" in str(e):
                dups.append(fname)
            else:
                fails.append((fname, str(e)))
    lines = [f"✅ أُضيف {ar(len(added))} خطًا: " + ("، ".join(added[:12]) or "—")]
    if dups:
        lines.append(f"♻️ مكرر ({ar(len(dups))}): " + "، ".join(dups[:8]))
    if fails:
        lines.append(f"❌ فشل ({ar(len(fails))}): " + "، ".join(n for n, _ in fails[:5]))
    from . import fontstore
    lines.append(f"📚 إجمالي المكتبة الآن: {ar(fontstore.storage_info()['font_count'])} خطًا")
    await ack.edit_text("\n".join(lines))


# ---------------------------------------------------------------- إشعار إضافة من الموقع
def _web_added_listener(rec: dict) -> None:
    """يستدعى من خيوط الويب عند إضافة خط — يُخطر المالك عبر البوت."""
    if _LOOP is None or _APP is None:
        return
    if str(rec.get("source", "")).startswith("تيليجرام"):
        return
    try:
        asyncio.run_coroutine_threadsafe(_notify_owner(rec), _LOOP)
    except Exception:
        pass


async def _notify_owner(rec: dict) -> None:
    from . import fontstore
    total = fontstore.storage_info()["font_count"]
    await _APP.bot.send_message(
        config.OWNER_TG_ID,
        f"🔔 أُضيف خط جديد للمكتبة تلقائيًا (من الموقع): *{rec['name']}*\n"
        f"📚 الإجمالي الآن: {ar(total)} خطًا — متاح فورًا للتحليل هنا وفي الموقع.",
        parse_mode="Markdown")


# ---------------------------------------------------------------- الإقلاع
def _build_app(token: str):
    from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                              MessageHandler, filters)
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("storage", cmd_storage))
    app.add_handler(CommandHandler("fonts", cmd_fonts))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, on_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


async def _post_init(app) -> None:
    global _APP, _LOOP
    _APP = app
    _LOOP = asyncio.get_running_loop()


def start() -> bool:
    """يطلق البوت في خيط مستقل. يعيد False إن لم يُضبط الرمز."""
    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        print("[arabawi] بوت تيليجرام معطّل (لم يُضبط ARABAWI_TELEGRAM_BOT_TOKEN)")
        return False

    def _thread():
        global _APP, _LOOP
        try:
            from . import fontstore
            app = _build_app(token)
            app.post_init = _post_init
            fontstore.on_font_added(_web_added_listener)
            app.run_polling(drop_pending_updates=True)
        except Exception as e:  # لا يُسقط الخادم أبدًا
            print("[arabawi] توقف البوت:", type(e).__name__, e)

    t = threading.Thread(target=_thread, name="arabawi-tg-bot", daemon=True)
    t.start()
    print(f"[arabawi] بوت تيليجرام يعمل — المالك: {config.OWNER_TG_ID}")
    return True
