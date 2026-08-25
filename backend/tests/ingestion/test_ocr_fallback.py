"""Smoke tests for the OCR fallback stub (Task 4).

These only confirm the function is callable and correctly gated by the
config flag; OCR accuracy is explicitly out of scope. Real OCR needs system
binaries (Tesseract, Poppler) that may not be present in every environment,
so the "enabled" path stubs out pdf2image/pytesseract rather than requiring
them.
"""
import pytest

from app.config import settings
from app.ingestion import ocr_fallback


@pytest.fixture(autouse=True)
def _restore_flag():
    original = settings.enable_ocr_fallback
    yield
    settings.enable_ocr_fallback = original


def test_raises_when_the_feature_flag_is_off():
    settings.enable_ocr_fallback = False
    with pytest.raises(ocr_fallback.OcrFallbackDisabled):
        ocr_fallback.extract_via_ocr(b"%PDF-fake%")


def test_is_callable_and_returns_per_page_text_when_enabled(monkeypatch):
    settings.enable_ocr_fallback = True

    fake_pages = ["page one image", "page two image"]
    monkeypatch.setattr(
        ocr_fallback, "convert_from_bytes", lambda data, dpi=200: fake_pages
    )
    monkeypatch.setattr(
        ocr_fallback.pytesseract,
        "image_to_string",
        lambda image: f"OCR TEXT: {image}",
    )

    result = ocr_fallback.extract_via_ocr(b"%PDF-fake%")

    assert result == ["OCR TEXT: page one image", "OCR TEXT: page two image"]
