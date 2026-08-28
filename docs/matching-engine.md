# The matching engine

This describes the scoring and decision logic in `backend/app/matching/`
(`types.py`, `scoring.py`, `config.py`, `engine.py`) — the part of the
reconciliation tool that decides, for every invoice and every bank
transaction, whether they represent the same real-world payment. It's
written for someone evaluating the project, not as an API reference; read
the module docstrings for exact call signatures.

The engine itself is deliberately boring in the best sense: no machine
learning, no external service calls, no hidden state. It's pure functions
over plain dataclasses (`InvoiceRecord`, `PaymentRecord` in `types.py`) —
score every pair, apply two hard gates, then commit only the pairs that are
unambiguously each other's best match. That predictability is the point: a
finance reviewer needs to trust *why* something matched, and a test suite
needs to assert on exact numbers rather than "close enough."

## The three sub-scores

Every invoice/payment pair gets three independent sub-scores, each on a
0–100 scale, computed in `scoring.py`:

| Sub-score | Weight | What it measures |
|---|---|---|
| Amount | 0.45 | How close the payment amount is to the invoice amount |
| Date | 0.30 | How close the payment date is to the invoice's due date (or invoice date, if no due date) |
| Reference | 0.25 | How strongly the payment's memo/counterparty text identifies the invoice |

**Amount** scores 100 for an exact match, decaying linearly to a floor of
25 at the edge of a tolerance band, and exactly 0 one cent past it. The
tolerance is `max($1.00 flat, 0.5% of the invoice amount)`, so small
invoices get a sane minimum cushion and large invoices get a proportional
one.

**Date** scores 100 for a same-day payment, decaying linearly to a floor of
10 at the edge of a 5-day window, and exactly 0 one day past it. The anchor
is the invoice's *due date* when one exists — payments are made relative to
when they're due, not when the invoice was raised.

**Reference** takes the better of two independent fuzzy-text signals,
computed with the `rapidfuzz` library (see `scoring.py` for the exact ratio
functions used):

- the invoice number matched fuzzily against every token in the payment's
  memo and counterparty fields — an *identifying* signal, worth up to 100;
- the invoice's vendor name and free-text description matched against the
  same payment fields — a *corroborating* signal, capped at 70, because
  many invoices share a vendor and vendor agreement alone shouldn't ever
  outscore an exact invoice-number hit.

Fuzzy ratios below 50 are treated as noise and floored to 0, so an
unrelated memo doesn't quietly drag a score up.

The three sub-scores combine into one **confidence**:

```
confidence = 0.45 × amount_score + 0.30 × date_score + 0.25 × reference_score
```

## Why there are hard gates, not just low scores

Amount and date aren't just weighted inputs — they're also **hard gates**.
A pair is never even scored, let alone considered a match candidate, unless
its amount is within tolerance *and* its date is within the window. This
matters for one specific failure mode: **partial and split payments**.

Consider an invoice for $1,000 paid with a single $500 transaction that has
an otherwise-perfect reference and same-day date. Without a hard gate, that
pair would score:

```
0.45 × 0 (amount, far outside tolerance) + 0.30 × 100 + 0.25 × 100 = 55.0
```

...which is close enough to the review threshold that a slightly more
generous reference match would push it over, and the engine would suggest
matching a $1,000 invoice to half its value. The amount gate makes this
impossible by construction: `score_amount` returns exactly 0 outside
tolerance, `generate_candidates` skips any pair scoring 0 on amount before
reference is even computed, and a pair that was never generated can't be
suggested, ambiguous, or anything else — it's simply absent, and the
invoice falls out as an exception with no candidates at all. The same logic
excludes a split payment (two $600 transactions against one $1,200
invoice): neither transaction alone is within tolerance, so neither ever
becomes a candidate.

This is also why the amount tolerance's floor score (25, `AMOUNT_BOUNDARY_SCORE`
in `config.py`) is set higher than the date tolerance's floor (10): amount
carries the largest weight and is the gate protecting against split
payments, so a pair sitting *exactly* on the amount boundary with a perfect
date and reference must still clear the 60-point review threshold —
`0.45 × 25 + 0.30 × 100 + 0.25 × 100 = 66.25`. A lower floor would
contradict the rule that the tolerance boundary itself still counts as a
(weak) agreement.

## Committing a match: mutual-best with a margin

Passing both gates and scoring well isn't enough to auto-commit a pair.
`engine.py` requires all four of these to hold:

1. The payment is this invoice's top-scoring candidate.
2. The invoice is this payment's top-scoring candidate (mutual best —
   this is what makes the matching a bijection: no payment is ever claimed
   by two invoices).
3. That confidence is at least the **needs-review threshold** (60).
4. No other candidate on *either* side sits within the **ambiguity margin**
   (2.0 points) of the top score.

A match at or above the **auto-suggest threshold** (85) is presented to a
reviewer as a high-confidence suggestion; one between 60 and 85 is
presented as needing closer review. Both are still just "suggested" until a
human accepts them — the engine never writes an accepted match on its own.

Everything that doesn't commit becomes an exception, classified by
`_classify()` in severity order:

