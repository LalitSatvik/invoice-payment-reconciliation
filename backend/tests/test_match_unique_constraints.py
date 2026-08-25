from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Invoice, Match, Payment, UploadBatch


def _make_upload_batch(session, kind="invoice_csv"):
    batch = UploadBatch(kind=kind, original_filename="test.csv", status="completed")
    session.add(batch)
    session.flush()
    return batch


def _make_invoice(session, upload_batch_id):
    invoice = Invoice(
        upload_batch_id=upload_batch_id,
        invoice_date=date(2026, 1, 1),
        amount=Decimal("100.00"),
    )
    session.add(invoice)
    session.flush()
    return invoice


def _make_payment(session, upload_batch_id):
    payment = Payment(
        upload_batch_id=upload_batch_id,
        payment_date=date(2026, 1, 2),
        amount=Decimal("100.00"),
        raw_row={"amount": "100.00"},
    )
    session.add(payment)
    session.flush()
    return payment


def _make_match(invoice_id, payment_id):
    return Match(
        invoice_id=invoice_id,
        payment_id=payment_id,
        confidence_score=Decimal("95.00"),
        amount_score=Decimal("100.00"),
        date_score=Decimal("90.00"),
        reference_score=Decimal("80.00"),
        match_status="suggested",
    )


def test_duplicate_invoice_id_on_match_raises_integrity_error(db_session):
    batch = _make_upload_batch(db_session)
    invoice = _make_invoice(db_session, batch.id)
    payment_a = _make_payment(db_session, batch.id)
    payment_b = _make_payment(db_session, batch.id)

    db_session.add(_make_match(invoice.id, payment_a.id))
    db_session.commit()

    db_session.add(_make_match(invoice.id, payment_b.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_duplicate_payment_id_on_match_raises_integrity_error(db_session):
    batch = _make_upload_batch(db_session)
    invoice_a = _make_invoice(db_session, batch.id)
    invoice_b = _make_invoice(db_session, batch.id)
    payment = _make_payment(db_session, batch.id)

    db_session.add(_make_match(invoice_a.id, payment.id))
    db_session.commit()

    db_session.add(_make_match(invoice_b.id, payment.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_distinct_invoice_and_payment_ids_on_match_succeed(db_session):
    batch = _make_upload_batch(db_session)
    invoice = _make_invoice(db_session, batch.id)
    payment = _make_payment(db_session, batch.id)

    db_session.add(_make_match(invoice.id, payment.id))
    db_session.commit()

    assert db_session.query(Match).count() == 1
