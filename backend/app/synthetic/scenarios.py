"""Canonical scenario definitions for the synthetic invoice/payment dataset.

This module is the single source of truth for the synthetic dataset used to
test the matching engine (Task 5). It builds an in-memory ``Dataset`` (a list
of invoice rows, a list of payment rows, and a list of ``Scenario`` records
describing the expected outcome of each invoice/payment grouping), then can
write that dataset out as three files:

- ``invoices.csv``       -- written by ``app.synthetic.generate_invoices``
- ``bank_statement.csv`` -- written by ``app.synthetic.generate_payments``
- ``ground_truth.json``  -- written by ``write_ground_truth`` in this module

Run ``python -m app.synthetic.scenarios`` from ``backend/`` to generate all
three files in one deterministic pass (default output directory:
``backend/data/synthetic/``). ``generate_invoices.py`` and
``generate_payments.py`` are also independently runnable
(``python -m app.synthetic.generate_invoices`` / ``generate_payments``) if you
only need to regenerate one CSV, but only this module's entrypoint writes
``ground_truth.json``.

## Determinism

``build_dataset(seed)`` is deterministic for a given seed: the "core" scenarios
below are fully hand-authored (no randomness at all), and the "filler"
background rows use a ``random.Random(seed)`` instance seeded once per call
so re-running with the same seed reproduces identical filler data. No
wall-clock timestamps or other non-deterministic values are ever written to
any output file, so re-running the generator (or the writers) with the same
seed produces byte-identical files.

## Row-identity convention (read this before writing a consumer)

- **Invoices** already have a natural stable key: ``invoice_number`` (a CSV
  column). ``ground_truth.json`` addresses invoices by this string.
- **Payments** come from a bank CSV that intentionally has no id column (real
  bank statements don't have one, and this dataset's payment CSV uses
  deliberately non-canonical headers -- see ``generate_payments.py``). So
  ``ground_truth.json`` addresses payments by ``payment_row_index``: a
  **0-based index into the payment CSV's data rows, excluding the header
  row** (i.e. the first data row is index 0, the CSV's second physical line).
  This is stable across runs because payment row order is fixed at
  generation time and is never shuffled.

## Matching-outcome assumptions this dataset is built against

Task 5 (the matching engine) owns the real thresholds; this generator picks
concrete, documented values so the "edge" scenarios are unambiguous, and
records those values in ``ground_truth.json``'s ``assumptions`` block so a
future consumer does not have to reverse-engineer them:

- **Amount tolerance:** a payment matches an invoice on amount iff
  ``abs(payment.amount - invoice.amount) <= max(AMOUNT_TOLERANCE_FLAT,
  AMOUNT_TOLERANCE_PCT * invoice.amount)`` (the percentage portion rounded to
  cents, ROUND_HALF_UP).
- **Date window:** a payment matches an invoice on date iff
  ``abs((payment.payment_date - invoice.due_date).days) <= DATE_WINDOW_DAYS``.
  The anchor is the invoice's ``due_date`` (not ``invoice_date``) -- this is
  this generator's assumption about what Task 5's matching window is
  measured against; if Task 5 anchors on ``invoice_date`` instead, the
  ``date_window_edge_match`` / ``date_window_exceeded`` scenarios below will
  need their dates re-derived (the rest of the dataset is unaffected).

## Scenario-type vocabulary

``SCENARIO_TYPES_REQUIRED`` is exactly the nine outcome categories named in
the Task 3 brief; every one of them appears at least once among the "core"
scenarios. Two additional (additive, not brief-mandated) scenario types are
also emitted, each the direct "should NOT match" sibling of a brief-mandated
edge-match type: ``amount_tolerance_exceeded`` and ``date_window_exceeded``.
"""
from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_SEED = 42

AMOUNT_TOLERANCE_FLAT = Decimal("1.00")
AMOUNT_TOLERANCE_PCT = Decimal("0.005")
DATE_WINDOW_DAYS = 5

# backend/app/synthetic/scenarios.py -> parents[2] == backend/
BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = BACKEND_DIR / "data" / "synthetic"

INVOICE_CSV_FILENAME = "invoices.csv"
PAYMENT_CSV_FILENAME = "bank_statement.csv"
GROUND_TRUTH_FILENAME = "ground_truth.json"

