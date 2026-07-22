BẢN 2.3.0 - SỬA DẤU TIẾNG VIỆT, SỐ MŨ/CHỈ SỐ VÀ TỰ CHIA BATCH

Các file đã sửa:
- api.py
- Dockerfile

Nâng cấp chính:
1. Tách phần văn xuôi và công thức ở cùng một dòng. Ví dụ dòng “Ví dụ 2: ...: x^8+98x^4+1” không còn bị PaddleOCR nhận cả công thức như chữ thường.
2. Khôi phục dấu tiếng Việt bằng chuẩn hóa không dấu + đối sánh gần cho các từ toán học thường gặp.
3. Nhận cả các lỗi OCR như “Ta cos”, “Ta c0” và đổi thành “Ta có:”.
4. Cắt công thức tại khe trắng sau tiền tố, tránh cắt mất ký tự đầu và số mũ.
5. Phóng lớn vùng công thức thấp lên tối thiểu 120 px trước Pix2Tex, thêm viền và chạy chế độ balanced để giảm mất số mũ/chỉ số dưới.
6. PDF tự chia batch mặc định 20 trang. Sau mỗi batch giải phóng ảnh và gc để giữ RAM ổn định. Không có giới hạn cứng số trang khi MAX_PAGES=0.

Thiết lập Railway khuyến nghị:
OCR_DPI=240
PADDLE_LANG=vi
FORCE_OCR=0
MAX_PAGES=0
AUTO_BATCH_PAGES=20
FORMULA_OCR_MODE=balanced
FORMULA_MIN_HEIGHT=120
OCR_CPU_THREADS=1
USE_GPU=0

Gọi API:
POST /ocr?batch_size=0&include_page_results=false
- batch_size=0: tự dùng AUTO_BATCH_PAGES.
- Có thể đặt batch_size=10..50 tùy RAM Railway.
- include_page_results=false giúp JSON nhỏ hơn nhiều với sách 100-500 trang.

Lưu ý: tự chia batch trong một request giữ RAM ổn định nhưng một PDF scan 500 trang vẫn có thể vượt thời gian tối đa của HTTP/Railway. Khi đó frontend nên gọi lần lượt start_page/end_page theo batch và ghép kết quả. API hiện vẫn hỗ trợ start_page/end_page.
