"""Tests for regex/heuristic PDF invoice extraction (Task 4).

Synthetic invoice PDFs are generated on the fly with reportlab -- simple
single-page, text-layer layouts are enough here since this is testing the
extraction heuristics, not OCR or complex PDF layout handling.
"""
import hashlib
import io

import pytest

# reportlab 4.4.3's PDFDocument unconditionally calls
# hashlib.md5(usedforsecurity=False); the OpenSSL-backed _hashlib shipped
# with this conda environment's Python 3.8 build doesn't accept that keyword.
# Patch reportlab's md5 reference to drop it before generating any PDF.
import reportlab.pdfbase.pdfdoc as _pdfdoc

_pdfdoc.md5 = lambda *args, **kwargs: hashlib.md5(*args)

from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from app.ingestion.pdf_extractor import extract_invoice_fields  # noqa: E402


def _make_pdf(lines):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    y = 750
    for line in lines:
        c.drawString(72, y, line)
        y -= 20
    c.showPage()
    c.save()
    return buf.getvalue()


def test_extracts_all_fields_from_a_well_formed_invoice():
    pdf_bytes = _make_pdf(
        [
            "Acme Robotics Inc",
            "123 Robot Way, Springfield",
            "",
            "INVOICE",
            "Invoice Number: INV-2001",
            "Invoice Date: 2026-01-15",
            "Due Date: 2026-02-14",
            "Description: Consulting services",
            "Total: $1,250.00",
        ]
    )

    result = extract_invoice_fields(pdf_bytes)

    assert result["invoice_number"] == "INV-2001"
    assert result["date"].isoformat() == "2026-01-15"
    assert result["due_date"].isoformat() == "2026-02-14"
    assert str(result["amount"]) == "1250.00"
    assert result["vendor_name"] == "Acme Robotics Inc"
    assert result["confidence"] == 1.0
    assert result["warnings"] == []


def test_extracts_fields_with_alternate_labels_and_date_format():
    pdf_bytes = _make_pdf(
        [
            "Blue Harbor Supplies",
            "Invoice No. INV-3005",
            "Invoice Date 01/10/2026",
            "Due Date 02/09/2026",
            "Subtotal: $75.00",
            "Amount Due: $80.00",
        ]
    )

    result = extract_invoice_fields(pdf_bytes)

    assert result["invoice_number"] == "INV-3005"
    assert result["date"].isoformat() == "2026-01-10"
    assert result["due_date"].isoformat() == "2026-02-09"
    # "Amount Due" must win over "Subtotal", even though Subtotal appears first.
    assert str(result["amount"]) == "80.00"
    assert result["confidence"] == 1.0


def test_missing_fields_come_back_as_none_with_warnings_not_an_exception():
    pdf_bytes = _make_pdf(
        [
            "Continental Freight Ltd",
            "INVOICE",
            "Invoice Date: 2026-01-20",
            "No total is printed anywhere on this document.",
        ]
    )

    result = extract_invoice_fields(pdf_bytes)

    assert result["invoice_number"] is None
    assert result["due_date"] is None
    assert result["amount"] is None
    assert result["date"].isoformat() == "2026-01-20"
    assert result["vendor_name"] == "Continental Freight Ltd"
    assert result["confidence"] < 1.0
    assert any("invoice number" in w.lower() for w in result["warnings"])
    assert any("total amount" in w.lower() for w in result["warnings"])
    assert any("due date" in w.lower() for w in result["warnings"])


def test_falls_back_to_bare_inv_token_when_no_label_is_present():
    pdf_bytes = _make_pdf(["Some Vendor", "Reference INV-9999 for services rendered"])
    result = extract_invoice_fields(pdf_bytes)
    assert result["invoice_number"] == "INV-9999"
