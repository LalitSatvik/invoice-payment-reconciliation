"""Optional OCR fallback for scanned/image-only PDF invoices.

``pdf_extractor.py`` only works on PDFs that have a text layer. When a PDF is
a scanned image (no text layer, so pdfplumber returns empty strings), this
module rasterizes each page and runs it through Tesseract OCR to recover
*raw* text.

This is deliberately a thin, best-effort stub: it does not attempt to run the
regex field heuristics against the OCR output, correct OCR errors, or handle
multi-column layouts. It exists so a later task can wire "extraction found
nothing" into an optional, explicitly opt-in fallback path — not to be a
production-grade OCR pipeline. OCR is slow and consumes an external Tesseract
binary + Poppler, so it is gated behind ``Settings.enable_ocr_fallback``
(default ``False``) and should stay opt-in.
"""
from __future__ import annotations

from typing import IO, List, Union

import pytesseract
from pdf2image import convert_from_bytes

from app.config import settings


class OcrFallbackDisabled(RuntimeError):
    """Raised when extract_via_ocr is called while the feature flag is off."""


def extract_via_ocr(pdf_bytes: Union[bytes, IO[bytes]], dpi: int = 200) -> List[str]:
    """Rasterize each page of a PDF and OCR it, returning one raw text blob per page.

    Raises :class:`OcrFallbackDisabled` unless ``Settings.enable_ocr_fallback``
    is ``True``. Returns raw OCR text only — no field extraction is
    attempted here; feed the output back through the ``pdf_extractor``
    heuristics (or a human reviewer) if structured fields are needed.
    """
    if not settings.enable_ocr_fallback:
        raise OcrFallbackDisabled(
            "OCR fallback is disabled; set ENABLE_OCR_FALLBACK=true to enable it."
        )

    data = pdf_bytes.read() if hasattr(pdf_bytes, "read") else pdf_bytes
    pages = convert_from_bytes(data, dpi=dpi)
    return [pytesseract.image_to_string(page) for page in pages]
