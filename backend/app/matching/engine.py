"""Candidate generation and match commitment.

The engine is deliberately conservative: it commits a pair only when both sides
independently prefer each other by a clear margin, and it explains every record
it declines to match. Nothing here touches a database or a web framework.
"""

from typing import Dict, List, Sequence, Tuple

from app.matching.config import DEFAULT_CONFIG, MatchConfig
from app.matching.scoring import score_amount, score_date, score_pair
from app.matching.types import (
    REASON_AMBIGUOUS,
    REASON_BELOW_THRESHOLD,
    REASON_CANDIDATE_CLAIMED,
    REASON_NO_CANDIDATE,
    SIDE_INVOICE,
    SIDE_PAYMENT,
    CandidateRef,
    ExceptionCandidate,
    InvoiceRecord,
    MatchingResult,
    PaymentRecord,
    ScoredMatch,
)


def generate_candidates(
    invoices: Sequence[InvoiceRecord],
    payments: Sequence[PaymentRecord],
    config: MatchConfig = DEFAULT_CONFIG,
) -> List[ScoredMatch]:
    """Every invoice x payment pair that clears both hard gates, scored.

    The amount gate runs first and on its own: a pair whose amounts differ by
    more than the tolerance is never scored and never becomes a candidate. That
    is what keeps partial and split payments out of the candidate pool entirely
    rather than merely ranking them low -- a half-payment carrying a perfect
    reference and a perfect date would otherwise score high enough to commit.

    The date gate follows, on the same "outside the window scores exactly 0"
    basis. Output is sorted deterministically so repeated runs are identical.
    """
    candidates = []  # type: List[ScoredMatch]

    for invoice in sorted(invoices, key=lambda record: str(record.id)):
        for payment in sorted(payments, key=lambda record: str(record.id)):
            if score_amount(invoice.amount, payment.amount, config) <= 0.0:
                continue
            if score_date(invoice.date_anchor, payment.date, config) <= 0.0:
                continue
            candidates.append(score_pair(invoice, payment, config))

    return candidates


def _index_candidates(
    candidates: Sequence[ScoredMatch], key_attr: str, tiebreak_attr: str
) -> Dict[str, List[ScoredMatch]]:
    """Group candidates by one side's id, each bucket ranked best-first.

    Ties are broken by the opposite side's id. That is purely for determinism:
    a tie never decides an outcome, because the ambiguity margin rejects the
    pair before the ordering matters.
    """
    index = {}  # type: Dict[str, List[ScoredMatch]]
    for candidate in candidates:
        index.setdefault(str(getattr(candidate, key_attr)), []).append(candidate)
    for bucket in index.values():
        bucket.sort(key=lambda c: (-c.confidence, str(getattr(c, tiebreak_attr))))
    return index


def _tied_group(
    ranked: Sequence[ScoredMatch], config: MatchConfig
) -> List[ScoredMatch]:
    """The leader plus every rival within ``ambiguity_margin`` of it.

    A group of length 1 means the leader is clear; anything longer is a genuine
    ambiguity that must not be resolved automatically.
    """
    if not ranked:
        return []
    leader = ranked[0].confidence
    return [c for c in ranked if leader - c.confidence < config.ambiguity_margin]


def _is_ambiguous(ranked: Sequence[ScoredMatch], config: MatchConfig) -> bool:
    return len(_tied_group(ranked, config)) > 1


def _refs(
    candidates: Sequence[ScoredMatch], side: str
) -> List[CandidateRef]:
    """Turn candidates into references to the records on the *other* side."""
    if side == SIDE_INVOICE:
        pairs = [(str(c.payment_id), c.confidence) for c in candidates]
    else:
        pairs = [(str(c.invoice_id), c.confidence) for c in candidates]
    pairs.sort(key=lambda pair: (-pair[1], pair[0]))
    return [CandidateRef(record_id=record_id, confidence=confidence)
            for record_id, confidence in pairs]


