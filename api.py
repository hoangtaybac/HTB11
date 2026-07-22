import os

# Railway chạy CPU. Phải đặt các cờ này TRƯỚC khi import Paddle/PaddleOCR
# để tránh lỗi oneDNN/PIR: ConvertPirAttribute2RuntimeAttribute not support.
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("FLAGS_enable_pir_in_executor", "0")
os.environ.setdefault("FLAGS_use_onednn", "0")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import re, tempfile, base64, shutil, subprocess, uuid, html as html_lib, zipfile, threading, gc, time, unicodedata, difflib, hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from PyPDF2 import PdfReader

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

try:
    from PIL import Image
except Exception:
    Image = None

app = FastAPI(title="Hoang Tay Bac Local Math OCR", version="2.7.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class ExportDocxPayload(BaseModel):
    content: str = ""
    images: Dict[str, str] = {}
    title: Optional[str] = "ket-qua-ocr"

class ExportPreviewHtmlPayload(BaseModel):
    html: str = ""
    title: Optional[str] = "ket-qua-ocr"

_ENGINE_LOCK = threading.Lock()
_PADDLE_ENGINE = None
_FORMULA_ENGINE = None
_ENGINE_ERRORS: Dict[str, str] = {}
_FORMULA_CACHE: Dict[str, str] = {}
_FORMULA_CACHE_LOCK = threading.Lock()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_paddle_engine():
    """Khởi tạo đúng một phiên bản PaddleOCR 2.x đã khóa trong requirements.

    Không dùng nhánh tương thích 3.x để tránh các lỗi use_gpu/predict/PIR từng xảy ra
    trên Railway.
    """
    global _PADDLE_ENGINE
    if _PADDLE_ENGINE is not None:
        return _PADDLE_ENGINE
    with _ENGINE_LOCK:
        if _PADDLE_ENGINE is not None:
            return _PADDLE_ENGINE
        try:
            from paddleocr import PaddleOCR
            _PADDLE_ENGINE = PaddleOCR(
                lang=os.getenv("PADDLE_LANG", "vi"),
                use_angle_cls=True,
                show_log=False,
                use_gpu=_env_bool("USE_GPU", False),
                enable_mkldnn=False,
                cpu_threads=max(1, int(os.getenv("OCR_CPU_THREADS", "1"))),
            )
            _ENGINE_ERRORS.pop("paddleocr", None)
            return _PADDLE_ENGINE
        except Exception as exc:
            _ENGINE_ERRORS["paddleocr"] = str(exc)
            raise RuntimeError(f"Không khởi tạo được PaddleOCR 2.x: {exc}")


def _get_formula_engine(required: bool = False):
    global _FORMULA_ENGINE
    if _FORMULA_ENGINE is not None:
        return _FORMULA_ENGINE
    if _env_bool("DISABLE_FORMULA_OCR", False):
        if required:
            raise RuntimeError("Formula OCR đang bị tắt bởi DISABLE_FORMULA_OCR")
        return None
    with _ENGINE_LOCK:
        if _FORMULA_ENGINE is not None:
            return _FORMULA_ENGINE
        try:
            from pix2tex.cli import LatexOCR
            _FORMULA_ENGINE = LatexOCR()
            return _FORMULA_ENGINE
        except Exception as exc:
            _ENGINE_ERRORS["pix2tex"] = str(exc)
            if required:
                raise RuntimeError(f"Không khởi tạo được mô hình công thức pix2tex: {exc}")
            return None


def _paddle_result_to_lines(raw) -> List[Dict[str, Any]]:
    """Chuẩn hóa kết quả PaddleOCR 2.x/3.x thành bbox, text và confidence."""
    lines: List[Dict[str, Any]] = []
    if raw is None:
        return lines

    def add_line(box, text, confidence=0.0):
        try:
            xs = [float(p[0]) for p in box]
            ys = [float(p[1]) for p in box]
            bbox = [min(xs), min(ys), max(xs), max(ys)]
            text = str(text or "").strip()
            if text:
                lines.append({"bbox": bbox, "text": text, "confidence": float(confidence or 0.0)})
        except Exception:
            pass

    # PaddleOCR 3.x: predict() trả Result/dict có rec_texts, rec_scores, rec_polys.
    results = raw if isinstance(raw, list) else [raw]
    for result in results:
        data = result
        if not isinstance(data, dict):
            for attr in ("json", "res"):
                try:
                    value = getattr(result, attr)
                    data = value() if callable(value) else value
                    if isinstance(data, dict):
                        break
                except Exception:
                    pass
        if isinstance(data, dict):
            if isinstance(data.get("res"), dict):
                data = data["res"]
            texts = data.get("rec_texts") or data.get("texts") or []
            scores = data.get("rec_scores") or data.get("scores") or []
            polys = data.get("rec_polys") or data.get("dt_polys") or data.get("polys") or []
            if texts and polys:
                for i, text in enumerate(texts):
                    add_line(polys[i], text, scores[i] if i < len(scores) else 0.0)
                continue

    if lines:
        lines.sort(key=lambda x: (round(x["bbox"][1] / 12), x["bbox"][0]))
        return lines

    # PaddleOCR 2.x: ocr() thường trả [[[box, (text, score)], ...]].
    pages = raw if isinstance(raw, list) else [raw]
    if len(pages) == 1 and isinstance(pages[0], list):
        pages = pages[0]
    for item in pages:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        box, rec = item[0], item[1]
        if isinstance(rec, (list, tuple)) and len(rec) >= 2:
            add_line(box, rec[0], rec[1])
        else:
            add_line(box, rec, 0.0)
    lines.sort(key=lambda x: (round(x["bbox"][1] / 12), x["bbox"][0]))
    return lines





def _ascii_fold(value: str) -> str:
    value = unicodedata.normalize("NFD", value or "")
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    return value.replace("đ", "d").replace("Đ", "D").lower()


def _inject_anchored_system_regions(lines: List[Dict[str, Any]], page_width: int) -> List[Dict[str, Any]]:
    """Tạo vùng 2D cho hệ phương trình dựa vào nhãn văn bản.

    Vùng được xác định theo thứ tự y thực tế, không dựa vào thứ tự ngẫu nhiên
    PaddleOCR trả về. Điều này tránh cắt cụt hệ hoặc nuốt sang bài kế tiếp.
    """
    if not lines:
        return []
    original = sorted((dict(x) for x in lines), key=lambda x: (x["bbox"][1], x["bbox"][0]))
    consumed = set()
    synthetic: List[Dict[str, Any]] = []
    stop_re = re.compile(r"^(?:TS\s+lớp|TS\s+lop|ĐS|DS|Đáp\s+số|Dap\s+so|\d+(?:\.\d+)+\s|Giải\s+hệ|Giai\s+he)", re.I)

    for ai, anchor in enumerate(original):
        folded = _ascii_fold(anchor.get("text", ""))
        if "giai he phuong trinh" not in folded and "he phuong trinh" not in folded:
            continue
        ax1, ay1, ax2, ay2 = anchor["bbox"]
        h = max(8.0, ay2 - ay1)
        left = min(page_width - 30.0, ax2 + max(4.0, h * 0.12))
        # Cho phép hệ dài/phân thức, nhưng không lấy vùng đáp số bên phải.
        right = min(page_width * 0.72, left + page_width * 0.44)
        top = max(0.0, ay1 - h * 0.65)
        bottom = min(ay1 + h * 7.5, ay1 + page_width * 0.34)

        for k in range(ai + 1, len(original)):
            item = original[k]
            bx1, by1, bx2, by2 = item["bbox"]
            if by1 <= ay2 + h * 0.30:
                continue
            txt = (item.get("text") or "").strip()
            folded_txt = _ascii_fold(txt)
            is_next_problem = bool(re.match(r"^\d+(?:\.\d+)+\b", txt))
            is_stop = bool(stop_re.match(txt)) or folded_txt.startswith(("ts lop", "ds", "dap so"))
            if (is_stop or is_next_problem) and bx1 < page_width * 0.78:
                bottom = min(bottom, by1 - h * 0.18)
                break
        bottom = max(ay2 + h * 1.6, bottom)

        selected=[]
        for k,item in enumerate(original):
            if k == ai or k in consumed:
                continue
            bx1,by1,bx2,by2=item["bbox"]
            cy=(by1+by2)/2
            if top <= cy <= bottom and bx2 >= left-h*0.35 and bx1 <= right:
                # Không nuốt dòng văn xuôi/đáp số nằm trong vùng.
                txt=(item.get("text") or "").strip()
                if _natural_word_count(txt) >= 3 and not _looks_like_math_line_text(txt):
                    continue
                selected.append((k,item))

        if right-left > 90 and bottom-top > h*1.4:
            for k,_ in selected:
                consumed.add(k)
            synthetic.append({
                "bbox":[max(0.0,left-h*0.55), top, right, bottom],
                "text":" ".join(x.get("text","") for _,x in selected),
                "confidence":sum(float(x.get("confidence",0)) for _,x in selected)/max(1,len(selected)),
                "multiline_math":True,
                "system_math":True,
                "merged_parts":len(selected),
            })

    result=[item for i,item in enumerate(original) if i not in consumed]+synthetic
    result.sort(key=lambda x:(x["bbox"][1],x["bbox"][0]))
    return result

def _normalize_system_latex(latex: str) -> str:
    latex = _repair_latex_delimiters(latex or "")
    if not latex:
        return latex
    # Chuẩn hóa array/aligned có dấu ngoặc hệ về cases.
    latex = re.sub(r"\\left\s*\\\{\s*", "", latex)
    latex = re.sub(r"\\right\s*\\?\.?\s*$", "", latex)
    latex = re.sub(r"\\begin\{array\}(?:\{[^}]*\})?", r"\begin{cases}", latex)
    latex = latex.replace(r"\end{array}", r"\end{cases}")
    latex = re.sub(r"\\begin\{aligned\}", r"\begin{cases}", latex)
    latex = re.sub(r"\\end\{aligned\}", r"\end{cases}", latex)
    # Nếu mô hình trả nhiều vế có \\ nhưng thiếu môi trường, tự bọc cases.
    if "\\begin{cases}" not in latex and len(re.findall(r"=", latex)) >= 2 and r"\\" in latex:
        latex = r"\begin{cases}" + latex + r"\end{cases}"
    return _repair_latex_delimiters(latex)


def _equations_from_ocr_text(text: str) -> List[str]:
    """Fallback nhanh: dựng cases từ các phương trình PaddleOCR đã thấy."""
    raw=(text or "").replace("−","-").replace("×", r"\times ")
    parts=re.split(r"(?:\n|\s{2,}|(?<=\d)\s+(?=[A-Za-z0-9({\[]))", raw)
    equations=[]
    for part in parts:
        t=part.strip(" ;,|{}")
        if not t or "=" not in t:
            continue
        if _natural_word_count(t) > 1:
            continue
        t=re.sub(r"\s+", "", t)
        t=t.replace("^", "^")
        if len(t) >= 3:
            equations.append(t)
    # Khử trùng lặp nhưng giữ thứ tự.
    out=[]
    for eq in equations:
        if eq not in out:
            out.append(eq)
    return out[:4]


def _fallback_system_latex(text: str) -> Optional[str]:
    equations=_equations_from_ocr_text(text)
    if len(equations) < 2:
        return None
    return r"\begin{cases}" + r"\\".join(equations) + r"\end{cases}"


def _recognize_system_formula(crop, ocr_text: str = "") -> Optional[str]:
    latex = _recognize_formula(crop, structural=True)
    if not latex:
        return _fallback_system_latex(ocr_text)
    latex = _normalize_system_latex(latex)
    # Hệ phải có ít nhất hai quan hệ; nếu không thì xem là nhận dạng hỏng.
    if len(re.findall(r"=|\\le|\\ge|<|>", latex)) < 2:
        return _fallback_system_latex(ocr_text)
    return latex

def _merge_same_row_boxes(lines: List[Dict[str, Any]], page_width: int) -> List[Dict[str, Any]]:
    """Gộp các bbox cùng một dòng để không cắt rời số mũ/chỉ số và vế công thức.

    PaddleOCR thường tách một công thức dài thành 2-4 bbox. Khi pix2tex nhận từng
    mảnh, phần x^4 hoặc chỉ số dưới rất dễ bị mất. Hàm này chỉ gộp các bbox có
    tâm y gần nhau và khoảng cách ngang nhỏ, đồng thời tránh gộp các dòng văn xuôi.
    """
    if not lines:
        return []
    ordered = sorted(lines, key=lambda x: ((x["bbox"][1] + x["bbox"][3]) / 2, x["bbox"][0]))
    rows: List[List[Dict[str, Any]]] = []
    for item in ordered:
        x1,y1,x2,y2=item["bbox"]
        cy=(y1+y2)/2; h=max(1.0,y2-y1)
        placed=False
        for row in rows[-4:]:
            ry1=min(v["bbox"][1] for v in row); ry2=max(v["bbox"][3] for v in row)
            rcy=(ry1+ry2)/2; rh=max(1.0,ry2-ry1)
            if abs(cy-rcy) <= max(h,rh)*0.48:
                row.append(item); placed=True; break
        if not placed:
            rows.append([item])
    merged=[]
    for row in rows:
        row=sorted(row,key=lambda v:v["bbox"][0])
        current=[row[0]]
        groups=[]
        for item in row[1:]:
            prev=current[-1]
            if item.get("system_math") or any(v.get("system_math") for v in current):
                groups.append(current); current=[item]; continue
            gap=item["bbox"][0]-prev["bbox"][2]
            h=max(prev["bbox"][3]-prev["bbox"][1], item["bbox"][3]-item["bbox"][1],1)
            left_text=' '.join(v['text'] for v in current)
            likely_math=bool(re.search(r'[=+\-*/^_(){}\[\]0-9]', left_text+item['text']))
            threshold=max(18, h*(2.4 if likely_math else 1.2))
            if gap <= threshold:
                current.append(item)
            else:
                groups.append(current); current=[item]
        groups.append(current)
        for g in groups:
            if len(g)==1:
                merged.append(g[0]); continue
            bbox=[min(v['bbox'][0] for v in g),min(v['bbox'][1] for v in g),max(v['bbox'][2] for v in g),max(v['bbox'][3] for v in g)]
            text=' '.join(v['text'] for v in g).strip()
            conf=sum(v.get('confidence',0) for v in g)/len(g)
            merged.append({'bbox':bbox,'text':text,'confidence':conf,'merged_parts':len(g), 'multiline_math': any(v.get('multiline_math') for v in g), 'system_math': any(v.get('system_math') for v in g)})
    merged.sort(key=lambda x:(round(x['bbox'][1]/12),x['bbox'][0]))
    return merged




def _looks_like_math_line_text(text: str) -> bool:
    value = (text or "").strip()
    if not value:
        return False
    if _natural_word_count(value) >= 3:
        return False
    marks = len(re.findall(r"[=+\-*/^_{}\[\]∫∑∏√≤≥≠±]|\d", value))
    return marks >= 2 or value.startswith(("{", "[", "(", "∫", "\\int"))


def _merge_multiline_math_regions(lines: List[Dict[str, Any]], page_width: int) -> List[Dict[str, Any]]:
    """Gộp hệ phương trình/tích phân nhiều dòng thành một vùng OCR toán duy nhất.

    OCR chữ thường tách dấu ngoặc hệ, từng phương trình và cận tích phân thành các
    bbox khác nhau. Pix2Tex phải nhìn toàn bộ cấu trúc 2D mới nhận đúng cases,
    array, cận trên/dưới và dấu tích phân.
    """
    if not lines:
        return []
    ordered = sorted(lines, key=lambda x: (x["bbox"][1], x["bbox"][0]))
    out: List[Dict[str, Any]] = []
    i = 0
    while i < len(ordered):
        first = ordered[i]
        if first.get("system_math"):
            out.append(first); i += 1; continue
        fb = first["bbox"]
        fh = max(1.0, fb[3]-fb[1])
        seed_text = first.get("text", "")
        seed_math = _looks_like_math_line_text(seed_text)
        seed_struct = bool(re.search(r"[∫∑∏]|^[{\[]", seed_text.strip()))
        group = [first]
        j = i + 1
        while j < len(ordered) and len(group) < 8:
            item = ordered[j]
            b = item["bbox"]
            prev = group[-1]["bbox"]
            gap = b[1] - prev[3]
            h = max(1.0, b[3]-b[1])
            overlap = max(0.0, min(fb[2], b[2]) - max(fb[0], b[0]))
            minw = max(1.0, min(fb[2]-fb[0], b[2]-b[0]))
            x_related = overlap/minw >= 0.18 or abs(b[0]-fb[0]) <= max(fh,h)*1.8
            item_math = _looks_like_math_line_text(item.get("text", ""))
            if gap <= max(fh,h)*1.15 and x_related and (seed_math or seed_struct) and item_math:
                group.append(item)
                seed_math = True
                j += 1
                continue
            break
        # Chỉ gộp khi thực sự có cấu trúc nhiều dòng toán hoặc dấu hệ/tích phân.
        all_text = " ".join(g.get("text", "") for g in group)
        has_relation = len(re.findall(r"=|≤|≥|<|>", all_text)) >= 2
        if len(group) >= 2 and (seed_struct or has_relation):
            bbox=[min(g['bbox'][0] for g in group),min(g['bbox'][1] for g in group),max(g['bbox'][2] for g in group),max(g['bbox'][3] for g in group)]
            conf=sum(float(g.get('confidence',0)) for g in group)/len(group)
            out.append({'bbox':bbox,'text':all_text,'confidence':conf,'multiline_math':True,'merged_parts':len(group)})
            i=j
        else:
            out.append(first)
            i+=1
    out.sort(key=lambda x:(x['bbox'][1],x['bbox'][0]))
    return out


def _repair_latex_delimiters(value: str) -> str:
    """Sửa LaTeX hỏng gây `Extra \left or missing \right`."""
    latex = (value or "").strip()
    # Dấu chấm vô hình của pix2tex không có ích khi lệnh bị lệch cặp.
    latex = latex.replace(r"\left .", "").replace(r"\right .", "")
    left_n = len(re.findall(r"\\left\b", latex))
    right_n = len(re.findall(r"\\right\b", latex))
    if left_n != right_n:
        latex = re.sub(r"\\left\s*", "", latex)
        latex = re.sub(r"\\right\s*", "", latex)
    # Chuẩn hóa các dạng hệ phổ biến mà mô hình thường sinh thiếu ngoặc đóng.
    latex = re.sub(r"\\left\s*\\\{\s*\\begin\{array\}", r"\begin{cases}", latex)
    latex = re.sub(r"\\end\{array\}\s*\\right\s*[.}]?", r"\end{cases}", latex)
    latex = re.sub(r"\\begin\{array\}\{[^}]*\}", r"\begin{aligned}", latex)
    latex = latex.replace(r"\end{array}", r"\end{aligned}")
    # Cân bằng môi trường nếu model chỉ trả một đầu.
    for env in ("cases", "aligned", "matrix", "pmatrix", "bmatrix"):
        b = len(re.findall(rf"\\begin\{{{env}\}}", latex))
        e = len(re.findall(rf"\\end\{{{env}\}}", latex))
        if b > e:
            latex += " " + (r"\end{" + env + "}") * (b-e)
    return latex.strip()


def _crop_with_padding(image, bbox, padding: int = 5):
    x1, y1, x2, y2 = [int(round(v)) for v in bbox]
    x1, y1 = max(0, x1 - padding), max(0, y1 - padding)
    x2, y2 = min(image.width, x2 + padding), min(image.height, y2 + padding)
    return image.crop((x1, y1, x2, y2))



def _preprocess_page_for_text_ocr(page_image):
    """Chuẩn bị ảnh cho OCR chữ mà không làm mất dấu tiếng Việt.

    Bản cũ dùng khử nhiễu mạnh trên ảnh xám. Với chữ nhỏ, các dấu sắc/huyền/
    hỏi/ngã/nặng rất dễ bị coi là nhiễu và bị xóa. Bản này chỉ cân bằng sáng nhẹ
    trên kênh độ sáng, giữ nguyên màu và kích thước nên bbox vẫn khớp ảnh gốc.
    """
    try:
        import cv2
        import numpy as np
        arr = np.asarray(page_image.convert("RGB"))
        lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        l = cv2.createCLAHE(clipLimit=1.35, tileGridSize=(12, 12)).apply(l)
        merged = cv2.merge((l, a, b))
        rgb = cv2.cvtColor(merged, cv2.COLOR_LAB2RGB)
        # Làm nét rất nhẹ; không threshold/denoise để bảo toàn dấu và nét mảnh.
        blur = cv2.GaussianBlur(rgb, (0, 0), 0.65)
        return cv2.addWeighted(rgb, 1.18, blur, -0.18, 0)
    except Exception:
        import numpy as np
        return np.asarray(page_image.convert("RGB"))


def _formula_crop_variants(crop):
    """Tạo nhiều biến thể ảnh để pix2tex chọn kết quả tốt nhất."""
    base = crop.convert("RGB")
    target_h = max(150, int(os.getenv("FORMULA_MIN_HEIGHT", "180")))
    if base.height < target_h:
        scale = target_h / float(max(1, base.height))
        base = base.resize((max(40, int(base.width * scale)), target_h), Image.Resampling.LANCZOS)
    base = Image.new("RGB", (base.width + 64, base.height + 48), "white") if False else base
    # Luôn thêm viền trắng rộng để bảo toàn số mũ/chỉ số nằm sát bbox.
    padded = Image.new("RGB", (base.width + 64, base.height + 56), "white")
    padded.paste(base, (32, 28))
    variants = [padded]
    try:
        import cv2
        import numpy as np
        arr = np.asarray(crop.convert("RGB"))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        # Viền trắng giúp mô hình không cắt mất chỉ số, dấu căn và phân số.
        gray = cv2.copyMakeBorder(gray, 34, 34, 38, 38, cv2.BORDER_CONSTANT, value=255)
        clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8)).apply(gray)
        variants.append(Image.fromarray(cv2.cvtColor(clahe, cv2.COLOR_GRAY2RGB)))
        binary = cv2.adaptiveThreshold(
            clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 31, 15
        )
        variants.append(Image.fromarray(cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)))
    except Exception:
        pass
    return variants


