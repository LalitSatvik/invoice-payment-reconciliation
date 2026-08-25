"""Tunable matching parameters."""

from dataclasses import dataclass
from decimal import Decimal

# Sub-score value awarded at the outer edge of each tolerance band.
#
# Both bands are inclusive: a difference exactly equal to the tolerance still
# counts as a (weak) agreement, and anything past it scores exactly 0.0 so the
# engine's hard gates can key off "score > 0". That means the linear decay must
# land on a small positive floor at the boundary rather than on zero.
#
# The amount floor is the higher of the two on purpose. Amount carries the
# largest weight and is the gate that keeps split/partial payments out, so a
# pair sitting exactly on the amount boundary but agreeing perfectly on date
# and reference must still clear ``needs_review_threshold``:
#     0.45 * 25.0 + 0.30 * 100 + 0.25 * 100 = 66.25  >= 60.0
# With a floor of 10.0 that same pair would score 59.5 and be rejected, which
# would contradict the inclusive-boundary rule the tolerances are defined by.
AMOUNT_BOUNDARY_SCORE = 25.0
DATE_BOUNDARY_SCORE = 10.0


@dataclass(frozen=True)
class MatchConfig:
    """Thresholds and weights that drive scoring and match commitment."""

    absolute_tolerance: Decimal = Decimal("1.00")
    percentage_tolerance: float = 0.005
    date_window_days: int = 5
    weight_amount: float = 0.45
    weight_date: float = 0.30
    weight_reference: float = 0.25
    auto_suggest_threshold: float = 85.0
    needs_review_threshold: float = 60.0
    ambiguity_margin: float = 2.0

    def __post_init__(self) -> None:
        total = self.weight_amount + self.weight_date + self.weight_reference
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                "MatchConfig weights must sum to 1.0, got "
                "{0!r} (amount={1!r}, date={2!r}, reference={3!r})".format(
                    total,
                    self.weight_amount,
                    self.weight_date,
                    self.weight_reference,
                )
            )


DEFAULT_CONFIG = MatchConfig()
