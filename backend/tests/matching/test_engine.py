"""Candidate generation and the mutual-best-with-margin commitment rule."""

from datetime import date
from decimal import Decimal

from app.matching.config import DEFAULT_CONFIG, MatchConfig
from app.matching.engine import generate_candidates, match_pairs, run_matching
from app.matching.types import (
    REASON_AMBIGUOUS,
    REASON_BELOW_THRESHOLD,
    REASON_CANDIDATE_CLAIMED,
    REASON_NO_CANDIDATE,
    SIDE_INVOICE,
    SIDE_PAYMENT,
    InvoiceRecord,
    PaymentRecord,
)


def invoice(
    id,
    amount="100.00",
    due_date=date(2026, 2, 1),
    number=None,
    vendor="Acme Robotics Inc",
    text=None,
):
    return InvoiceRecord(
        id=id,
        amount=Decimal(amount),
        date=date(2026, 1, 1),
        due_date=due_date,
        invoice_number=number if number is not None else id,
        vendor_name=vendor,
        raw_reference_text=text,
    )


def payment(
    id,
    amount="100.00",
    on=date(2026, 2, 1),
    reference=None,
    counterparty="Acme Robotics Inc",
):
    return PaymentRecord(
        id=id,
        amount=Decimal(amount),
        date=on,
        reference=reference,
        counterparty=counterparty,
    )


def exception_for(result, side, record_id):
    for candidate in result.exceptions:
        if candidate.side == side and candidate.record_id == record_id:
            return candidate
    raise AssertionError(
        "no exception for {0} {1}; got {2}".format(
            side,
            record_id,
            [(e.side, e.record_id, e.reason) for e in result.exceptions],
        )
    )


# --- candidate generation -------------------------------------------------


def test_a_clean_pair_becomes_a_candidate():
    invoices = [invoice("INV-1", number="INV-1")]
    payments = [payment("PAY-1", reference="INV-1 Acme Robotics Inc")]

    candidates = generate_candidates(invoices, payments, DEFAULT_CONFIG)

    assert [(c.invoice_id, c.payment_id) for c in candidates] == [("INV-1", "PAY-1")]
    assert candidates[0].confidence == 100.0


def test_an_amount_outside_tolerance_never_becomes_a_candidate():
    """A half-payment with a perfect reference and a perfect date is excluded.

    Not merely low-scoring -- absent. Without the hard amount gate this pair
    would score 0.30 * 100 + 0.25 * 100 = 55 on date and reference alone, and a
    weaker gate would let split payments creep into the candidate pool.
    """
    invoices = [invoice("INV-1", amount="1000.00", number="INV-1")]
    payments = [
        payment("PAY-1", amount="500.00", reference="INV-1 partial payment"),
    ]

    candidates = generate_candidates(invoices, payments, DEFAULT_CONFIG)

    assert candidates == []


def test_an_amount_one_cent_past_tolerance_never_becomes_a_candidate():
    invoices = [invoice("INV-1", amount="80.00", number="INV-1")]
    payments = [
        payment("PAY-IN", amount="79.00", reference="INV-1"),
        payment("PAY-OUT", amount="78.99", reference="INV-1"),
    ]

    candidates = generate_candidates(invoices, payments, DEFAULT_CONFIG)

    assert [c.payment_id for c in candidates] == ["PAY-IN"]


def test_a_date_outside_the_window_never_becomes_a_candidate():
    invoices = [invoice("INV-1", due_date=date(2026, 2, 1), number="INV-1")]
    payments = [
        payment("PAY-IN", on=date(2026, 2, 6), reference="INV-1"),
        payment("PAY-OUT", on=date(2026, 2, 7), reference="INV-1"),
    ]

    candidates = generate_candidates(invoices, payments, DEFAULT_CONFIG)

    assert [c.payment_id for c in candidates] == ["PAY-IN"]


def test_generate_candidates_does_not_mutate_its_inputs():
    invoices = [invoice("INV-2"), invoice("INV-1")]
    payments = [payment("PAY-2"), payment("PAY-1")]
    invoice_order = [record.id for record in invoices]
    payment_order = [record.id for record in payments]

    generate_candidates(invoices, payments, DEFAULT_CONFIG)

    assert [record.id for record in invoices] == invoice_order
    assert [record.id for record in payments] == payment_order


# --- commitment -----------------------------------------------------------