def _latex_quality_score(latex: str) -> float:
    """Chấm điểm để chọn kết quả pix2tex ít rác nhất."""
    if not _latex_is_sane(latex):
        return -10_000.0
    score = 20.0
    score += min(25, len(latex) / 8)
    score += 4 * len(re.findall(r"\\(?:frac|sqrt|sum|prod|int|begin|sin|cos|tan|log|ln)\\b", latex))
    score += 8 * len(re.findall(r"\\begin\{(?:cases|aligned|array|matrix)", latex))
    score += 2 * len(re.findall(r"[\^_]\{?[-+A-Za-z0-9]", latex))
    score += 1.5 * len(re.findall(r"[=+\-<>]", latex))
    score -= 8 * len(re.findall(r"\\qquad", latex))
    score -= 5 * len(re.findall(r"\\(?:widetilde|overbrace|underbrace)\b", latex))
    score -= 2 * len(re.findall(r"\?", latex))
    # Chuỗi lặp thường là dấu hiệu mô hình suy diễn sai.
    if re.search(r"(.{4,20})\1{2,}", latex):
        score -= 35
    return score


def _is_display_formula_bbox(bbox, page_width: int) -> bool:
    width = max(1.0, bbox[2] - bbox[0])
    return width >= page_width * 0.34


