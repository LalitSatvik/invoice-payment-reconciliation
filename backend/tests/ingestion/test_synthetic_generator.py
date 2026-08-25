"""Tests for the synthetic invoice/payment/ground-truth generator (Task 3)."""
import json

from app.synthetic.generate_invoices import write_invoice_csv
from app.synthetic.generate_payments import write_payment_csv
from app.synthetic.scenarios import (
    DEFAULT_SEED,
    SCENARIO_TYPES_REQUIRED,
    build_dataset,
    write_ground_truth,
)


def test_every_required_scenario_type_is_present():
    dataset = build_dataset(DEFAULT_SEED)
    present_types = {s.scenario_type for s in dataset.scenarios}
    missing = set(SCENARIO_TYPES_REQUIRED) - present_types
    assert not missing, f"missing required scenario types: {missing}"


def test_build_dataset_is_deterministic_for_the_same_seed():
    a = build_dataset(DEFAULT_SEED)
    b = build_dataset(DEFAULT_SEED)
    assert a.invoices == b.invoices
    assert a.payments == b.payments
    assert a.scenarios == b.scenarios


def test_different_seeds_change_the_filler_rows():
    a = build_dataset(1)
    b = build_dataset(2)
    # The core (hand-authored) scenarios never vary; only filler rows do.
    assert a.invoices[:18] == b.invoices[:18]
    assert a.invoices != b.invoices


def test_invoice_numbers_are_unique_and_each_is_referenced_by_exactly_one_scenario():
    dataset = build_dataset(DEFAULT_SEED)
    invoice_numbers = [inv.invoice_number for inv in dataset.invoices]
    assert len(invoice_numbers) == len(set(invoice_numbers))

    referenced = [num for s in dataset.scenarios for num in s.invoice_numbers]
    assert sorted(referenced) == sorted(invoice_numbers)
    assert len(referenced) == len(set(referenced))


def test_every_payment_row_is_referenced_by_exactly_one_scenario():
    dataset = build_dataset(DEFAULT_SEED)
    referenced = [idx for s in dataset.scenarios for idx in s.payment_row_indices]
    assert sorted(referenced) == list(range(len(dataset.payments)))
    assert len(referenced) == len(set(referenced))


def test_generated_files_are_byte_identical_across_runs_with_the_same_seed(tmp_path):
    outputs = {}
    for label in ("run_a", "run_b"):
        out_dir = tmp_path / label
        dataset = build_dataset(DEFAULT_SEED)
        write_invoice_csv(dataset.invoices, out_dir / "invoices.csv")
        write_payment_csv(dataset.payments, out_dir / "bank_statement.csv")
        write_ground_truth(dataset, out_dir / "ground_truth.json")
        outputs[label] = out_dir

    for name in ("invoices.csv", "bank_statement.csv", "ground_truth.json"):
        content_a = (outputs["run_a"] / name).read_bytes()
        content_b = (outputs["run_b"] / name).read_bytes()
        assert content_a == content_b, f"{name} differed across identical-seed runs"


def test_ground_truth_json_is_valid_and_matches_row_counts(tmp_path):
    dataset = build_dataset(DEFAULT_SEED)
    gt_path = tmp_path / "ground_truth.json"
    write_ground_truth(dataset, gt_path)

    payload = json.loads(gt_path.read_text(encoding="utf-8"))
    assert payload["counts"]["invoice_count"] == len(dataset.invoices)
    assert payload["counts"]["payment_count"] == len(dataset.payments)
    assert payload["counts"]["scenario_count"] == len(dataset.scenarios)

    present_types = {s["scenario_type"] for s in payload["scenarios"]}
    assert set(payload["scenario_types_required"]).issubset(present_types)

    # Reverse indices resolve to real scenario ids.
    scenario_ids = {s["scenario_id"] for s in payload["scenarios"]}
    for scenario_id in payload["index"]["by_invoice_number"].values():
        assert scenario_id in scenario_ids
    for scenario_id in payload["index"]["by_payment_row_index"].values():
        assert scenario_id in scenario_ids


def test_invoice_csv_row_count_matches_dataset(tmp_path):
    dataset = build_dataset(DEFAULT_SEED)
    csv_path = tmp_path / "invoices.csv"
    write_invoice_csv(dataset.invoices, csv_path)

    lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "invoice_number,vendor_name,invoice_date,due_date,amount,description"
    assert len(lines) - 1 == len(dataset.invoices)


def test_payment_csv_row_count_matches_dataset(tmp_path):
    dataset = build_dataset(DEFAULT_SEED)
    csv_path = tmp_path / "bank_statement.csv"
    write_payment_csv(dataset.payments, csv_path)

    lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "Post Date,Trans Amt,Memo,Other Party"
    assert len(lines) - 1 == len(dataset.payments)
