BẢN SỬA LỖI DẤU TIẾNG VIỆT VÀ CÔNG THỨC - 22/07/2026

Đã sửa trong file: api.py

1. Không còn khử nhiễu ảnh xám quá mạnh vì bước này làm mất dấu sắc, huyền,
   hỏi, ngã, nặng và làm mờ các nét mảnh của số mũ.
2. Chỉ cân bằng ánh sáng nhẹ trên kênh sáng và làm nét nhẹ, giữ nguyên màu,
   kích thước và vị trí bbox.
3. Không gửi nguyên dòng câu văn như "Ví dụ 1: Phân tích..." sang pix2tex.
   Đây là nguyên nhân tạo ra các chuỗi sai kiểu "Widu", "Plian tich...".
4. Dòng có tiền tố "Ta có:", "Suy ra:", "Do đó:" được tách phần chữ và phần
   công thức. Chỉ phần bên phải được đưa sang mô hình nhận dạng công thức.
5. Bổ sung khôi phục dấu cho các cụm tiếng Việt thường gặp trong tài liệu toán:
   Các ví dụ minh họa, Ví dụ, Phân tích đa thức, thành nhân tử, Giải, Ta có,
   phương trình, hệ phương trình, điều kiện, rút gọn...
6. Siết điều kiện nhận dạng công thức để dòng văn bản có nhiều từ không bị
   nhận nhầm thành công thức.

Biến Railway nên đặt:
OCR_DPI=240
FORCE_OCR=0
PADDLE_LANG=vi
OCR_MIN_CONFIDENCE=0.30
USE_GPU=0
DISABLE_FORMULA_OCR=0
OCR_CPU_THREADS=1

Sau khi cập nhật, Railway cần Redeploy để tải lại model và mã nguồn.