# The nine outcome categories named verbatim in the Task 3 brief. Every one
# must appear at least once in build_dataset()'s scenarios.
SCENARIO_TYPES_REQUIRED = [
    "clean_match",
    "amount_tolerance_edge_match",
    "date_window_edge_match",
    "fuzzy_reference_match",
    "orphan_invoice",
    "orphan_payment",
    "ambiguous_tie",
    "looks_like_partial_payment",
    "duplicate_looking_payment",
]


def amount_tolerance(invoice_amount: Decimal) -> Decimal:
    """The maximum |payment.amount - invoice.amount| that still counts as a match."""
    pct_amount = (invoice_amount * AMOUNT_TOLERANCE_PCT).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return max(AMOUNT_TOLERANCE_FLAT, pct_amount)


@dataclass
class InvoiceRow:
    invoice_number: str
    vendor_name: str
    invoice_date: date
    due_date: date
    amount: Decimal
    description: str


@dataclass
class PaymentRow:
    payment_date: date
    amount: Decimal
    memo: str
    counterparty: str


@dataclass
class ExpectedPair:
    invoice_number: str
    payment_row_index: int


@dataclass
class Scenario:
    scenario_id: str
    scenario_type: str
    description: str
    invoice_numbers: List[str]
    payment_row_indices: List[int]
    expected_match: bool
    expected_pairs: List[ExpectedPair]
    expected_exception_reason: Optional[str]
    notes: str


@dataclass
class Dataset:
    seed: int
    invoices: List[InvoiceRow] = field(default_factory=list)
    payments: List[PaymentRow] = field(default_factory=list)
    scenarios: List[Scenario] = field(default_factory=list)


class _Builder:
    """Accumulates invoices/payments/scenarios while tracking payment row indices."""

    def __init__(self) -> None:
        self.invoices: List[InvoiceRow] = []
        self.payments: List[PaymentRow] = []
        self.scenarios: List[Scenario] = []

    def add_invoice(self, invoice: InvoiceRow) -> InvoiceRow:
        self.invoices.append(invoice)
        return invoice

    def add_payment(self, payment: PaymentRow) -> int:
        self.payments.append(payment)
        return len(self.payments) - 1

    def add_scenario(
        self,
        scenario_id: str,
        scenario_type: str,
        description: str,
        invoices: List[InvoiceRow],
        payment_row_indices: List[int],
        expected_pairs: List[ExpectedPair],
        expected_exception_reason: Optional[str],
        notes: str,
    ) -> None:
        self.scenarios.append(
            Scenario(
                scenario_id=scenario_id,
                scenario_type=scenario_type,
                description=description,
                invoice_numbers=[inv.invoice_number for inv in invoices],
                payment_row_indices=list(payment_row_indices),
                expected_match=bool(expected_pairs),
                expected_pairs=expected_pairs,
                expected_exception_reason=expected_exception_reason,
                notes=notes,
            )
        )


