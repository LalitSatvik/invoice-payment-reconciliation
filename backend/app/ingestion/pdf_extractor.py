"""Best-effort field extraction from PDF invoices.

Uses ``pdfplumber`` to pull the text layer out of a PDF, then a handful of
regex heuristics to locate the invoice number, invoice date, due date, total
amount, and vendor name. This is intentionally heuristic, not a general
invoice-parsing engine: it is tuned for reasonably conventional, text-layer
invoices (not scanned images — see ``ocr_fallback.py`` for that case) with
labeled fields such as "Invoice Number:", "Invoice Date:", "Total:".

Every field that can't be confidently located comes back as ``None`` rather
than raising, and is called out in ``warnings`` so the API layer can flag the
upload for review instead of silently persisting incomplete data. Callers
should always check ``confidence``/``warnings`` before trusting the result.

Known limitations (documented rather than solved here):
- Requires a text layer; scanned/photographed invoices need OCR fallback.
- Assumes the vendor name is the first non-empty line of text (the
  letterhead), which fails for invoices with a logo-only header, a return
  address before the vendor name, or a decorative "INVOICE" banner that
  pdfplumber renders as the first line.
- The amount heuristic looks for a labeled total on a single line; it won't
  find totals that are split across a table cell boundary, in a currency
  other than a leading currency symbol, or negative/credit amounts.
- Date parsing supports a fixed set of common formats (ISO, US slash dates,
  "Month D, YYYY"); anything else is reported as not found rather than
  guessed at.
- Multi-page invoices are read as one concatenated text blob in page order;
  no attempt is made to determine which page a field belongs to.
"""
from __future__ import annotations

import io
import re
from datetime import date as date_
from decimal import Decimal
from typing import IO, Any, Dict, List, Optional, Union

import pdfplumber

from app.ingestion.csv_parser import parse_amount, parse_date

# --- invoice number -----------------------------------------------------
# Tried in order; the first pattern to match wins. Patterns are anchored on
# an explicit "Invoice" label so we don't accidentally grab "Invoice Date"
# or "Invoice Total" as if they were the invoice number.
_INVOICE_NUMBER_PATTERNS = [
    re.compile(r"Invoice\s*(?:No\.?|Number|#)\s*[:\-]?\s*([A-Za-z0-9][\w\-/]*)", re.IGNORECASE),
    re.compile(r"Invoice\s*:\s*([A-Za-z0-9][\w\-/]*)", re.IGNORECASE),
    # Fallback: a bare INV-style token anywhere in the document.
    re.compile(r"\b(INV[-_]\d[\w\-]*)\b", re.IGNORECASE),
]

# --- dates ---------------------------------------------------------------
_DATE_TOKEN = r"([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})"
_INVOICE_DATE_PATTERN = re.compile(r"Invoice\s*Date\s*[:\-]?\s*" + _DATE_TOKEN, re.IGNORECASE)
_DUE_DATE_PATTERN = re.compile(r"Due\s*Date\s*[:\-]?\s*" + _DATE_TOKEN, re.IGNORECASE)

# --- total amount ----------------------------------------------------------
# Checked in priority order (most specific/unambiguous label first) so that,
# e.g., "Amount Due" wins over a generic "Total" line if both are present.
_AMOUNT_TOKEN = r"\$?\s*([\d,]+\.\d{2})"
_PRIORITY_AMOUNT_LABELS = ["Amount Due", "Total Due", "Balance Due", "Grand Total"]
_SUBTOTAL_RE = re.compile(r"sub\s*total", re.IGNORECASE)
_PLAIN_TOTAL_RE = re.compile(r"\bTotal\b\s*[:\-]?\s*" + _AMOUNT_TOKEN, re.IGNORECASE)

_FIELDS_FOR_CONFIDENCE = ("invoice_number", "date", "amount", "due_date", "vendor_name")


def extract_text_from_pdf(pdf_bytes: Union[bytes, IO[bytes]]) -> str:
    """Extract and concatenate the text layer of every page of a PDF."""
    stream = io.BytesIO(pdf_bytes) if isinstance(pdf_bytes, bytes) else pdf_bytes
    with pdfplumber.open(stream) as pdf:
        page_texts = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(page_texts)


def _extract_invoice_number(text: str) -> Optional[str]:
    for pattern in _INVOICE_NUMBER_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    return None


def _extract_labeled_date(text: str, pattern: "re.Pattern[str]") -> Optional[date_]:
    match = pattern.search(text)
    if not match:
        return None
    try:
        return parse_date(match.group(1))
    except ValueError:
        return None


def _extract_total_amount(text: str) -> Optional[Decimal]:
    for label in _PRIORITY_AMOUNT_LABELS:
        pattern = re.compile(re.escape(label) + r"\s*[:\-]?\s*" + _AMOUNT_TOKEN, re.IGNORECASE)
        match = pattern.search(text)
        if match:
            return parse_amount(match.group(1))

    # Fall back to a plain "Total" line, skipping any line that is really a
    # subtotal (e.g. "Subtotal: $100.00" would otherwise match "\bTotal\b").
    for line in text.splitlines():
        if _SUBTOTAL_RE.search(line):
            continue
        match = _PLAIN_TOTAL_RE.search(line)
        if match:
            return parse_amount(match.group(1))
    return None


def _extract_vendor_name(text: str) -> Optional[str]:
    """Best-effort: the first non-empty line that isn't a generic document title."""
    generic_titles = {"invoice", "invoice.", "bill", "receipt", "statement"}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower() in generic_titles:
            continue
        return stripped
    return None


def extract_invoice_fields(pdf_bytes: Union[bytes, IO[bytes]]) -> Dict[str, Any]:
    """Extract canonical invoice fields from a PDF invoice's text layer.

    Returns a dict shaped like the invoice-target fields produced by
    ``csv_parser.parse_csv`` (``date``, ``amount``, ``invoice_number``,
    ``vendor_name``, ``due_date``), typed the same way (``date`` objects,
    ``Decimal`` amount, stripped strings), plus ``confidence`` (fraction of
    the five fields that were found, 0.0-1.0 — a rough heuristic score, not a
    calibrated probability) and ``warnings`` (a list of human-readable
    strings, one per field that couldn't be confidently extracted). Fields
    that can't be found are ``None`` rather than raising, so a single
    unparseable invoice never crashes a batch upload.
    """
    text = extract_text_from_pdf(pdf_bytes)

    invoice_number = _extract_invoice_number(text)
    invoice_date = _extract_labeled_date(text, _INVOICE_DATE_PATTERN)
    due_date = _extract_labeled_date(text, _DUE_DATE_PATTERN)
    amount = _extract_total_amount(text)
    vendor_name = _extract_vendor_name(text)

    result: Dict[str, Any] = {
        "invoice_number": invoice_number,
        "vendor_name": vendor_name,
        "date": invoice_date,
        "due_date": due_date,
        "amount": amount,
    }

    warnings: List[str] = []
    field_labels = {
        "invoice_number": "invoice number",
        "date": "invoice date",
        "due_date": "due date",
        "amount": "total amount",
        "vendor_name": "vendor name",
    }
    for field_name in _FIELDS_FOR_CONFIDENCE:
        if result[field_name] is None:
            warnings.append(f"Could not confidently extract {field_labels[field_name]}")

    confidence = sum(result[f] is not None for f in _FIELDS_FOR_CONFIDENCE) / len(
        _FIELDS_FOR_CONFIDENCE
    )

    result["confidence"] = confidence
    result["warnings"] = warnings
    return result