def _strip_accents(value: str) -> str:
    value = (value or "").replace("đ", "d").replace("Đ", "D")
    return "".join(ch for ch in unicodedata.normalize("NFD", value) if unicodedata.category(ch) != "Mn").lower()


_VI_MATH_WORDS = {
    "vi": "Ví", "du": "dụ", "phan": "Phân", "tich": "tích", "da": "đa",
    "thuc": "thức", "sau": "sau", "thanh": "thành", "nhan": "nhân", "tu": "tử",
    "giai": "Giải", "ta": "Ta", "co": "có", "loi": "Lời", "cau": "Câu",
    "bai": "Bài", "bieu": "biểu", "gia": "giá", "tri": "trị", "chung": "chứng",
    "minh": "minh", "phuong": "phương", "trinh": "trình", "he": "hệ",
    "dieu": "điều", "kien": "kiện", "rut": "rút", "gon": "gọn", "cac": "Các",
    "hoa": "họa"
}


def _closest_vi_word(token: str) -> Optional[str]:
    norm = _strip_accents(token)
    if norm in _VI_MATH_WORDS:
        return _VI_MATH_WORDS[norm]
    if len(norm) < 3 or not norm.isalpha():
        return None
    best = None
    best_score = 0.0
    for key, replacement in _VI_MATH_WORDS.items():
        if abs(len(key) - len(norm)) > 2:
            continue
        score = difflib.SequenceMatcher(None, norm, key).ratio()
        if score > best_score:
            best, best_score = replacement, score
    return best if best_score >= 0.78 else None


def _restore_vietnamese_prose(text: str) -> str:
    value = (text or "").strip()
    norm = _strip_accents(value)
    m = re.match(r"^vi\s*du\s*(\d+)\s*[:.]?\s*(.*)$", norm)
    if m:
        number = m.group(1)
        tail = m.group(2)
        if difflib.SequenceMatcher(None, tail[:48], "phan tich da thuc sau thanh nhan tu").ratio() >= 0.60:
            return f"Ví dụ {number}: Phân tích đa thức sau thành nhân tử:"
        return f"Ví dụ {number}: " + value.split(":", 1)[-1].strip()
    if re.match(r"^giai\s*[:.]?$", norm) or difflib.SequenceMatcher(None, norm.strip(" :."), "giai").ratio() >= 0.75:
        return "Giải:"
    if re.match(r"^ta\s+c[oas0]*\s*[:.]?$", norm):
        return "Ta có:"
    pieces = re.findall(r"[A-Za-zÀ-ỹĐđ]+|[^A-Za-zÀ-ỹĐđ]+", value)
    out = []
    for piece in pieces:
        if re.fullmatch(r"[A-Za-zÀ-ỹĐđ]+", piece):
            replacement = _closest_vi_word(piece)
            if replacement:
                if piece.islower():
                    replacement = replacement.lower()
                elif piece[:1].isupper():
                    replacement = replacement[:1].upper() + replacement[1:]
                out.append(replacement)
            else:
                out.append(piece)
        else:
            out.append(piece)
    return "".join(out)


def _split_trailing_formula(text: str) -> Tuple[str, str]:
    value = (text or "").strip()
    positions = [m.start() for m in re.finditer(r"[:：]", value)]
    for pos in reversed(positions):
        left, right = value[:pos + 1].strip(), value[pos + 1:].strip()
        natural = len(re.findall(r"[A-Za-zÀ-ỹĐđ]{2,}", right))
        if len(right) >= 3 and natural <= 1 and bool(re.search(r"\d|[=+\-*/^()]", right)):
            return left, right
    return value, ""


def _clean_ocr_text(text: str) -> str:
    text = (text or "").replace("|", "I").strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])(?=[A-Za-zÀ-ỹ])", r"\1 ", text)
    text = re.sub(r"\s{2,}", " ", text)
    prose, formula = _split_trailing_formula(text)
    prose = _restore_vietnamese_prose(prose)
    text = f"{prose} {formula}".strip() if formula else prose
    text = re.sub(r"\bTa\s+c[oóòs5]*\s*:", "Ta có:", text, flags=re.I)
    return text


def _natural_word_count(text: str) -> int:
    """Đếm từ ngôn ngữ tự nhiên để không gửi cả câu văn sang pix2tex."""
    words = re.findall(r"[A-Za-zÀ-ỹĐđ]{2,}", text or "")
    math_names = {"sin", "cos", "tan", "cot", "log", "ln", "lim", "max", "min"}
    return sum(1 for w in words if w.lower() not in math_names)


def _split_math_prefix(text: str):
    value = (text or "").strip()
    norm = _strip_accents(value)
    m = re.match(r"^(ta\s+c[oas05]*|suy\s+ra|do\s+do|khi\s+do)\s*[:;.]?\s*(.+)$", norm, flags=re.I)
    if not m:
        return "", value
    colon = re.search(r"[:;.]", value)
    rest = value[colon.end():].strip() if colon else value[len(m.group(1)):].strip()
    prefix_norm = m.group(1)
    if prefix_norm.startswith("ta"):
        return "Ta có:", rest
    if prefix_norm.startswith("suy"):
        return "Suy ra:", rest
    if prefix_norm.startswith("khi"):
        return "Khi đó:", rest
    return "Do đó:", rest


def _crop_formula_after_prefix(crop, prefix_fraction: float):
    try:
        import numpy as np
        arr = np.asarray(crop.convert("L"))
        density = (arr < 210).mean(axis=0)
        estimate = int(crop.width * prefix_fraction)
        lo = max(1, estimate - int(crop.width * 0.10))
        hi = min(crop.width - 2, estimate + int(crop.width * 0.14))
        if hi > lo:
            cut = lo + int(density[lo:hi].argmin())
            return crop.crop((max(0, cut - 10), 0, crop.width, crop.height))
    except Exception:
        pass
    cut = int(crop.width * prefix_fraction)
    return crop.crop((max(0, cut - 10), 0, crop.width, crop.height))