def _build_core_scenarios(b: _Builder) -> None:
    """Hand-authored scenarios: exactly the cases the Task 3 brief requires."""

    # -- 1. clean_match: amount, date, and reference all exact -------------
    inv = b.add_invoice(
        InvoiceRow(
            invoice_number="INV-1001",
            vendor_name="Acme Robotics Inc",
            invoice_date=date(2026, 1, 5),
            due_date=date(2026, 2, 4),
            amount=Decimal("1250.00"),
            description="Consulting services - January 2026 (INV-1001)",
        )
    )
    pidx = b.add_payment(
        PaymentRow(
            payment_date=date(2026, 2, 4),
            amount=Decimal("1250.00"),
            memo="INV-1001 ACME ROBOTICS INC",
            counterparty="Acme Robotics Inc",
        )
    )
    b.add_scenario(
        "clean_match_1",
        "clean_match",
        "Exact match on amount, date, and reference.",
        [inv],
        [pidx],
        [ExpectedPair("INV-1001", pidx)],
        None,
        "Baseline clean_match case: amount, payment date (== due date), and "
        "reference text all agree exactly.",
    )

    # -- 2/3. amount_tolerance_edge_match / _exceeded, flat-$1 binding -----
    # invoice amount $80.00 -> 0.5% = $0.40 < $1.00 flat, so the flat amount
    # is the binding tolerance.
    inv = b.add_invoice(
        InvoiceRow(
            invoice_number="INV-1101",
            vendor_name="Blue Harbor Supplies",
            invoice_date=date(2026, 1, 10),
            due_date=date(2026, 2, 9),
            amount=Decimal("80.00"),
            description="Office supplies order (INV-1101)",
        )
    )
    pidx = b.add_payment(
        PaymentRow(
            payment_date=date(2026, 2, 9),
            amount=Decimal("79.00"),
            memo="INV-1101 Blue Harbor Supplies",
            counterparty="Blue Harbor Supplies",
        )
    )
    b.add_scenario(
        "amount_tolerance_edge_match_flat",
        "amount_tolerance_edge_match",
        "Payment is exactly $1.00 below invoice amount; flat tolerance binds "
        "(0.5% of $80 is only $0.40).",
        [inv],
        [pidx],
        [ExpectedPair("INV-1101", pidx)],
        None,
        "Tolerance = max($1.00, 0.5% * $80.00) = $1.00. Diff is exactly "
        "$1.00 -- at the boundary, should match.",
    )

    inv = b.add_invoice(
        InvoiceRow(
            invoice_number="INV-1102",
            vendor_name="Blue Harbor Supplies",
            invoice_date=date(2026, 1, 10),
            due_date=date(2026, 2, 9),
            amount=Decimal("80.00"),
            description="Office supplies order (INV-1102)",
        )
    )
    pidx = b.add_payment(
        PaymentRow(
            payment_date=date(2026, 2, 9),
            amount=Decimal("78.99"),
            memo="INV-1102 Blue Harbor Supplies",
            counterparty="Blue Harbor Supplies",
        )
    )
    b.add_scenario(
        "amount_tolerance_exceeded_flat",
        "amount_tolerance_exceeded",
        "Payment is $1.01 below invoice amount -- one cent past the flat "
        "tolerance boundary.",
        [inv],
        [pidx],
        [],
        "amount_mismatch_only",
        "Tolerance = $1.00; diff is $1.01, one cent past it. Must NOT match. "
        "Date and reference otherwise agree exactly, so "
        "'amount_mismatch_only' is the advisory expected exception reason "
        "(Task 5 owns the final exception-classification logic).",
    )

    # -- 4/5. amount_tolerance_edge_match / _exceeded, pct binding ----------
    # invoice amount $10,000.00 -> 0.5% = $50.00 > $1.00 flat, so the
    # percentage tolerance is the binding one.
    inv = b.add_invoice(
        InvoiceRow(
            invoice_number="INV-1151",
            vendor_name="Continental Freight Ltd",
            invoice_date=date(2026, 1, 15),
            due_date=date(2026, 2, 14),
            amount=Decimal("10000.00"),
            description="Freight services Q1 contract (INV-1151)",
        )
    )
    pidx = b.add_payment(
        PaymentRow(
            payment_date=date(2026, 2, 14),
            amount=Decimal("9950.00"),
            memo="INV-1151 Continental Freight Ltd",
            counterparty="Continental Freight Ltd",
        )
    )
    b.add_scenario(
        "amount_tolerance_edge_match_pct",
        "amount_tolerance_edge_match",
        "Payment is exactly $50.00 below invoice amount; percentage "
        "tolerance binds (0.5% of $10,000 is $50, more than the $1 flat).",
        [inv],
        [pidx],
        [ExpectedPair("INV-1151", pidx)],
        None,
        "Tolerance = max($1.00, 0.5% * $10,000.00) = $50.00. Diff is "
        "exactly $50.00 -- at the boundary, should match.",
    )

    inv = b.add_invoice(
        InvoiceRow(
            invoice_number="INV-1152",
            vendor_name="Continental Freight Ltd",
            invoice_date=date(2026, 1, 15),
            due_date=date(2026, 2, 14),
            amount=Decimal("10000.00"),
            description="Freight services Q1 contract (INV-1152)",
        )
    )
    pidx = b.add_payment(
        PaymentRow(
            payment_date=date(2026, 2, 14),
            amount=Decimal("9949.99"),
            memo="INV-1152 Continental Freight Ltd",
            counterparty="Continental Freight Ltd",
        )
    )
    b.add_scenario(
        "amount_tolerance_exceeded_pct",
        "amount_tolerance_exceeded",
        "Payment is $50.01 below invoice amount -- one cent past the "
        "percentage tolerance boundary.",
        [inv],
        [pidx],
        [],
        "amount_mismatch_only",
        "Tolerance = $50.00; diff is $50.01, one cent past it. Must NOT "
        "match.",
    )

    # -- 6/7. date_window_edge_match / _exceeded ----------------------------
    inv = b.add_invoice(
        InvoiceRow(
            invoice_number="INV-1301",
            vendor_name="Delta Machining Co",
            invoice_date=date(2026, 1, 2),
            due_date=date(2026, 2, 1),
            amount=Decimal("2345.67"),
            description="CNC machining parts order (INV-1301)",
        )
    )
    pidx = b.add_payment(
        PaymentRow(
            payment_date=date(2026, 2, 6),  # due_date + 5 days
            amount=Decimal("2345.67"),
            memo="INV-1301 Delta Machining Co",
            counterparty="Delta Machining Co",
        )
    )
    b.add_scenario(
        "date_window_edge_match",
        "date_window_edge_match",
        "Payment lands exactly 5 days after the invoice due date (the "
        "assumed default window boundary).",
        [inv],
        [pidx],
        [ExpectedPair("INV-1301", pidx)],
        None,
        "Amount and reference exact; payment_date - due_date == 5 days, "
        "the boundary -- should match.",
    )

    inv = b.add_invoice(
        InvoiceRow(
            invoice_number="INV-1302",
            vendor_name="Delta Machining Co",
            invoice_date=date(2026, 1, 2),
            due_date=date(2026, 2, 1),
            amount=Decimal("2345.67"),
            description="CNC machining parts order (INV-1302)",
        )
    )
    pidx = b.add_payment(
        PaymentRow(
            payment_date=date(2026, 2, 7),  # due_date + 6 days
            amount=Decimal("2345.67"),
            memo="INV-1302 Delta Machining Co",
            counterparty="Delta Machining Co",
        )
    )
    b.add_scenario(
        "date_window_exceeded",
        "date_window_exceeded",
        "Payment lands 6 days after the invoice due date -- one day past "
        "the window.",
        [inv],
        [pidx],
        [],
        "below_threshold",
        "Amount and reference exact; payment_date - due_date == 6 days, "
        "one day past the 5-day window. Must NOT match. "
        "'below_threshold' is an advisory expected exception reason.",
    )

    # -- 8. fuzzy_reference_match: typo'd invoice number --------------------
    inv = b.add_invoice(
        InvoiceRow(
            invoice_number="INV-1401",
            vendor_name="Golden Gate Textiles",
            invoice_date=date(2026, 1, 8),
            due_date=date(2026, 2, 7),
            amount=Decimal("675.50"),
            description="Fabric shipment (INV-1401)",
        )
    )
    pidx = b.add_payment(
        PaymentRow(
            payment_date=date(2026, 2, 7),
            amount=Decimal("675.50"),
            memo="Payment INV-1410 Golden Gate Textiles",  # digits transposed
            counterparty="Golden Gate Textiles",
        )
    )
    b.add_scenario(
        "fuzzy_reference_match_typo",
        "fuzzy_reference_match",
        "Payment memo references a typo'd invoice number (digits "
        "transposed: 1410 instead of 1401).",
        [inv],
        [pidx],
        [ExpectedPair("INV-1401", pidx)],
        None,
        "Amount and date exact; reference is a near-miss fuzzy match "
        "(transposed digits) plus an exact vendor name -- should still "
        "match.",
    )

    # -- 9. fuzzy_reference_match: reordered-words memo ---------------------
    inv = b.add_invoice(
        InvoiceRow(
            invoice_number="INV-1411",
            vendor_name="Harbor Point Logistics",
            invoice_date=date(2026, 1, 11),
            due_date=date(2026, 2, 10),
            amount=Decimal("980.25"),
            description="Freight forwarding services (INV-1411)",
        )
    )
    pidx = b.add_payment(
        PaymentRow(
            payment_date=date(2026, 2, 10),
            amount=Decimal("980.25"),
            memo="Logistics Point Harbor - Invoice Payment",  # words reordered
            counterparty="LOGISTICS HARBOR POINT",
        )
    )
    b.add_scenario(
        "fuzzy_reference_match_reordered",
        "fuzzy_reference_match",
        "Payment memo contains the vendor name with its words reordered "
        "and no invoice number.",
        [inv],
        [pidx],
        [ExpectedPair("INV-1411", pidx)],
        None,
        "Amount and date exact; reference text is a token-reordered "
        "variant of the vendor name -- should still match via fuzzy "
        "token matching.",
    )

    # -- 10. fuzzy_reference_match: abbreviated vendor name ------------------
    inv = b.add_invoice(
        InvoiceRow(
            invoice_number="INV-1421",
            vendor_name="International Business Machines Corp",
            invoice_date=date(2026, 1, 12),
            due_date=date(2026, 2, 11),
            amount=Decimal("4500.00"),
            description="Server hardware maintenance (INV-1421)",
        )
    )
    pidx = b.add_payment(
        PaymentRow(
            payment_date=date(2026, 2, 11),
            amount=Decimal("4500.00"),
            memo="IBM CORP PYMT INV1421",  # abbreviated vendor + no-hyphen ref
            counterparty="IBM CORP",
        )
    )
    b.add_scenario(
        "fuzzy_reference_match_abbreviated",
        "fuzzy_reference_match",
        "Payment references an abbreviated vendor name (IBM) instead of "
        "the full legal name.",
        [inv],
        [pidx],
        [ExpectedPair("INV-1421", pidx)],
        None,
        "Amount and date exact; vendor is abbreviated to its common "
        "initialism and the invoice number has no hyphen -- should still "
        "match.",
    )

    # -- 11. fuzzy_reference_match: no usable reference text at all --------
    inv = b.add_invoice(
        InvoiceRow(
            invoice_number="INV-1431",
            vendor_name="Juniper Creek Analytics",
            invoice_date=date(2026, 1, 14),
            due_date=date(2026, 2, 13),
            amount=Decimal("312.40"),
            description="Data analytics subscription (INV-1431)",
        )
    )
    pidx = b.add_payment(
        PaymentRow(
            payment_date=date(2026, 2, 13),
            amount=Decimal("312.40"),
            memo="",  # no usable reference text at all
            counterparty="ONLINE TRANSFER",
        )
    )
    b.add_scenario(
        "fuzzy_reference_match_no_reference_text",
        "fuzzy_reference_match",
        "Payment has an empty memo and a generic, non-identifying "
        "counterparty -- no usable reference text at all.",
        [inv],
        [pidx],
        [ExpectedPair("INV-1431", pidx)],
        None,
        "Amount and date exact; reference/counterparty carry no "
        "identifying signal (expected reference_score ~= 0), so the match "
        "must be inferable from amount + date alone.",
    )

    # -- 12. orphan_invoice: no payment ever generated ----------------------
    inv = b.add_invoice(
        InvoiceRow(
            invoice_number="INV-1501",
            vendor_name="Kingsley & Vance LLP",
            invoice_date=date(2026, 1, 20),
            due_date=date(2026, 2, 19),
            amount=Decimal("2200.00"),
            description="Legal retainer (INV-1501)",
        )
    )
    b.add_scenario(
        "orphan_invoice_1",
        "orphan_invoice",
        "Invoice with no corresponding payment anywhere in the dataset.",
        [inv],
        [],
        [],
        "no_candidate",
        "True orphan invoice: never paid.",
    )

    # -- 13. orphan_payment: refund / unrelated transaction ------------------
    pidx = b.add_payment(
        PaymentRow(
            payment_date=date(2026, 2, 15),
            amount=Decimal("150.00"),
            memo="REFUND - RETURNED GOODS",
            counterparty="Amazon Business",
        )
    )
    b.add_scenario(
        "orphan_payment_1",
        "orphan_payment",
        "Bank transaction with no corresponding invoice (a refund).",
        [],
        [pidx],
        [],
        "no_candidate",
        "True orphan payment: a refund/unrelated transaction that was "
        "never invoiced.",
    )

    # -- 14. ambiguous_tie: two invoices, one payment fits either -----------
    inv_a = b.add_invoice(
        InvoiceRow(
            invoice_number="INV-1701",
            vendor_name="Lighthouse Media Group",
            invoice_date=date(2026, 1, 22),
            due_date=date(2026, 2, 21),
            amount=Decimal("860.00"),
            description="Ad campaign services - Phase 1 (INV-1701)",
        )
    )
    inv_b = b.add_invoice(
        InvoiceRow(
            invoice_number="INV-1702",
            vendor_name="Lighthouse Media Group",
            invoice_date=date(2026, 1, 22),
            due_date=date(2026, 2, 21),
            amount=Decimal("860.00"),
            description="Ad campaign services - Phase 2 (INV-1702)",
        )
    )
    pidx = b.add_payment(
        PaymentRow(
            payment_date=date(2026, 2, 21),
            amount=Decimal("860.00"),
            memo="Lighthouse Media Group payment",
            counterparty="Lighthouse Media Group",
        )
    )
    b.add_scenario(
        "ambiguous_tie_1",
        "ambiguous_tie",
        "Two invoices with identical amount and due date; one payment "
        "with a generic reference fits either equally well.",
        [inv_a, inv_b],
        [pidx],
        [],
        "ambiguous_multiple_candidates",
        "INV-1701 and INV-1702 are identical on amount/date/vendor; the "
        "payment's reference does not favor either. Must not auto-match; "
        "expect an ambiguous-candidates exception listing both as "
        "candidates.",
    )

    # -- 15. looks_like_partial_payment: exactly half of one invoice -------
    inv = b.add_invoice(
        InvoiceRow(
            invoice_number="INV-1801",
            vendor_name="Meridian Steel Works",
            invoice_date=date(2026, 1, 25),
            due_date=date(2026, 2, 24),
            amount=Decimal("1000.00"),
            description="Structural steel order (INV-1801)",
        )
    )
    pidx = b.add_payment(
        PaymentRow(
            payment_date=date(2026, 2, 24),
            amount=Decimal("500.00"),  # exactly half of the invoice amount
            memo="INV-1801 partial payment",
            counterparty="Meridian Steel Works",
        )
    )
    b.add_scenario(
        "looks_like_partial_payment_half",
        "looks_like_partial_payment",
        "Payment amount is exactly half of the invoice amount; reference "
        "and date otherwise agree.",
        [inv],
        [pidx],
        [],
        "possible_split_payment",
        "Despite an exact reference/date match, the amount is only half "
        "of the invoice and far outside tolerance. Must NOT auto-match "
        "as a full payment.",
    )

    # -- 16. looks_like_partial_payment: invoice == sum of two payments -----
    inv = b.add_invoice(
        InvoiceRow(
            invoice_number="INV-1851",
            vendor_name="Meridian Steel Works",
            invoice_date=date(2026, 1, 26),
            due_date=date(2026, 2, 25),
            amount=Decimal("1200.00"),
            description="Structural steel order (INV-1851)",
        )
    )
    pidx_a = b.add_payment(
        PaymentRow(
            payment_date=date(2026, 2, 25),
            amount=Decimal("600.00"),
            memo="INV-1851 payment 1 of 2",
            counterparty="Meridian Steel Works",
        )
    )
    pidx_b = b.add_payment(
        PaymentRow(
            payment_date=date(2026, 2, 26),
            amount=Decimal("600.00"),
            memo="INV-1851 payment 2 of 2",
            counterparty="Meridian Steel Works",
        )
    )
    b.add_scenario(
        "looks_like_partial_payment_sum",
        "looks_like_partial_payment",
        "Invoice amount equals the sum of two separate payments, "
        "neither of which individually matches it.",
        [inv],
        [pidx_a, pidx_b],
        [],
        "possible_split_payment",
        "$600 + $600 == $1,200, but neither payment individually is "
        "within tolerance of the invoice. Neither should auto-match.",
    )

    # -- 17. duplicate_looking_payment: same amount/day, different refs -----
    inv_a = b.add_invoice(
        InvoiceRow(
            invoice_number="INV-1901",
            vendor_name="Nightingale Health Partners",
            invoice_date=date(2026, 1, 28),
            due_date=date(2026, 2, 27),
            amount=Decimal("750.00"),
            description="Medical equipment lease (INV-1901)",
        )
    )
    inv_b = b.add_invoice(
        InvoiceRow(
            invoice_number="INV-1902",
            vendor_name="Oakridge Diagnostics",
            invoice_date=date(2026, 1, 28),
            due_date=date(2026, 2, 27),
            amount=Decimal("750.00"),
            description="Medical equipment lease (INV-1902)",
        )
    )
    pidx_a = b.add_payment(
        PaymentRow(
            payment_date=date(2026, 2, 27),
            amount=Decimal("750.00"),
            memo="INV-1901 Nightingale Health Partners",
            counterparty="Nightingale Health Partners",
        )
    )
    pidx_b = b.add_payment(
        PaymentRow(
            payment_date=date(2026, 2, 27),
            amount=Decimal("750.00"),
            memo="INV-1902 Oakridge Diagnostics",
            counterparty="Oakridge Diagnostics",
        )
    )
    b.add_scenario(
        "duplicate_looking_payment_1",
        "duplicate_looking_payment",
        "Two payments with the same amount and the same day, but "
        "different references, correctly resolving to two distinct "
        "invoices.",
        [inv_a, inv_b],
        [pidx_a, pidx_b],
        [ExpectedPair("INV-1901", pidx_a), ExpectedPair("INV-1902", pidx_b)],
        None,
        "The amount+date collision could look like a duplicate payment "
        "to a matcher that only looks at amount/date, but the references "
        "clearly disambiguate: both are legitimate, distinct clean-ish "
        "matches and both should match.",
    )


