BẢN SỬA XUẤT WORD EQUATION

- Toàn bộ công thức có delimiters $...$, $$...$$, \(...\), \[...\] được chuẩn hóa.
- Tự bọc các môi trường cases, aligned, matrix, pmatrix, bmatrix... nếu OCR thiếu delimiters.
- Pandoc chuyển công thức sang Office MathML (OMML), tức Equation thật của Microsoft Word.
- Sau khi tạo DOCX, server kiểm tra document.xml. Nếu còn LaTeX thô như \frac, \sqrt, \begin{cases}, hệ thống báo lỗi thay vì trả file sai.
- Công thức có thể bấm vào và chỉnh sửa trực tiếp trong Word.

Railway phải build bằng Dockerfile để có Pandoc.
Bản hiện tại không cần MISTRAL_API_KEY; OCR chạy cục bộ bằng PaddleOCR và pix2tex.
