#!/bin/sh
# تشغيل خادم العرباوي — مع تفعيل مسار مكتبات CPU stubs إن وُجدت
STUBS="${ARABAWI_CUDA_STUBS:-/home/user/cudastubs}"
if [ -d "$STUBS" ]; then
  export LD_LIBRARY_PATH="$STUBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
export ARABAWI_HOST="${ARABAWI_HOST:-0.0.0.0}"
export ARABAWI_PORT="${ARABAWI_PORT:-${PORT:-8000}}"
exec python3 -m uvicorn server.main:app --host "$ARABAWI_HOST" --port "$ARABAWI_PORT"
