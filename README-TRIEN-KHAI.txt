BẢN RAILWAY KHÔNG DÙNG MISTRAL API

API OCR:
https://mathpix-production.up.railway.app/ocr

Kiểm tra server:
https://mathpix-production.up.railway.app/health

Các thiết lập mặc định:
- Python 3.10
- PaddlePaddle 2.6.2
- PaddleOCR 2.9.1
- pix2tex 0.1.4
- FORCE_OCR=0 để tự dùng text layer sạch và chỉ OCR trang có text layer lỗi
- OCR_DPI=180
- MAX_PAGES=0
- DISABLE_FORMULA_OCR=0

Cách triển khai:
1. Đưa toàn bộ file trong thư mục này lên thư mục gốc GitHub.
2. Railway > Deployments > Redeploy > Clear build cache and deploy.
3. Chờ /health trả về {"ok":true,...}.
4. Thử ảnh hoặc PDF 1 trang trước.

Lưu ý:
- Đây là OCR chạy cục bộ trên Railway, không cần MISTRAL_API_KEY.
- pix2tex và PaddleOCR dùng nhiều RAM. Gói Railway RAM thấp có thể bị dừng khi xử lý PDF lớn.
- Muốn xử lý nhiều trang, tăng MAX_PAGES sau khi thử ổn định.
