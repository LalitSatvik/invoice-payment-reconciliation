"""Sub-score behavior, especially at the tolerance boundaries.

The boundaries matter more than the middle of the curve: the engine's hard
gates test for a score of exactly 0.0, so "inside the band" and "outside the
band" have to be separated to the cent and to the day.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.matching.config import (
    AMOUNT_BOUNDARY_SCORE,
    DATE_BOUNDARY_SCORE,
    DEFAULT_CONFIG,
    MatchConfig,
)
from app.matching.scoring import (
    amount_tolerance,
    score_amount,
    score_date,
    score_pair,
    score_reference,
)
from app.matching.types import InvoiceRecord, PaymentRecord


def make_invoice(**overrides):
    fields = dict(
        id="INV-1",
        amount=Decimal("100.00"),
        date=date(2026, 1, 1),
        due_date=date(2026, 1, 31),
        invoice_number="INV-1",
        vendor_name="Acme Robotics Inc",
        raw_reference_text="Consulting services (INV-1)",
    )
    fields.update(overrides)
    return InvoiceRecord(**fields)


def make_payment(**overrides):
    fields = dict(
        id="PAY-1",
        amount=Decimal("100.00"),
        date=date(2026, 1, 31),
        reference="INV-1 ACME ROBOTICS INC",
        counterparty="Acme Robotics Inc",
    )
    fields.update(overrides)
    return PaymentRecord(**fields)


# --- amount ---------------------------------------------------------------


def test_score_amount_is_100_for_an_exact_amount():
    assert score_amount(Decimal("1250.00"), Decimal("1250.00"), DEFAULT_CONFIG) == 100.0


def test_amount_tolerance_uses_the_flat_floor_for_small_invoices():
    # 0.5% of $80.00 is only $0.40, so the $1.00 flat tolerance binds.
    assert amount_tolerance(Decimal("80.00"), DEFAULT_CONFIG) == Decimal("1.00")


def test_amount_tolerance_uses_the_percentage_for_large_invoices():
    # 0.5% of $10,000.00 is $50.00, well above the flat $1.00.
    assert amount_tolerance(Decimal("10000.00"), DEFAULT_CONFIG) == Decimal("50.00")


def test_score_amount_at_the_flat_tolerance_boundary_is_the_boundary_score():
    # $80.00 invoice, $79.00 payment: difference is exactly the $1.00 tolerance.
    assert (
        score_amount(Decimal("80.00"), Decimal("79.00"), DEFAULT_CONFIG)
        == AMOUNT_BOUNDARY_SCORE
    )


def test_score_amount_one_cent_past_the_flat_tolerance_is_exactly_zero():
    assert score_amount(Decimal("80.00"), Decimal("78.99"), DEFAULT_CONFIG) == 0.0


def test_score_amount_at_the_percentage_tolerance_boundary_is_the_boundary_score():
    # $10,000.00 invoice, $9,950.00 payment: difference is exactly $50.00.
    assert (
        score_amount(Decimal("10000.00"), Decimal("9950.00"), DEFAULT_CONFIG)
        == AMOUNT_BOUNDARY_SCORE
    )


def test_score_amount_one_cent_past_the_percentage_tolerance_is_exactly_zero():
    assert score_amount(Decimal("10000.00"), Decimal("9949.99"), DEFAULT_CONFIG) == 0.0


def test_score_amount_is_symmetric_about_an_overpayment_and_an_underpayment():
    under = score_amount(Decimal("80.00"), Decimal("79.50"), DEFAULT_CONFIG)
    over = score_amount(Decimal("80.00"), Decimal("80.50"), DEFAULT_CONFIG)
    assert under == over


def test_score_amount_decays_monotonically_across_the_band():
    scores = [
        score_amount(Decimal("80.00"), Decimal("80.00") - step, DEFAULT_CONFIG)
        for step in (Decimal("0.00"), Decimal("0.25"), Decimal("0.50"), Decimal("1.00"))
    ]
    assert scores == sorted(scores, reverse=True)
    assert len(set(scores)) == len(scores)


def test_score_amount_at_the_band_midpoint():
    # Halfway across the band: halfway between 100.0 and the boundary score.
    midpoint = score_amount(Decimal("80.00"), Decimal("79.50"), DEFAULT_CONFIG)
    assert midpoint == pytest.approx((100.0 + AMOUNT_BOUNDARY_SCORE) / 2.0)


def test_score_amount_is_zero_for_a_half_payment():
    assert score_amount(Decimal("1000.00"), Decimal("500.00"), DEFAULT_CONFIG) == 0.0


# --- date -----------------------------------------------------------------


def test_score_date_is_100_for_a_same_day_payment():
    assert score_date(date(2026, 2, 4), date(2026, 2, 4), DEFAULT_CONFIG) == 100.0


def test_score_date_at_the_window_boundary_is_the_boundary_score():
    # Five days late, with a five-day window: inclusive, so still in the band.
    assert (
        score_date(date(2026, 2, 1), date(2026, 2, 6), DEFAULT_CONFIG)
        == DATE_BOUNDARY_SCORE
    )


def test_score_date_one_day_past_the_window_is_exactly_zero():
    assert score_date(date(2026, 2, 1), date(2026, 2, 7), DEFAULT_CONFIG) == 0.0


def test_score_date_treats_early_and_late_payments_alike():
    early = score_date(date(2026, 2, 10), date(2026, 2, 8), DEFAULT_CONFIG)
    late = score_date(date(2026, 2, 10), date(2026, 2, 12), DEFAULT_CONFIG)
    assert early == late


def test_score_date_decays_monotonically_across_the_window():
    anchor = date(2026, 2, 1)
    scores = [
        score_date(anchor, date(2026, 2, 1 + delta), DEFAULT_CONFIG)
        for delta in range(0, 6)
    ]
    assert scores == sorted(scores, reverse=True)
    assert scores[-1] == DATE_BOUNDARY_SCORE


def test_score_date_boundary_moves_with_a_widened_window():
    config = MatchConfig(date_window_days=10)
    assert score_date(date(2026, 2, 1), date(2026, 2, 7), config) > 0.0
    assert score_date(date(2026, 2, 1), date(2026, 2, 11), config) == DATE_BOUNDARY_SCORE
    assert score_date(date(2026, 2, 1), date(2026, 2, 12), config) == 0.0


def test_date_anchor_prefers_the_due_date_over_the_invoice_date():
    invoice = make_invoice(date=date(2026, 1, 1), due_date=date(2026, 1, 31))
    assert invoice.date_anchor == date(2026, 1, 31)


def test_date_anchor_falls_back_to_the_invoice_date_when_no_due_date_is_known():
    invoice = make_invoice(date=date(2026, 1, 1), due_date=None)
    assert invoice.date_anchor == date(2026, 1, 1)


def test_score_pair_measures_the_date_from_the_due_date():
    invoice = make_invoice(date=date(2026, 1, 1), due_date=date(2026, 1, 31))
    on_due_date = make_payment(date=date(2026, 1, 31))
    on_invoice_date = make_payment(date=date(2026, 1, 1))

    assert score_pair(invoice, on_due_date, DEFAULT_CONFIG).date_score == 100.0
    assert score_pair(invoice, on_invoice_date, DEFAULT_CONFIG).date_score == 0.0


# --- reference ------------------------------------------------------------


def test_score_reference_is_100_for_an_exact_invoice_number_in_the_memo():
    invoice = make_invoice(invoice_number="INV-1001")
    payment = make_payment(reference="INV-1001 ACME ROBOTICS INC")
    assert score_reference(invoice, payment) == 100.0


def test_score_reference_ignores_punctuation_in_the_invoice_number():
    invoice = make_invoice(invoice_number="INV-1421")
    payment = make_payment(reference="IBM CORP PYMT INV1421", counterparty="IBM CORP")
    assert score_reference(invoice, payment) == 100.0


def test_score_reference_stays_high_for_a_typo_in_the_invoice_number():
    # Digits transposed: the memo says INV-1410 for invoice INV-1401.
    invoice = make_invoice(invoice_number="INV-1401", vendor_name="Golden Gate Textiles")
    payment = make_payment(
        reference="Payment INV-1410 Golden Gate Textiles",
        counterparty="Golden Gate Textiles",
    )
    score = score_reference(invoice, payment)
    assert 80.0 <= score < 100.0


def test_score_reference_handles_reordered_vendor_tokens():
    invoice = make_invoice(
        invoice_number="INV-1411",
        vendor_name="Harbor Point Logistics",
        raw_reference_text="Freight forwarding services (INV-1411)",
    )
    payment = make_payment(
        reference="Logistics Point Harbor - Invoice Payment",
        counterparty="LOGISTICS HARBOR POINT",
    )
    # No invoice number in the memo, so only the corroborating vendor signal is
    # available -- and that signal is capped below a perfect score.
    assert score_reference(invoice, payment) == 70.0


def test_score_reference_caps_a_vendor_only_agreement_below_an_invoice_number_hit():
    invoice = make_invoice(invoice_number="INV-1701", vendor_name="Lighthouse Media Group")
    vendor_only = make_payment(
        reference="Lighthouse Media Group payment", counterparty="Lighthouse Media Group"
    )
    numbered = make_payment(
        reference="INV-1701 Lighthouse Media Group", counterparty="Lighthouse Media Group"
    )
    assert score_reference(invoice, vendor_only) == 70.0
    assert score_reference(invoice, numbered) == 100.0


def test_score_reference_separates_two_invoices_from_one_vendor():
    """The whole point of the vendor cap: sibling invoices must be separable."""
    first = make_invoice(
        id="INV-1101",
        invoice_number="INV-1101",
        vendor_name="Blue Harbor Supplies",
        raw_reference_text="Office supplies order (INV-1101)",
    )
    second = make_invoice(
        id="INV-1102",
        invoice_number="INV-1102",
        vendor_name="Blue Harbor Supplies",
        raw_reference_text="Office supplies order (INV-1102)",
    )
    payment = make_payment(
        reference="INV-1101 Blue Harbor Supplies", counterparty="Blue Harbor Supplies"
    )
    assert score_reference(first, payment) == 100.0
    assert score_reference(second, payment) < score_reference(first, payment)


def test_score_reference_is_zero_when_the_payment_carries_no_text():
    invoice = make_invoice()
    payment = make_payment(reference=None, counterparty=None)
    assert score_reference(invoice, payment) == 0.0


def test_score_reference_is_zero_when_the_invoice_carries_no_text():
    invoice = make_invoice(
        invoice_number=None, vendor_name=None, raw_reference_text=None
    )
    payment = make_payment()
    assert score_reference(invoice, payment) == 0.0


def test_score_reference_is_zero_for_unrelated_text_on_both_sides():
    invoice = make_invoice(
        invoice_number="INV-1431",
        vendor_name="Juniper Creek Analytics",
        raw_reference_text="Data analytics subscription (INV-1431)",
    )
    payment = make_payment(reference=None, counterparty="ONLINE TRANSFER")
    assert score_reference(invoice, payment) == 0.0


# --- combination ----------------------------------------------------------


def test_score_pair_combines_sub_scores_with_the_configured_weights():
    invoice = make_invoice(invoice_number="INV-1001")
    payment = make_payment(reference="INV-1001 ACME ROBOTICS INC")
    scored = score_pair(invoice, payment, DEFAULT_CONFIG)

    assert (scored.amount_score, scored.date_score, scored.reference_score) == (
        100.0,
        100.0,
        100.0,
    )
    assert scored.confidence == 100.0
    assert scored.invoice_id == invoice.id
    assert scored.payment_id == payment.id


def test_score_pair_weights_a_reference_only_miss_as_expected():
    invoice = make_invoice()
    payment = make_payment(reference=None, counterparty=None)
    scored = score_pair(invoice, payment, DEFAULT_CONFIG)

    # 0.45 * 100 + 0.30 * 100 + 0.25 * 0
    assert scored.confidence == pytest.approx(75.0)


def test_score_pair_at_both_boundaries_lands_where_the_floors_predict():
    invoice = make_invoice(amount=Decimal("80.00"), due_date=date(2026, 2, 9))
    payment = make_payment(
        amount=Decimal("79.00"),
        date=date(2026, 2, 14),
        reference=None,
        counterparty=None,
    )
    scored = score_pair(invoice, payment, DEFAULT_CONFIG)

    # 0.45 * 25.0 + 0.30 * 10.0 + 0.25 * 0.0
    assert scored.confidence == pytest.approx(14.25)


# --- config validation ----------------------------------------------------


def test_default_config_weights_sum_to_one():
    assert (
        DEFAULT_CONFIG.weight_amount
        + DEFAULT_CONFIG.weight_date
        + DEFAULT_CONFIG.weight_reference
    ) == pytest.approx(1.0)


def test_match_config_rejects_weights_that_do_not_sum_to_one():
    with pytest.raises(ValueError) as excinfo:
        MatchConfig(weight_amount=0.5, weight_date=0.3, weight_reference=0.25)
    assert "sum to 1.0" in str(excinfo.value)


def test_match_config_rejects_weights_that_sum_to_less_than_one():
    with pytest.raises(ValueError):
        MatchConfig(weight_amount=0.4, weight_date=0.3, weight_reference=0.2)


def test_match_config_accepts_weights_within_floating_point_tolerance():
    # 0.1 + 0.2 + 0.7 is 0.9999999999999999 in binary floating point.
    config = MatchConfig(weight_amount=0.1, weight_date=0.2, weight_reference=0.7)
    assert config.weight_reference == 0.7
