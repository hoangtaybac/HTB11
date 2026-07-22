BẢN TỐI ƯU OCR PDF 100-500 TRANG
================================

FILE ĐÃ SỬA
- api.py
- Dockerfile

1. KHÔNG GIỚI HẠN SỐ TRANG
- MAX_PAGES=0: không chặn số trang.
- MAX_UPLOAD_BYTES=524288000: nhận file tối đa 500 MB.
- Có thể xử lý toàn bộ PDF hoặc chia đợt bằng:
  POST /ocr?start_page=1&end_page=20
  POST /ocr?start_page=21&end_page=40

2. GIẢM RAM
- Upload được ghi theo từng khối 1 MB xuống file tạm, không đọc toàn bộ file vào RAM.
- PDF được mở một lần và xử lý lần lượt từng trang.
- Ảnh từng trang được giải phóng ngay sau OCR.
- GC chạy theo chu kỳ 5 trang, không chạy quá dày gây chậm.
- Có thể gọi include_page_results=false để không trả bbox/block chi tiết, giúp JSON nhỏ hơn nhiều khi xử lý 100-500 trang.

3. TĂNG TỐC
- FORCE_OCR=0: trang nào có lớp chữ Unicode sạch sẽ lấy trực tiếp, không OCR ảnh.
- Trang có text sạch không còn bị render thành ảnh; đây là tối ưu lớn với PDF điện tử.
- FORMULA_OCR_MODE=fast: pix2tex chỉ chạy một lần cho mỗi công thức thay vì luôn chạy ba lần.
- Nếu cần chất lượng công thức cao hơn tốc độ, đặt FORMULA_OCR_MODE=balanced hoặc quality.
- OCR_DPI=200 là mức cân bằng tốc độ/chất lượng. Có thể tăng 220-240 cho bản scan mờ, nhưng sẽ chậm hơn và tốn RAM hơn.

4. KHUYẾN NGHỊ RAILWAY
- Dùng Dockerfile builder.
- Tối thiểu 4 GB RAM cho tài liệu dài; 8 GB tốt hơn nếu PDF scan nhiều công thức.
- Chỉ dùng 1 worker vì PaddleOCR và pix2tex rất nặng RAM.
- Với 100-500 trang scan, nên chia đợt 10-30 trang để tránh timeout HTTP của hạ tầng.
- Với PDF có text layer sạch, có thể xử lý nhiều trang hơn mỗi đợt.

5. THAM SỐ HỮU ÍCH
- include_page_results=false: giảm dung lượng phản hồi.
- start_page, end_page: chia PDF thành từng đợt.
- FORMULA_OCR_MODE=fast|balanced|quality|off.
- FORCE_OCR=0: tự dùng text layer sạch; đặt 1 chỉ khi bắt buộc OCR mọi trang.

LƯU Ý
Không thể đảm bảo một request duy nhất chạy hết 500 trang scan trên mọi gói Railway vì còn phụ thuộc CPU, RAM và timeout. Code đã bỏ giới hạn và giữ RAM ổn định; cách an toàn nhất cho 100-500 trang là frontend tự gọi theo từng đợt rồi ghép kết quả.
