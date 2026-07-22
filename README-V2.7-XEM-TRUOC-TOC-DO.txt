HTB OCR V2.7

Đã sửa:
1. Trang có hệ phương trình, nguyên hàm, tích phân, ma trận sẽ tự ép OCR toán; trang chữ sạch vẫn lấy text layer để tăng tốc.
2. Vùng hệ phương trình được cắt theo đúng thứ tự dọc và dừng trước TS lớp/ĐS/bài tiếp theo.
3. Có fallback tạo \begin{cases}...\end{cases} khi Pix2Tex không trả đủ hai phương trình.
4. Cache kết quả công thức lặp lại; chế độ balanced chỉ thử tối đa 2 ảnh, giúp nhanh hơn quality.
5. API bọc các môi trường cases/aligned/array/matrix bằng $$ để frontend luôn render.
6. Frontend mới chờ MathJax tải xong, bảo vệ LaTeX trước marked và hiện lỗi render rõ ràng.

Railway khuyến nghị:
OCR_DPI=250
FORCE_OCR=0
FORMULA_OCR_MODE=balanced
FORMULA_MIN_HEIGHT=190
FORMULA_MAX_WIDTH=2200
FORMULA_EARLY_ACCEPT_SCORE=42
FORMULA_CACHE_SIZE=512
AUTO_BATCH_PAGES=10
MAX_PAGES=0
