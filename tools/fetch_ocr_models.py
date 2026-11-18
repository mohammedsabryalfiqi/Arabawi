#!/usr/bin/env python3
"""تنزيل نماذج التعرف الضوئي (EasyOCR: عربي + كاشف CRAFT) إلى data/easyocr_models.

شغّلها على الخادم الفعلي مرة واحدة؛ بعدها يصبح /api/ocr/status جاهزًا
ويمتلئ حقل النص تلقائيًا عند التعرف. (داخل بيئات معزولة قد تُحجب
أصول التنزيل؛ عندها تبقى طريقة الإدخال اليدوي للنص تعمل.)
"""
import os
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(HERE, "..", "data", "easyocr_models")

FILES = {
    "arabic.pth": "https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/arabic.zip",
    "craft_mlt_25k.pth": "https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/craft_mlt_25k.zip",
}


def main() -> None:
    os.makedirs(DEST, exist_ok=True)
    for name, url in FILES.items():
        target = os.path.join(DEST, name)
        if os.path.exists(target) and os.path.getsize(target) > 1000:
            print("موجود:", name)
            continue
        print("تنزيل:", url)
        zpath = os.path.join(DEST, name + ".zip")
        urllib.request.urlretrieve(url, zpath)
        with zipfile.ZipFile(zpath) as z:
            members = [m for m in z.namelist() if m.endswith(".pth")]
            if not members:
                print("!! لا يوجد ملف .pth داخل", name + ".zip")
                sys.exit(1)
            data = z.read(members[0])
            with open(target, "wb") as f:
                f.write(data)
        os.remove(zpath)
        print("✓", name, f"{len(data)/1e6:.1f} MB")
    print("تم. إن كان الخادم يعمل بالفعل أثناء التنزيل فأعد تشغيله؛ وإلا فالمحرك يتفعّل تلقائيًا عند الإقلاع.")


if __name__ == "__main__":
    main()
