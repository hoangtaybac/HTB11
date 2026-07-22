CÁC FILE ĐÃ SỬA ĐỂ NHẬN PDF HƠN 100 TRANG
===========================================

1) Dockerfile
- Đổi MAX_PAGES=5 thành MAX_PAGES=0 (không giới hạn số trang).
- Đổi FORCE_OCR=1 thành FORCE_OCR=0 để trang có lớp chữ Unicode sạch được đọc trực tiếp, nhanh hơn OCR.
- Tăng MAX_UPLOAD_BYTES lên 500 MB.

2) api.py
- Bỏ chặn cứng 5 trang.
- Đọc số trang bằng PyMuPDF, tránh mở PDF thêm bằng PyPDF2.
- Render/xử lý từng trang và giải phóng ảnh sau từng trang để hạn chế tràn RAM.
- Thêm tham số start_page và end_page cho endpoint /ocr.
  Ví dụ: POST /ocr?start_page=1&end_page=20
  Sau đó: POST /ocr?start_page=21&end_page=40
- Kết quả bổ sung total_pages, start_page, end_page và elapsed_seconds.

CẬP NHẬT LÊN GITHUB
- Ít nhất thay 2 file: api.py và Dockerfile.
- Có thể tải toàn bộ thư mục này lên GitHub để chắc chắn đồng bộ.

LƯU Ý
- MAX_PAGES=0 cho phép xử lý toàn bộ tài liệu, nhưng OCR 100 trang vẫn phụ thuộc CPU/RAM và thời gian chờ của Railway.
- Với tài liệu rất dài, nên gọi theo từng đợt 10-20 trang bằng start_page/end_page để tránh request chạy quá lâu.
