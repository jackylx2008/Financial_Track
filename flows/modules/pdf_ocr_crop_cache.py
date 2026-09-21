from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


BEIJING_TIMEZONE = timezone(timedelta(hours=8), name="北京时间")
CROP_SCHEMA_VERSION = 1
OCR_RENDER_SCALE = 2.0
OCR_MIN_CONFIDENCE = 0.55
OCR_HORIZONTAL_PADDING_RATIO = 0.02
MIN_CONTENT_WIDTH_RATIO = 0.35

OcrBox = tuple[list[list[float]], str, float]


def load_or_detect_pdf_crop(
    document: Any,
    pdf_sha256: str,
    cache_path: Path,
    *,
    ocr: Callable[[Path], list[OcrBox]] | None = None,
) -> tuple[dict[str, Any], bool]:
    """Return a document-wide horizontal crop; OCR at most once per PDF hash."""
    if not pdf_sha256.strip():
        raise ValueError("PDF 缺少 SHA-256，不能建立裁边缓存")
    payload = _load_cache(cache_path)
    cached = payload["documents"].get(pdf_sha256)
    if cached is not None:
        return cached, True

    crop = detect_pdf_horizontal_crop(document, ocr=ocr)
    crop.update(
        {
            "pdf_sha256": pdf_sha256,
            "detected_at": datetime.now(BEIJING_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    payload["documents"][pdf_sha256] = crop
    payload["updated_at"] = crop["detected_at"]
    _write_cache(cache_path, payload)
    return crop, False


def detect_pdf_horizontal_crop(
    document: Any,
    *,
    ocr: Callable[[Path], list[OcrBox]] | None = None,
) -> dict[str, Any]:
    if document.page_count < 1:
        raise ValueError("PDF 没有页面，无法识别左右边框")
    page = document.load_page(0)
    pixmap = _render_page(page)
    with tempfile.TemporaryDirectory(prefix="financial_pdf_crop_") as directory:
        image_path = Path(directory) / "page_0001.png"
        pixmap.save(image_path)
        boxes = (ocr or _rapid_ocr_boxes)(image_path)

    usable = [box for box in boxes if _usable_ocr_box(box)]
    if not usable:
        return _full_page_crop("ocr_no_boxes")
    left = min(min(point[0] for point in box[0]) for box in usable) / pixmap.width
    right = max(max(point[0] for point in box[0]) for box in usable) / pixmap.width
    left = max(0.0, left - OCR_HORIZONTAL_PADDING_RATIO)
    right = min(1.0, right + OCR_HORIZONTAL_PADDING_RATIO)
    if right - left < MIN_CONTENT_WIDTH_RATIO:
        return _full_page_crop("ocr_width_too_narrow")
    return {
        "left_ratio": round(left, 6),
        "right_ratio": round(right, 6),
        "sample_page": 1,
        "ocr_box_count": len(usable),
        "method": "rapidocr_text_bounds",
    }


def crop_page_rect(page: Any, crop: dict[str, Any]) -> Any:
    import fitz

    left = max(0.0, min(1.0, float(crop.get("left_ratio", 0.0))))
    right = max(left, min(1.0, float(crop.get("right_ratio", 1.0))))
    return fitz.Rect(page.rect.width * left, 0, page.rect.width * right, page.rect.height)


def _render_page(page: Any) -> Any:
    import fitz

    return page.get_pixmap(matrix=fitz.Matrix(OCR_RENDER_SCALE, OCR_RENDER_SCALE), alpha=False)


def _rapid_ocr_boxes(path: Path) -> list[OcrBox]:
    from rapidocr_onnxruntime import RapidOCR

    engine = getattr(_rapid_ocr_boxes, "_engine", None)
    if engine is None:
        engine = RapidOCR()
        setattr(_rapid_ocr_boxes, "_engine", engine)
    result, _ = engine(str(path))
    return [
        (
            [[float(point[0]), float(point[1])] for point in item[0]],
            str(item[1]),
            float(item[2]),
        )
        for item in result or []
        if len(item) >= 3
    ]


def _usable_ocr_box(box: OcrBox) -> bool:
    _, text, confidence = box
    if confidence < OCR_MIN_CONFIDENCE or not text.strip():
        return False
    return any(character.isalnum() or "\u4e00" <= character <= "\u9fff" for character in text)


def _full_page_crop(reason: str) -> dict[str, Any]:
    return {
        "left_ratio": 0.0,
        "right_ratio": 1.0,
        "sample_page": 1,
        "ocr_box_count": 0,
        "method": reason,
    }


def _load_cache(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": CROP_SCHEMA_VERSION, "documents": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != CROP_SCHEMA_VERSION:
        raise ValueError(f"不支持的 PDF 裁边缓存版本：{path}")
    payload.setdefault("documents", {})
    return payload


def _write_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