def test_mutual_best_commits():
    invoices = [
        invoice("INV-1", amount="100.00", number="INV-1"),
        invoice("INV-2", amount="250.00", number="INV-2", vendor="Blue Harbor Supplies"),
    ]
    payments = [
        payment("PAY-1", amount="100.00", reference="INV-1 Acme Robotics Inc"),
        payment(
            "PAY-2",
            amount="250.00",
            reference="INV-2 Blue Harbor Supplies",
            counterparty="Blue Harbor Supplies",
        ),
    ]

    result = run_matching(invoices, payments, DEFAULT_CONFIG)

    assert match_pairs(result) == [("INV-1", "PAY-1"), ("INV-2", "PAY-2")]
    assert result.exceptions == []


def test_a_committed_match_carries_its_explaining_sub_scores():
    invoices = [invoice("INV-1", number="INV-1")]
    payments = [payment("PAY-1", reference="INV-1 Acme Robotics Inc")]

    match = run_matching(invoices, payments, DEFAULT_CONFIG).matches[0]

    assert match.amount_score == 100.0
    assert match.date_score == 100.0
    assert match.reference_score == 100.0
    assert match.confidence == 100.0


def test_a_tie_produces_an_ambiguity_exception_and_commits_nothing():
    """Two identical invoices, one payment that fits either equally well."""
    invoices = [
        invoice("INV-1", vendor="Lighthouse Media Group", number="INV-1701"),
        invoice("INV-2", vendor="Lighthouse Media Group", number="INV-1702"),
    ]
    payments = [
        payment(
            "PAY-1",
            reference="Lighthouse Media Group payment",
            counterparty="Lighthouse Media Group",
        )
    ]

    result = run_matching(invoices, payments, DEFAULT_CONFIG)

    assert result.matches == []

    ambiguity = exception_for(result, SIDE_PAYMENT, "PAY-1")
    assert ambiguity.reason == REASON_AMBIGUOUS
    assert {ref.record_id for ref in ambiguity.candidates} == {"INV-1", "INV-2"}
    assert all(ref.confidence > 0 for ref in ambiguity.candidates)

    # Both invoices are told the payment they wanted is contested, too.
    for invoice_id in ("INV-1", "INV-2"):
        entry = exception_for(result, SIDE_INVOICE, invoice_id)
        assert entry.reason == REASON_AMBIGUOUS
        assert [ref.record_id for ref in entry.candidates] == ["PAY-1"]


def test_a_rival_just_inside_the_margin_blocks_the_commit():
    invoices = [invoice("INV-1", number="INV-1")]
    payments = [payment("PAY-1", reference="INV-1"), payment("PAY-2", reference="INV-1")]

    # Identical candidates: nothing separates PAY-1 from PAY-2.
    result = run_matching(invoices, payments, DEFAULT_CONFIG)

    assert result.matches == []
    assert exception_for(result, SIDE_INVOICE, "INV-1").reason == REASON_AMBIGUOUS


# Amount alone carries the confidence in the next two tests, which makes the
# gap between two rivals exactly computable. A $100.00 invoice tolerates $1.00,
# and the score decays from 100.0 to 25.0 across that band -- so every cent of
# shortfall costs exactly 0.75 points.
AMOUNT_ONLY_CONFIG = MatchConfig(
    weight_amount=1.0,
    weight_date=0.0,
    weight_reference=0.0,
    ambiguity_margin=3.0,
)


def test_a_rival_exactly_at_the_margin_does_not_block_the_commit():
    """The margin is exclusive: a gap of exactly ``ambiguity_margin`` commits."""
    invoices = [invoice("INV-1", amount="100.00", number="INV-1")]
    payments = [
        payment("PAY-1", amount="100.00"),
        payment("PAY-2", amount="99.96"),  # 4 cents short: exactly 3.0 points back
    ]

    result = run_matching(invoices, payments, AMOUNT_ONLY_CONFIG)

    ranked = generate_candidates(invoices, payments, AMOUNT_ONLY_CONFIG)
    gap = max(c.confidence for c in ranked) - min(c.confidence for c in ranked)
    assert gap == AMOUNT_ONLY_CONFIG.ambiguity_margin

    assert match_pairs(result) == [("INV-1", "PAY-1")]
    assert exception_for(result, SIDE_PAYMENT, "PAY-2").reason == (
        REASON_CANDIDATE_CLAIMED
    )


def test_a_rival_one_cent_inside_the_margin_blocks_the_commit():
    invoices = [invoice("INV-1", amount="100.00", number="INV-1")]
    payments = [
        payment("PAY-1", amount="100.00"),
        payment("PAY-2", amount="99.97"),  # 3 cents short: only 2.25 points back
    ]

    result = run_matching(invoices, payments, AMOUNT_ONLY_CONFIG)

    assert result.matches == []
    ambiguity = exception_for(result, SIDE_INVOICE, "INV-1")
    assert ambiguity.reason == REASON_AMBIGUOUS
    assert {ref.record_id for ref in ambiguity.candidates} == {"PAY-1", "PAY-2"}


