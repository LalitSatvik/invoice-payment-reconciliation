"""Write the synthetic invoice CSV from the canonical scenario dataset.

Standalone usage::

    python -m app.synthetic.generate_invoices [--seed N] [--out-dir DIR]

writes only ``invoices.csv``. For the full three-file generation (invoices +
bank statement + ground_truth.json) in one deterministic pass, run
``python -m app.synthetic.scenarios`` instead.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import List

from app.synthetic.scenarios import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_SEED,
    INVOICE_CSV_FILENAME,
    InvoiceRow,
    build_dataset,
)

# Canonical invoice CSV headers, per the Task 3 brief.
INVOICE_CSV_HEADER = [
    "invoice_number",
    "vendor_name",
    "invoice_date",
    "due_date",
    "amount",
    "description",
]


def write_invoice_csv(invoices: List[InvoiceRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(INVOICE_CSV_HEADER)
        for inv in invoices:
            writer.writerow(
                [
                    inv.invoice_number,
                    inv.vendor_name,
                    inv.invoice_date.isoformat(),
                    inv.due_date.isoformat(),
                    format(inv.amount, ".2f"),
                    inv.description,
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic invoice CSV.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    dataset = build_dataset(args.seed)
    out_path = args.out_dir / INVOICE_CSV_FILENAME
    write_invoice_csv(dataset.invoices, out_path)
    print(f"Wrote {len(dataset.invoices)} invoice rows to {out_path}")


if __name__ == "__main__":
    main()