def _looks_like_formula(text: str, crop=None) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    math_marks = len(re.findall(r"[=+×÷√∫∑∏∞≤≥≠±∓<>^_{}\\]|\d\s*/\s*\d", text))
    digits = len(re.findall(r"\d", text))
    natural_words = _natural_word_count(text)

    # Câu văn có nhiều từ (đặc biệt dòng Ví dụ/Câu/Bài) không bao giờ được đưa
    # nguyên dòng vào pix2tex, dù cuối dòng có một công thức ngắn.
    if natural_words >= 3:
        return False
    if re.match(r"^(Ví dụ|Vi du|Câu|Cau|Bài|Bai)\b", text, flags=re.I):
        return False
    if text.startswith("=") or math_marks >= 3:
        return True
    if math_marks >= 2 and natural_words <= 1:
        return True
    if digits >= 2 and natural_words == 0 and any(ch in text for ch in "/()[]"):
        return True
    if crop is not None and natural_words == 0:
        try:
            import numpy as np
            arr = np.asarray(crop.convert("L"))
            dark = arr < 100
            row_density = dark.mean(axis=1) if dark.size else []
            if len(row_density) and float(max(row_density)) > 0.55:
                return True
        except Exception:
            pass
    return False


def _clean_latex_from_model(value: str) -> str:
    value = (value or "").strip()
    value = re.sub(r"^\$+|\$+$", "", value).strip()
    value = value.replace("\\left .", "").replace("\\right .", "")
    value = re.sub(r"\s+", " ", value)
    value = _repair_latex_delimiters(value)
    return value


def _latex_is_sane(latex: str) -> bool:
    if not latex or len(latex) > 1200:
        return False
    if len(re.findall(r"\\qquad", latex)) > 5:
        return False
    if len(re.findall(r"\\sqrt", latex)) > 12:
        return False
    if re.search(r"(?:\\sqrt\s*\{){4,}|(?:\\frac\s*\{){4,}", latex):
        return False
    # Kiểm tra ngoặc nhọn cơ bản để tránh đưa LaTeX hỏng sang MathJax/Word.
    balance = 0
    escaped = False
    for ch in latex:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
        elif ch == "{":
            balance += 1
        elif ch == "}":
            balance -= 1
            if balance < 0:
                return False
    return balance == 0


def _recognize_formula(crop, structural: bool = False) -> Optional[str]:
    """Nhận dạng công thức với đường nhanh trước, chỉ thử nhiều ảnh khi cần.

    Bản cũ luôn chạy pix2tex 3 lần cho mỗi công thức. Với tài liệu dài đây là
    nút thắt lớn nhất. Chế độ fast chạy 1 lần; balanced chỉ chạy thêm biến thể
    khi kết quả đầu có chất lượng thấp.
    """
    engine = _get_formula_engine(required=False)
    if engine is None:
        return None
    try:
        max_width = int(os.getenv("FORMULA_MAX_WIDTH", "1600"))
        mode = os.getenv("FORMULA_OCR_MODE", "balanced").strip().lower()
        # Hệ/tích phân cần giữ bố cục 2D nhưng vẫn giới hạn số lượt để không quá chậm.
        if structural and mode == "fast":
            mode = "balanced"
        variants = _formula_crop_variants(crop)
        cache_img = variants[0].convert("L").resize((min(900, variants[0].width), max(1, int(variants[0].height * min(1.0, 900/max(1,variants[0].width))))))
        cache_key = hashlib.sha1(cache_img.tobytes()).hexdigest() + (":S" if structural else ":N")
        with _FORMULA_CACHE_LOCK:
            cached = _FORMULA_CACHE.get(cache_key)
        if cached:
            return cached
        if mode in {"off", "disabled", "0"}:
            return None
        if mode == "fast":
            variants = variants[:1]
        elif mode == "balanced":
            variants = variants[:2]
        elif mode == "quality":
            # Chỉ công thức cấu trúc phức tạp mới thử 3 ảnh; công thức thường thử 2 để tăng tốc.
            variants = variants[:3 if structural else 2]

        candidates = []
        for index, variant in enumerate(variants):
            if variant.width > max_width:
                ratio = max_width / float(variant.width)
                variant = variant.resize((max_width, max(40, int(variant.height * ratio))))
            raw = str(engine(variant.convert("RGB")))
            latex = _clean_latex_from_model(raw)
            score = _latex_quality_score(latex)
            candidates.append((latex, score))
            # Kết quả đầu đã tốt thì không cần chạy thêm 2 lượt tốn CPU.
            if index == 0 and score >= float(os.getenv("FORMULA_EARLY_ACCEPT_SCORE", "42")):
                with _FORMULA_CACHE_LOCK:
                    _FORMULA_CACHE[cache_key] = latex
                return latex

        if not candidates:
            return None
        best, score = max(candidates, key=lambda x: x[1])
        if score > 0:
            with _FORMULA_CACHE_LOCK:
                if len(_FORMULA_CACHE) >= int(os.getenv("FORMULA_CACHE_SIZE", "512")):
                    _FORMULA_CACHE.clear()
                _FORMULA_CACHE[cache_key] = best
            return best
        return None
    except Exception as exc:
        _ENGINE_ERRORS["pix2tex_runtime"] = str(exc)
        return None


def _join_ocr_lines(lines: List[Dict[str, Any]], page_image) -> Tuple[str, List[Dict[str, Any]]]:
    output: List[str] = []
    blocks: List[Dict[str, Any]] = []
    previous_y2 = None
    page_width = int(page_image.width)
    min_conf = float(os.getenv("OCR_MIN_CONFIDENCE", "0.30"))

    for line in lines:
        bbox = line["bbox"]
        text = _clean_ocr_text(line["text"])
        confidence = float(line.get("confidence", 0.0))
        line_h = max(1.0, bbox[3]-bbox[1])
        crop = _crop_with_padding(page_image, bbox, padding=max(24 if line.get("multiline_math") else 14, int(line_h * (0.28 if line.get("multiline_math") else 0.55))))
        block_type = "text"
        rendered = text
        latex = None

        # Dòng có ký hiệu toán hoặc confidence thấp nhưng hình dáng giống công thức
        # sẽ được chuyển qua mô hình chuyên dụng. Không đưa câu văn tự nhiên vào pix2tex.
        prefix, math_text = _split_math_prefix(text)
        prose_prefix, trailing_math = _split_trailing_formula(text)
        if trailing_math and not prefix:
            prefix = _restore_vietnamese_prose(prose_prefix)
            math_text = trailing_math
        formula_candidate = bool(line.get("multiline_math")) or _looks_like_formula(math_text, crop)
        if confidence < min_conf and len(math_text) <= 45 and _natural_word_count(math_text) == 0:
            formula_candidate = formula_candidate or bool(re.search(r"[0-9A-Za-z(){}\[\]=+\-/:^]", math_text))

        if formula_candidate:
            formula_crop = crop
            # Với dạng "Ta có: <công thức>", cắt bỏ phần chữ bên trái trước khi
            # gọi pix2tex. Ước lượng theo tỉ lệ ký tự, có chừa biên để không mất nét.
            if prefix and math_text and len(text) > len(math_text):
                ratio = min(0.72, max(0.06, (len(text) - len(math_text)) / max(1, len(text))))
                candidate_crop = _crop_formula_after_prefix(crop, ratio)
                if candidate_crop.width >= 40:
                    formula_crop = candidate_crop
            latex = _recognize_system_formula(formula_crop, line.get("text", "")) if line.get("system_math") else _recognize_formula(formula_crop, structural=bool(line.get("multiline_math")))
            if latex:
                block_type = "formula"
                delimiter = "$$" if line.get("multiline_math") or line.get("system_math") or _is_display_formula_bbox(bbox, page_width) else "$"
                math_rendered = f"{delimiter}{latex}{delimiter}"
                rendered = f"{prefix} {math_rendered}".strip() if prefix else math_rendered

        # Bỏ các mẩu OCR cực kém nếu chúng không tạo được công thức hợp lệ.
        if block_type == "text" and confidence < 0.12 and len(text) <= 2:
            continue

        if previous_y2 is not None:
            gap = bbox[1] - previous_y2
            median_height = max(1.0, bbox[3] - bbox[1])
            if gap > median_height * 0.8:
                output.append("")
        output.append(rendered)
        blocks.append({
            "type": block_type,
            "bbox": [round(v, 2) for v in bbox],
            "text": text,
            "latex": latex,
            "confidence": round(confidence, 4),
        })
        previous_y2 = max(previous_y2 or bbox[3], bbox[3])
    return "\n".join(output).strip(), blocks


def _ocr_page_image(page_image, page_number: int) -> Dict[str, Any]:
    if Image is None:
        raise RuntimeError("Thiếu Pillow")
    engine = _get_paddle_engine()
    import numpy as np
    image_array = _preprocess_page_for_text_ocr(page_image)
    raw = engine.ocr(image_array, cls=True)
    lines = _paddle_result_to_lines(raw)
    lines = _inject_anchored_system_regions(lines, page_image.width)
    lines = _merge_same_row_boxes(lines, page_image.width)
    lines = _merge_multiline_math_regions(lines, page_image.width)
    markdown, blocks = _join_ocr_lines(lines, page_image)
    return {
        "page": page_number,
        "width": page_image.width,
        "height": page_image.height,
        "markdown": markdown,
        "blocks": blocks,
    }


def _render_pdf_pages(pdf_path: str, dpi: int, start_page: int = 1, end_page: Optional[int] = None):
    """Render lần lượt từng trang để RAM không tăng theo số trang của tài liệu.

    start_page/end_page dùng số trang bắt đầu từ 1. Nhờ vậy frontend có thể gửi
    tài liệu rất dài theo từng đợt (ví dụ 1-20, 21-40...) nếu hạ tầng có timeout.
    """
    if fitz is None:
        raise RuntimeError("Thiếu PyMuPDF để đọc và render PDF")
    doc = fitz.open(pdf_path)
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    first = max(1, int(start_page or 1))
    last = min(len(doc), int(end_page or len(doc)))
    try:
        for page_number in range(first, last + 1):
            page = doc.load_page(page_number - 1)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            del pix
            yield page_number, page, image
            # Giải phóng ảnh trang trước ngay khi vòng lặp tiếp tục.
            del image, page
            gc.collect()
    finally:
        doc.close()


