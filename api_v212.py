"""HTB11 v2.12.0 stable layer.

Khôi phục luồng OCR gốc để tránh cắt nhầm cả dòng TS/ĐS vào công thức.
Chỉ giữ hai bản vá an toàn: sửa LaTeX không dùng replacement escape của re.sub
và khôi phục một số địa danh tiếng Việt thường bị OCR mất dấu.
"""
import re
import api as core

_ORIGINAL_CLEAN_OCR_TEXT = core._clean_ocr_text


def _safe_repair_latex_delimiters(value: str) -> str:
    latex = (value or "").strip()
    if not latex:
        return latex

    latex = latex.replace(r"\left .", "").replace(r"\right .", "")

    left_n = len(re.findall(r"\\left\b", latex))
    right_n = len(re.findall(r"\\right\b", latex))
    if left_n != right_n:
        latex = re.sub(r"\\left\s*", "", latex)
        latex = re.sub(r"\\right\s*", "", latex)

    # Không truyền chuỗi LaTeX trực tiếp làm replacement của re.sub.
    latex = re.sub(
        r"\\left\s*\\\{\s*\\begin\{array\}(?:\{[^}]*\})?",
        lambda _: r"\begin{cases}",
        latex,
    )
    latex = re.sub(
        r"\\end\{array\}\s*\\right\s*[.}]?",
        lambda _: r"\end{cases}",
        latex,
    )
    latex = re.sub(
        r"\\begin\{array\}\{[^}]*\}",
        lambda _: r"\begin{aligned}",
        latex,
    )
    latex = latex.replace(r"\end{array}", r"\end{aligned}")

    for env in ("cases", "aligned", "matrix", "pmatrix", "bmatrix"):
        begin_n = len(re.findall(rf"\\begin\{{{env}\}}", latex))
        end_n = len(re.findall(rf"\\end\{{{env}\}}", latex))
        if begin_n > end_n:
            latex += " " + (r"\end{" + env + "}") * (begin_n - end_n)

    return latex.strip()


_PROPER_NOUNS = [
    (r"(?i)\bda\s*na(?:ng|mg|nq)\b", "Đà Nẵng"),
    (r"(?i)\bđa\s*n(?:a|ă|ắ|â)ng\b", "Đà Nẵng"),
    (r"(?i)\bbinh\s*thuan\b", "Bình Thuận"),
    (r"(?i)\bbac\s*giang\b", "Bắc Giang"),
    (r"(?i)\btphcm\b", "TPHCM"),
]


def _clean_ocr_text(text: str) -> str:
    value = _ORIGINAL_CLEAN_OCR_TEXT(text)
    for pattern, replacement in _PROPER_NOUNS:
        value = re.sub(pattern, replacement, value)
    return value


# Chỉ monkey-patch các hàm an toàn. Không thay logic cắt vùng hệ phương trình.
core._repair_latex_delimiters = _safe_repair_latex_delimiters
core._clean_ocr_text = _clean_ocr_text
core.app.version = "2.12.0"

app = core.app