_FILLER_VENDORS = [
    "Pinecrest Logistics",
    "Redwood Analytics",
    "Silverline Manufacturing",
    "Cobalt Ridge Consulting",
    "Amber Fields Distribution",
    "Vantage Point Security",
    "Windmill Creative Studio",
    "Cascade Valley Foods",
    "Ironclad Fabrication",
    "Bright Horizon Staffing",
    "Cedarwood Property Services",
    "Nova Terra Energy",
]

_FILLER_ORPHAN_PAYMENT_MEMOS = [
    ("WIRE TRANSFER - MISC", "Unknown Sender"),
    ("BANK FEE ADJUSTMENT", "First National Bank"),
    ("PAYROLL FUNDING", "Internal Payroll"),
]


def _random_amount(rng: random.Random, low: str, high: str) -> Decimal:
    low_d, high_d = Decimal(low), Decimal(high)
    span = high_d - low_d
    frac = Decimal(str(round(rng.uniform(0.0, 1.0), 6)))
    return (low_d + span * frac).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _random_date(rng: random.Random, start: date, end: date) -> date:
    delta_days = (end - start).days
    return start + timedelta(days=rng.randint(0, delta_days))


def _build_filler(
    b: _Builder,
    rng: random.Random,
    n_clean: int = 10,
    n_orphan_invoice: int = 3,
    n_orphan_payment: int = 2,
) -> None:
    """Background rows for bulk/realism, generated from a seeded RNG.

    These are not required by the brief (every required scenario type is
    already covered by the hand-authored core scenarios above); they exist
    to exercise the seeded-randomness determinism path and give the dataset
    more realistic bulk.
    """
    for i in range(n_clean):
        vendor = rng.choice(_FILLER_VENDORS)
        invoice_date_ = _random_date(rng, date(2026, 1, 1), date(2026, 1, 31))
        due_date = invoice_date_ + timedelta(days=30)
        amount = _random_amount(rng, "100.00", "9000.00")
        invoice_number = f"INV-50{i:02d}"
        inv = b.add_invoice(
            InvoiceRow(
                invoice_number=invoice_number,
                vendor_name=vendor,
                invoice_date=invoice_date_,
                due_date=due_date,
                amount=amount,
                description=f"{vendor} services ({invoice_number})",
            )
        )
        pidx = b.add_payment(
            PaymentRow(
                payment_date=due_date,
                amount=amount,
                memo=f"{invoice_number} {vendor}",
                counterparty=vendor,
            )
        )
        b.add_scenario(
            f"clean_match_bg_{i:02d}",
            "clean_match",
            f"Background clean match for {vendor}.",
            [inv],
            [pidx],
            [ExpectedPair(invoice_number, pidx)],
            None,
            "Randomly generated (seeded) filler clean_match for dataset bulk.",
        )

    for i in range(n_orphan_invoice):
        vendor = rng.choice(_FILLER_VENDORS)
        invoice_date_ = _random_date(rng, date(2026, 1, 1), date(2026, 1, 31))
        due_date = invoice_date_ + timedelta(days=30)
        amount = _random_amount(rng, "100.00", "9000.00")
        invoice_number = f"INV-59{i:02d}"
        inv = b.add_invoice(
            InvoiceRow(
                invoice_number=invoice_number,
                vendor_name=vendor,
                invoice_date=invoice_date_,
                due_date=due_date,
                amount=amount,
                description=f"{vendor} services ({invoice_number})",
            )
        )
        b.add_scenario(
            f"orphan_invoice_bg_{i:02d}",
            "orphan_invoice",
            f"Background orphan invoice for {vendor}.",
            [inv],
            [],
            [],
            "no_candidate",
            "Randomly generated (seeded) filler orphan invoice.",
        )

    for i in range(n_orphan_payment):
        memo, counterparty = _FILLER_ORPHAN_PAYMENT_MEMOS[i % len(_FILLER_ORPHAN_PAYMENT_MEMOS)]
        payment_date_ = _random_date(rng, date(2026, 2, 1), date(2026, 2, 28))
        amount = _random_amount(rng, "20.00", "500.00")
        pidx = b.add_payment(
            PaymentRow(
                payment_date=payment_date_,
                amount=amount,
                memo=memo,
                counterparty=counterparty,
            )
        )
        b.add_scenario(
            f"orphan_payment_bg_{i:02d}",
            "orphan_payment",
            f"Background orphan payment ({memo}).",
            [],
            [pidx],
            [],
            "no_candidate",
            "Randomly generated (seeded) filler orphan payment.",
        )


