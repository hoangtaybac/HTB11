# HTB11 – OCR toán PDF/ảnh

Bản hiện tại chạy qua `api_v28.py` và giữ nguyên lõi `api.py`.

## Nội dung đã sửa

- Mở rộng vùng cắt hệ phương trình để giữ dấu ngoặc, phân số và phương trình cuối.
- Dừng vùng cắt trước dòng `TS lớp`, `ĐS` hoặc số bài tiếp theo.
- Tự dựng `\begin{cases}...\end{cases}` khi pix2tex không nhận đủ cấu trúc.
- Giao diện `index.html` bảo vệ LaTeX trước khi chuyển Markdown.
- Không còn ẩn đoạn đầu tiên của phần xem trước.
- Chờ MathJax tải xong trước khi render.
- PDF dài tự chia batch; trang có text layer tốt không bị OCR lại toàn bộ.

## Railway

Railway phải build bằng `Dockerfile`. Lệnh chạy hiện tại:

```bash
uvicorn api_v28:app --host 0.0.0.0 --port $PORT --workers 1
```

Biến môi trường khuyến nghị:

```env
OCR_DPI=250
FORCE_OCR=0
FORMULA_OCR_MODE=balanced
FORMULA_MAX_WIDTH=2400
FORMULA_MIN_HEIGHT=200
AUTO_BATCH_PAGES=10
MAX_PAGES=0
DISABLE_FORMULA_OCR=0
USE_GPU=0
OCR_CPU_THREADS=1
```

API chính: `POST /ocr`.
