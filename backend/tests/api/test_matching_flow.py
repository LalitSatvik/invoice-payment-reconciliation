"""End-to-end integration test for Task 7: run matching, review suggestions
via the accept/reject endpoints, resolve an exception, and confirm both
exports reflect the final state.

Amounts are chosen far enough apart (differences of hundreds of dollars
against tolerances of a few dollars) that the amount gate alone rules out
every cross-pair, so the intended matches/exceptions are the only possible
outcome regardless of the date/reference signals.
"""
import uuid
from datetime import date
from decimal import Decimal

from app.models import ExceptionRecord, Invoice, Match, Payment, UploadBatch


def _seed(db_session):
    batch = UploadBatch(kind="invoice_csv", original_filename="seed.csv", status="completed")
    db_session.add(batch)
    db_session.flush()

    # A: exact amount, exact date, matching invoice number in the payment
    # reference -- an unambiguous mutual-best pair. Accepted in the test.
    invoice_a = Invoice(
        upload_batch_id=batch.id,
        invoice_number="INV-A",
        vendor_name="Acme Co",
        invoice_date=date(2026, 1, 1),
        amount=Decimal("500.00"),
    )
    payment_a = Payment(
        upload_batch_id=batch.id,
        payment_date=date(2026, 1, 1),
        amount=Decimal("500.00"),
        reference="INV-A payment",
        counterparty="Acme Co",
        raw_row={"amount": "500.00"},
    )

    # B: same shape as A, a second unambiguous mutual-best pair. Rejected in
    # the test.
    invoice_b = Invoice(
        upload_batch_id=batch.id,
        invoice_number="INV-B",
        vendor_name="Blue Inc",
        invoice_date=date(2026, 1, 5),
        amount=Decimal("300.00"),
    )
    payment_b = Payment(
        upload_batch_id=batch.id,
        payment_date=date(2026, 1, 5),
        amount=Decimal("300.00"),
        reference="INV-B settlement",
        counterparty="Blue Inc",
        raw_row={"amount": "300.00"},
    )

    # C: an invoice with no candidate payment anywhere near its amount ->
    # no_candidate exception on the invoice side.
    invoice_c = Invoice(
        upload_batch_id=batch.id,
        invoice_number="INV-C",
        vendor_name="Zephyr Ltd",
        invoice_date=date(2026, 3, 1),
        amount=Decimal("999.00"),
    )

    # D: a payment with no candidate invoice anywhere near its amount ->
    # no_candidate exception on the payment side.
    payment_d = Payment(
        upload_batch_id=batch.id,
        payment_date=date(2026, 3, 15),
        amount=Decimal("777.00"),
        reference="unrelated wire",
        counterparty="Nobody Corp",
        raw_row={"amount": "777.00"},
    )

    db_session.add_all(
        [invoice_a, payment_a, invoice_b, payment_b, invoice_c, payment_d]
    )
    db_session.commit()
    for obj in (invoice_a, payment_a, invoice_b, payment_b, invoice_c, payment_d):
        db_session.refresh(obj)

    return {
        "invoice_a": invoice_a,
        "payment_a": payment_a,
        "invoice_b": invoice_b,
        "payment_b": payment_b,
        "invoice_c": invoice_c,
        "payment_d": payment_d,
    }


def _match_for(matches, invoice_id):
    for match in matches:
        if match["invoice_id"] == str(invoice_id):
            return match
    raise AssertionError(f"no match found for invoice {invoice_id}")


def _exception_for(exceptions, *, invoice_id=None, payment_id=None):
    for exc in exceptions:
        if invoice_id is not None and exc["invoice_id"] == str(invoice_id):
            return exc
        if payment_id is not None and exc["payment_id"] == str(payment_id):
            return exc
    raise AssertionError("no matching exception found")


