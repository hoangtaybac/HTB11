BẢN 2.4 - SỬA SỐ MŨ, CHỈ SỐ TRÊN/DƯỚI VÀ PDF DÀI

Các thay đổi chính trong api.py:
1. Gộp các bbox PaddleOCR nằm cùng một hàng trước khi đưa sang pix2tex.
   Việc này tránh công thức bị tách thành nhiều mảnh, làm mất x^4, x_1, a_n.
2. Tăng vùng đệm theo cả chiều trên/dưới và trái/phải quanh công thức.
3. Phóng ảnh công thức lên tối thiểu 180 px chiều cao.
4. Chế độ quality thử nhiều biến thể ảnh và không nhận sớm kết quả đầu tiên.
5. Cắt phần chữ “Ta có:” bằng khe trắng nhưng vẫn giữ thêm 10 px bên trái.
6. PDF vẫn tự chia batch, mặc định 15 trang/batch, MAX_PAGES=0.

Biến Railway khuyến nghị:
OCR_DPI=260
FORMULA_OCR_MODE=quality
FORMULA_MIN_HEIGHT=180
FORMULA_MAX_WIDTH=2200
FORMULA_EARLY_ACCEPT_SCORE=34
AUTO_BATCH_PAGES=15
MAX_PAGES=0
FORCE_OCR=0
PADDLE_LANG=vi

Lưu ý: quality chính xác hơn nhưng chậm hơn balanced. Với sách 100-500 trang,
frontend nên gọi từng khoảng start_page/end_page 10-20 trang để tránh timeout HTTP.
Code phía server vẫn tự giải phóng RAM sau mỗi batch.

=== BỔ SUNG V2.5: HỆ PHƯƠNG TRÌNH, TÍCH PHÂN, CẬN TRÊN/DƯỚI ===
- Gộp nhiều bbox theo chiều dọc thành một vùng công thức 2D trước khi gọi Pix2Tex.
- Nhận dạng hệ 2, 3, 4 ẩn bằng cases/aligned thay vì OCR từng dòng rời.
- Giữ nguyên cận trên, cận dưới của tích phân, tổng và tích.
- Tự sửa LaTeX mất cặp \\left/\\right để tránh lỗi MathJax:
  Extra \\left or missing \\right.
- Tự cân bằng các môi trường cases, aligned, matrix, pmatrix, bmatrix.

Biến Railway khuyến nghị:
OCR_DPI=300
FORMULA_OCR_MODE=quality
FORMULA_MIN_HEIGHT=220
FORMULA_MAX_WIDTH=2600
AUTO_BATCH_PAGES=10
MAX_PAGES=0
