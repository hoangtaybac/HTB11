HTB9 V2.6 - SỬA NHẬN DẠNG HỆ PHƯƠNG TRÌNH
===========================================

Nguyên nhân lỗi cũ:
- PaddleOCR thường không tạo bbox cho dấu ngoặc nhọn lớn của hệ.
- Vì không thấy dấu ngoặc, code không gộp hai phương trình thành một vùng 2D.
- Các phương trình bị đưa ra như văn bản thường, mất dấu hệ, phân số và bố cục.

Thay đổi trong api.py:
1. Dùng dòng "Giải hệ phương trình:" làm mốc bố cục.
2. Tự cắt nguyên vùng công thức ở bên phải nhãn, đến trước dòng TS/ĐS kế tiếp.
3. Không cho vùng hệ bị gộp nhầm trở lại với dòng chữ trong bước merge cùng hàng.
4. Đưa nguyên vùng 2D sang pix2tex và chuẩn hóa array/aligned thành cases.
5. Chỉ chấp nhận kết quả hệ khi có ít nhất hai quan hệ toán học.
6. Phiên bản API tăng lên 2.6.0.

Cấu hình Railway khuyến nghị:
OCR_DPI=300
FORMULA_OCR_MODE=quality
FORMULA_MIN_HEIGHT=220
FORMULA_MAX_WIDTH=2600
AUTO_BATCH_PAGES=10
MAX_PAGES=0
FORCE_OCR=1
PADDLE_LANG=vi

Sau khi cập nhật GitHub, hãy Redeploy Railway và kiểm tra /engine-status.