def _native_text_is_usable(text: str) -> bool:
    """Chỉ dùng text layer khi thật sự sạch.

    PDF toán thường có text layer hỏng chứa hàng loạt \sqrt, \qquad, ký tự font
    riêng. Dùng lớp đó sẽ tạo đúng kiểu chuỗi rác mà người dùng đã gặp.
    """
    text = text or ""
    visible = len(re.findall(r"[A-Za-zÀ-ỹ0-9]", text))
    bad = text.count("�") + len(re.findall(r"[-]", text))
    latex_tokens = len(re.findall(r"\\(?:qquad|sqrt|frac|widetilde|overbrace|bot|mathcal)", text))
    slash_ratio = text.count("\\") / max(1, len(text))
    repeated = bool(re.search(r"(?:\\qquad){3,}|(?:\\sqrt\s*\{){3,}", text))
    return (
        visible >= 80
        and bad <= max(2, visible * 0.02)
        and latex_tokens <= 2
        and slash_ratio < 0.01
        and not repeated
    )


def _page_needs_math_ocr(text: str) -> bool:
    """Chỉ ép OCR ảnh ở trang có cấu trúc toán mà text layer không giữ được 2D."""
    t=text or ""
    folded=_ascii_fold(t)
    structural_words=("he phuong trinh", "nguyen ham", "tich phan", "ma tran", "dinh thuc")
    if any(w in folded for w in structural_words):
        return True
    if any(ch in t for ch in ("∫","∑","∏","√","⎧","⎨","⎩")):
        return True
    # Nhiều phương trình trên cùng trang thường cần nhận dạng số mũ/phân số chuyên dụng.
    relations=len(re.findall(r"[=≤≥]",t))
    powers=len(re.findall(r"[²³⁴⁵⁶⁷⁸⁹]|\^",t))
    return relations >= 4 or powers >= 3


def _extract_native_page(page, page_number: int) -> Dict[str, Any]:
    text = page.get_text("text", sort=True).strip()
    blocks = []
    for item in page.get_text("blocks", sort=True):
        if len(item) < 5 or not str(item[4]).strip():
            continue
        blocks.append({
            "type": "text",
            "bbox": [round(float(v), 2) for v in item[:4]],
            "text": str(item[4]).strip(),
            "latex": None,
            "confidence": 1.0,
        })
    return {"page": page_number, "markdown": text, "blocks": blocks, "source": "pdf-text"}



def _ensure_math_environments_wrapped(text: str) -> str:
    """Bọc môi trường LaTeX trần để frontend/MathJax luôn render được."""
    if not text:
        return text
    envs=r"(?:cases|aligned|alignedat|array|matrix|pmatrix|bmatrix|Bmatrix|vmatrix|Vmatrix|gathered|split)"
    pat=re.compile(rf"(?<!\$)(\\begin\{{{envs}\}}[\s\S]*?\\end\{{{envs}\}})(?!\$)")
    return pat.sub(lambda m: "$$"+m.group(1)+"$$", text)

