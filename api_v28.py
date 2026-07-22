"""HTB11 v2.9.1 compatibility layer.

Giữ nguyên backend api.py hiện tại nhưng thay các hàm nhận dạng vùng hệ phương
trình bằng phiên bản ổn định hơn. Railway khởi động module này qua Dockerfile.
"""
import re
from typing import Any, Dict, List, Optional

import api as core

# Lưu tham chiếu tới hàm gốc TRƯỚC khi monkey-patch.
# Nếu gọi core._clean_ocr_text sau khi đã gán lại, Python sẽ gọi chính wrapper
# này vô hạn và phát sinh "maximum recursion depth exceeded".
_ORIGINAL_CLEAN_OCR_TEXT = core._clean_ocr_text


def _inject_anchored_system_regions(lines: List[Dict[str, Any]], page_width: int) -> List[Dict[str, Any]]:
    """Cắt toàn bộ vùng 2D nằm sau nhãn 'Giải hệ phương trình'."""
    if not lines:
        return []
    original = sorted((dict(x) for x in lines), key=lambda x: (x["bbox"][1], x["bbox"][0]))
    consumed = set()
    synthetic: List[Dict[str, Any]] = []
    stop_re = re.compile(
        r"^(?:TS\s+lớp|TS\s+lop|ĐS|DS|Đáp\s+số|Dap\s+so|\d+(?:\.\d+)+\b|Giải\s+hệ|Giai\s+he)",
        re.I,
    )

    for ai, anchor in enumerate(original):
        folded = core._ascii_fold(anchor.get("text", ""))
        if "giai he phuong trinh" not in folded and "he phuong trinh" not in folded:
            continue

        _, ay1, ax2, ay2 = anchor["bbox"]
        h = max(8.0, ay2 - ay1)
        left = max(0.0, min(page_width - 30.0, ax2 - h * 0.10))
        right = min(page_width * 0.84, left + page_width * 0.54)
        top = max(0.0, ay1 - h * 0.85)
        bottom = min(ay1 + h * 10.0, ay1 + page_width * 0.42)

        for k in range(ai + 1, len(original)):
            item = original[k]
            bx1, by1, _, _ = item["bbox"]
            if by1 <= ay2 + h * 0.25:
                continue
            txt = (item.get("text") or "").strip()
            folded_txt = core._ascii_fold(txt)
            if (stop_re.match(txt) or folded_txt.startswith(("ts lop", "ds", "dap so"))) and bx1 < page_width * 0.80:
                bottom = min(bottom, by1 - h * 0.20)
                break

        bottom = max(ay2 + h * 1.8, bottom)
        selected = []
        for k, item in enumerate(original):
            if k == ai or k in consumed:
                continue
            bx1, by1, bx2, by2 = item["bbox"]
            cy = (by1 + by2) / 2
            if top <= cy <= bottom and bx2 >= left - h * 0.70 and bx1 <= right:
                txt = (item.get("text") or "").strip()
                if core._natural_word_count(txt) >= 3 and not core._looks_like_math_line_text(txt):
                    continue
                selected.append((k, item))

        if bottom - top <= h * 1.4:
            continue
        for k, _ in selected:
            consumed.add(k)
        synthetic.append({
            "bbox": [max(0.0, left - h * 0.75), top, right, bottom],
            "text": "\n".join(x.get("text", "") for _, x in selected),
            "confidence": sum(float(x.get("confidence", 0)) for _, x in selected) / max(1, len(selected)),
            "multiline_math": True,
            "system_math": True,
            "merged_parts": len(selected),
        })

    result = [item for i, item in enumerate(original) if i not in consumed] + synthetic
    result.sort(key=lambda x: (x["bbox"][1], x["bbox"][0]))
    return result


def _normalize_system_latex(latex: str) -> str:
    value = core._repair_latex_delimiters(latex or "").strip()
    if not value:
        return value
    value = re.sub(r"\$+", "", value).strip()
    value = re.sub(r"\\left\s*\\\{\s*", "", value)
    value = re.sub(r"\\right\s*[.}]?\s*$", "", value)
    value = re.sub(r"\\begin\{array\}(?:\{[^}]*\})?", r"\begin{cases}", value)
    value = value.replace(r"\end{array}", r"\end{cases}")
    value = re.sub(r"\\begin\{aligned\}", r"\begin{cases}", value)
    value = re.sub(r"\\end\{aligned\}", r"\end{cases}", value)
    if r"\begin{cases}" not in value and len(re.findall(r"=|\\le|\\ge|\\neq|<|>", value)) >= 2:
        rows = [x.strip() for x in re.split(r"\\\\|\n", value) if x.strip()]
        if len(rows) >= 2:
            value = r"\begin{cases}" + r"\\".join(rows[:4]) + r"\end{cases}"
    return core._repair_latex_delimiters(value)