def test_a_below_threshold_pair_produces_an_exception_not_a_weak_match():
    """Both amount and date sit on their boundaries and the memo says nothing.

    0.45 * 25.0 + 0.30 * 10.0 + 0.25 * 0.0 = 14.25, far under the 60.0 review
    threshold -- the engine must decline rather than commit a weak guess.
    """
    invoices = [
        invoice("INV-1", amount="80.00", due_date=date(2026, 2, 9), vendor=None)
    ]
    payments = [
        payment(
            "PAY-1",
            amount="79.00",
            on=date(2026, 2, 14),
            reference=None,
            counterparty=None,
        )
    ]

    result = run_matching(invoices, payments, DEFAULT_CONFIG)

    assert result.matches == []
    for side, record_id in ((SIDE_INVOICE, "INV-1"), (SIDE_PAYMENT, "PAY-1")):
        entry = exception_for(result, side, record_id)
        assert entry.reason == REASON_BELOW_THRESHOLD
        assert [ref.confidence for ref in entry.candidates] == [14.25]


def test_a_record_with_no_candidates_at_all_reports_no_candidate():
    invoices = [invoice("INV-1", amount="100.00")]
    payments = [payment("PAY-1", amount="900.00", counterparty="Somebody Else")]

    result = run_matching(invoices, payments, DEFAULT_CONFIG)

    assert result.matches == []
    assert exception_for(result, SIDE_INVOICE, "INV-1").reason == REASON_NO_CANDIDATE
    assert exception_for(result, SIDE_PAYMENT, "PAY-1").reason == REASON_NO_CANDIDATE
    assert exception_for(result, SIDE_INVOICE, "INV-1").candidates == []


def test_a_loser_whose_only_candidate_was_claimed_says_so():
    """INV-2 wanted PAY-1 too, but INV-2 lost by a decisive margin."""
    invoices = [
        invoice("INV-1", number="INV-1101", vendor="Blue Harbor Supplies"),
        invoice("INV-2", number="INV-1102", vendor="Blue Harbor Supplies"),
    ]
    payments = [
        payment(
            "PAY-1",
            reference="INV-1101 Blue Harbor Supplies",
            counterparty="Blue Harbor Supplies",
        )
    ]

    result = run_matching(invoices, payments, DEFAULT_CONFIG)

    assert match_pairs(result) == [("INV-1", "PAY-1")]
    loser = exception_for(result, SIDE_INVOICE, "INV-2")
    assert loser.reason == REASON_CANDIDATE_CLAIMED
    assert [ref.record_id for ref in loser.candidates] == ["PAY-1"]


def test_a_claimed_loser_reports_its_runners_up_not_just_its_leader():
    """An exception must carry the whole ranked list, not only the best entry.

    INV-2 loses PAY-1 to INV-1, but INV-2 also has PAY-2 as a second candidate
    scoring above ``auto_suggest_threshold``. That runner-up is precisely what a
    human resolving the exception needs to see -- reporting only the leader
    would hide a viable pairing behind the one that got away.
    """
    invoices = [
        invoice("INV-1", number="INV-1"),
        invoice("INV-2", number="INV-2"),
    ]
    payments = [
        payment("PAY-1", reference="INV-1 Acme Robotics Inc"),
        payment(
            "PAY-2", on=date(2026, 2, 3), reference="INV-2 Acme Robotics Inc"
        ),
    ]

    result = run_matching(invoices, payments, DEFAULT_CONFIG)

    assert match_pairs(result) == [("INV-1", "PAY-1")]

    loser = exception_for(result, SIDE_INVOICE, "INV-2")
    assert loser.reason == REASON_CANDIDATE_CLAIMED
    assert [ref.record_id for ref in loser.candidates] == ["PAY-1", "PAY-2"]
    # Best first, and the runner-up would have been an auto-suggestion.
    assert loser.candidates[0].confidence > loser.candidates[1].confidence
    assert loser.candidates[1].confidence > DEFAULT_CONFIG.auto_suggest_threshold