def build_dataset(seed: int = DEFAULT_SEED) -> Dataset:
    """Build the full synthetic dataset deterministically for the given seed."""
    b = _Builder()
    _build_core_scenarios(b)
    rng = random.Random(seed)
    _build_filler(b, rng)
    return Dataset(seed=seed, invoices=b.invoices, payments=b.payments, scenarios=b.scenarios)


def _scenario_to_dict(s: Scenario) -> dict:
    return {
        "scenario_id": s.scenario_id,
        "scenario_type": s.scenario_type,
        "description": s.description,
        "invoice_numbers": s.invoice_numbers,
        "payment_row_indices": s.payment_row_indices,
        "expected_match": s.expected_match,
        "expected_pairs": [
            {"invoice_number": p.invoice_number, "payment_row_index": p.payment_row_index}
            for p in s.expected_pairs
        ],
        "expected_exception_reason": s.expected_exception_reason,
        "notes": s.notes,
    }


def _invoice_index(scenarios: List[Scenario]) -> Dict[str, str]:
    index: Dict[str, str] = {}
    for s in scenarios:
        for num in s.invoice_numbers:
            index[num] = s.scenario_id
    return index


def _payment_index(scenarios: List[Scenario]) -> Dict[str, str]:
    index: Dict[str, str] = {}
    for s in scenarios:
        for idx in s.payment_row_indices:
            index[str(idx)] = s.scenario_id
    return index


