"""إعدادات الخادم — قابلة للضبط عبر متغيرات البيئة.

التخزين قابل للرفع: غيّر ARABAWI_STORAGE_QUOTA_GB أو اقرص مجلد البيانات
على قرص خارجي عبر ARABAWI_DATA_DIR لرفع سعة تخزين الخطوط.
"""
from __future__ import annotations

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


DATA_DIR = os.path.abspath(_env("ARABAWI_DATA_DIR", os.path.join(BASE_DIR, "data")))
FONTS_DIR = os.path.join(DATA_DIR, "fonts")
INBOX_DIR = os.path.join(DATA_DIR, "fonts_inbox")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
PREVIEWS_DIR = os.path.join(DATA_DIR, "previews")
MODELS_DIR = os.path.join(DATA_DIR, "easyocr_models")
DB_PATH = os.path.join(DATA_DIR, "index.db")

# سعة تخزين مكتبة الخطوط (جيجابايت) — افتراضيًا 250GB قابلة للرفع
STORAGE_QUOTA_GB = float(_env("ARABAWI_STORAGE_QUOTA_GB", "250"))
MAX_UPLOAD_MB = float(_env("ARABAWI_MAX_UPLOAD_MB", "64"))

HOST = _env("ARABAWI_HOST", "0.0.0.0")
# PORT: متغير المنفذ القياسي على Railway/هيروكو وغيرها
PORT = int(_env("ARABAWI_PORT", os.environ.get("PORT", "8000")))

# بوت تيليجرام: الرمز اختياري؛ إن غاب يعمل الموقع بدون بوت
TELEGRAM_BOT_TOKEN = _env("ARABAWI_TELEGRAM_BOT_TOKEN", "")
# معرف المالك الوحيد المسموح له رفع الخطوط عبر تيليجرام
OWNER_TG_ID = int(_env("ARABAWI_OWNER_TG_ID", "5231453921"))

WEB_DIR = os.path.join(BASE_DIR, "web")

ALLOWED_FONT_EXT = (".ttf", ".otf", ".woff", ".woff2", ".ttc")


def ensure_dirs() -> None:
    for d in (DATA_DIR, FONTS_DIR, INBOX_DIR, UPLOADS_DIR, PREVIEWS_DIR, MODELS_DIR):
        os.makedirs(d, exist_ok=True)