- **`no_candidate`** — no payment/invoice cleared the hard gates against
  this record at all. Usually a genuine orphan (never paid, or a refund/fee
  with nothing to reconcile against) — or, per the split-payment gate
  above, a payment/invoice pair that looks related to a human but was never
  a numerically valid full payment.
- **`below_threshold`** — there's a best candidate, but its confidence is
  under 60. Typically a coincidental amount+date overlap with no
  corroborating reference text at all.
- **`ambiguous_multiple_candidates`** — this record's own top choices are
  tied within the ambiguity margin, *or* its clear top choice is itself
  being contested by another tied record on the other side. The engine
  would rather ask a human than guess between two equally-good options.
- **`candidate_claimed_elsewhere`** — this record has one clear,
  uncontested preference, but that preference belongs to someone else by a
  decisive margin.

Every exception *except* `no_candidate` carries a ranked candidate list (the
full list, not just the leader) — including `below_threshold`, which is why
the exceptions queue offers a candidate picker for all three of them rather
than dismiss-only. The second-best option is often the right one, and a
reviewer resolving an exception by hand needs to see it.

## Worked examples

These are drawn from the actual synthetic corpus at
`backend/data/synthetic/` (`invoices.csv`, `bank_statement.csv`), seeded
deterministically — the numbers below are what `run_matching` really
produces, not invented illustrations, unless noted otherwise.

**1. Clean match.** Invoice `INV-1001` ($1,250.00, due 2026-02-04) against a
payment of $1,250.00 posted 2026-02-04 with memo `"INV-1001 ACME ROBOTICS
INC"`. Amount score 100, date score 100, reference score 100 (exact
invoice-number hit) → confidence **100.0**. Comfortably above the
auto-suggest threshold; committed as a match.

**2. The amount-tolerance boundary decides a contested pair.**
`INV-1101` and `INV-1102` are both Blue Harbor Supplies invoices for
exactly $80.00, both due 2026-02-09 — a same-vendor, same-amount, same-date
collision. One payment of $79.00 posts on 2026-02-09 with memo `"INV-1101
Blue Harbor Supplies"`. The $1.00 shortfall sits *exactly* on the flat
tolerance boundary, so amount scores 25 (not 0) for both invoices; date
scores 100 for both. Reference is where they diverge: the memo names
`INV-1101` outright (reference score 100), while `INV-1102`'s identifier
only fuzzy-matches the same memo text via a one-digit transposition
(`inv1102` vs. `inv1101`, a `rapidfuzz` ratio of 85.71 rather than a clean
0 or 100 — this is what "fuzzy" buys over exact string equality). That
gives:

```
INV-1101: 0.45×25 + 0.30×100 + 0.25×100  = 66.25
INV-1102: 0.45×25 + 0.30×100 + 0.25×85.71 = 62.68
```

`INV-1101` wins the payment as its mutual-best match (confidence 66.25,
just above the 60 review threshold — this is the exact boundary case
`AMOUNT_BOUNDARY_SCORE` is tuned around, see above). `INV-1102` had a
plausible-looking second-best claim on the same payment, but the gap
(66.25 − 62.68 = 3.57) is wider than the 2.0-point ambiguity margin, so it
is not treated as a tie — `INV-1102` becomes a `candidate_claimed_elsewhere`
exception, with its one candidate (this payment, at 62.68) listed for a
reviewer to see and dismiss.

**3. A genuine tie.** `INV-1701` and `INV-1702` are two invoices for
Lighthouse Media Group, both $860.00, both due 2026-02-21 (two phases of
the same ad campaign). A single $860.00 payment posts on 2026-02-21 with
memo `"Lighthouse Media Group payment"` — no invoice number at all, just
the vendor name. Both invoices score identically: amount 100, date 100,
reference 70 (the vendor-name signal, capped below an invoice-number hit —
there's no invoice number in the memo to fuzzy-match either identifier
against, so both fall back to the same capped vendor score) → confidence
**92.5** for both. Neither invoice can be preferred over the other, so
committing either would be a guess. The payment and both invoices all
surface as `ambiguous_multiple_candidates` exceptions, each listing the
other side's tied candidates by score — this is exactly the case the
mutual-best-with-margin rule exists to catch instead of silently picking
one.

**4. Why the hard gate matters.** `INV-1801` ($1,000.00, due 2026-02-24,
Meridian Steel Works) has a payment for $500.00 on the same due date with
memo `"INV-1801 partial payment"` — reference and date would both score
perfectly. But the tolerance for a $1,000 invoice is `max($1.00, 0.5% ×
$1,000) = $5.00`, and the $500 shortfall is a hundred times that. The
amount gate rejects the pair before reference is ever computed, so it never
becomes a candidate for anything — `INV-1801` surfaces as a `no_candidate`
exception (assuming no other invoice or payment happens to also clear its
gates), not a low-confidence match. This is the mechanism described above
that keeps a partial payment from ever masquerading as a full one.

*(`below_threshold` doesn't happen to occur in the shipped 61-record
synthetic corpus, so it isn't illustrated with real data above — see the
description in the previous section. It's exercised directly by unit tests
in `backend/tests/matching/`, including `test_scenarios.py`, which is the
project's own regression corpus described in the root `README.md`.)*
