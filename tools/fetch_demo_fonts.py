#!/usr/bin/env python3
"""تنزيل خطوط عربية حرة (OFL) من مستودع google/fonts إلى صندوق الوارد في الخادم.

الخطوط تُحفظ في data/fonts_inbox/ ويلتقطها الخادم تلقائيًا عند الإقلاع
(أو عبر API الإضافة). لا تُودع ملفات الخطوط في Git — تُنزَّل عند الحاجة.

الاستخدام:  python3 tools/fetch_demo_fonts.py [--only amiri,cairo]
"""
import base64
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

REPO = "google/fonts"
FONTS = {
    "amiri":     ["ofl/amiri/Amiri-Regular.ttf", "ofl/amiri/Amiri-Bold.ttf"],
    "reemkufi":  ["ofl/reemkufi/ReemKufi[wght].ttf"],
    "lalezar":   ["ofl/lalezar/Lalezar-Regular.ttf"],
    "jomhuria":  ["ofl/jomhuria/Jomhuria-Regular.ttf"],
    "arefruqaa": ["ofl/arefruqaa/ArefRuqaa-Regular.ttf"],
    "cairo":     ["ofl/cairo/Cairo[slnt,wght].ttf"],
    "almarai":   ["ofl/almarai/Almarai-Regular.ttf"],
    "changa":    ["ofl/changa/Changa[wght].ttf"],
    "marhey":    ["ofl/marhey/Marhey[wght].ttf"],
    "rakkas":    ["ofl/rakkas/Rakkas-Regular.ttf"],
    "mirza":     ["ofl/mirza/Mirza-Regular.ttf"],
    "katibeh":   ["ofl/katibeh/Katibeh-Regular.ttf"],
}

HERE = os.path.dirname(os.path.abspath(__file__))
INBOX = os.path.join(HERE, "..", "data", "fonts_inbox")


def token() -> str:
    tok = os.environ.get("GITHUB_TOKEN", "")
    if tok:
        return tok
    try:
        return subprocess.run(["gh", "auth", "token"], capture_output=True,
                              text=True, timeout=15).stdout.strip()
    except Exception:
        return ""


def fetch(path: str, dest: str, tok: str) -> bool:
    url = f"https://api.github.com/repos/{REPO}/contents/{urllib.parse.quote(path)}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "arabawi-fetcher",
        **({"Authorization": f"Bearer {tok}"} if tok else {}),
    })
    with urllib.request.urlopen(req, timeout=120) as r:
        meta = json.load(r)
    data = base64.b64decode(meta["content"])
    if len(data) != meta["size"]:
        print("  !! حجم غير مطابق:", path)
        return False
    with open(dest, "wb") as f:
        f.write(data)
    print(f"  ✓ {os.path.basename(dest)}  ({len(data)/1024:.0f} KB)")
    return True


def main() -> None:
    only = []
    if len(sys.argv) > 2 and sys.argv[1] == "--only":
        only = sys.argv[2].split(",")
    os.makedirs(INBOX, exist_ok=True)
    tok = token()
    print("مصادقة GitHub:", "نعم" if tok else "لا (حدود أقل)")
    for family, paths in FONTS.items():
        if only and family not in only:
            continue
        print(f"• {family}")
        for p in paths:
            safe = p.split("/")[-1].replace("[", "_").replace("]", "_")
            dest = os.path.join(INBOX, f"{family}__{safe}")
            if os.path.exists(dest) and os.path.getsize(dest) > 1000:
                print("  - موجود مسبقًا:", os.path.basename(dest))
                continue
            try:
                fetch(p, dest, tok)
            except Exception as e:
                print("  !! فشل:", p, e)


if __name__ == "__main__":
    main()