def _classify(
    side: str,
    record_id: str,
    own_ranked: Sequence[ScoredMatch],
    opposite_index: Dict[str, List[ScoredMatch]],
    config: MatchConfig,
) -> ExceptionCandidate:
    """Explain why an unmatched record did not commit.

    The order of the checks is the order of severity: no candidate at all beats
    a too-weak candidate, which beats a contested one, which beats one that
    simply lost to a better claim.
    """
    if not own_ranked:
        return ExceptionCandidate(
            side=side, record_id=record_id, reason=REASON_NO_CANDIDATE, candidates=[]
        )

    best = own_ranked[0]
    if best.confidence < config.needs_review_threshold:
        return ExceptionCandidate(
            side=side,
            record_id=record_id,
            reason=REASON_BELOW_THRESHOLD,
            candidates=_refs(own_ranked, side),
        )

    own_tied = _tied_group(own_ranked, config)
    if len(own_tied) > 1:
        return ExceptionCandidate(
            side=side,
            record_id=record_id,
            reason=REASON_AMBIGUOUS,
            candidates=_refs(own_tied, side),
        )

    # This record has one clear preference, but the record it prefers is itself
    # being fought over -- so the ambiguity is real for this record too.
    counterpart_id = (
        best.payment_id if side == SIDE_INVOICE else best.invoice_id
    )
    counterpart_ranked = opposite_index.get(str(counterpart_id), [])
    if _is_ambiguous(counterpart_ranked, config):
        return ExceptionCandidate(
            side=side,
            record_id=record_id,
            reason=REASON_AMBIGUOUS,
            candidates=_refs([best], side),
        )

    # Clear preference, uncontested counterpart -- the counterpart simply
    # preferred someone else by a decisive margin.
    return ExceptionCandidate(
        side=side,
        record_id=record_id,
        reason=REASON_CANDIDATE_CLAIMED,
        candidates=_refs([best], side),
    )


def run_matching(
    invoices: Sequence[InvoiceRecord],
    payments: Sequence[PaymentRecord],
    config: MatchConfig = DEFAULT_CONFIG,
) -> MatchingResult:
    """Score, commit mutual-best pairs, and explain everything left over.

    A pair (I, P) commits only when all four conditions hold:

    1. P is I's top-scoring candidate;
    2. I is P's top-scoring candidate;
    3. that confidence is at least ``needs_review_threshold``;
    4. no other candidate on *either* side sits within ``ambiguity_margin`` of
       the top score.

    Mutual-best is a bijection, so no payment can be claimed twice. The run does
    not mutate its inputs and never depends on dict or set iteration order, so
    two runs over the same input produce identical output.
    """
    candidates = generate_candidates(invoices, payments, config)
    by_invoice = _index_candidates(candidates, "invoice_id", "payment_id")
    by_payment = _index_candidates(candidates, "payment_id", "invoice_id")

    ordered_invoices = sorted(invoices, key=lambda record: str(record.id))
    ordered_payments = sorted(payments, key=lambda record: str(record.id))

    matches = []  # type: List[ScoredMatch]
    matched_invoices = set()
    matched_payments = set()

    for invoice in ordered_invoices:
        invoice_id = str(invoice.id)
        invoice_ranked = by_invoice.get(invoice_id, [])
        if not invoice_ranked:
            continue

        best = invoice_ranked[0]
        payment_ranked = by_payment.get(str(best.payment_id), [])
        if not payment_ranked or str(payment_ranked[0].invoice_id) != invoice_id:
            continue  # not mutual-best
        if best.confidence < config.needs_review_threshold:
            continue
        if _is_ambiguous(invoice_ranked, config) or _is_ambiguous(
            payment_ranked, config
        ):
            continue

        matches.append(best)
        matched_invoices.add(invoice_id)
        matched_payments.add(str(best.payment_id))

    exceptions = []  # type: List[ExceptionCandidate]
    for invoice in ordered_invoices:
        invoice_id = str(invoice.id)
        if invoice_id in matched_invoices:
            continue
        exceptions.append(
            _classify(
                SIDE_INVOICE,
                invoice_id,
                by_invoice.get(invoice_id, []),
                by_payment,
                config,
            )
        )
    for payment in ordered_payments:
        payment_id = str(payment.id)
        if payment_id in matched_payments:
            continue
        exceptions.append(
            _classify(
                SIDE_PAYMENT,
                payment_id,
                by_payment.get(payment_id, []),
                by_invoice,
                config,
            )
        )

    matches.sort(key=lambda c: (str(c.invoice_id), str(c.payment_id)))
    return MatchingResult(matches=matches, exceptions=exceptions)


def match_pairs(result: MatchingResult) -> List[Tuple[str, str]]:
    """The committed pairs as ``(invoice_id, payment_id)`` tuples."""
    return [(str(m.invoice_id), str(m.payment_id)) for m in result.matches]