def clean_text_and_images(text: str, images: Dict[str, str]) -> str:
    cleaned = text or ""
    cleaned = re.sub(r'(Câu\s+\d+\.?[:]?)', r'\n\n\1', cleaned)
    cleaned = re.sub(r'(Bài\s+\d+\.?[:]?)', r'\n\n\1', cleaned)
    cleaned = re.sub(r'(?m)^\s*([A-D]\.)\s*', r'\n\1 ', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


@app.get("/")
def root():
    return {
        "ok": True,
        "service": "Hoang Tay Bac Local Math OCR",
        "version": "2.7.0",
        "uses_external_api": False,
        "endpoint": "POST /ocr",
        "export": "POST /export-docx",
    }


@app.get("/health")
def health():
    return {"ok": True, "service": "local-math-ocr", "version": app.version}


@app.get("/engine-status")
def engine_status():
    return {
        "external_api": False,
        "paddleocr_loaded": _PADDLE_ENGINE is not None,
        "formula_ocr_loaded": _FORMULA_ENGINE is not None,
        "formula_ocr_disabled": _env_bool("DISABLE_FORMULA_OCR", False),
        "use_gpu": _env_bool("USE_GPU", False),
        "errors": _ENGINE_ERRORS,
    }


async def _save_upload_streaming(upload: UploadFile, suffix: str, max_bytes: int) -> Tuple[str, int]:
    """Ghi upload theo khối, không nạp toàn bộ PDF 500 trang vào RAM."""
    total = 0
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    path = tmp.name
    try:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(status_code=413, detail=f"File vượt giới hạn {max_bytes} byte")
            tmp.write(chunk)
        tmp.flush()
        return path, total
    except Exception:
        tmp.close()
        try:
            os.unlink(path)
        except Exception:
            pass
        raise
    finally:
        try:
            tmp.close()
        except Exception:
            pass


def _render_one_page(page, dpi: int):
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    try:
        return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    finally:
        del pix


@app.post("/ocr")
async def ocr_pdf_or_image(
    file: UploadFile = File(...),
    start_page: int = Query(1, ge=1, description="Trang bắt đầu, tính từ 1"),
    end_page: Optional[int] = Query(None, ge=1, description="Trang kết thúc; bỏ trống để xử lý đến hết"),
    include_page_results: bool = Query(True, description="Tắt để giảm mạnh dung lượng JSON cho tài liệu dài"),
    batch_size: int = Query(0, ge=0, le=100, description="0 = tự động; PDF dài sẽ tự chia batch"),
):
    """PDF/ảnh -> Markdown + LaTeX. Xử lý tuần tự từng trang để giữ RAM ổn định."""
    filename = file.filename or "upload"
    lower_name = filename.lower()
    image_exts = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff")
    is_pdf = lower_name.endswith(".pdf") or file.content_type == "application/pdf"
    is_image = lower_name.endswith(image_exts) or (file.content_type or "").startswith("image/")
    if not (is_pdf or is_image):
        raise HTTPException(status_code=400, detail="Chỉ nhận PDF hoặc ảnh JPG/PNG/JPEG/WEBP/TIFF")

    max_bytes = int(os.getenv("MAX_UPLOAD_BYTES", "524288000"))
    suffix = ".pdf" if is_pdf else (Path(lower_name).suffix or ".jpg")
    tmp_path = None
    try:
        tmp_path, upload_bytes = await _save_upload_streaming(file, suffix, max_bytes)
        pages: List[Dict[str, Any]] = []
        joined: List[str] = []
        dpi = max(96, min(300, int(os.getenv("OCR_DPI", "200"))))
        force_ocr = _env_bool("FORCE_OCR", False)
        max_pages = max(0, int(os.getenv("MAX_PAGES", "0")))
        started_at = time.time()
        formula_count = 0
        native_pages = 0
        ocr_pages = 0
        processed_pages = 0
        page_count = 1
        actual_end = 1
        batch_reports: List[Dict[str, Any]] = []

        if is_image:
            if Image is None:
                raise RuntimeError("Thiếu Pillow")
            with Image.open(tmp_path) as src:
                image = src.convert("RGB")
            result = _ocr_page_image(image, 1)
            result["source"] = "local-paddleocr"
            ocr_pages = 1
            processed_pages = 1
            formula_count = sum(1 for b in result.get("blocks", []) if b.get("type") == "formula")
            joined.append(f"<!-- PAGE 1 -->\n\n{result.get('markdown', '')}")
            if include_page_results:
                pages.append(result)
            del image
        else:
            if fitz is None:
                raise RuntimeError("Thiếu PyMuPDF để đọc PDF")
            with fitz.open(tmp_path) as doc:
                page_count = len(doc)
                if max_pages > 0 and page_count > max_pages:
                    raise HTTPException(status_code=400, detail=f"PDF có {page_count} trang, vượt giới hạn quản trị {max_pages}")
                if start_page > page_count:
                    raise HTTPException(status_code=400, detail=f"start_page={start_page} vượt quá tổng {page_count} trang")
                selected_end = min(page_count, end_page or page_count)
                if selected_end < start_page:
                    raise HTTPException(status_code=400, detail="end_page phải lớn hơn hoặc bằng start_page")

                auto_batch = batch_size or max(1, int(os.getenv("AUTO_BATCH_PAGES", "20")))
                for batch_start in range(start_page, selected_end + 1, auto_batch):
                    batch_end = min(selected_end, batch_start + auto_batch - 1)
                    batch_started = time.time()
                    batch_ocr = 0
                    batch_native = 0
                    for page_number in range(batch_start, batch_end + 1):
                        page = doc.load_page(page_number - 1)
                        native_text = page.get_text("text", sort=True)
                        if not force_ocr and _native_text_is_usable(native_text) and not _page_needs_math_ocr(native_text):
                            page_result = _extract_native_page(page, page_number)
                            scale = dpi / 72.0
                            page_result.update({"width": round(page.rect.width * scale), "height": round(page.rect.height * scale)})
                            native_pages += 1
                            batch_native += 1
                        else:
                            image = _render_one_page(page, dpi)
                            page_result = _ocr_page_image(image, page_number)
                            page_result["source"] = "local-paddleocr"
                            ocr_pages += 1
                            batch_ocr += 1
                            try:
                                image.close()
                            except Exception:
                                pass
                            del image

                        formula_count += sum(1 for b in page_result.get("blocks", []) if b.get("type") == "formula")
                        joined.append(f"<!-- PAGE {page_number} -->\n\n{page_result.get('markdown', '')}")
                        if include_page_results:
                            pages.append(page_result)
                        processed_pages += 1
                        actual_end = page_number
                        del page_result, page

                    batch_reports.append({
                        "batch": len(batch_reports) + 1,
                        "start_page": batch_start,
                        "end_page": batch_end,
                        "pages": batch_end - batch_start + 1,
                        "ocr_pages": batch_ocr,
                        "native_text_pages": batch_native,
                        "elapsed_seconds": round(time.time() - batch_started, 2),
                    })
                    gc.collect()

        text = "\n\n".join(joined).strip()
        return {
            "text": text,
            "cleaned_text": _ensure_math_environments_wrapped(clean_text_and_images(text, {})),
            "images": {},
            "pages": processed_pages,
            "total_pages": page_count,
            "start_page": 1 if is_image else start_page,
            "end_page": 1 if is_image else actual_end,
            "elapsed_seconds": round(time.time() - started_at, 2),
            "upload_bytes": upload_bytes,
            "file_type": "image" if is_image else "pdf",
            "engine": "local",
            "uses_external_api": False,
            "formula_count": formula_count,
            "native_text_pages": native_pages,
            "ocr_pages": ocr_pages,
            "page_results": pages if include_page_results else [],
            "page_results_included": include_page_results,
            "batch_size": 1 if is_image else (batch_size or max(1, int(os.getenv("AUTO_BATCH_PAGES", "20")))),
            "batches": batch_reports,
            "batch_count": len(batch_reports),
            "engine_errors": _ENGINE_ERRORS,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi OCR nội bộ: {exc}")
    finally:
        try:
            await file.close()
        except Exception:
            pass
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def _safe_filename(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9_\-.]+", "-", name or "ket-qua-ocr").strip("-_.")
    return name or "ket-qua-ocr"


def _decode_image_to_file(img_id: str, b64: str, img_dir: Path) -> Optional[Path]:
    try:
        raw = b64.split(",", 1)[1] if b64.startswith("data:") and "," in b64 else b64
        data = base64.b64decode(raw)
        ext = Path(img_id).suffix.lower() or ".jpg"
        if ext not in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
            ext = ".jpg"
        out = img_dir / (Path(img_id).stem + ext)
        out.write_bytes(data)
        return out
    except Exception:
        return None




def _normalize_math_for_pandoc(md: str) -> str:
    """Chuẩn hóa mọi cú pháp toán phổ biến về dạng Pandoc chắc chắn tạo OMML.

    Hỗ trợ: $...$, $$...$$, \(...\), \[...\] và các môi trường LaTeX
    như cases, aligned, matrix khi OCR trả về mà thiếu dấu bao công thức.
    """
    md = (md or "").replace("\r\n", "\n").replace("\r", "\n")

    # Bảo vệ code fence để không biến ví dụ mã nguồn thành Equation.
    protected = []
    def keep_code(m):
        protected.append(m.group(0))
        return f"@@CODE_BLOCK_{len(protected)-1}@@"
    md = re.sub(r"```[\s\S]*?```", keep_code, md)

    # Chuẩn hóa MathJax delimiters sang dollar math mà Pandoc xử lý ổn định nhất.
    md = re.sub(r"\\\[([\s\S]*?)\\\]", lambda m: "\n\n$$\n" + _clean_latex_piece_for_docx(m.group(1)) + "\n$$\n\n", md)
    md = re.sub(r"\\\(([\s\S]*?)\\\)", lambda m: "$" + _clean_latex_piece_for_docx(m.group(1)).replace("\n", " ") + "$", md)

    # Nếu OCR trả về môi trường toán mà không có delimiters, tự bọc thành display equation.
    envs = r"(?:cases|aligned|alignedat|array|matrix|pmatrix|bmatrix|Bmatrix|vmatrix|Vmatrix|gathered|split)"
    env_pat = re.compile(r"(\\begin\{" + envs + r"\}[\s\S]*?\\end\{" + envs + r"\})")
    chunks = re.split(r"(\$\$[\s\S]*?\$\$|(?<!\$)\$(?!\$)[^\n$]+?(?<!\$)\$(?!\$))", md)
    for i in range(0, len(chunks), 2):
        chunks[i] = env_pat.sub(lambda m: "\n\n$$\n" + _clean_latex_piece_for_docx(m.group(1)) + "\n$$\n\n", chunks[i])
    md = "".join(chunks)

    # Làm sạch nội dung trong display math và inline math.
    md = re.sub(r"\$\$([\s\S]*?)\$\$", lambda m: "\n\n$$\n" + _clean_latex_piece_for_docx(m.group(1)) + "\n$$\n\n" if _clean_latex_piece_for_docx(m.group(1)) else "", md)
    md = re.sub(r"(?<!\$)\$(?!\$)([^\n$]+?)(?<!\$)\$(?!\$)", lambda m: "$" + _clean_latex_piece_for_docx(m.group(1)).replace("\n", " ") + "$", md)

    for i, block in enumerate(protected):
        md = md.replace(f"@@CODE_BLOCK_{i}@@", block)
    return re.sub(r"\n{4,}", "\n\n", md).strip() + "\n"


def _audit_docx_equations(docx_path: Path) -> Dict[str, Any]:
    """Kiểm tra DOCX thực sự chứa Word Equation (OMML), không còn LaTeX thô."""
    with zipfile.ZipFile(docx_path, 'r') as z:
        xml = z.read('word/document.xml').decode('utf-8', errors='ignore')
    equation_count = len(re.findall(r'<m:oMath(?:Para)?\b', xml))
    text_nodes = re.findall(r'<w:t[^>]*>([\s\S]*?)</w:t>', xml)
    visible = html_lib.unescape(' '.join(text_nodes))
    raw_patterns = [r'\\frac\s*\{', r'\\sqrt(?:\[[^]]*\])?\s*\{', r'\\begin\{(?:cases|aligned|matrix|pmatrix|bmatrix)', r'\$\$']
    raw_hits = [pat for pat in raw_patterns if re.search(pat, visible)]
    return {"equation_count": equation_count, "raw_latex_patterns": raw_hits}


def _ensure_docx_equations_are_real(docx_path: Path) -> Dict[str, Any]:
    audit = _audit_docx_equations(docx_path)
    if audit["raw_latex_patterns"]:
        raise RuntimeError("Word vẫn còn LaTeX thô thay vì Equation: " + ", ".join(audit["raw_latex_patterns"]))
    return audit

def _prepare_markdown_for_docx(content: str, images: Dict[str, str], workdir: Path) -> str:
    """Chuẩn hóa Markdown để Pandoc chuyển $...$/$$...$$ thành Word Equation thật (OMML)."""
    md = content or ""

    # Bỏ vài ký hiệu Markdown thừa do OCR để Word gọn hơn.
    md = re.sub(r"^\s*```.*?$", "", md, flags=re.MULTILINE)
    md = re.sub(r"\*\*\s*(Lời\s*giải\s*:?)\s*\*\*", r"\n\n**\1**\n", md, flags=re.I)

    img_dir = workdir / "images"
    img_dir.mkdir(exist_ok=True)
    for img_id, b64 in (images or {}).items():
        img_path = _decode_image_to_file(img_id, b64, img_dir)
        if not img_path:
            continue
        rel = img_path.relative_to(workdir).as_posix()
        md_img = f"\n\n![{img_id}]({rel})\n\n"
        patterns = [
            r"\[\s*HÌNH\s*:\s*" + re.escape(img_id) + r"\s*\]",
            r"\[\s*Hình\s*:\s*" + re.escape(img_id) + r"\s*\]",
            re.escape(img_id),
        ]
        for pat in patterns:
            md = re.sub(pat, md_img, md, flags=re.I)

    # Giảm lỗi bảng markdown OCR: bỏ hàng chỉ toàn --- nếu bị đứng riêng.
    md = re.sub(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", "", md, flags=re.MULTILINE)
    return _normalize_math_for_pandoc(md)

@app.post("/export-docx")
async def export_docx(payload: ExportDocxPayload):
    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="Chưa có nội dung để xuất Word")

    pandoc_bin = os.getenv("PANDOC_PATH") or shutil.which("pandoc")
    if not pandoc_bin:
        raise HTTPException(
            status_code=500,
            detail="Server chưa có Pandoc nên chưa xuất được Word Equation thật. Cần cài pandoc hoặc đặt biến PANDOC_PATH."
        )

    tmp_root = Path(tempfile.mkdtemp(prefix="docx_export_"))
    try:
        md = _prepare_markdown_for_docx(payload.content, payload.images, tmp_root)
        md_path = tmp_root / "input.md"
        docx_path = tmp_root / f"{uuid.uuid4().hex}.docx"
        md_path.write_text(md, encoding="utf-8")

        cmd = [
            pandoc_bin,
            str(md_path),
            "-f", "markdown+tex_math_dollars+tex_math_single_backslash+pipe_tables",
            "-t", "docx",
            "--resource-path", str(tmp_root),
            "-o", str(docx_path),
        ]
        completed = subprocess.run(cmd, cwd=str(tmp_root), capture_output=True, text=True, timeout=120)
        if completed.returncode != 0 or not docx_path.exists():
            raise RuntimeError(completed.stderr or completed.stdout or "Pandoc không tạo được file docx")

        _add_visible_borders_to_docx(docx_path)
        _ensure_docx_equations_are_real(docx_path)
        filename = _safe_filename(payload.title or "ket-qua-ocr") + ".docx"
        return FileResponse(
            path=str(docx_path),
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            background=None,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi xuất Word: {e}")



def _strip_tags_for_detect(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html_lib.unescape(s).replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _variation_label_and_cells(line: str):
    """Nhận 1 dòng kiểu: x -∞ -1 1 +∞ / f'(x) + 0 - 0 / f(x) -∞ 2 -2 +∞."""
    text = _strip_tags_for_detect(line)
    if not text:
        return None
    text = (text.replace("−", "-")
                .replace("\\(", " ").replace("\\)", " ")
                .replace("$", " ").replace("\\,", " "))
    text = re.sub(r"\s+", " ", text).strip()
    m = re.match(r"^(x|f\s*['′]\s*\(\s*x\s*\)|f\s*\(\s*x\s*\)|y\s*['′]?|y)\b\s*(.*)$", text, re.I)
    if not m:
        return None
    label = re.sub(r"\s+", "", m.group(1))
    label = label.replace("′", "'")
    rest = m.group(2).strip()
    if label.lower() == "y":
        label = "y"
    parts = [label]
    if rest:
        # Tách các mốc/cell; giữ dấu vô cực và dấu + - thành cell riêng khi đứng riêng.
        rest = rest.replace("+∞", "+∞").replace("-∞", "-∞")
        parts += [p for p in re.split(r"\s+", rest) if p]
    return parts



def _generic_table_cells(line: str):
    """Nhận các dòng bảng số liệu và ép thành cell thật để Word có hàng/cột/kẻ bảng."""
    text = _strip_tags_for_detect(line)
    if not text:
        return None
    text = text.replace("−", "-").replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text).strip()

    # Tránh bắt nhầm dòng câu hỏi/văn bản thường.
    if re.match(r"^(Câu|Bài)\s+\d+", text, re.I):
        return None
    if text.endswith((".", "?", ":", "：")) and not re.search(r"\[[^\]]+\)", text):
        return None

    # Bảng có cột dạng khoảng: Thời gian (phút) [0; 20) [20; 40) ...
    intervals = re.findall(r"\[[^\]]+\)|\([^\)]+\)|\{[^\}]+\}", text)
    if len(intervals) >= 2:
        first_pos = min([text.find(x) for x in intervals if text.find(x) >= 0] or [0])
        label = text[:first_pos].strip()
        return ([label] if label else []) + intervals

    # Dòng dữ liệu dạng: Số học sinh 5 9 12 10 6
    m_nums = re.match(r"^(.+?)\s+((-?\d+(?:[,.]\d+)?)(?:\s+-?\d+(?:[,.]\d+)?){1,})$", text)
    if m_nums:
        label = m_nums.group(1).strip()
        nums = re.findall(r"-?\d+(?:[,.]\d+)?", m_nums.group(2))
        if label and len(nums) >= 2:
            return [label] + nums

    # Bảng có tab hoặc nhiều khoảng trắng rõ ràng.
    raw = _strip_tags_for_detect(line).replace("\u00a0", " ")
    if "\t" in raw:
        cells = [c.strip() for c in raw.split("\t") if c.strip()]
    else:
        cells = [c.strip() for c in re.split(r"\s{2,}", raw) if c.strip()]

    if len(cells) >= 3:
        return cells
    if len(cells) >= 2 and re.search(r"\[[^\]]+\)|\d", raw) and not raw.strip().endswith((".", "?", ":")):
        return cells
    return None


def _any_table_cells(line: str):
    return _variation_label_and_cells(line) or _generic_table_cells(line)

def _html_table_from_variation_rows(rows):
    parsed = []
    max_cols = 0
    for r in rows:
        cells = _any_table_cells(r)
        if not cells:
            continue
        parsed.append(cells)
        max_cols = max(max_cols, len(cells))
    if len(parsed) < 2:
        return "<br>".join(rows)
    for cells in parsed:
        while len(cells) < max_cols:
            cells.append("&nbsp;")
    out = ['<table class="latex-table">']
    for cells in parsed:
        out.append('<tr>')
        for i, c in enumerate(cells):
            c = c if c == "&nbsp;" else html_lib.escape(str(c))
            out.append(f'<td class="row-head">{c}</td>' if i == 0 else f'<td>{c}</td>')
        out.append('</tr>')
    out.append('</table>')
    return "".join(out)


def _convert_plain_variation_tables_in_fragment(fragment: str) -> str:
    """Chuyển các dòng bảng còn ở dạng chữ thành <table> trước khi xuất Word."""
    if not fragment:
        return fragment
    pieces = re.split(r"(<br\s*/?>|\n)", fragment, flags=re.I)
    lines, seps = [], []
    for i, p in enumerate(pieces):
        if re.fullmatch(r"<br\s*/?>|\n", p or "", flags=re.I):
            seps.append(p)
        else:
            lines.append(p)
    if len(lines) < 2:
        return fragment
    out = []
    buf = []

    def flush_buf():
        nonlocal buf
        if buf:
            out.append(_html_table_from_variation_rows(buf))
            buf = []

    for line in lines:
        if _any_table_cells(line):
            buf.append(line)
        else:
            flush_buf()
            if line.strip():
                out.append(line)
    flush_buf()
    return "<br>".join(out)


def _convert_plain_variation_tables_in_html(html: str) -> str:
    # Xử lý trong từng thẻ p/div trước, tránh phá cấu trúc ảnh/table đã có.
    def repl_block(m):
        tag, attrs, inner = m.group(1), m.group(2) or "", m.group(3)
        if "<table" in inner.lower() or "<img" in inner.lower():
            return m.group(0)
        fixed = _convert_plain_variation_tables_in_fragment(inner)
        return f"<{tag}{attrs}>{fixed}</{tag}>"
    html = re.sub(r"<(p|div)([^>]*)>(.*?)</\1>", repl_block, html or "", flags=re.I|re.S)
    return html


def _clean_latex_piece_for_docx(s: str) -> str:
    """Làm sạch LaTeX nằm trong HTML preview trước khi đưa cho Pandoc.
    Lỗi hay gặp: marked.js biến xuống dòng trong $$...$$ thành <br>, khiến Pandoc xuất nguyên $$ ra Word.
    """
    s = s or ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>\s*<p[^>]*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html_lib.unescape(s).replace("\xa0", " ")
    # Chuẩn hóa vài lệnh LaTeX phổ biến nếu bị nhân đôi slash khi đi qua HTML/JSON.
    for cmd in ["left","right","sqrt","frac","widehat","tan","approx","circ","Rightarrow","le","ge","in","notin"]:
        s = s.replace("\\\\" + cmd, "\\" + cmd)
    s = re.sub(r"\n{2,}", "\n", s).strip()
    return s


def _fix_latex_math_blocks_for_docx(html: str) -> str:
    """Sửa công thức trước khi Pandoc đọc HTML.
    Nếu trong $$...$$ có thẻ <br>, Pandoc thường xuất nguyên LaTeX ra Word.
    Hàm này đổi về $$\\n...\\n$$ sạch để Word nhận Equation.
    """
    if not html:
        return html

    def repl_display(m):
        latex = _clean_latex_piece_for_docx(m.group(1))
        if not latex:
            return ""
        return "\n<p>$$\n" + latex + "\n$$</p>\n"

    html = re.sub(r"\$\$([\s\S]*?)\$\$", repl_display, html)

    def repl_bracket(m):
        latex = _clean_latex_piece_for_docx(m.group(1))
        if not latex:
            return ""
        return "\n<p>$$\n" + latex + "\n$$</p>\n"

    html = re.sub(r"\\\[([\s\S]*?)\\\]", repl_bracket, html)

    def repl_inline_paren(m):
        latex = _clean_latex_piece_for_docx(m.group(1)).replace("\n", " ")
        return r"\(" + latex + r"\)"

    html = re.sub(r"\\\(([\s\S]*?)\\\)", repl_inline_paren, html)
    return html


def _prepare_preview_html_for_docx(html: str, workdir: Path) -> str:
    """Nhận đúng HTML phần xem trước, tách data:image ra file thật để Pandoc không lặp/không mất ảnh."""
    html = html or ""

    # FIX: Không để CSS/JS/head bị Pandoc đọc thành chữ và in lên đầu file Word.
    # Lỗi trước đây: phần <style>body{...}</style> bị chuyển thành văn bản thường trong DOCX.
    html = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.I)
    html = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", html, flags=re.I)
    html = re.sub(r"<!doctype[^>]*>", "", html, flags=re.I)
    html = re.sub(r"<head[^>]*>[\s\S]*?</head>", "", html, flags=re.I)
    html = re.sub(r"</?(?:html|body)[^>]*>", "", html, flags=re.I)

    # Quan trọng: sửa công thức trước khi Pandoc đọc HTML. Nếu trong $$...$$ có <br>, Word sẽ hiện nguyên LaTeX.
    html = _fix_latex_math_blocks_for_docx(html)
    html = _convert_plain_variation_tables_in_html(html)
    img_dir = workdir / "preview_images"
    img_dir.mkdir(exist_ok=True)

    html = re.sub(r"\[\s*HÌNH\s*:?\s*\]", "", html, flags=re.I)
    html = re.sub(r"^\s*\]\s*$", "", html, flags=re.M)

    def repl_img(match):
        before, src, after = match.group(1), match.group(2), match.group(3)
        if not src.startswith("data:image"):
            return match.group(0)
        try:
            header, raw = src.split(",", 1)
            ext = ".png"
            if "jpeg" in header or "jpg" in header:
                ext = ".jpg"
            elif "gif" in header:
                ext = ".gif"
            elif "webp" in header:
                ext = ".webp"
            data = base64.b64decode(raw)
            out = img_dir / f"img_{uuid.uuid4().hex}{ext}"
            out.write_bytes(data)
            rel = out.relative_to(workdir).as_posix()
            return f'<img{before} src="{rel}"{after}>'
        except Exception:
            return ""

    html = re.sub(r"<img([^>]*?)\s+src=[\"']([^\"']+)[\"']([^>]*)>", repl_img, html, flags=re.I)
    html = re.sub(r"(?im)^\s*img-\d+\.(?:jpe?g|png|webp)\s*$", "", html)

    style = """
    <style>
      body{font-family:Arial, sans-serif;font-size:12pt;line-height:1.25;color:#111827;}
      p{margin:2px 0;}
      img{max-width:55%;display:block;margin:8px auto;border:0;}
      table{border-collapse:collapse !important;border:1px solid #334155 !important;margin:10px 0 !important;width:auto !important;}
      tr{border:1px solid #334155 !important;}
      td,th{border:1px solid #334155 !important;padding:6px 10px !important;text-align:center !important;vertical-align:middle !important;min-width:40px;}
      .latex-table{border-collapse:collapse !important;border:1px solid #334155 !important;}
      .latex-table td,.latex-table th{border:1px solid #334155 !important;}
      .row-head{font-weight:700;background:#f8fafc;}
      .solution-title{display:block;width:100%;text-align:center;color:#0f3d91;font-size:13pt;font-weight:700;margin:8px 0 6px;}
    </style>
    """

    if "<html" not in html.lower():
        html = f'<!doctype html><html><head><meta charset="utf-8">{style}</head><body>{html}</body></html>'
    elif "</head>" in html.lower():
        html = re.sub(r"</head>", style + "</head>", html, count=1, flags=re.I)
    return html


def _add_visible_borders_to_docx(docx_path: Path):
    """Ép tất cả bảng trong DOCX có đường kẻ rõ, vì Pandoc đôi khi tạo bảng nhưng Word không hiện border."""
    tmp_dir = docx_path.parent / (docx_path.stem + "_unzipped")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(docx_path, 'r') as z:
        z.extractall(tmp_dir)
    document_xml = tmp_dir / 'word' / 'document.xml'
    if not document_xml.exists():
        return
    import xml.etree.ElementTree as ET
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    ET.register_namespace('w', ns['w'])
    tree = ET.parse(document_xml)
    root = tree.getroot()
    W = '{%s}' % ns['w']
    changed = False
    for tbl in root.findall('.//w:tbl', ns):
        tblPr = tbl.find('w:tblPr', ns)
        if tblPr is None:
            tblPr = ET.Element(W + 'tblPr')
            tbl.insert(0, tblPr)
        old = tblPr.find('w:tblBorders', ns)
        if old is not None:
            tblPr.remove(old)
        borders = ET.Element(W + 'tblBorders')
        for name in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
            el = ET.SubElement(borders, W + name)
            el.set(W + 'val', 'single')
            el.set(W + 'sz', '8')
            el.set(W + 'space', '0')
            el.set(W + 'color', '334155')
        tblPr.append(borders)
        changed = True
    if changed:
        tree.write(document_xml, encoding='utf-8', xml_declaration=True)
        new_docx = docx_path.parent / (docx_path.stem + '_bordered.docx')
        with zipfile.ZipFile(new_docx, 'w', zipfile.ZIP_DEFLATED) as zout:
            for f in tmp_dir.rglob('*'):
                if f.is_file():
                    zout.write(f, f.relative_to(tmp_dir).as_posix())
        shutil.move(str(new_docx), str(docx_path))
    shutil.rmtree(tmp_dir, ignore_errors=True)



def _html_preview_to_markdown_for_pandoc(html: str) -> str:
    """Đổi HTML phần xem trước về Markdown để Pandoc nhận $$...$$ thành Word Equation thật.
    Lý do: Pandoc đọc HTML thường giữ $$ dưới dạng chữ; đọc Markdown thì chuyển đúng sang OMML.
    Hàm này vẫn giữ bảng bằng pipe table và giữ ảnh bằng Markdown image.
    """
    html = html or ""

    # FIX chắc chắn lần 2: xóa CSS/JS/head trước khi bỏ tag HTML.
    # Nếu không xóa ở đây, nội dung trong <style> sẽ còn lại thành chữ ở đầu Word.
    html = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.I)
    html = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", html, flags=re.I)
    html = re.sub(r"<head[^>]*>[\s\S]*?</head>", "", html, flags=re.I)

    # Chuyển các bảng HTML thành bảng Markdown pipe table để Word có hàng/cột thật.
    def repl_table(m):
        table_html = m.group(0)
        rows = []
        for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", table_html, flags=re.I | re.S):
            cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr, flags=re.I | re.S)
            row = []
            for c in cells:
                c = re.sub(r"<br\s*/?>", " ", c, flags=re.I)
                c = re.sub(r"<[^>]+>", " ", c)
                c = html_lib.unescape(c).replace("\xa0", " ")
                c = re.sub(r"\s+", " ", c).strip()
                c = c.replace("|", r"\|")
                row.append(c or " ")
            if row:
                rows.append(row)

        if not rows:
            return ""

        max_cols = max(len(r) for r in rows)
        for r in rows:
            while len(r) < max_cols:
                r.append(" ")

        header = rows[0]
        out = []
        out.append("| " + " | ".join(header) + " |")
        out.append("| " + " | ".join(["---"] * max_cols) + " |")
        for r in rows[1:]:
            out.append("| " + " | ".join(r) + " |")
        return "\n\n" + "\n".join(out) + "\n\n"

    html = re.sub(r"<table\b[\s\S]*?</table>", repl_table, html, flags=re.I)

    # Ảnh: giữ đường dẫn ảnh tương đối đã được tách ra ở _prepare_preview_html_for_docx.
    def repl_img(m):
        tag = m.group(0)
        src_m = re.search(r"\bsrc=[\"']([^\"']+)[\"']", tag, flags=re.I)
        if not src_m:
            return ""
        src = src_m.group(1)
        return "\n\n![](" + src + ")\n\n"

    html = re.sub(r"<img\b[^>]*>", repl_img, html, flags=re.I)

    # Chuyển danh sách HTML sang Markdown không cần bs4.
    def _convert_lists(src):
        # Preserve ordered list numbering for pandoc
        def ol_repl(m):
            inner=m.group(1)
            items=re.findall(r'<li[^>]*>(.*?)</li>',inner,flags=re.I|re.S)
            out=[]
            for i,it in enumerate(items,1):
                out.append(f"\n{i}. "+re.sub(r'<[^>]+>','',it).strip())
            return "\n".join(out)
        src=re.sub(r'<ol[^>]*>(.*?)</ol>',ol_repl,src,flags=re.I|re.S)
        def ul_repl(m):
            inner=m.group(1)
            items=re.findall(r'<li[^>]*>(.*?)</li>',inner,flags=re.I|re.S)
            return "\n".join(["\n- "+re.sub(r'<[^>]+>','',it).strip() for it in items])
        src=re.sub(r'<ul[^>]*>(.*?)</ul>',ul_repl,src,flags=re.I|re.S)
        src=re.sub(r'</?li[^>]*>','',src,flags=re.I)
        return src
    html=_convert_lists(html)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</li>", "\n", html, flags=re.I)
    html = re.sub(r"</?(ol|ul)\b[^>]*>", "\n", html, flags=re.I)
    html = re.sub(r"</(p|div|h1|h2|h3|h4|h5|h6)>", "\n\n", html, flags=re.I)
    html = re.sub(r"<(p|div|h1|h2|h3|h4|h5|h6)\b[^>]*>", "\n", html, flags=re.I)

    # Bỏ tag còn lại, giữ text.
    md = re.sub(r"<[^>]+>", "", html)
    md = html_lib.unescape(md).replace("\xa0", " ")

    # Sửa lỗi phổ biến: $$ bị tách dòng/paragraph riêng. Gom lại thành block math chuẩn.
    md = re.sub(r"(?m)^\s*\$\$\s*$", "$$", md)
    md = re.sub(r"\$\$\s*\n\s*\$\$", "", md)  # bỏ block rỗng $$ $$
    md = re.sub(r"\$\$\s*([^\n$][\s\S]*?)\s*\$\$", lambda m: "\n\n$$\n" + _clean_latex_piece_for_docx(m.group(1)) + "\n$$\n\n", md)

    # Chuyển \[...\] thành $$...$$ để Pandoc Markdown nhận chắc chắn.
    md = re.sub(
        r"\\\[([\s\S]*?)\\\]",
        lambda m: "\n\n$$\n" + _clean_latex_piece_for_docx(m.group(1)) + "\n$$\n\n",
        md,
    )

    # Chuyển các công thức dạng \( ... \) về inline math sạch.
    md = re.sub(
        r"\\\(([\s\S]*?)\\\)",
        lambda m: r"\(" + _clean_latex_piece_for_docx(m.group(1)).replace("\n", " ") + r"\)",
        md,
    )

    # Nếu OCR tạo block kiểu:
    # $$
    # công thức
    # $$
    # thì giữ; nếu có dòng $$ lẻ không đóng, xóa để không hiện ra Word.
    lines = md.splitlines()
    fixed = []
    in_math = False
    math_buf = []
    for line in lines:
        if line.strip() == "$$":
            if not in_math:
                in_math = True
                math_buf = []
            else:
                latex = _clean_latex_piece_for_docx("\n".join(math_buf))
                if latex:
                    fixed.append("")
                    fixed.append("$$")
                    fixed.append(latex)
                    fixed.append("$$")
                    fixed.append("")
                in_math = False
                math_buf = []
            continue
        if in_math:
            math_buf.append(line)
        else:
            fixed.append(line)
    # Nếu còn $$ mở mà không đóng thì đưa nội dung ra text thường, bỏ dấu $$ để Word không hiện $$.
    if in_math and math_buf:
        fixed.extend(math_buf)

    md = "\n".join(fixed)

    # Dọn khoảng trắng quá nhiều nhưng không phá bảng/công thức.
    md = re.sub(r"[ \t]+\n", "\n", md)
    md = re.sub(r"\n{4,}", "\n\n", md).strip() + "\n"
    return _normalize_math_for_pandoc(md)

