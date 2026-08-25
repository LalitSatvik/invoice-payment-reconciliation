"""Tests for the mapping-driven CSV parser (Task 4)."""
from datetime import date
from decimal import Decimal

import pytest

from app.ingestion.csv_parser import (
    CsvParseError,
    parse_amount,
    parse_csv,
    parse_date,
    preview_headers,
)

# Mirrors backend/data/synthetic/bank_statement.csv's deliberately
# non-canonical headers.
BANK_CSV = (
    "Post Date,Trans Amt,Memo,Other Party\n"
    "2026-02-04,1250.00,INV-1001 ACME ROBOTICS INC,Acme Robotics Inc\n"
    "2026-02-09,79.00,INV-1101 Blue Harbor Supplies,Blue Harbor Supplies\n"
)
BANK_COLUMN_MAP = {
    "date": "Post Date",
    "amount": "Trans Amt",
    "reference": "Memo",
    "counterparty": "Other Party",
}

INVOICE_CSV = (
    "invoice_number,vendor_name,invoice_date,due_date,amount,description\n"
    "INV-1001,Acme Robotics Inc,2026-01-05,2026-02-04,1250.00,Consulting services\n"
    "INV-1101,Blue Harbor Supplies,2026-01-10,,80.00,Office supplies\n"
)
INVOICE_COLUMN_MAP = {
    "date": "invoice_date",
    "amount": "amount",
    "invoice_number": "invoice_number",
    "vendor_name": "vendor_name",
    "due_date": "due_date",
}


def test_parses_a_well_formed_bank_csv_with_non_canonical_headers():
    result = parse_csv(BANK_CSV, BANK_COLUMN_MAP)

    assert result.errors == []
    assert len(result.rows) == 2

    first = result.rows[0]
    assert first["date"] == date(2026, 2, 4)
    assert isinstance(first["date"], date)
    assert first["amount"] == Decimal("1250.00")
    assert isinstance(first["amount"], Decimal)
    assert first["reference"] == "INV-1001 ACME ROBOTICS INC"
    assert first["counterparty"] == "Acme Robotics Inc"
    assert first["raw_row"] == {
        "Post Date": "2026-02-04",
        "Trans Amt": "1250.00",
        "Memo": "INV-1001 ACME ROBOTICS INC",
        "Other Party": "Acme Robotics Inc",
    }


def test_parses_a_well_formed_invoice_csv_with_a_different_target_field_set():
    result = parse_csv(INVOICE_CSV, INVOICE_COLUMN_MAP)

    assert result.errors == []
    first = result.rows[0]
    assert first["invoice_number"] == "INV-1001"
    assert first["vendor_name"] == "Acme Robotics Inc"
    assert first["date"] == date(2026, 1, 5)
    assert first["due_date"] == date(2026, 2, 4)
    assert first["amount"] == Decimal("1250.00")
    # Fields not in column_map (reference/counterparty) are simply absent.
    assert "reference" not in first
    assert "counterparty" not in first


def test_blank_optional_field_comes_back_as_none_not_an_error():
    result = parse_csv(INVOICE_CSV, INVOICE_COLUMN_MAP)

    assert result.errors == []
    second = result.rows[1]
    assert second["due_date"] is None


def test_column_map_may_omit_optional_canonical_fields_entirely():
    # A caller that only cares about date/amount/invoice_number should be
    # able to omit vendor_name/due_date from column_map altogether.
    minimal_map = {"date": "invoice_date", "amount": "amount", "invoice_number": "invoice_number"}
    result = parse_csv(INVOICE_CSV, minimal_map)

    assert result.errors == []
    assert set(result.rows[0].keys()) == {"date", "amount", "invoice_number", "raw_row"}


def test_malformed_amount_is_flagged_as_a_row_level_error_not_a_crash():
    csv_data = (
        "Post Date,Trans Amt,Memo,Other Party\n"
        "2026-02-04,1250.00,INV-1001,Acme Robotics Inc\n"
        "2026-02-09,not-a-number,INV-1101,Blue Harbor Supplies\n"
        "2026-02-14,9950.00,INV-1151,Continental Freight Ltd\n"
    )
    result = parse_csv(csv_data, BANK_COLUMN_MAP)

    # The one bad row is reported, not fatal to the rest of the batch.
    assert len(result.rows) == 2
    assert len(result.errors) == 1
    bad_row = result.errors[0]
    assert bad_row.row_number == 2
    assert "amount" in bad_row.message.lower()
    assert bad_row.raw_row["Trans Amt"] == "not-a-number"


def test_missing_required_field_is_a_row_level_error():
    csv_data = "Post Date,Trans Amt,Memo,Other Party\n,1250.00,INV-1001,Acme Robotics Inc\n"
    result = parse_csv(csv_data, BANK_COLUMN_MAP)

    assert result.rows == []
    assert len(result.errors) == 1
    assert "date" in result.errors[0].message.lower()


def test_column_map_missing_date_or_amount_raises_at_parse_time():
    with pytest.raises(CsvParseError):
        parse_csv(BANK_CSV, {"reference": "Memo"})


def test_column_map_referencing_a_header_not_in_the_csv_raises():
    with pytest.raises(CsvParseError):
        parse_csv(BANK_CSV, {"date": "Post Date", "amount": "Nonexistent Header"})


def test_preview_headers_returns_headers_and_sample_rows():
    preview = preview_headers(BANK_CSV)

    assert preview["headers"] == ["Post Date", "Trans Amt", "Memo", "Other Party"]
    assert len(preview["sample_rows"]) == 2
    assert preview["sample_rows"][0] == {
        "Post Date": "2026-02-04",
        "Trans Amt": "1250.00",
        "Memo": "INV-1001 ACME ROBOTICS INC",
        "Other Party": "Acme Robotics Inc",
    }


def test_preview_headers_respects_sample_size():
    many_rows = "a,b\n" + "\n".join(f"{i},{i}" for i in range(10))
    preview = preview_headers(many_rows, sample_size=3)
    assert len(preview["sample_rows"]) == 3


def test_parse_csv_accepts_bytes_input_with_bom():
    csv_bytes = ("﻿" + BANK_CSV).encode("utf-8")
    result = parse_csv(csv_bytes, BANK_COLUMN_MAP)
    assert result.errors == []
    assert len(result.rows) == 2


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("$1,250.00", Decimal("1250.00")),
        ("1250.00", Decimal("1250.00")),
        ("(123.45)", Decimal("-123.45")),
        ("-50.00", Decimal("-50.00")),
        ("€99.99", Decimal("99.99")),
    ],
)
def test_parse_amount_handles_common_formats(raw, expected):
    assert parse_amount(raw) == expected


def test_parse_amount_rejects_garbage():
    with pytest.raises(ValueError):
        parse_amount("not-a-number")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-01-05", date(2026, 1, 5)),
        ("01/05/2026", date(2026, 1, 5)),
        ("January 5, 2026", date(2026, 1, 5)),
    ],
)
def test_parse_date_handles_common_formats(raw, expected):
    assert parse_date(raw) == expected


def test_parse_date_rejects_garbage():
    with pytest.raises(ValueError):
        parse_date("not-a-date")
