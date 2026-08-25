"""The standing regression guardrail: the engine against the synthetic corpus.

Loads the fixed synthetic invoices, bank statement, and ``ground_truth.json``
produced by the scenario generator, runs the engine once, and asserts that every
declared scenario resolves the way the ground truth says it must.

``expected_match`` and ``expected_pairs`` are binding. ``expected_exception_reason``
is advisory: the generator recorded what it *guessed* a matcher would say, while
the engine's own classification is authoritative. The divergences are asserted
explicitly below so a future change to either side is caught rather than shrugged
off.

These tests read CSVs with the standard library and touch no database and no web
framework -- the only project import is ``app.matching``.
"""

import csv
import json
import os
from datetime import datetime
from decimal import Decimal

import pytest

from app.matching import (
    DEFAULT_CONFIG,
    REASON_AMBIGUOUS,
    REASON_CANDIDATE_CLAIMED,
    REASON_NO_CANDIDATE,
    SIDE_INVOICE,
    SIDE_PAYMENT,
    InvoiceRecord,
    PaymentRecord,
    generate_candidates,
    run_matching,
)

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "synthetic",
)

# The bank statement predates any column-mapping UI and carries non-canonical
# headers, so its columns are read by position under a known mapping rather
# than by assuming canonical names.
PAYMENT_COLUMNS = ("Post Date", "Trans Amt", "Memo", "Other Party")
PAYMENT_DATE, PAYMENT_AMOUNT, PAYMENT_MEMO, PAYMENT_PARTY = range(4)


def payment_id(row_index):
    """Stable id for a payment, derived from its 0-based data-row index."""
    return "PAY-ROW-{0:04d}".format(row_index)


def _parse_date(value):
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def load_ground_truth():
    with open(os.path.join(DATA_DIR, "ground_truth.json")) as handle:
        return json.load(handle)


def load_invoices():
    records = []
    with open(os.path.join(DATA_DIR, "invoices.csv"), newline="") as handle:
        for row in csv.DictReader(handle):
            records.append(
                InvoiceRecord(
                    id=row["invoice_number"],
                    amount=Decimal(row["amount"]),
                    date=_parse_date(row["invoice_date"]),
                    due_date=_parse_date(row["due_date"]),
                    invoice_number=row["invoice_number"],
                    vendor_name=row["vendor_name"] or None,
                    raw_reference_text=row["description"] or None,
                )
            )
    return records


