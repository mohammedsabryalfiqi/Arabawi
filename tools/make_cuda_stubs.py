#!/usr/bin/env python3
"""بناء مكتبات CUDA وهمية (stubs) لتشغيل PyTorch على معالجCPU فقط.

حزم PyTGPU الرسمية على PyPI تربط ضد مكتبات NVIDIA غير الموجودة في بيئات CPU.
هذه الأداة تقرأ الرموز غير المعرّفة (undefined) من مكتبات torch وتولّد مكتبات
 ortak وهمية تحمل نفس الأسماء والإصدارات حتى ينجح الاستيراد ويعمل المحرك على CPU.

الاستخدام:  python3 tools/make_cuda_stubs.py [مسار_الإخراج]
"""
import os
import re
import subprocess
import sys
import glob
import collections
import importlib.util

_spec = importlib.util.find_spec("torch")
TORCH_LIB = os.path.join(_spec.submodule_search_locations[0], "lib")

KNOWN = {
    "libcublas.so.11", "libcublasLt.so.11", "libcudart.so.11.0", "libcufft.so.10",
    "libcurand.so.10", "libnvToolsExt.so.1", "libcudnn.so.8", "libcupti.so.11.7",
    "libcusparse.so.11", "libnccl.so.2", "libcusolver.so.11", "libnvjpeg.so.11",
    "libcudart.so.12", "libcublas.so.12", "libcublasLt.so.12", "libcufft.so.11",
    "libcurand.so.11", "libcusparse.so.12", "libcusolver.so.12", "libcudnn.so.9",
}

# Num: Value Size Type Bind Vis Ndx Name
SYM_RE = re.compile(r"^\s*\d+:\s+[0-9a-f]+\s+\d+\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.*)$")

PREFIX_MAP = [
    ("cublasLt", "libcublasLt.so.11"), ("cublas", "libcublas.so.11"),
    ("cudnn", "libcudnn.so.8"), ("curand", "libcurand.so.10"),
    ("cufft", "libcufft.so.10"), ("cusparse", "libcusparse.so.11"),
    ("cusolver", "libcusolver.so.11"), ("nvjpeg", "libnvjpeg.so.11"),
    ("nccl", "libnccl.so.2"), ("nvTools", "libnvToolsExt.so.1"),
    ("nvtx", "libnvToolsExt.so.1"), ("cupti", "libcupti.so.11.7"),
    ("cuda", "libcudart.so.11.0"),
]


def collect():
    need = collections.defaultdict(dict)  # soname -> {symbol: type}
    for lib in glob.glob(os.path.join(TORCH_LIB, "*.so*")):
        out = subprocess.run(["readelf", "-W", "--dyn-syms", lib],
                             capture_output=True, text=True).stdout
        for line in out.splitlines():
            m = SYM_RE.match(line)
            if not m:
                continue
            typ, _bind, _vis, ndx, name = m.groups()
            if ndx != "UND":
                continue
            if "@" not in name:
                # رموز بلا إصدار: نُسندُها لمكتبتها بادئةَ الاسم
                bare = name.split("@")[0]
                for pref, soname in PREFIX_MAP:
                    if bare.startswith(pref):
                        need[soname][bare] = typ
                        break
                continue
            sym, _, ver = name.partition("@")
            ver = ver.lstrip("@").split()[0]
            if ver in KNOWN and sym:
                need[ver][sym.split("@")[0]] = typ
    return need


def build(outdir):
    os.makedirs(outdir, exist_ok=True)
    need = collect()
    # كل مكتبات CUDA المطلوبة كـ DT_NEEDED يجب أن يوجد ملفها حتى لو بلا رموز
    for soname in KNOWN:
        need.setdefault(soname, {})
    for soname, syms in need.items():
        src = os.path.join(outdir, "stub.c")
        with open(src, "w") as f:
            f.write("/* stub symbols for %s */\n" % soname)
            for sym, typ in sorted(syms.items()):
                clean = sym.split("@")[0]
                if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", clean):
                    continue
                if typ == "OBJECT":
                    f.write("char %s[32];\n" % clean)
                else:
                    f.write("void %s(void){}\n" % clean)
        ver = os.path.join(outdir, "ver.map")
        with open(ver, "w") as f:
            f.write("%s { global: *; };\n" % soname)
        dst = os.path.join(outdir, soname)
        subprocess.run(["gcc", "-shared", "-fPIC", "-O0", "-o", dst,
                        "-Wl,-soname," + soname, "-Wl,--version-script=" + ver, src],
                       check=True)
        print("built", dst, "with", len(syms), "symbols")
    if not need:
        print("no symbols collected!")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "/home/user/cudastubs")
