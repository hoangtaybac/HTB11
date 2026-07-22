BẢN 2.1 - OCR TOÁN CHUYÊN DỤNG, KHÔNG DÙNG MISTRAL

Các nâng cấp chính:
1. PaddleOCR chuyên đọc chữ tiếng Việt sau bước khử nhiễu và tăng tương phản.
2. pix2tex chuyên nhận dạng vùng công thức toán.
3. Mỗi vùng công thức được thử trên 3 biến thể ảnh: gốc, tăng tương phản, nhị phân.
4. Tự chấm điểm và loại kết quả LaTeX rác như lặp quá nhiều \\qquad, \\sqrt.
5. Công thức dài được bọc dạng display $$...$$; công thức ngắn dùng $...$.
6. Lọc mẩu OCR có độ tin cậy rất thấp.
7. FORCE_OCR=0 để tự dùng lớp chữ sạch; code sẽ OCR lại trang có lớp chữ lỗi.
8. Xuất DOCX tiếp tục dùng Pandoc để tạo Word Equation OMML thật.

Railway Variables khuyến nghị:
OCR_DPI=220
FORCE_OCR=0
USE_GPU=0
DISABLE_FORMULA_OCR=0
OCR_CPU_THREADS=1
OCR_MIN_CONFIDENCE=0.30
FORMULA_MAX_WIDTH=1600
MAX_PAGES=0

Lưu ý tài nguyên:
- PaddleOCR + pix2tex khá nặng. Nên dùng Railway RAM tối thiểu 4 GB.
- Thử PDF 1-3 trang trước.
- Với tài liệu dài, gọi /ocr?start_page=1&end_page=3 rồi xử lý theo từng đợt.
