"""مخزن الخطوط: رفع/تحليل/فهرسة + حصة تخزين قابلة للرفع.

الخطوط تُخزَّن على قرص الخادم (data/fonts) بفهرس SQLite. عند إضافة خط
يُحلَّل محارفه (تغطية عربية، سماكات، ارتفاعات، أسماء) ويُحفَظ التحليل
في الفهرس لتسريع المطابقة لاحقًا. يمكن إضافة الخطوط أيضًا بوضع الملفات
في مجلد الصندوق data/fonts_inbox (يلتقطها الخادم عند الإقلاع).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import threading
import time
import uuid

from . import config
from .render import get_renderer

_LOCK = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS fonts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    family TEXT, style TEXT,
    license TEXT, source TEXT,
    filename TEXT, sha256 TEXT UNIQUE, bytes INTEGER,
    path TEXT, added_at REAL, status TEXT, analysis TEXT
);
"""


def _conn() -> sqlite3.Connection:
    config.ensure_dirs()
    c = sqlite3.connect(config.DB_PATH, timeout=20)
    c.row_factory = sqlite3.Row
    c.execute(SCHEMA)
    return c


def storage_info() -> dict:
    used = 0
    count = 0
    for root, _dirs, files in os.walk(config.FONTS_DIR):
        for f in files:
            used += os.path.getsize(os.path.join(root, f))
            count += 1
    quota = int(config.STORAGE_QUOTA_GB * 1024 ** 3)
    try:
        disk_free = shutil.disk_usage(config.DATA_DIR).free
    except OSError:
        disk_free = 0
    return {
        "used_bytes": used,
        "used_gb": round(used / 1024 ** 3, 3),
        "quota_bytes": quota,
        "quota_gb": config.STORAGE_QUOTA_GB,
        "free_bytes": max(quota - used, 0),
        "free_gb": round(max(quota - used, 0) / 1024 ** 3, 2),
        "disk_free_gb": round(disk_free / 1024 ** 3, 2),
        "font_count": count,
    }


def list_fonts() -> list[dict]:
    with _LOCK, _conn() as c:
        rows = c.execute("SELECT * FROM fonts ORDER BY added_at DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["analysis"] = json.loads(d["analysis"] or "{}")
        out.append(d)
    return out


def get_font(font_id: str) -> dict | None:
    with _LOCK, _conn() as c:
        r = c.execute("SELECT * FROM fonts WHERE id=?", (font_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["analysis"] = json.loads(d["analysis"] or "{}")
    return d


def find_by_sha(sha: str) -> dict | None:
    with _LOCK, _conn() as c:
        r = c.execute("SELECT * FROM fonts WHERE sha256=?", (sha,)).fetchone()
    return dict(r) if r else None


def add_font(data: bytes, filename: str, license_: str = "", source: str = "مكتبة المالك",
             display_name: str = "") -> dict:
    """يحفظ الخط ويحلّل محارفه. يرفض تجاوز حصة التخزين أو التكرار."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in config.ALLOWED_FONT_EXT:
        raise ValueError("امتداد غير مدعوم: " + (ext or "؟"))
    sha = hashlib.sha256(data).hexdigest()
    existing = find_by_sha(sha)
    if existing:
        raise ValueError("الخط مضاف مسبقًا باسم: " + existing["name"])
    info = storage_info()
    if info["used_bytes"] + len(data) > info["quota_bytes"]:
        raise ValueError("تجاوز حصة التخزين المسموحة (%.0f جيجابايت)" % info["quota_gb"])

    fid = uuid.uuid4().hex[:12]
    rel = os.path.join(sha[:2], sha + ext)
    path = os.path.join(config.FONTS_DIR, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)

    analysis = {}
    status = "ready"
    try:
        analysis = get_renderer(path).glyph_stats()
    except Exception as e:  # ملف تالف أو غير خط
        os.remove(path)
        raise ValueError("تعذّر قراءة الخط: %s" % e)
    name = display_name or analysis.get("family") or os.path.splitext(filename)[0]
    with _LOCK, _conn() as c:
        c.execute(
            "INSERT INTO fonts (id,name,family,style,license,source,filename,sha256,bytes,path,added_at,status,analysis)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (fid, name, analysis.get("family", ""), analysis.get("style", ""),
             license_ or "غير محددة", source, filename, sha, len(data), path,
             time.time(), status, json.dumps(analysis, ensure_ascii=False)))
    return get_font(fid)


def delete_font(font_id: str) -> bool:
    f = get_font(font_id)
    if not f:
        return False
    try:
        if f["path"] and os.path.exists(f["path"]):
            os.remove(f["path"])
    except OSError:
        pass
    with _LOCK, _conn() as c:
        c.execute("DELETE FROM fonts WHERE id=?", (font_id,))
    return True


def scan_inbox() -> int:
    """يلتقط ملفات الخطوط الموضوعة في صندوق الوارد ويضيفها للمكتبة."""
    added = 0
    if not os.path.isdir(config.INBOX_DIR):
        return 0
    for fn in sorted(os.listdir(config.INBOX_DIR)):
        p = os.path.join(config.INBOX_DIR, fn)
        if not os.path.isfile(p):
            continue
        if os.path.splitext(fn)[1].lower() not in config.ALLOWED_FONT_EXT:
            continue
        with open(p, "rb") as f:
            data = f.read()
        try:
            clean = fn.split("__", 1)[-1] if "__" in fn else fn
            add_font(data, clean, license_="OFL / رخصة حرة", source="خطوط جوجل")
            added += 1
        except ValueError:
            pass  # مكرر أو تالف: نتجاهله
        finally:
            os.remove(p)
    return added