_VI_PROPER_NOUN_PATTERNS = [
    (r"(?i)\bda\s*nang\b", "Đà Nẵng"),
    (r"(?i)\bda\s*na[nm]g\b", "Đà Nẵng"),
    (r"(?i)\bđa\s*nang\b", "Đà Nẵng"),
    (r"(?i)\bđa\s*năng\b", "Đà Nẵng"),
    (r"(?i)\bđa\s*nắng\b", "Đà Nẵng"),
    (r"(?i)\bbinh\s*thuan\b", "Bình Thuận"),
    (r"(?i)\bbac\s*giang\b", "Bắc Giang"),
    (r"(?i)\btphcm\b", "TPHCM"),
]


def _restore_vietnamese_proper_nouns(text: str) -> str:
    value = text or ""
    for pattern, replacement in _VI_PROPER_NOUN_PATTERNS:
        value = re.sub(pattern, replacement, value)
    return value


def _clean_ocr_text(text: str) -> str:
    # Gọi đúng hàm gốc đã lưu, không gọi core._clean_ocr_text sau monkey-patch.
    cleaned = _ORIGINAL_CLEAN_OCR_TEXT(text)
    return _restore_vietnamese_proper_nouns(cleaned)


def _clean_system_ocr_text(text: str) -> str:
    value = (text or "").replace("−", "-").replace("×", r"\times ")
    value = re.sub(r"(?i)\b(?:giai|giải)\s+(?:he|hệ)\s+(?:phuong|phương)\s+(?:trinh|trình)\s*:?", "", value)
    value = re.sub(r"(?i)\bTS\s+(?:lop|lớp)\b.*$", "", value)
    value = re.sub(r"(?i)\b(?:DS|ĐS|Dap\s+so|Đáp\s+số)\b.*$", "", value)
    return value.strip()


def _equations_from_ocr_text(text: str) -> List[str]:
    """Dựng hệ từ OCR chữ khi pix2tex không đọc được toàn vùng."""
    raw = _clean_system_ocr_text(text)
    candidates = re.split(
        r"\n+|\s{2,}|(?<=[0-9A-Za-z\)\]])\s+(?=[+\-]?(?:\d|[A-Za-z]|\\frac|\())",
        raw,
    )
    equations: List[str] = []
    for value in candidates:
        value = value.strip(" ;,{}[]")
        if not value or "=" not in value:
            continue
        if re.search(r"(?i)\b(?:TS|DS|ĐS|lop|lớp)\b", value):
            continue
        natural = core._natural_word_count(value)
        if natural > 1 and not re.search(r"\\frac|/|[|√]", value):
            continue
        value = re.sub(r"\s+", "", value)
        if 3 <= len(value) <= 160 and value not in equations:
            equations.append(value)
    return equations[:4]


def _fallback_system_latex(text: str) -> Optional[str]:
    equations = _equations_from_ocr_text(text)
    if len(equations) < 2:
        return None
    return r"\begin{cases}" + r"\\".join(equations) + r"\end{cases}"


def _recognize_system_formula(crop, ocr_text: str = "") -> Optional[str]:
    latex = core._recognize_formula(crop, structural=True)
    fallback = _fallback_system_latex(ocr_text)
    if not latex:
        return fallback
    latex = _normalize_system_latex(latex)
    relation_count = len(re.findall(r"=|\\le|\\ge|\\neq|<|>", latex))
    row_count = len(re.findall(r"\\\\", latex)) + (1 if relation_count else 0)
    bad_table = bool(re.search(r"\\begin\{(?:array|matrix|tabular)\}.*?\bx\b.*?\\\\.*?\by\b", latex, re.S))
    if relation_count < 2 or row_count < 2 or bad_table:
        return fallback
    return latex


core._inject_anchored_system_regions = _inject_anchored_system_regions
core._clean_ocr_text = _clean_ocr_text
core._equations_from_ocr_text = _equations_from_ocr_text
core._fallback_system_latex = _fallback_system_latex
core._normalize_system_latex = _normalize_system_latex
core._recognize_system_formula = _recognize_system_formula
core.app.version = "2.9.1"

app = core.app