def write_ground_truth(dataset: Dataset, path: Path) -> None:
    """Write ``ground_truth.json`` describing the expected outcome of every scenario.

    See this module's docstring for the full schema description and the
    row-identity convention (invoice_number for invoices, 0-based
    payment_row_index for payments).
    """
    payload = {
        "seed": dataset.seed,
        "generated_by": "app.synthetic.scenarios",
        "files": {
            "invoices_csv": INVOICE_CSV_FILENAME,
            "payments_csv": PAYMENT_CSV_FILENAME,
        },
        "assumptions": {
            "amount_tolerance": {
                "flat": format(AMOUNT_TOLERANCE_FLAT, ".2f"),
                "percent": str(AMOUNT_TOLERANCE_PCT),
                "rule": (
                    "tolerance = max(flat, percent * invoice_amount), percent "
                    "portion rounded to cents (ROUND_HALF_UP); a pair matches "
                    "on amount iff abs(payment.amount - invoice.amount) <= "
                    "tolerance"
                ),
            },
            "date_window": {
                "days": DATE_WINDOW_DAYS,
                "anchor": "invoice.due_date",
                "rule": (
                    "a pair matches on date iff "
                    "abs((payment.payment_date - invoice.due_date).days) <= days"
                ),
            },
            "payment_row_index": (
                "0-based index into payments_csv's data rows (excluding the "
                "header row); stable because row order is fixed at "
                "generation time and never shuffled."
            ),
        },
        "scenario_types_required": SCENARIO_TYPES_REQUIRED,
        "counts": {
            "invoice_count": len(dataset.invoices),
            "payment_count": len(dataset.payments),
            "scenario_count": len(dataset.scenarios),
        },
        "scenarios": [_scenario_to_dict(s) for s in dataset.scenarios],
        "index": {
            "by_invoice_number": _invoice_index(dataset.scenarios),
            "by_payment_row_index": _payment_index(dataset.scenarios),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=False)
        fh.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the full synthetic dataset: invoices.csv, "
            "bank_statement.csv, and ground_truth.json, in one deterministic "
            "pass."
        )
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    # Imported lazily to avoid a circular import at module load time (both
    # generate_invoices and generate_payments import from this module).
    from app.synthetic.generate_invoices import write_invoice_csv
    from app.synthetic.generate_payments import write_payment_csv

    dataset = build_dataset(args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_invoice_csv(dataset.invoices, args.out_dir / INVOICE_CSV_FILENAME)
    write_payment_csv(dataset.payments, args.out_dir / PAYMENT_CSV_FILENAME)
    write_ground_truth(dataset, args.out_dir / GROUND_TRUTH_FILENAME)

    print(
        f"Generated {len(dataset.invoices)} invoices, {len(dataset.payments)} "
        f"payments, {len(dataset.scenarios)} scenarios (seed={args.seed}) -> "
        f"{args.out_dir}"
    )


if __name__ == "__main__":
    main()
