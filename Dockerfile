# خادم العرباوي — التعرف على الخطوط العربية من الصور
# البناء:  docker build -t arabawi .
# التشغيل: docker run -p 8000:8000 -v arabawi_data:/app/data -e ARABAWI_STORAGE_QUOTA_GB=500 arabawi
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ binutils curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-ocr.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# محرك OCR اختياري — احذف السطر التالي لو لا تريده (تبقى طريقة الإدخال اليدوي)
RUN pip install --no-cache-dir -r requirements-ocr.txt || true

COPY . .

# مكتبات CUDA وهمية لتشغيل PyTorch على CPU داخل الحاوية
RUN python3 tools/make_cuda_stubs.py /opt/cudastubs || true
ENV LD_LIBRARY_PATH=/opt/cudastubs
ENV ARABAWI_DATA_DIR=/app/data
ENV ARABAWI_STORAGE_QUOTA_GB=500
ENV ARABAWI_HOST=0.0.0.0
ENV ARABAWI_PORT=8000
VOLUME /app/data
EXPOSE 8000

# نزّل نماذج OCR عند أول إقلاع إن غابت (يتجاهل الفشل بصمت)
CMD sh -c "python3 tools/fetch_ocr_models.py || true; ./run_server.sh"