def test_end_to_end_matching_review_and_export_flow(client, db_session):
    seed = _seed(db_session)

    run_response = client.post("/api/v1/matching/run", json={})
    assert run_response.status_code == 200
    assert run_response.json() == {"matches_created": 2, "exceptions_created": 2}

    # --- matches were created correctly ---
    matches_response = client.get("/api/v1/matches", params={"status": "suggested"})
    assert matches_response.status_code == 200
    matches_body = matches_response.json()
    assert matches_body["total"] == 2
    matches = matches_body["items"]

    match_a = _match_for(matches, seed["invoice_a"].id)
    assert match_a["payment_id"] == str(seed["payment_a"].id)
    assert Decimal(match_a["confidence_score"]) == Decimal("100.00")

    match_b = _match_for(matches, seed["invoice_b"].id)
    assert match_b["payment_id"] == str(seed["payment_b"].id)

    # Full detail view carries both linked records for the review card.
    detail_response = client.get(f"/api/v1/matches/{match_a['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["invoice"]["id"] == str(seed["invoice_a"].id)
    assert detail["payment"]["id"] == str(seed["payment_a"].id)

    # --- exceptions were created correctly ---
    exceptions_response = client.get("/api/v1/exceptions")
    assert exceptions_response.status_code == 200
    exceptions_body = exceptions_response.json()
    assert exceptions_body["total"] == 2
    exceptions = exceptions_body["items"]

    exc_c = _exception_for(exceptions, invoice_id=seed["invoice_c"].id)
    assert exc_c["reason"] == "no_candidate"
    assert exc_c["status"] == "open"
    assert exc_c["candidate_ids"] == []

    exc_d = _exception_for(exceptions, payment_id=seed["payment_d"].id)
    assert exc_d["reason"] == "no_candidate"

    # Invoice/payment status flips reflect the matching-run outcome.
    db_session.refresh(seed["invoice_a"])
    db_session.refresh(seed["payment_a"])
    db_session.refresh(seed["invoice_c"])
    db_session.refresh(seed["payment_d"])
    assert seed["invoice_a"].status == "matched"
    assert seed["payment_a"].status == "matched"
    assert seed["invoice_c"].status == "exception"
    assert seed["payment_d"].status == "exception"

    # --- accept match A ---
    accept_response = client.post(f"/api/v1/matches/{match_a['id']}/accept")
    assert accept_response.status_code == 200
    accepted = accept_response.json()
    assert accepted["match_status"] == "accepted"
    assert accepted["reviewed_at"] is not None

    # Accepting an already-accepted match is a clear 4xx, not a silent
    # success or a 500.
    re_accept_response = client.post(f"/api/v1/matches/{match_a['id']}/accept")
    assert 400 <= re_accept_response.status_code < 500

    # --- reject match B ---
    reject_response = client.post(f"/api/v1/matches/{match_b['id']}/reject")
    assert reject_response.status_code == 200
    rejected = reject_response.json()
    assert rejected["match_status"] == "rejected"
    assert rejected["reviewed_at"] is not None

    db_session.refresh(seed["invoice_b"])
    db_session.refresh(seed["payment_b"])
    assert seed["invoice_b"].status == "unmatched"
    assert seed["payment_b"].status == "unmatched"

    rejection_exceptions = db_session.query(ExceptionRecord).filter(
        ExceptionRecord.reason == "rejected_by_reviewer"
    ).all()
    assert len(rejection_exceptions) == 1
    assert rejection_exceptions[0].invoice_id == seed["invoice_b"].id
    assert rejection_exceptions[0].payment_id == seed["payment_b"].id

    # --- resolving an exception with an invalid link is a clear 4xx ---
    bad_resolve_response = client.post(
        f"/api/v1/exceptions/{exc_c['id']}/resolve",
        json={
            "link_invoice_id": str(seed["invoice_c"].id),
            "link_payment_id": str(uuid.uuid4()),
        },
    )
    assert 400 <= bad_resolve_response.status_code < 500

    # --- dismiss the invoice-side no_candidate exception ---
    dismiss_response = client.post(
        f"/api/v1/exceptions/{exc_c['id']}/resolve",
        json={"dismiss": True, "resolution_note": "vendor confirmed write-off"},
    )
    assert dismiss_response.status_code == 200
    dismissed = dismiss_response.json()
    assert dismissed["status"] == "resolved"
    assert dismissed["resolution_note"] == "vendor confirmed write-off"

    # --- export summary reflects the accept/reject actions ---
    summary_response = client.get("/api/v1/export/summary")
    assert summary_response.status_code == 200
    summary = summary_response.json()

    assert summary["matched"]["count"] == 1
    assert Decimal(summary["matched"]["amount"]) == Decimal("500.00")

    # invoice_b is back to unmatched; invoice_c was resolved (dismissed), not
    # reopened, so it stays out of the unmatched pool.
    assert summary["unmatched"]["invoices"]["count"] == 1
    assert Decimal(summary["unmatched"]["invoices"]["amount"]) == Decimal("300.00")
    assert summary["unmatched"]["payments"]["count"] == 1
    assert Decimal(summary["unmatched"]["payments"]["amount"]) == Decimal("300.00")

    # Only *open* exceptions count towards the KPI: invoice_c's no_candidate
    # exception was dismissed above, so payment_d's is the only one left.
    reasons = summary["exceptions_by_reason"]
    assert reasons["no_candidate"]["count"] == 1
    assert Decimal(reasons["no_candidate"]["amount"]) == Decimal("777.00")
    assert reasons["rejected_by_reviewer"]["count"] == 1
    assert Decimal(reasons["rejected_by_reviewer"]["amount"]) == Decimal("300.00")

    # --- reconciliation CSV contains only the accepted match ---
    csv_response = client.get("/api/v1/export/reconciliation.csv")
    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")

    lines = csv_response.text.strip("\r\n").split("\r\n")
    header = lines[0].split(",")
    assert header[:2] == ["match_id", "invoice_id"]
    assert len(lines) == 2  # header + exactly one accepted match

    row = dict(zip(header, lines[1].split(",")))
    assert row["invoice_id"] == str(seed["invoice_a"].id)
    assert row["payment_id"] == str(seed["payment_a"].id)
    assert row["invoice_amount"] == "500.00"
    assert row["payment_amount"] == "500.00"
    assert row["amount_variance"] == "0.00"
    assert row["date_variance_days"] == "0"
    assert row["confidence_score"] == "100.00"


def test_accept_unknown_match_returns_404(client):
    response = client.post(f"/api/v1/matches/{uuid.uuid4()}/accept")
    assert response.status_code == 404


def test_resolve_unknown_exception_returns_404(client):
    response = client.post(
        f"/api/v1/exceptions/{uuid.uuid4()}/resolve",
        json={"dismiss": True},
    )
    assert response.status_code == 404


def test_matching_run_scoped_to_batch_ids_ignores_other_batches(client, db_session):
    batch_1 = UploadBatch(kind="invoice_csv", original_filename="b1.csv", status="completed")
    batch_2 = UploadBatch(kind="invoice_csv", original_filename="b2.csv", status="completed")
    db_session.add_all([batch_1, batch_2])
    db_session.flush()

    invoice_1 = Invoice(
        upload_batch_id=batch_1.id,
        invoice_number="SCOPED-1",
        invoice_date=date(2026, 4, 1),
        amount=Decimal("111.00"),
    )
    payment_1 = Payment(
        upload_batch_id=batch_1.id,
        payment_date=date(2026, 4, 1),
        amount=Decimal("111.00"),
        reference="SCOPED-1",
        raw_row={"amount": "111.00"},
    )
    invoice_2 = Invoice(
        upload_batch_id=batch_2.id,
        invoice_number="SCOPED-2",
        invoice_date=date(2026, 4, 2),
        amount=Decimal("222.00"),
    )
    payment_2 = Payment(
        upload_batch_id=batch_2.id,
        payment_date=date(2026, 4, 2),
        amount=Decimal("222.00"),
        reference="SCOPED-2",
        raw_row={"amount": "222.00"},
    )
    db_session.add_all([invoice_1, payment_1, invoice_2, payment_2])
    db_session.commit()

    response = client.post(
        "/api/v1/matching/run", json={"batch_ids": [str(batch_1.id)]}
    )
    assert response.status_code == 200
    assert response.json() == {"matches_created": 1, "exceptions_created": 0}

    db_session.refresh(invoice_1)
    db_session.refresh(invoice_2)
    assert invoice_1.status == "matched"
    assert invoice_2.status == "unmatched"  # untouched: outside the scoped batch


def test_list_matches_rejects_invalid_status_filter(client):
    response = client.get("/api/v1/matches", params={"status": "not-a-real-status"})
    assert response.status_code == 422


def test_list_exceptions_rejects_invalid_reason_filter(client):
    response = client.get("/api/v1/exceptions", params={"reason": "not-a-real-reason"})
    assert response.status_code == 422


def test_candidate_claimed_elsewhere_reason_round_trips_through_the_enum(
    client, db_session
):
    """Regression guard for the migration this task adds: persisting a
    ``candidate_claimed_elsewhere`` exception must not 500 against a
    database that has picked up the new ``exception_reason`` enum value.

    Two invoices share their only viable payment candidate. Invoice B wins
    the mutual-best pairing outright (same-day date match beats invoice A's
    one-day-off date match by more than the ambiguity margin), so invoice A
    is left with a single, uncontested, above-threshold candidate that was
    nonetheless claimed by a rival -- exactly the engine's
    ``REASON_CANDIDATE_CLAIMED`` case.
    """
    batch = UploadBatch(kind="invoice_csv", original_filename="claimed.csv", status="completed")
    db_session.add(batch)
    db_session.flush()

    invoice_a = Invoice(
        upload_batch_id=batch.id,
        invoice_number="CLAIM-A",
        invoice_date=date(2026, 5, 9),  # one day off the payment
        amount=Decimal("650.00"),
    )
    invoice_b = Invoice(
        upload_batch_id=batch.id,
        invoice_number="CLAIM-B",
        invoice_date=date(2026, 5, 10),  # same day as the payment
        amount=Decimal("650.00"),
    )
    payment = Payment(
        upload_batch_id=batch.id,
        payment_date=date(2026, 5, 10),
        amount=Decimal("650.00"),
        raw_row={"amount": "650.00"},
    )
    db_session.add_all([invoice_a, invoice_b, payment])
    db_session.commit()
    db_session.refresh(invoice_a)
    db_session.refresh(invoice_b)

    response = client.post("/api/v1/matching/run", json={})
    assert response.status_code == 200
    assert response.json() == {"matches_created": 1, "exceptions_created": 1}

    list_response = client.get(
        "/api/v1/exceptions", params={"reason": "candidate_claimed_elsewhere"}
    )
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["total"] == 1
    exc = body["items"][0]
    assert exc["invoice_id"] == str(invoice_a.id)
    assert exc["reason"] == "candidate_claimed_elsewhere"
    assert len(exc["candidate_ids"]) == 1
    assert exc["candidate_ids"][0]["id"] == str(payment.id)

    stored = (
        db_session.query(ExceptionRecord)
        .filter(ExceptionRecord.invoice_id == invoice_a.id)
        .one()
    )
    assert stored.reason == "candidate_claimed_elsewhere"


def test_rejected_pairing_can_be_rematched_on_a_later_run(client, db_session):
    """A rejected match must not permanently block its invoice/payment from
    ever being matched again. Reject reopens both sides to ``unmatched``, so
    the deterministic engine immediately re-proposes the very same pairing on
    the next ``/matching/run`` -- nothing else in the seed data changed. That
    re-proposal has to succeed (not collide with the stale rejected ``Match``
    row's unique constraints on ``invoice_id``/``payment_id``), or the
    brief's "eligible for a future /matching/run" contract for rejected
    records is broken.
    """
    batch = UploadBatch(kind="invoice_csv", original_filename="rematch.csv", status="completed")
    db_session.add(batch)
    db_session.flush()

    invoice = Invoice(
        upload_batch_id=batch.id,
        invoice_number="REMATCH-1",
        vendor_name="Rematch Co",
        invoice_date=date(2026, 6, 1),
        amount=Decimal("450.00"),
    )
    payment = Payment(
        upload_batch_id=batch.id,
        payment_date=date(2026, 6, 1),
        amount=Decimal("450.00"),
        reference="REMATCH-1 payment",
        counterparty="Rematch Co",
        raw_row={"amount": "450.00"},
    )
    db_session.add_all([invoice, payment])
    db_session.commit()

    first_run = client.post("/api/v1/matching/run", json={})
    assert first_run.status_code == 200
    assert first_run.json() == {"matches_created": 1, "exceptions_created": 0}

    matches = client.get("/api/v1/matches", params={"status": "suggested"}).json()["items"]
    match = _match_for(matches, invoice.id)

    reject_response = client.post(f"/api/v1/matches/{match['id']}/reject")
    assert reject_response.status_code == 200

    db_session.refresh(invoice)
    db_session.refresh(payment)
    assert invoice.status == "unmatched"
    assert payment.status == "unmatched"

    # The critical assertion: a second run over the same (now reopened)
    # invoice/payment must succeed, not 500 on a stale unique constraint.
    second_run = client.post("/api/v1/matching/run", json={})
    assert second_run.status_code == 200
    assert second_run.json() == {"matches_created": 1, "exceptions_created": 0}

    new_matches = client.get(
        "/api/v1/matches", params={"status": "suggested"}
    ).json()["items"]
    new_match = _match_for(new_matches, invoice.id)
    assert new_match["payment_id"] == str(payment.id)
    assert new_match["id"] != match["id"]

    # The rejection is still on record as an exception (the audit trail),
    # even though the Match row it pointed at is gone.
    rejection_exceptions = (
        db_session.query(ExceptionRecord)
        .filter(ExceptionRecord.reason == "rejected_by_reviewer")
        .filter(ExceptionRecord.invoice_id == invoice.id)
        .all()
    )
    assert len(rejection_exceptions) == 1


def test_resolve_exception_allows_manual_link_for_previously_rejected_pairing(
    client, db_session
):
    """A previously-rejected invoice/payment pair must still be linkable
    through manual exception resolution -- rejection should not leave behind
    a stale Match row that makes the pre-check ("is this id already linked to
    a match?") report a false conflict.
    """
    batch = UploadBatch(kind="invoice_csv", original_filename="resolve.csv", status="completed")
    db_session.add(batch)
    db_session.flush()

    invoice = Invoice(
        upload_batch_id=batch.id,
        invoice_number="RESOLVE-1",
        vendor_name="Resolve Co",
        invoice_date=date(2026, 7, 1),
        amount=Decimal("640.00"),
    )
    payment = Payment(
        upload_batch_id=batch.id,
        payment_date=date(2026, 7, 1),
        amount=Decimal("640.00"),
        reference="RESOLVE-1 payment",
        counterparty="Resolve Co",
        raw_row={"amount": "640.00"},
    )
    db_session.add_all([invoice, payment])
    db_session.commit()

    run_response = client.post("/api/v1/matching/run", json={})
    assert run_response.status_code == 200
    assert run_response.json()["matches_created"] == 1

    matches = client.get("/api/v1/matches", params={"status": "suggested"}).json()["items"]
    match = _match_for(matches, invoice.id)
    client.post(f"/api/v1/matches/{match['id']}/reject")

    exceptions = client.get(
        "/api/v1/exceptions", params={"reason": "rejected_by_reviewer"}
    ).json()["items"]
    exc = _exception_for(exceptions, invoice_id=invoice.id)

    resolve_response = client.post(
        f"/api/v1/exceptions/{exc['id']}/resolve",
        json={
            "link_invoice_id": str(invoice.id),
            "link_payment_id": str(payment.id),
            "resolution_note": "manually confirmed after review",
        },
    )
    assert resolve_response.status_code == 200
    resolved = resolve_response.json()
    assert resolved["status"] == "resolved"

    db_session.refresh(invoice)
    db_session.refresh(payment)
    assert invoice.status == "matched"
    assert payment.status == "matched"


def test_exception_record_is_reconsidered_by_a_later_matching_run(client, db_session):
    """An invoice that became an exception because its payment had not been
    uploaded yet must be matched by the next run once that payment arrives.

    Regression guard for two coupled defects:

    1. ``run_matching_for_unmatched`` only ever loaded ``status="unmatched"``
       records, so anything flipped to ``status="exception"`` dropped out of
       the pool permanently -- no later run could ever reconsider it, which
       is precisely the "upload more data, re-run matching" workflow.
    2. Widening the pool without closing the record's previous exception
       leaves the stale ``open`` row behind, so each run stacks another open
       exception on the same record. Hence the exact-count assertion below:
       one exception row for this invoice across the whole sequence, closed
       rather than duplicated.
    """
    batch = UploadBatch(kind="invoice_csv", original_filename="rerun.csv", status="completed")
    db_session.add(batch)
    db_session.flush()

    invoice = Invoice(
        upload_batch_id=batch.id,
        invoice_number="RERUN-1",
        vendor_name="Rerun Co",
        invoice_date=date(2026, 8, 1),
        amount=Decimal("820.00"),
    )
    db_session.add(invoice)
    db_session.commit()

    # Run 1: the invoice is alone, so it can only become an exception.
    first_run = client.post("/api/v1/matching/run", json={})
    assert first_run.status_code == 200
    assert first_run.json() == {"matches_created": 0, "exceptions_created": 1}

    db_session.refresh(invoice)
    assert invoice.status == "exception"

    # The matching payment is uploaded after the fact.
    payment = Payment(
        upload_batch_id=batch.id,
        payment_date=date(2026, 8, 1),
        amount=Decimal("820.00"),
        reference="RERUN-1 payment",
        counterparty="Rerun Co",
        raw_row={"amount": "820.00"},
    )
    db_session.add(payment)
    db_session.commit()

    # Run 2 must reconsider the exception invoice and match it.
    second_run = client.post("/api/v1/matching/run", json={})
    assert second_run.status_code == 200
    assert second_run.json() == {"matches_created": 1, "exceptions_created": 0}

    db_session.refresh(invoice)
    db_session.refresh(payment)
    assert invoice.status == "matched"
    assert payment.status == "matched"

    matches = client.get("/api/v1/matches", params={"status": "suggested"}).json()["items"]
    assert _match_for(matches, invoice.id)["payment_id"] == str(payment.id)

    # Exactly one exception row for this invoice, and it is closed out -- not
    # a second open row piled on top of the first.
    invoice_exceptions = (
        db_session.query(ExceptionRecord)
        .filter(ExceptionRecord.invoice_id == invoice.id)
        .all()
    )
    assert len(invoice_exceptions) == 1
    assert invoice_exceptions[0].status == "resolved"
    assert invoice_exceptions[0].resolved_at is not None

    open_exceptions = client.get(
        "/api/v1/exceptions", params={"status": "open"}
    ).json()
    assert open_exceptions["total"] == 0


def test_manual_link_closes_the_counterpart_side_exception_too(client, db_session):
    """Linking two orphans must close *both* records' exceptions.

    The seed produces two independent one-sided exception rows (an invoice
    with no candidate and a payment with no candidate -- their amounts are
    hundreds of dollars apart, so the amount gate rules the pairing out
    automatically). A reviewer who links them from the invoice-side card
    resolves that row explicitly; the payment-side row has to be closed as
    well, or it stays open forever *and* becomes unresolvable, since
    resolving it would now fail the "payment is already linked" pre-check.
    """
    batch = UploadBatch(kind="invoice_csv", original_filename="link.csv", status="completed")
    db_session.add(batch)
    db_session.flush()

    invoice = Invoice(
        upload_batch_id=batch.id,
        invoice_number="LINK-1",
        vendor_name="Link Co",
        invoice_date=date(2026, 9, 1),
        amount=Decimal("910.00"),
    )
    payment = Payment(
        upload_batch_id=batch.id,
        payment_date=date(2026, 9, 20),
        amount=Decimal("410.00"),
        reference="unlabelled transfer",
        counterparty="Unknown",
        raw_row={"amount": "410.00"},
    )
    db_session.add_all([invoice, payment])
    db_session.commit()

    run_response = client.post("/api/v1/matching/run", json={})
    assert run_response.status_code == 200
    assert run_response.json() == {"matches_created": 0, "exceptions_created": 2}

    exceptions = client.get("/api/v1/exceptions", params={"status": "open"}).json()["items"]
    invoice_exc = _exception_for(exceptions, invoice_id=invoice.id)
    payment_exc = _exception_for(exceptions, payment_id=payment.id)
    assert invoice_exc["id"] != payment_exc["id"]  # two genuinely separate rows

    resolve_response = client.post(
        f"/api/v1/exceptions/{invoice_exc['id']}/resolve",
        json={
            "link_invoice_id": str(invoice.id),
            "link_payment_id": str(payment.id),
            "resolution_note": "confirmed with the vendor",
        },
    )
    assert resolve_response.status_code == 200

    stored_invoice_exc = db_session.get(ExceptionRecord, uuid.UUID(invoice_exc["id"]))
    stored_payment_exc = db_session.get(ExceptionRecord, uuid.UUID(payment_exc["id"]))
    db_session.refresh(stored_invoice_exc)
    db_session.refresh(stored_payment_exc)

    # The targeted row keeps the reviewer's own note...
    assert stored_invoice_exc.status == "resolved"
    assert stored_invoice_exc.resolution_note == "confirmed with the vendor"
    # ...and the counterpart is closed out too, rather than left dangling.
    assert stored_payment_exc.status == "resolved"
    assert stored_payment_exc.resolved_at is not None

    assert client.get("/api/v1/exceptions", params={"status": "open"}).json()["total"] == 0


def test_rejected_by_reviewer_exception_closes_when_the_pair_is_rematched(
    client, db_session
):
    """``reject_match``'s audit exception is an open exception like any other,
    so it must close once its records get a newer outcome -- otherwise a
    rejected-then-rematched pair leaves a permanently open exception claiming
    a rejection that no longer reflects reality.
    """
    batch = UploadBatch(kind="invoice_csv", original_filename="reclose.csv", status="completed")
    db_session.add(batch)
    db_session.flush()

    invoice = Invoice(
        upload_batch_id=batch.id,
        invoice_number="RECLOSE-1",
        vendor_name="Reclose Co",
        invoice_date=date(2026, 10, 1),
        amount=Decimal("530.00"),
    )
    payment = Payment(
        upload_batch_id=batch.id,
        payment_date=date(2026, 10, 1),
        amount=Decimal("530.00"),
        reference="RECLOSE-1 payment",
        counterparty="Reclose Co",
        raw_row={"amount": "530.00"},
    )
    db_session.add_all([invoice, payment])
    db_session.commit()

    client.post("/api/v1/matching/run", json={})
    matches = client.get("/api/v1/matches", params={"status": "suggested"}).json()["items"]
    match = _match_for(matches, invoice.id)
    assert client.post(f"/api/v1/matches/{match['id']}/reject").status_code == 200

    rejection = (
        db_session.query(ExceptionRecord)
        .filter(ExceptionRecord.reason == "rejected_by_reviewer")
        .one()
    )
    assert rejection.status == "open"

    # The deterministic engine re-proposes the same pairing on the next run.
    assert client.post("/api/v1/matching/run", json={}).status_code == 200

    db_session.refresh(rejection)
    assert rejection.status == "resolved"
    assert rejection.resolved_at is not None


def test_export_summary_separates_suggested_matches_from_accepted_ones(
    client, db_session
):
    """A suggested-but-unreviewed match belongs in its own ``in_review``
    bucket. Both its records already left the ``unmatched`` pool, so before
    ``in_review`` existed they were counted nowhere at all. Also asserts a
    resolved exception drops out of ``exceptions_by_reason``.
    """
    batch = UploadBatch(kind="invoice_csv", original_filename="summary.csv", status="completed")
    db_session.add(batch)
    db_session.flush()

    invoice = Invoice(
        upload_batch_id=batch.id,
        invoice_number="SUM-1",
        vendor_name="Summary Co",
        invoice_date=date(2026, 11, 1),
        amount=Decimal("250.00"),
    )
    payment = Payment(
        upload_batch_id=batch.id,
        payment_date=date(2026, 11, 1),
        amount=Decimal("250.00"),
        reference="SUM-1 payment",
        counterparty="Summary Co",
        raw_row={"amount": "250.00"},
    )
    orphan_invoice = Invoice(
        upload_batch_id=batch.id,
        invoice_number="SUM-ORPHAN",
        vendor_name="Nobody Ltd",
        invoice_date=date(2026, 11, 5),
        amount=Decimal("880.00"),
    )
    db_session.add_all([invoice, payment, orphan_invoice])
    db_session.commit()

    run_response = client.post("/api/v1/matching/run", json={})
    assert run_response.json() == {"matches_created": 1, "exceptions_created": 1}

    summary = client.get("/api/v1/export/summary").json()
    assert summary["in_review"]["count"] == 1
    assert Decimal(summary["in_review"]["amount"]) == Decimal("250.00")
    assert summary["matched"]["count"] == 0
    assert Decimal(summary["matched"]["amount"]) == Decimal("0.00")
    # Neither side is in the unmatched pool either -- that is exactly why the
    # in_review bucket has to exist.
    assert summary["unmatched"]["invoices"]["count"] == 0
    assert summary["unmatched"]["payments"]["count"] == 0
    assert summary["exceptions_by_reason"]["no_candidate"]["count"] == 1

    matches = client.get("/api/v1/matches", params={"status": "suggested"}).json()["items"]
    match = _match_for(matches, invoice.id)
    assert client.post(f"/api/v1/matches/{match['id']}/accept").status_code == 200

    exceptions = client.get("/api/v1/exceptions", params={"status": "open"}).json()["items"]
    orphan_exc = _exception_for(exceptions, invoice_id=orphan_invoice.id)
    assert (
        client.post(
            f"/api/v1/exceptions/{orphan_exc['id']}/resolve",
            json={"dismiss": True, "resolution_note": "written off"},
        ).status_code
        == 200
    )

    after = client.get("/api/v1/export/summary").json()
    assert after["matched"]["count"] == 1
    assert Decimal(after["matched"]["amount"]) == Decimal("250.00")
    assert after["in_review"]["count"] == 0
    assert Decimal(after["in_review"]["amount"]) == Decimal("0.00")
    # The dismissed exception is resolved work, not outstanding work.
    assert "no_candidate" not in after["exceptions_by_reason"]