def load_payments():
    records = []
    with open(os.path.join(DATA_DIR, "bank_statement.csv"), newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        assert tuple(h.strip() for h in header) == PAYMENT_COLUMNS, (
            "bank_statement.csv header changed; the positional mapping in this "
            "test needs updating: {0!r}".format(header)
        )
        for row_index, row in enumerate(reader):
            records.append(
                PaymentRecord(
                    id=payment_id(row_index),
                    amount=Decimal(row[PAYMENT_AMOUNT]),
                    date=_parse_date(row[PAYMENT_DATE]),
                    reference=row[PAYMENT_MEMO].strip() or None,
                    counterparty=row[PAYMENT_PARTY].strip() or None,
                )
            )
    return records


@pytest.fixture(scope="module")
def ground_truth():
    return load_ground_truth()


@pytest.fixture(scope="module")
def invoices():
    return load_invoices()


@pytest.fixture(scope="module")
def payments():
    return load_payments()


@pytest.fixture(scope="module")
def result(invoices, payments):
    return run_matching(invoices, payments, DEFAULT_CONFIG)


@pytest.fixture(scope="module")
def committed_pairs(result):
    return {(match.invoice_id, match.payment_id) for match in result.matches}


@pytest.fixture(scope="module")
def exceptions_by_record(result):
    return {
        (entry.side, entry.record_id): entry for entry in result.exceptions
    }


def scenarios():
    return load_ground_truth()["scenarios"]


def scenario_ids():
    return [scenario["scenario_id"] for scenario in scenarios()]


# --- fixture sanity -------------------------------------------------------


def test_fixture_counts_agree_with_the_ground_truth(ground_truth, invoices, payments):
    counts = ground_truth["counts"]
    assert len(invoices) == counts["invoice_count"]
    assert len(payments) == counts["payment_count"]
    assert len(ground_truth["scenarios"]) == counts["scenario_count"]


def test_every_required_scenario_type_is_present(ground_truth):
    present = {scenario["scenario_type"] for scenario in ground_truth["scenarios"]}
    assert set(ground_truth["scenario_types_required"]) <= present


def test_engine_defaults_agree_with_the_generator_assumptions(ground_truth):
    """The corpus was generated against these tolerances; drift invalidates it."""
    assumptions = ground_truth["assumptions"]
    assert DEFAULT_CONFIG.absolute_tolerance == Decimal(
        assumptions["amount_tolerance"]["flat"]
    )
    assert DEFAULT_CONFIG.percentage_tolerance == float(
        assumptions["amount_tolerance"]["percent"]
    )
    assert DEFAULT_CONFIG.date_window_days == assumptions["date_window"]["days"]
    assert assumptions["date_window"]["anchor"] == "invoice.due_date"


def test_invoice_index_resolves_to_real_records(ground_truth, invoices):
    known = {record.id for record in invoices}
    for scenario in ground_truth["scenarios"]:
        for number in scenario["invoice_numbers"]:
            assert number in known, scenario["scenario_id"]


def test_payment_index_resolves_to_real_records(ground_truth, payments):
    known = {record.id for record in payments}
    for scenario in ground_truth["scenarios"]:
        for row_index in scenario["payment_row_indices"]:
            assert payment_id(row_index) in known, scenario["scenario_id"]


# --- the guardrail itself -------------------------------------------------


@pytest.mark.parametrize("scenario", scenarios(), ids=scenario_ids())
def test_scenario_resolves_as_declared(scenario, committed_pairs):
    """Each scenario's records must commit exactly the declared pairs.

    Checked in both directions: every expected pair is present, and no *other*
    pair involving any of the scenario's invoices or payments was committed --
    so a wrong match is a failure just as much as a missing one.
    """
    expected = {
        (pair["invoice_number"], payment_id(pair["payment_row_index"]))
        for pair in scenario["expected_pairs"]
    }
    involved_invoices = set(scenario["invoice_numbers"])
    involved_payments = {
        payment_id(index) for index in scenario["payment_row_indices"]
    }
    actual = {
        pair
        for pair in committed_pairs
        if pair[0] in involved_invoices or pair[1] in involved_payments
    }

    assert actual == expected
    assert bool(expected) == scenario["expected_match"]


@pytest.mark.parametrize("scenario", scenarios(), ids=scenario_ids())
def test_every_unmatched_scenario_record_is_explained(scenario, exceptions_by_record,
                                                      committed_pairs):
    """No record is silently dropped: unmatched means an exception exists."""
    matched_invoices = {pair[0] for pair in committed_pairs}
    matched_payments = {pair[1] for pair in committed_pairs}

    for number in scenario["invoice_numbers"]:
        if number not in matched_invoices:
            assert (SIDE_INVOICE, number) in exceptions_by_record
    for index in scenario["payment_row_indices"]:
        identifier = payment_id(index)
        if identifier not in matched_payments:
            assert (SIDE_PAYMENT, identifier) in exceptions_by_record


def test_the_declared_matches_are_exactly_the_committed_matches(
    ground_truth, committed_pairs
):
    """The corpus-wide total, not just the per-scenario slices."""
    declared = set()
    for scenario in ground_truth["scenarios"]:
        for pair in scenario["expected_pairs"]:
            declared.add(
                (pair["invoice_number"], payment_id(pair["payment_row_index"]))
            )
    assert committed_pairs == declared


def test_every_record_is_either_matched_or_explained(result, invoices, payments):
    matched_invoices = {match.invoice_id for match in result.matches}
    matched_payments = {match.payment_id for match in result.matches}
    explained = {(entry.side, entry.record_id) for entry in result.exceptions}

    for record in invoices:
        assert record.id in matched_invoices or (SIDE_INVOICE, record.id) in explained
    for record in payments:
        assert record.id in matched_payments or (SIDE_PAYMENT, record.id) in explained


def test_no_record_is_matched_twice(result):
    invoice_ids = [match.invoice_id for match in result.matches]
    payment_ids = [match.payment_id for match in result.matches]
    assert len(invoice_ids) == len(set(invoice_ids))
    assert len(payment_ids) == len(set(payment_ids))


def test_run_matching_over_the_corpus_is_idempotent(invoices, payments):
    first = run_matching(invoices, payments, DEFAULT_CONFIG)
    second = run_matching(invoices, payments, DEFAULT_CONFIG)
    assert first == second


# --- scenario families, asserted on their specific mechanics --------------


def test_orphans_report_no_candidate(ground_truth, exceptions_by_record):
    for scenario in ground_truth["scenarios"]:
        if scenario["scenario_type"] not in ("orphan_invoice", "orphan_payment"):
            continue
        for number in scenario["invoice_numbers"]:
            entry = exceptions_by_record[(SIDE_INVOICE, number)]
            assert entry.reason == REASON_NO_CANDIDATE, scenario["scenario_id"]
            assert entry.candidates == []
        for index in scenario["payment_row_indices"]:
            entry = exceptions_by_record[(SIDE_PAYMENT, payment_id(index))]
            assert entry.reason == REASON_NO_CANDIDATE, scenario["scenario_id"]
            assert entry.candidates == []


def test_partial_payments_never_reach_the_candidate_pool(
    ground_truth, invoices, payments
):
    """The hard amount gate, verified on the real corpus.

    A split or partial payment carries a perfect reference and a perfect date;
    only the amount gate keeps it out. Asserted as absence from
    ``generate_candidates``, not as a low score.
    """
    candidates = generate_candidates(invoices, payments, DEFAULT_CONFIG)
    pool = {(c.invoice_id, c.payment_id) for c in candidates}

    checked = 0
    for scenario in ground_truth["scenarios"]:
        if scenario["scenario_type"] != "looks_like_partial_payment":
            continue
        for number in scenario["invoice_numbers"]:
            for index in scenario["payment_row_indices"]:
                assert (number, payment_id(index)) not in pool
                checked += 1
    assert checked > 0


def test_the_ambiguous_tie_lists_both_candidates_and_picks_neither(
    ground_truth, exceptions_by_record, committed_pairs
):
    ties = [
        scenario
        for scenario in ground_truth["scenarios"]
        if scenario["scenario_type"] == "ambiguous_tie"
    ]
    assert ties

    for scenario in ties:
        contested = [payment_id(i) for i in scenario["payment_row_indices"]]
        rivals = set(scenario["invoice_numbers"])

        for identifier in contested:
            entry = exceptions_by_record[(SIDE_PAYMENT, identifier)]
            assert entry.reason == REASON_AMBIGUOUS, scenario["scenario_id"]
            assert {ref.record_id for ref in entry.candidates} == rivals
            # A genuine tie: every listed rival sits within the margin.
            best = max(ref.confidence for ref in entry.candidates)
            for ref in entry.candidates:
                assert best - ref.confidence < DEFAULT_CONFIG.ambiguity_margin

        for number in rivals:
            assert not any(pair[0] == number for pair in committed_pairs)
            assert exceptions_by_record[(SIDE_INVOICE, number)].reason == (
                REASON_AMBIGUOUS
            )


def test_amount_tolerance_edges_commit_but_land_in_the_review_band(result):
    """Boundary-tolerance matches commit, and are flagged rather than trusted.

    INV-1101/INV-1151 are paid exactly one tolerance short (the flat $1.00 and
    the 0.5% $50.00 respectively). Both commit, both land under
    ``auto_suggest_threshold`` -- which is the behavior a reviewer wants: the
    engine names the pair but asks a human to confirm it.
    """
    by_invoice = {match.invoice_id: match for match in result.matches}

    for number in ("INV-1101", "INV-1151"):
        match = by_invoice[number]
        assert match.amount_score < 100.0
        assert (
            DEFAULT_CONFIG.needs_review_threshold
            <= match.confidence
            < DEFAULT_CONFIG.auto_suggest_threshold
        )


def test_the_reference_free_payment_matches_on_amount_and_date_alone(result):
    """INV-1431's payment has an empty memo and a generic counterparty."""
    match = {m.invoice_id: m for m in result.matches}["INV-1431"]
    assert match.reference_score == 0.0
    assert match.amount_score == 100.0
    assert match.date_score == 100.0
    assert match.confidence >= DEFAULT_CONFIG.needs_review_threshold


def test_duplicate_looking_payments_resolve_to_distinct_invoices(
    ground_truth, committed_pairs
):
    duplicates = [
        scenario
        for scenario in ground_truth["scenarios"]
        if scenario["scenario_type"] == "duplicate_looking_payment"
    ]
    assert duplicates

    for scenario in duplicates:
        expected = {
            (pair["invoice_number"], payment_id(pair["payment_row_index"]))
            for pair in scenario["expected_pairs"]
        }
        assert expected <= committed_pairs
        assert len({pair[0] for pair in expected}) == len(expected)


# --- documented divergences from the advisory expected_exception_reason ----

# The generator recorded a guess at each non-matching scenario's exception
# reason before the engine existed. Where the engine's own classification is
# more precise, the actual reason is pinned here so the divergence stays
# deliberate and visible.
ADVISORY_DIVERGENCES = {
    # Generator guessed "amount_mismatch_only". The engine has no such reason:
    # the amount gate simply removes the pair, so the payment has nothing left
    # to consider, while the invoice's only in-tolerance payment was decisively
    # won by its sibling invoice.
    ("amount_tolerance_exceeded_flat", SIDE_INVOICE, "INV-1102"): (
        REASON_CANDIDATE_CLAIMED
    ),
    ("amount_tolerance_exceeded_flat", SIDE_PAYMENT, payment_id(2)): (
        REASON_NO_CANDIDATE
    ),
    ("amount_tolerance_exceeded_pct", SIDE_INVOICE, "INV-1152"): (
        REASON_CANDIDATE_CLAIMED
    ),
    ("amount_tolerance_exceeded_pct", SIDE_PAYMENT, payment_id(4)): (
        REASON_NO_CANDIDATE
    ),
    # Generator guessed "below_threshold". The date window is a hard gate, not a
    # score penalty, so the late payment has no candidates at all.
    ("date_window_exceeded", SIDE_INVOICE, "INV-1302"): REASON_CANDIDATE_CLAIMED,
    ("date_window_exceeded", SIDE_PAYMENT, payment_id(6)): REASON_NO_CANDIDATE,
    # Generator guessed "possible_split_payment". Detecting split payments is a
    # later feature; today the amount gate correctly refuses to pair them, and
    # both sides are honestly reported as having no candidate.
    ("looks_like_partial_payment_half", SIDE_INVOICE, "INV-1801"): (
        REASON_NO_CANDIDATE
    ),
    ("looks_like_partial_payment_half", SIDE_PAYMENT, payment_id(13)): (
        REASON_NO_CANDIDATE
    ),
    ("looks_like_partial_payment_sum", SIDE_INVOICE, "INV-1851"): REASON_NO_CANDIDATE,
    ("looks_like_partial_payment_sum", SIDE_PAYMENT, payment_id(14)): (
        REASON_NO_CANDIDATE
    ),
    ("looks_like_partial_payment_sum", SIDE_PAYMENT, payment_id(15)): (
        REASON_NO_CANDIDATE
    ),
}


@pytest.mark.parametrize(
    "key,expected_reason",
    sorted(ADVISORY_DIVERGENCES.items()),
    ids=["{0}:{1}:{2}".format(*key) for key in sorted(ADVISORY_DIVERGENCES)],
)
def test_documented_divergence_holds(key, expected_reason, exceptions_by_record):
    _, side, record_id = key
    assert exceptions_by_record[(side, record_id)].reason == expected_reason


def test_scenarios_without_a_documented_divergence_agree_with_the_advisory_reason(
    ground_truth, exceptions_by_record, committed_pairs
):
    """Everything not listed above must land on the reason the generator guessed."""
    matched_invoices = {pair[0] for pair in committed_pairs}
    matched_payments = {pair[1] for pair in committed_pairs}
    compared = 0

    for scenario in ground_truth["scenarios"]:
        advisory = scenario["expected_exception_reason"]
        if advisory is None:
            continue
        scenario_id = scenario["scenario_id"]

        records = [
            (SIDE_INVOICE, number)
            for number in scenario["invoice_numbers"]
            if number not in matched_invoices
        ] + [
            (SIDE_PAYMENT, payment_id(index))
            for index in scenario["payment_row_indices"]
            if payment_id(index) not in matched_payments
        ]

        for side, record_id in records:
            if (scenario_id, side, record_id) in ADVISORY_DIVERGENCES:
                continue
            assert exceptions_by_record[(side, record_id)].reason == advisory, (
                scenario_id,
                side,
                record_id,
            )
            compared += 1

    assert compared > 0
