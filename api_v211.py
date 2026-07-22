"""HTB11 v2.10.2 hotfix.

Sửa triệt để lỗi `bad escape \\e at position 0` phát sinh từ các replacement
LaTeX trong re.sub của hàm sửa delimiter gốc.
"""
import re

import api as core
import api_v28 as layer


def _safe_repair_latex_delimiters(value: str) -> str:
    """Sửa delimiter LaTeX mà không dùng replacement string chứa backslash.

    Mọi replacement LaTeX đều đi qua lambda hoặc str.replace, vì replacement
    trực tiếp như r"\\end{cases}" có thể bị re.sub hiểu `\\e` là escape lỗi.
    """
    latex = (value or "").strip()
    if not latex:
        return latex

    latex = latex.replace(r"\left .", "").replace(r"\right .", "")

    left_n = len(re.findall(r"\\left\b", latex))
    right_n = len(re.findall(r"\\right\b", latex))
    if left_n != right_n:
        latex = re.sub(r"\\left\s*", lambda _: "", latex)
        latex = re.sub(r"\\right\s*", lambda _: "", latex)

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

    for env in ("cases", "aligned", "matrix", "pmatrix", "bmatrix", "Bmatrix", "vmatrix", "Vmatrix"):
        begin_token = "\\begin{" + env + "}"
        end_token = "\\end{" + env + "}"
        begin_count = latex.count(begin_token)
        end_count = latex.count(end_token)
        if begin_count > end_count:
            latex += " " + end_token * (begin_count - end_count)
        elif end_count > begin_count:
            # Không xóa nội dung; chỉ loại các end dư từ phải sang trái.
            for _ in range(end_count - begin_count):
                pos = latex.rfind(end_token)
                if pos >= 0:
                    latex = latex[:pos] + latex[pos + len(end_token):]

    return latex.strip()


# Patch cả module gốc và tên core mà lớp api_v28 đang sử dụng.
core._repair_latex_delimiters = _safe_repair_latex_delimiters
layer.core._repair_latex_delimiters = _safe_repair_latex_delimiters

core.app.version = "2.10.2"
app = core.app