def test_a_contested_counterparts_exception_reports_runners_up_too():
    """Same requirement on the other ambiguity branch.

    Both invoices want PAY-1 equally, so PAY-1 is contested and neither commits.
    Each invoice also has PAY-2 as a clear second choice, which must be listed.
    """
    vendor = "Lighthouse Media Group"
    invoices = [
        invoice("INV-1", number="INV-1701", vendor=vendor),
        invoice("INV-2", number="INV-1702", vendor=vendor),
    ]
    payments = [
        payment("PAY-1", reference=vendor + " payment", counterparty=vendor),
        payment(
            "PAY-2",
            on=date(2026, 2, 4),
            reference="INV-1701 " + vendor,
            counterparty=vendor,
        ),
    ]

    result = run_matching(invoices, payments, DEFAULT_CONFIG)

    assert result.matches == []

    for invoice_id in ("INV-1", "INV-2"):
        entry = exception_for(result, SIDE_INVOICE, invoice_id)
        assert entry.reason == REASON_AMBIGUOUS
        assert [ref.record_id for ref in entry.candidates] == ["PAY-1", "PAY-2"]
        assert entry.candidates[0].confidence > entry.candidates[1].confidence


def test_every_exception_lists_its_candidates_best_first():
    """Ordering is part of the contract: the list is a ranking, not a bag."""
    invoices = [
        invoice("INV-1", number="INV-1"),
        invoice("INV-2", number="INV-2"),
    ]
    payments = [
        payment("PAY-1", reference="INV-1 Acme Robotics Inc"),
        payment(
            "PAY-2", on=date(2026, 2, 3), reference="INV-2 Acme Robotics Inc"
        ),
    ]

    result = run_matching(invoices, payments, DEFAULT_CONFIG)

    assert result.exceptions
    for entry in result.exceptions:
        scores = [ref.confidence for ref in entry.candidates]
        assert scores == sorted(scores, reverse=True)
        ids = [ref.record_id for ref in entry.candidates]
        assert len(ids) == len(set(ids))


def test_every_unmatched_record_gets_exactly_one_exception():
    invoices = [invoice("INV-1"), invoice("INV-2", amount="5000.00")]
    payments = [payment("PAY-1"), payment("PAY-2", amount="7000.00")]

    result = run_matching(invoices, payments, DEFAULT_CONFIG)

    matched_invoices = {m.invoice_id for m in result.matches}
    matched_payments = {m.payment_id for m in result.matches}
    reported = [(e.side, e.record_id) for e in result.exceptions]

    assert len(reported) == len(set(reported))
    assert set(reported) == (
        {(SIDE_INVOICE, i.id) for i in invoices if i.id not in matched_invoices}
        | {(SIDE_PAYMENT, p.id) for p in payments if p.id not in matched_payments}
    )


def test_a_payment_is_never_committed_to_two_invoices():
    invoices = [
        invoice("INV-1", number="INV-1"),
        invoice("INV-2", number="INV-2"),
        invoice("INV-3", number="INV-3"),
    ]
    payments = [payment("PAY-1", reference="INV-1 Acme Robotics Inc")]

    result = run_matching(invoices, payments, DEFAULT_CONFIG)

    committed = [m.payment_id for m in result.matches]
    assert len(committed) == len(set(committed))


# --- determinism ----------------------------------------------------------


def test_run_matching_is_idempotent():
    invoices = [
        invoice("INV-3", amount="300.00", number="INV-3"),
        invoice("INV-1", amount="100.00", number="INV-1"),
        invoice("INV-2", amount="100.00", number="INV-2"),
    ]
    payments = [
        payment("PAY-2", amount="300.00", reference="INV-3 Acme Robotics Inc"),
        payment("PAY-1", amount="100.00", reference="Acme Robotics Inc"),
        payment("PAY-3", amount="900.00", counterparty="Nobody At All"),
    ]

    first = run_matching(invoices, payments, DEFAULT_CONFIG)
    second = run_matching(invoices, payments, DEFAULT_CONFIG)

    assert first == second
    assert first.matches == second.matches
    assert first.exceptions == second.exceptions


def test_run_matching_does_not_depend_on_input_order():
    invoices = [
        invoice("INV-1", amount="100.00", number="INV-1"),
        invoice("INV-2", amount="300.00", number="INV-2"),
    ]
    payments = [
        payment("PAY-1", amount="100.00", reference="INV-1 Acme Robotics Inc"),
        payment("PAY-2", amount="300.00", reference="INV-2 Acme Robotics Inc"),
    ]

    forward = run_matching(invoices, payments, DEFAULT_CONFIG)
    reversed_ = run_matching(
        list(reversed(invoices)), list(reversed(payments)), DEFAULT_CONFIG
    )

    assert forward == reversed_


def test_run_matching_does_not_mutate_its_inputs():
    invoices = [invoice("INV-2"), invoice("INV-1")]
    payments = [payment("PAY-2"), payment("PAY-1")]
    invoice_order = [record.id for record in invoices]
    payment_order = [record.id for record in payments]

    run_matching(invoices, payments, DEFAULT_CONFIG)

    assert [record.id for record in invoices] == invoice_order
    assert [record.id for record in payments] == payment_order
