"""Deterministic sub-scores for an invoice/payment pair.

Every score is a float in [0.0, 100.0]. A score of exactly 0.0 on amount or
date means "outside tolerance" and is what the engine's hard gates test for, so
those boundaries are exact rather than approximate.
"""

import re
from datetime import date as date_type
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional

from rapidfuzz import fuzz

from app.matching.config import (
    AMOUNT_BOUNDARY_SCORE,
    DATE_BOUNDARY_SCORE,
    DEFAULT_CONFIG,
    MatchConfig,
)
from app.matching.types import InvoiceRecord, PaymentRecord, ScoredMatch

_CENT = Decimal("0.01")

# A vendor name or free-text description agreeing is corroborating evidence, not
# identifying evidence: many invoices share one vendor. Capping that signal
# below a perfect score keeps an exact invoice-number hit strictly stronger than
# an exact vendor-name hit, which is what lets the engine separate two invoices
# from the same vendor for the same amount on the same day.
VENDOR_SIGNAL_CEILING = 70.0

# Fuzzy ratios below this are treated as noise (no shared identity) rather than
# as weak evidence, so an unrelated memo scores 0 instead of a misleading 30.
REFERENCE_NOISE_FLOOR = 50.0

_NON_ALNUM = re.compile(r"[^0-9a-z]+")
_SPLIT = re.compile(r"\s+")


def amount_tolerance(invoice_amount: Decimal, config: MatchConfig) -> Decimal:
    """The absolute amount difference tolerated for this invoice.

    ``max(absolute_tolerance, percentage_tolerance * invoice_amount)``, with the
    percentage portion rounded to cents so the boundary is exactly representable
    in currency terms.
    """
    percentage_component = (
        abs(invoice_amount) * Decimal(str(config.percentage_tolerance))
    ).quantize(_CENT, rounding=ROUND_HALF_UP)
    return max(config.absolute_tolerance, percentage_component)


def score_amount(
    invoice_amount: Decimal,
    payment_amount: Decimal,
    config: MatchConfig = DEFAULT_CONFIG,
) -> float:
    """100.0 for an exact amount, decaying linearly across the tolerance band.

    The band is inclusive: a difference exactly equal to the tolerance scores
    ``AMOUNT_BOUNDARY_SCORE``; anything beyond it scores exactly 0.0.
    """
    difference = abs(Decimal(invoice_amount) - Decimal(payment_amount))
    if difference == 0:
        return 100.0

    tolerance = amount_tolerance(Decimal(invoice_amount), config)
    if tolerance <= 0 or difference > tolerance:
        return 0.0

    span = float(difference / tolerance)
    return round(100.0 - (100.0 - AMOUNT_BOUNDARY_SCORE) * span, 4)


def score_date(
    invoice_date: date_type,
    payment_date: date_type,
    config: MatchConfig = DEFAULT_CONFIG,
) -> float:
    """100.0 for a same-day payment, decaying linearly across the date window.

    ``invoice_date`` is the anchor date -- for a full ``InvoiceRecord`` that is
    ``InvoiceRecord.date_anchor`` (the due date when present, else the invoice
    date). The window is inclusive: a delta exactly equal to
    ``date_window_days`` scores ``DATE_BOUNDARY_SCORE``; one day further scores
    exactly 0.0.
    """
    delta_days = abs((payment_date - invoice_date).days)
    if delta_days == 0:
        return 100.0

    window = config.date_window_days
    if window <= 0 or delta_days > window:
        return 0.0

    span = delta_days / float(window)
    return round(100.0 - (100.0 - DATE_BOUNDARY_SCORE) * span, 4)


def _normalize(text: Optional[str]) -> str:
    """Lowercase and strip everything that is not a letter or a digit."""
    if not text:
        return ""
    return _NON_ALNUM.sub(" ", text.lower()).strip()


def _identifier(text: Optional[str]) -> str:
    """Collapse an identifier to comparable form: 'INV-1421' -> 'inv1421'."""
    if not text:
        return ""
    return _NON_ALNUM.sub("", text.lower())


def _identifier_tokens(text: Optional[str]) -> List[str]:
    """Whitespace-split ``text`` and collapse each token to identifier form."""
    if not text:
        return []
    tokens = (_identifier(token) for token in _SPLIT.split(text.strip()))
    return [token for token in tokens if token]


def _denoise(value: float) -> float:
    return value if value >= REFERENCE_NOISE_FLOOR else 0.0


def _invoice_number_signal(invoice_number: Optional[str], texts: List[str]) -> float:
    """Best fuzzy agreement between the invoice number and any single token.

    Comparing token-by-token rather than against the whole memo keeps a long
    memo from diluting an exact invoice-number hit, and keeps a short memo from
    scoring highly just because it happens to be short.
    """
    needle = _identifier(invoice_number)
    if not needle:
        return 0.0

    best = 0.0
    for text in texts:
        for token in _identifier_tokens(text):
            best = max(best, fuzz.ratio(needle, token))
    return _denoise(best)


def _free_text_signal(invoice_texts: List[str], payment_texts: List[str]) -> float:
    """Best token-order-insensitive agreement between free-text fields."""
    best = 0.0
    for invoice_text in invoice_texts:
        left = _normalize(invoice_text)
        if not left:
            continue
        for payment_text in payment_texts:
            right = _normalize(payment_text)
            if not right:
                continue
            best = max(best, fuzz.token_sort_ratio(left, right))
    return min(_denoise(best), VENDOR_SIGNAL_CEILING)


def score_reference(invoice: InvoiceRecord, payment: PaymentRecord) -> float:
    """How strongly the payment's text identifies this invoice.

    Two independent signals are considered and the stronger one wins:

    * the invoice number against each token of the payment's reference and
      counterparty -- an identifying signal, worth up to 100.0;
    * the invoice's vendor name and raw reference text against the payment's
      reference and counterparty -- a corroborating signal, capped at
      ``VENDOR_SIGNAL_CEILING``.

    Returns 0.0 when either side carries no comparable text.
    """
    payment_texts = [text for text in (payment.reference, payment.counterparty) if text]
    if not payment_texts:
        return 0.0

    invoice_texts = [
        text for text in (invoice.vendor_name, invoice.raw_reference_text) if text
    ]
    if not invoice.invoice_number and not invoice_texts:
        return 0.0

    number_signal = _invoice_number_signal(invoice.invoice_number, payment_texts)
    text_signal = _free_text_signal(invoice_texts, payment_texts)
    return round(max(number_signal, text_signal), 4)


def score_pair(
    invoice: InvoiceRecord,
    payment: PaymentRecord,
    config: MatchConfig = DEFAULT_CONFIG,
) -> ScoredMatch:
    """Score one pair on all three axes and combine them into a confidence."""
    amount_score = score_amount(invoice.amount, payment.amount, config)
    date_score = score_date(invoice.date_anchor, payment.date, config)
    reference_score = score_reference(invoice, payment)

    confidence = (
        config.weight_amount * amount_score
        + config.weight_date * date_score
        + config.weight_reference * reference_score
    )

    return ScoredMatch(
        invoice_id=invoice.id,
        payment_id=payment.id,
        amount_score=amount_score,
        date_score=date_score,
        reference_score=reference_score,
        confidence=round(confidence, 4),
    )