@app.post("/export-docx-preview")
async def export_docx_preview(payload: ExportPreviewHtmlPayload):
    if not payload.html.strip():
        raise HTTPException(status_code=400, detail="Chưa có nội dung xem trước để xuất Word")

    pandoc_bin = os.getenv("PANDOC_PATH") or shutil.which("pandoc")
    if not pandoc_bin:
        raise HTTPException(status_code=500, detail="Server chưa có Pandoc nên chưa xuất được Word. Cần cài pandoc hoặc đặt biến PANDOC_PATH.")

    tmp_root = Path(tempfile.mkdtemp(prefix="docx_preview_export_"))
    try:
        html = _prepare_preview_html_for_docx(payload.html, tmp_root)

        # QUAN TRỌNG:
        # Không cho Pandoc đọc trực tiếp HTML khi có $$...$$, vì dễ bị xuất nguyên LaTeX ra Word.
        # Đổi sang Markdown rồi dùng tex_math_dollars để Pandoc tạo Word Equation thật.
        md = _html_preview_to_markdown_for_pandoc(html)
        md_path = tmp_root / "preview.md"
        docx_path = tmp_root / f"{uuid.uuid4().hex}.docx"
        md_path.write_text(md, encoding="utf-8")
        cmd = [
            pandoc_bin,
            str(md_path),
            "-f", "markdown+tex_math_dollars+tex_math_single_backslash+pipe_tables",
            "-t", "docx",
            "--resource-path", str(tmp_root),
            "-o", str(docx_path),
        ]
        completed = subprocess.run(cmd, cwd=str(tmp_root), capture_output=True, text=True, timeout=120)
        if completed.returncode != 0 or not docx_path.exists():
            raise RuntimeError(completed.stderr or completed.stdout or "Pandoc không tạo được file docx")
        _add_visible_borders_to_docx(docx_path)
        _ensure_docx_equations_are_real(docx_path)
        filename = _safe_filename(payload.title or "ket-qua-ocr") + ".docx"
        return FileResponse(path=str(docx_path), filename=filename, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", background=None)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi xuất Word từ phần xem trước: {e}")

