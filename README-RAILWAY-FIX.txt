BẢN SỬA RAILWAY - PADDLEOCR CPU

Đã sửa:
1. Khóa PaddlePaddle 3.2.2 và PaddleOCR 3.3.2 để tránh tự nâng phiên bản gây lỗi.
2. Tắt oneDNN/MKLDNN và PIR trước khi import PaddleOCR.
3. Khởi tạo PaddleOCR 3.x bằng device=cpu, enable_mkldnn=False.
4. predict(image) không truyền cls.
5. Giữ tương thích dự phòng với PaddleOCR 2.x.
6. Bổ sung compiler trong Dockerfile và .dockerignore.

Cách triển khai:
- Đẩy toàn bộ file trong thư mục này lên thư mục gốc GitHub.
- Railway: Deployments -> Redeploy -> Clear build cache and deploy.
- Không giữ requirements.txt cũ.
- Thử PDF/ảnh 1 trang trước.

API:
https://mathpix-production.up.railway.app/ocr
Phương thức: POST multipart/form-data, trường file.

Kiểm tra:
https://mathpix-production.up.railway.app/
https://mathpix-production.up.railway.app/engine-status
https://mathpix-production.up.railway.app/docs
