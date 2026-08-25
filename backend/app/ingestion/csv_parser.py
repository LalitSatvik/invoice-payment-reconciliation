"""Mapping-driven CSV parser shared by invoice-CSV and bank-CSV ingestion.

Uploaded CSVs rarely use canonical header names (a bank export might call the
amount column "Trans Amt"), so callers pass a ``column_map`` that says which
canonical field lives under which actual header. The same :func:`parse_csv`
is used for both invoice and payment ingestion; the only difference is which
canonical keys the caller includes in ``column_map``:

- Bank/payment CSVs typically map ``date``, ``amount``, ``reference``,
  ``counterparty``.
- Invoice CSVs typically map ``date`` (-> the invoice date column),
  ``amount``, ``invoice_number``, ``vendor_name``, ``due_date``.

``date`` and ``amount`` are the only two canonical keys treated as required:
every other supported key is optional and simply omitted from the resulting
row dict (as ``None``, or dropped entirely for a plain value) when the
caller's ``column_map`` doesn't include it.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date as date_
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Union

# Canonical fields this parser knows how to type-convert, keyed by how their
# raw string value should be interpreted.
DATE_FIELDS = {"date", "due_date"}
DECIMAL_FIELDS = {"amount"}
# String fields are anything else named in a column_map (reference,
# counterparty, invoice_number, vendor_name, ...); no fixed allow-list is
# enforced so new canonical fields can be added by callers without changing
# this module.

REQUIRED_FIELDS = {"date", "amount"}

# Accepted textual date formats, tried in order. ISO (the format the Task 3
# synthetic generator writes) is tried first.
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%m/%d/%y",
    "%B %d, %Y",
    "%b %d, %Y",
)


class CsvParseError(ValueError):
    """Raised for CSV-level problems (bad column_map, empty file, ...)."""


@dataclass
class RowError:
    """A single row that failed to parse; does not abort the rest of the batch."""

    row_number: int  # 1-indexed data row, header excluded (row_number=1 is the first data row)
    message: str
    raw_row: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "row_number": self.row_number,
            "message": self.message,
            "raw_row": self.raw_row,
        }


@dataclass
class ParseResult:
    """Outcome of parsing a mapped CSV: successfully parsed rows plus any
    row-level errors, so one bad row never discards the rest of the batch.
    """

    rows: List[Dict[str, Any]]
    errors: List[RowError]

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


def _decode(csv_data: Union[bytes, str]) -> str:
    if isinstance(csv_data, bytes):
        return csv_data.decode("utf-8-sig")
    return csv_data


def _dict_reader(csv_data: Union[bytes, str]) -> csv.DictReader:
    text = _decode(csv_data)
    return csv.DictReader(io.StringIO(text))


def parse_date(raw_value: str) -> date_:
    """Parse a date string using the accepted formats, raising ValueError if none match."""
    value = raw_value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"could not parse {raw_value!r} as a date")


def parse_amount(raw_value: str) -> Decimal:
    """Parse a monetary string into a Decimal.

    Tolerates a leading currency symbol, thousands separators, surrounding
    whitespace, and parentheses-as-negative (e.g. "(123.45)" -> -123.45).
    Raises ValueError/InvalidOperation (via a plain ValueError) for anything
    that isn't recognizably a number.
    """
    value = raw_value.strip()
    if not value:
        raise ValueError("amount is empty")
    negative = False
    if value.startswith("(") and value.endswith(")"):
        negative = True
        value = value[1:-1].strip()
    for symbol in ("$", "£", "€", ","):
        value = value.replace(symbol, "")
    value = value.strip()
    if value.startswith("-"):
        negative = True
        value = value[1:].strip()
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"could not parse {raw_value!r} as an amount") from exc
    return -amount if negative else amount


def _parse_field(canonical_field: str, raw_value: Optional[str]) -> Any:
    value = (raw_value or "").strip()
    if canonical_field in DATE_FIELDS:
        if not value:
            return None
        return parse_date(value)
    if canonical_field in DECIMAL_FIELDS:
        return parse_amount(value)
    # Plain string field: stripped, or None if blank.
    return value or None


def parse_csv(csv_data: Union[bytes, str], column_map: Dict[str, str]) -> ParseResult:
    """Parse a raw CSV (bytes or text) into canonical dicts driven by column_map.

    ``column_map`` maps canonical field name -> actual header name present in
    the CSV, e.g. ``{"date": "Post Date", "amount": "Trans Amt",
    "reference": "Memo", "counterparty": "Other Party"}``.

    Returns a :class:`ParseResult` with ``rows`` (each a dict keyed by the
    canonical field names present in column_map, plus ``raw_row`` holding the
    untouched original row as a header->value dict) and ``errors`` for any
    row that failed to parse (e.g. a malformed amount) — a bad row is
    reported, not allowed to abort the whole batch.
    """
    if not column_map.get("date") or not column_map.get("amount"):
        raise CsvParseError("column_map must map both 'date' and 'amount'")

    reader = _dict_reader(csv_data)
    if reader.fieldnames is None:
        raise CsvParseError("CSV has no header row")

    missing_headers = [
        header for header in column_map.values() if header not in reader.fieldnames
    ]
    if missing_headers:
        raise CsvParseError(
            f"column_map references headers not present in the CSV: {missing_headers}"
        )

    rows: List[Dict[str, Any]] = []
    errors: List[RowError] = []

    for row_number, raw_row in enumerate(reader, start=1):
        try:
            parsed: Dict[str, Any] = {}
            for canonical_field, header in column_map.items():
                raw_value = raw_row.get(header)
                if canonical_field in REQUIRED_FIELDS and not (raw_value or "").strip():
                    raise ValueError(f"required field '{canonical_field}' is missing or blank")
                parsed[canonical_field] = _parse_field(canonical_field, raw_value)
            parsed["raw_row"] = dict(raw_row)
            rows.append(parsed)
        except ValueError as exc:
            errors.append(RowError(row_number=row_number, message=str(exc), raw_row=dict(raw_row)))

    return ParseResult(rows=rows, errors=errors)


def preview_headers(csv_data: Union[bytes, str], sample_size: int = 5) -> Dict[str, Any]:
    """Read just the headers and a few sample rows, for the column-mapping UI.

    Returns ``{"headers": [...], "sample_rows": [{header: raw_value, ...}, ...]}``.
    Values in sample_rows are raw (unparsed) strings, exactly as they appear
    in the file, since the caller hasn't chosen a column_map yet.
    """
    reader = _dict_reader(csv_data)
    if reader.fieldnames is None:
        raise CsvParseError("CSV has no header row")

    headers = list(reader.fieldnames)
    sample_rows: List[Dict[str, Any]] = []
    for row in reader:
        if len(sample_rows) >= sample_size:
            break
        sample_rows.append(dict(row))

    return {"headers": headers, "sample_rows": sample_rows}
