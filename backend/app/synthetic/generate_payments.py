"""Write the synthetic bank statement CSV from the canonical scenario dataset.

Standalone usage::

    python -m app.synthetic.generate_payments [--seed N] [--out-dir DIR]

writes only ``bank_statement.csv``. For the full three-file generation
(invoices + bank statement + ground_truth.json) in one deterministic pass,
run ``python -m app.synthetic.scenarios`` instead.

The header names below are deliberately *non-canonical* (they don't match
``payment_date`` / ``amount`` / ``reference`` / ``counterparty``, nor the
invoice CSV's headers): real bank statement exports use all sorts of
column-naming conventions, which is exactly why Task 9's column-mapping UI
exists. A test asserting against these exact header strings would be testing
an implementation detail of this generator, not a requirement -- treat the
header names as illustrative, not contractual.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import List

from app.synthetic.scenarios import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SEED,
    PAYMENT_CSV_FILENAME,
    PaymentRow,
    build_dataset,
)

# Deliberately non-canonical bank statement headers -- see module docstring.
PAYMENT_CSV_HEADER = ["Post Date", "Trans Amt", "Memo", "Other Party"]


def write_payment_csv(payments: List[PaymentRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(PAYMENT_CSV_HEADER)
        for pmt in payments:
            writer.writerow(
                [
                    pmt.payment_date.isoformat(),
                    format(pmt.amount, ".2f"),
                    pmt.memo,
                    pmt.counterparty,
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic bank statement CSV.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    dataset = build_dataset(args.seed)
    out_path = args.out_dir / PAYMENT_CSV_FILENAME
    write_payment_csv(dataset.payments, out_path)
    print(f"Wrote {len(dataset.payments)} payment rows to {out_path}")


if __name__ == "__main__":
    main()
