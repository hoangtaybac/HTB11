"""HTB11 v2.10.0 compatibility layer.

Tăng độ ổn định khi nhận dạng hệ phương trình có phân số, trị tuyệt đối và căn.
Railway khởi động module này qua Dockerfile.
"""
import re
from typing import Any, Dict, List, Optional

import api as core

# Lưu hàm gốc trước khi monkey-patch để tránh đệ quy vô hạn.
_ORIGINAL_CLEAN_OCR_TEXT = core._clean_ocr_text
_ORIGINAL_RECOGNIZE_FORMULA = core._recognize_formula


def _inject_anchored_system_regions(lines: List[Dict[str, Any]], page_width: int) -> List[Dict[str, Any]]:
    """Cắt đúng vùng 2D sau nhãn “Giải hệ phương trình”.

    Không dùng tiêu đề chương làm mỏ neo. Chỉ tạo vùng hệ khi tìm được ít nhất hai
    mảnh toán, đồng thời dừng trước TS lớp, ĐS và số bài kế tiếp.
    """
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
        anchor_text = (anchor.get("text") or "").strip()
        folded = core._ascii_fold(anchor_text)
        if "he phuong trinh" not in folded:
            continue
        # Loại tiêu đề “Chủ đề 4. Hệ phương trình” và dòng mục lớn.
        if "chu de" in folded or ("giai he phuong trinh" in folded and len(anchor_text) > 42):
            continue

        _, ay1, ax2, ay2 = anchor["bbox"]
        h = max(8.0, ay2 - ay1)
        # Lùi sang trái đủ để giữ toàn bộ ngoặc hệ; không ăn lại phần chữ nhãn.
        left = max(0.0, min(page_width - 30.0, ax2 - h * 0.45))
        right = min(page_width * 0.82, left + page_width * 0.48)
        top = max(0.0, ay1 - h * 0.55)
        bottom = min(ay1 + h * 8.5, ay1 + page_width * 0.34)

        for k in range(ai + 1, len(original)):
            item = original[k]
            bx1, by1, _, _ = item["bbox"]
            if by1 <= ay2 + h * 0.20:
                continue
            txt = (item.get("text") or "").strip()
            folded_txt = core._ascii_fold(txt)
            is_stop = bool(stop_re.match(txt)) or folded_txt.startswith(("ts lop", "ds", "dap so"))
            if is_stop and bx1 < page_width * 0.82:
                bottom = min(bottom, by1 - h * 0.12)
                break

        bottom = max(ay2 + h * 1.65, bottom)
        selected = []
        for k, item in enumerate(original):
            if k == ai or k in consumed:
                continue
            bx1, by1, bx2, by2 = item["bbox"]
            cy = (by1 + by2) / 2
            if top <= cy <= bottom and bx2 >= left - h * 0.40 and bx1 <= right:
                txt = (item.get("text") or "").strip()
                if core._natural_word_count(txt) >= 3 and not core._looks_like_math_line_text(txt):
                    continue
                selected.append((k, item))

        # Không tạo vùng rỗng hoặc chỉ có một mẩu x/y rời.
        relation_parts = sum(1 for _, x in selected if re.search(r"=|≤|≥|<|>", x.get("text", "")))
        if len(selected) < 2 and relation_parts < 2:
            continue

        for k, _ in selected:
            consumed.add(k)
        synthetic.append({
            "bbox": [max(0.0, left - h * 0.45), top, right, bottom],
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
    value = re.sub(r"\\begin\{array\}(?:\{[^}]*\})?", r"\\begin{cases}", value)
    value = value.replace(r"\end{array}", r"\end{cases}")
    value = re.sub(r"\\begin\{aligned\}", r"\\begin{cases}", value)
    value = re.sub(r"\\end\{aligned\}", r"\\end{cases}", value)

    # Chuẩn hóa trị tuyệt đối và căn để MathJax/Word không làm mất ký hiệu.
    value = re.sub(r"(?<!\\)\|\s*([^|]+?)\s*\|", r"\\left|\1\\right|", value)
    value = re.sub(r"\\sqrt\s+([A-Za-z0-9]+)", r"\\sqrt{\1}", value)

    if r"\begin{cases}" not in value and len(re.findall(r"=|\\le|\\ge|\\neq|<|>", value)) >= 2:
        rows = [x.strip() for x in re.split(r"\\\\|\n", value) if x.strip()]
        if len(rows) >= 2:
            value = r"\begin{cases}" + r"\\".join(rows[:4]) + r"\end{cases}"
    return core._repair_latex_delimiters(value)


_VI_PROPER_NOUN_PATTERNS = [
    (r"(?i)\bda\s*na(?:ng|mg|nq)\b", "Đà Nẵng"),
    (r"(?i)\bđa\s*n(?:a|ă|ắ|â)ng\b", "Đà Nẵng"),
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
    return _restore_vietnamese_proper_nouns(_ORIGINAL_CLEAN_OCR_TEXT(text))


def _clean_system_ocr_text(text: str) -> str:
    value = (text or "").replace("−", "-").replace("×", r"\times ")
    value = re.sub(r"(?i)\b(?:giai|giải)\s+(?:he|hệ)\s+(?:phuong|phương)\s+(?:trinh|trình)\s*:?", "", value)
    value = re.sub(r"(?i)\bTS\s+(?:lop|lớp)\b.*$", "", value, flags=re.M)
    value = re.sub(r"(?i)\b(?:DS|ĐS|Dap\s+so|Đáp\s+số)\b.*$", "", value, flags=re.M)
    return value.strip()


def _equations_from_ocr_text(text: str) -> List[str]:
    """Fallback chỉ dùng với hai phương trình tuyến tính sạch.

    Không ghép các mẩu phân số rời (3, 4, x, y), vì điều đó tạo kết quả sai nặng.
    Hệ phân số/căn/trị tuyệt đối phải ưu tiên mô hình ảnh chuyên dụng.
    """
    raw = _clean_system_ocr_text(text)
    equations: List[str] = []
    for value in re.split(r"\n+|\s{2,}", raw):
        value = value.strip(" ;,{}[]")
        if not value or value.count("=") != 1:
            continue
        if re.search(r"(?i)\b(?:TS|DS|ĐS|lop|lớp)\b", value):
            continue
        # Không fallback cho phân số/căn/trị tuyệt đối bị OCR tách vụn.
        if re.search(r"[/√]|\\frac|\\sqrt|\|", value):
            continue
        value = re.sub(r"\s+", "", value)
        if not re.fullmatch(r"[0-9A-Za-z+\-().=^]+", value):
            continue
        if len(re.findall(r"[A-Za-z]", value)) < 1:
            continue
        if 3 <= len(value) <= 100 and value not in equations:
            equations.append(value)
    return equations[:4]


def _fallback_system_latex(text: str) -> Optional[str]:
    equations = _equations_from_ocr_text(text)
    if len(equations) < 2:
        return None
    return r"\begin{cases}" + r"\\".join(equations) + r"\end{cases}"


def _tighten_system_crop(crop):
    """Cắt mép trắng, giữ ngoặc hệ và thêm viền để pix2tex nhìn rõ cấu trúc 2D."""
    try:
        from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps
        img = crop.convert("L")
        # Làm tương phản nhẹ, không threshold mạnh để giữ dấu căn và vạch phân số.
        img = ImageEnhance.Contrast(img).enhance(1.35)
        inv = ImageOps.invert(img)
        bbox = inv.point(lambda p: 255 if p > 28 else 0).getbbox()
        if bbox:
            x1, y1, x2, y2 = bbox
            pad_x, pad_y = 30, 24
            x1, y1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
            x2, y2 = min(img.width, x2 + pad_x), min(img.height, y2 + pad_y)
            img = img.crop((x1, y1, x2, y2))
        img = ImageOps.expand(img, border=(42, 30, 42, 30), fill=255)
        if img.height < 260:
            scale = 260.0 / max(1, img.height)
            img = img.resize((max(80, int(img.width * scale)), 260), Image.Resampling.LANCZOS)
        img = img.filter(ImageFilter.SHARPEN)
        return img.convert("RGB")
    except Exception:
        return crop


def _system_complexity(crop, ocr_text: str) -> Dict[str, bool]:
    text = ocr_text or ""
    flags = {
        "fraction": bool(re.search(r"/|\\frac", text)),
        "absolute": bool(re.search(r"\|", text)),
        "radical": bool(re.search(r"√|\\sqrt", text)),
    }
    try:
        import numpy as np
        arr = np.asarray(crop.convert("L")) < 105
        if arr.size:
            # Nhiều đoạn ngang ngắn ở hai cao độ khác nhau thường là vạch phân số.
            row_counts = arr.sum(axis=1)
            strong_rows = int((row_counts > max(16, arr.shape[1] * 0.10)).sum())
            flags["fraction"] = flags["fraction"] or strong_rows >= 4
    except Exception:
        pass
    return flags


def _system_latex_is_valid(latex: str, complexity: Dict[str, bool]) -> bool:
    if not latex:
        return False
    relation_count = len(re.findall(r"=|\\le|\\ge|\\neq|<|>", latex))
    rows = [x for x in re.split(r"\\\\|\n", latex) if re.search(r"=|\\le|\\ge|\\neq|<|>", x)]
    if relation_count < 2 or len(rows) < 2:
        return False
    # Loại kết quả bảng x/y hoặc chuỗi mẩu rời.
    if re.search(r"\\begin\{(?:array|matrix|tabular)\}.*?\bx\b.*?\\\\.*?\by\b", latex, re.S):
        return False
    compact = re.sub(r"\s+", "", latex)
    if complexity.get("fraction") and r"\frac" not in compact:
        return False
    if complexity.get("absolute") and not re.search(r"\\(?:left)?\||\\lvert|\|[^|]+\|", compact):
        return False
    if complexity.get("radical") and r"\sqrt" not in compact:
        return False
    return True


def _recognize_system_formula(crop, ocr_text: str = "") -> Optional[str]:
    prepared = _tighten_system_crop(crop)
    complexity = _system_complexity(prepared, ocr_text)

    # Thử ảnh đã cắt sát trước; nếu chưa đạt mới thử ảnh gốc.
    candidates = []
    for candidate_crop in (prepared, crop):
        latex = _ORIGINAL_RECOGNIZE_FORMULA(candidate_crop, structural=True)
        latex = _normalize_system_latex(latex or "")
        if latex:
            candidates.append(latex)
            if _system_latex_is_valid(latex, complexity):
                return latex

    # Chỉ dùng fallback cho hệ tuyến tính sạch. Hệ phân số/căn/trị tuyệt đối không
    # được ghép từ các mẩu OCR rời vì sẽ tạo nội dung sai như 3, 4, x, y.
    fallback = _fallback_system_latex(ocr_text)
    if fallback and _system_latex_is_valid(fallback, {"fraction": False, "absolute": False, "radical": False}):
        return fallback
    return None


core._inject_anchored_system_regions = _inject_anchored_system_regions
core._clean_ocr_text = _clean_ocr_text
core._equations_from_ocr_text = _equations_from_ocr_text
core._fallback_system_latex = _fallback_system_latex
core._normalize_system_latex = _normalize_system_latex
core._recognize_system_formula = _recognize_system_formula
core.app.version = "2.10.0"

app = core.app
