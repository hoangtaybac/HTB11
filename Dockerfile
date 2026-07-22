FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PADDLE_LANG=vi \
    OCR_DPI=250 \
    FORCE_OCR=0 \
    USE_GPU=0 \
    DISABLE_FORMULA_OCR=0 \
    MAX_PAGES=0 \
    OCR_CPU_THREADS=1 \
    OCR_MIN_CONFIDENCE=0.30 \
    FORMULA_MAX_WIDTH=2400 \
    FORMULA_OCR_MODE=balanced \
    FORMULA_EARLY_ACCEPT_SCORE=42 \
    GC_EVERY_PAGES=5 \
    AUTO_BATCH_PAGES=10 \
    FORMULA_MIN_HEIGHT=200 \
    FORMULA_CACHE_SIZE=512 \
    MAX_UPLOAD_BYTES=524288000 \
    FLAGS_use_mkldnn=0 \
    FLAGS_use_onednn=0 \
    FLAGS_enable_pir_api=0 \
    FLAGS_enable_pir_in_executor=0 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential gcc g++ python3-dev pkg-config \
       pandoc libgl1 libglib2.0-0 libgomp1 libsm6 libxext6 libxrender1 \
       libjpeg62-turbo zlib1g \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "uvicorn api_v211:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
