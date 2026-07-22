HOÀNG TÂY BẮC LOCAL MATH OCR 2.0
================================

Bản này KHÔNG gọi Mistral/Mathpix hay API OCR bên ngoài.

Luồng xử lý:
- PDF có lớp chữ tốt: đọc trực tiếp bằng PyMuPDF.
- PDF scan/ảnh: PaddleOCR tiếng Việt chạy ngay trên máy chủ.
- Dòng nghi là công thức: pix2tex nhận dạng thành LaTeX.
- Xuất Word: Pandoc chuyển LaTeX thành Equation OMML thật.

API:
- POST /ocr
- GET /engine-status
- POST /export-docx
- POST /export-docx-preview

Biến môi trường:
- USE_GPU=0 hoặc 1
- OCR_DPI=220 (có thể tăng 260-300 nếu ảnh nhỏ, đổi lại chậm và tốn RAM)
- FORCE_OCR=0: ưu tiên lớp chữ PDF; đặt 1 để OCR toàn bộ trang
- DISABLE_FORMULA_OCR=0: đặt 1 để chỉ OCR chữ
- MAX_PAGES=0: 0 là không giới hạn
- MAX_UPLOAD_BYTES=104857600
- PADDLE_LANG=vi

LƯU Ý TRIỂN KHAI:
- Mô hình OCR nội bộ nặng hơn rất nhiều so với gọi API.
- Railway gói RAM thấp có thể bị hết bộ nhớ hoặc timeout khi xử lý PDF dài.
- Khuyến nghị VPS tối thiểu 8 GB RAM; tốt hơn là máy có NVIDIA GPU 8 GB VRAM.
- Lần chạy đầu mô hình có thể tải trọng số, nên cần ổ đĩa lưu bền hoặc build sẵn model.
- PDF 160 trang nên xử lý theo từng phần 10-20 trang để ổn định ở bản đầu.

ĐỘ CHÍNH XÁC:
Đây là bản nền tảng chạy hoàn toàn nội bộ, chưa thể ngang Mathpix thương mại ngay lập tức.
Cần tiếp tục huấn luyện/tinh chỉnh trên đề Toán Việt Nam và bổ sung mô hình phân tích bố cục.
