"""Tests for the upload endpoints (Task 6): preview, invoice/bank CSV
ingestion, PDF invoice ingestion, and batch status lookup.
"""
import hashlib
import io

from app.models import Invoice, Payment, UploadBatch

# reportlab 4.4.3's PDFDocument unconditionally calls
# hashlib.md5(usedforsecurity=False); the OpenSSL-backed _hashlib shipped
# with this conda environment's Python 3.8 build doesn't accept that keyword.
# Patch reportlab's md5 reference to drop it before generating any PDF.
import reportlab.pdfbase.pdfdoc as _pdfdoc

_pdfdoc.md5 = lambda *args, **kwargs: hashlib.md5(*args)

from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

INVOICE_CSV = (
    "invoice_number,vendor_name,invoice_date,due_date,amount,description\n"
    "INV-1001,Acme Robotics Inc,2026-01-05,2026-02-04,1250.00,Consulting services\n"
    "INV-1101,Blue Harbor Supplies,2026-01-10,2026-02-09,80.00,Office supplies\n"
)
INVOICE_COLUMN_MAP = {
    "date": "invoice_date",
    "amount": "amount",
    "invoice_number": "invoice_number",
    "vendor_name": "vendor_name",
    "due_date": "due_date",
}

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


def _create_mapping(client, source_name, target_kind, column_map):
    response = client.post(
        "/api/v1/mappings",
        json={"source_name": source_name, "target_kind": target_kind, "column_map": column_map},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_preview_returns_headers_and_positional_sample_rows(client):
    response = client.post(
        "/api/v1/uploads/preview",
        files={"file": ("bank.csv", BANK_CSV, "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["headers"] == ["Post Date", "Trans Amt", "Memo", "Other Party"]
    assert body["sample_rows"][0] == [
        "2026-02-04",
        "1250.00",
        "INV-1001 ACME ROBOTICS INC",
        "Acme Robotics Inc",
    ]


def test_preview_rejects_headerless_csv(client):
    response = client.post(
        "/api/v1/uploads/preview",
        files={"file": ("empty.csv", "", "text/csv")},
    )
    assert response.status_code == 422


def test_upload_invoice_csv_persists_invoices(client, db_session):
    mapping = _create_mapping(client, "Invoice export", "invoice", INVOICE_COLUMN_MAP)

    response = client.post(
        "/api/v1/uploads/invoices",
        data={"source_mapping_id": mapping["id"]},
        files={"file": ("invoices.csv", INVOICE_CSV, "text/csv")},
    )
    assert response.status_code == 201, response.text
    batch = response.json()
    assert batch["status"] == "completed"
    assert batch["row_count"] == 2
    assert batch["error_summary"] is None
    assert batch["kind"] == "invoice_csv"

    invoices = (
        db_session.query(Invoice)
        .filter(Invoice.upload_batch_id == batch["id"])
        .order_by(Invoice.invoice_number)
        .all()
    )
    assert len(invoices) == 2
    assert invoices[0].invoice_number == "INV-1001"
    assert invoices[0].vendor_name == "Acme Robotics Inc"
    assert invoices[0].invoice_date.isoformat() == "2026-01-05"
    assert invoices[0].due_date.isoformat() == "2026-02-04"
    assert str(invoices[0].amount) == "1250.00"

    status_response = client.get(f"/api/v1/uploads/{batch['id']}")
    assert status_response.status_code == 200
    assert status_response.json()["row_count"] == 2


def test_upload_bank_statement_persists_payments(client, db_session):
    mapping = _create_mapping(client, "Chase export", "payment", BANK_COLUMN_MAP)

    response = client.post(
        "/api/v1/uploads/bank-statement",
        data={"source_mapping_id": mapping["id"]},
        files={"file": ("bank.csv", BANK_CSV, "text/csv")},
    )
    assert response.status_code == 201, response.text
    batch = response.json()
    assert batch["status"] == "completed"
    assert batch["row_count"] == 2
    assert batch["kind"] == "bank_csv"

    payments = (
        db_session.query(Payment)
        .filter(Payment.upload_batch_id == batch["id"])
        .order_by(Payment.amount.desc())
        .all()
    )
    assert len(payments) == 2
    assert payments[0].payment_date.isoformat() == "2026-02-04"
    assert str(payments[0].amount) == "1250.00"
    assert payments[0].reference == "INV-1001 ACME ROBOTICS INC"
    assert payments[0].counterparty == "Acme Robotics Inc"
    assert payments[0].raw_row["Memo"] == "INV-1001 ACME ROBOTICS INC"


def test_upload_csv_with_mapping_missing_a_column_fails_batch_with_no_rows(client, db_session):
    # The mapping references a header ("Trans Amt") not present in this
    # month's export -- a whole-file failure, not a row-level one.
    mapping = _create_mapping(
        client,
        "Renamed export",
        "payment",
        {"date": "Post Date", "amount": "Trans Amt"},
    )
    renamed_csv = "Post Date,Amount\n2026-02-04,1250.00\n"

    response = client.post(
        "/api/v1/uploads/bank-statement",
        data={"source_mapping_id": mapping["id"]},
        files={"file": ("bank.csv", renamed_csv, "text/csv")},
    )
    assert response.status_code == 201, response.text
    batch = response.json()
    assert batch["status"] == "failed"
    assert batch["row_count"] == 0
    assert "Trans Amt" in batch["error_summary"]

    payments = (
        db_session.query(Payment).filter(Payment.upload_batch_id == batch["id"]).all()
    )
    assert payments == []


def test_upload_csv_with_some_bad_rows_persists_the_good_ones_and_reports_the_rest(
    client, db_session
):
    mapping = _create_mapping(client, "Partial export", "payment", BANK_COLUMN_MAP)
    mixed_csv = (
        "Post Date,Trans Amt,Memo,Other Party\n"
        "2026-02-04,1250.00,INV-1001,Acme Robotics Inc\n"
        "2026-02-09,not-a-number,INV-1101,Blue Harbor Supplies\n"
    )

    response = client.post(
        "/api/v1/uploads/bank-statement",
        data={"source_mapping_id": mapping["id"]},
        files={"file": ("bank.csv", mixed_csv, "text/csv")},
    )
    assert response.status_code == 201, response.text
    batch = response.json()
    assert batch["status"] == "completed"
    assert batch["row_count"] == 1
    assert "row 2" in batch["error_summary"]

    payments = (
        db_session.query(Payment).filter(Payment.upload_batch_id == batch["id"]).all()
    )
    assert len(payments) == 1
    assert str(payments[0].amount) == "1250.00"


def test_upload_invoices_csv_without_source_mapping_id_is_rejected(client):
    response = client.post(
        "/api/v1/uploads/invoices",
        files={"file": ("invoices.csv", INVOICE_CSV, "text/csv")},
    )
    assert response.status_code == 422


def test_upload_invoices_with_unknown_mapping_id_returns_404(client):
    response = client.post(
        "/api/v1/uploads/invoices",
        data={"source_mapping_id": "00000000-0000-0000-0000-000000000000"},
        files={"file": ("invoices.csv", INVOICE_CSV, "text/csv")},
    )
    assert response.status_code == 404


def test_upload_invoices_with_a_payment_mapping_is_rejected(client):
    mapping = _create_mapping(client, "Wrong kind mapping", "payment", BANK_COLUMN_MAP)
    response = client.post(
        "/api/v1/uploads/invoices",
        data={"source_mapping_id": mapping["id"]},
        files={"file": ("invoices.csv", INVOICE_CSV, "text/csv")},
    )
    assert response.status_code == 422


def test_upload_pdf_invoice_persists_extracted_fields(client, db_session):
    pdf_bytes = _make_pdf(
        [
            "Acme Robotics Inc",
            "123 Robot Way, Springfield",
            "",
            "INVOICE",
            "Invoice Number: INV-2001",
            "Invoice Date: 2026-01-15",
            "Due Date: 2026-02-14",
            "Total: $1,250.00",
        ]
    )

    response = client.post(
        "/api/v1/uploads/invoices",
        files={"file": ("invoice.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    batch = response.json()
    assert batch["status"] == "completed"
    assert batch["row_count"] == 1
    assert batch["kind"] == "invoice_pdf"
    assert batch["error_summary"] is None

    invoice = (
        db_session.query(Invoice).filter(Invoice.upload_batch_id == batch["id"]).one()
    )
    assert invoice.invoice_number == "INV-2001"
    assert invoice.vendor_name == "Acme Robotics Inc"
    assert invoice.invoice_date.isoformat() == "2026-01-15"
    assert invoice.due_date.isoformat() == "2026-02-14"
    assert str(invoice.amount) == "1250.00"


def test_upload_pdf_invoice_missing_required_fields_fails_the_batch(client, db_session):
    pdf_bytes = _make_pdf(["Some Vendor", "No amount or date printed here at all."])

    response = client.post(
        "/api/v1/uploads/invoices",
        files={"file": ("invoice.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    batch = response.json()
    assert batch["status"] == "failed"
    assert batch["row_count"] == 0
    assert batch["error_summary"]

    invoices = (
        db_session.query(Invoice).filter(Invoice.upload_batch_id == batch["id"]).all()
    )
    assert invoices == []


def test_get_unknown_batch_returns_404(client):
    response = client.get("/api/v1/uploads/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_preview_rejects_a_non_csv_extension(client):
    response = client.post(
        "/api/v1/uploads/preview",
        files={"file": ("notes.txt", "hello", "text/plain")},
    )
    assert response.status_code == 415
    assert ".txt" in response.json()["detail"]


def test_bank_statement_upload_rejects_pdf(client):
    response = client.post(
        "/api/v1/uploads/bank-statement",
        data={"source_mapping_id": "00000000-0000-0000-0000-000000000000"},
        files={"file": ("statement.pdf", b"%PDF-1.4", "application/pdf")},
    )
    # Extension is checked before the mapping lookup, so this 415s rather
    # than 404ing on the bogus mapping id.
    assert response.status_code == 415


def test_upload_rejects_a_file_over_the_configured_size_limit(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "max_upload_bytes", 10)
    response = client.post(
        "/api/v1/uploads/preview",
        files={"file": ("invoices.csv", INVOICE_CSV, "text/csv")},
    )
    assert response.status_code == 413
    assert "10 byte upload limit" in response.json()["detail"]
