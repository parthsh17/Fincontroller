import argparse
import csv
import json
import os
import random
import sys
from datetime import date, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from data.generators.noise import inject_noise


def generate_data(seed: int = 42, count: int = 100):
    random.seed(seed)

    base_records = []
    start_date = date(2026, 10, 1)
    descriptions = [
        "Coffee subscription",
        "BrewBox Premium",
        "BrewBox Starter",
        "BrewBox Connoisseur",
        "Refund",
    ]
    customers = [
        "Aditya Sharma",
        "Priya Patel",
        "Rohan Gupta",
        "Ananya Iyer",
        "Vikram Singh",
        "Sneha Reddy",
        "Karan Verma",
        "Pooja Nair",
        "Rahul Joshi",
        "Meera Menon",
    ]

    for i in range(count):
        amt_int = random.randint(499, 14999)
        amount = Decimal(str(amt_int))
        dt = start_date + timedelta(days=random.randint(0, 30))
        ref_id = f"REF{random.randint(100000, 999999)}"
        desc = random.choice(descriptions)
        cust = random.choice(customers)

        base_records.append({
            "amount": amount,
            "date": dt,
            "ref_id": ref_id,
            "description": desc,
            "customer_name": cust,
        })

    noisy_batch = inject_noise(base_records, seed=seed)

    os.makedirs("data/samples", exist_ok=True)
    os.makedirs("data/testset", exist_ok=True)

    bank_path = "data/samples/bank_statement.csv"
    with open(bank_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["date", "amount", "ref_id", "description"]
        )
        writer.writeheader()
        writer.writerows(noisy_batch.bank_rows)

    rp_path = "data/samples/settlement_report.csv"
    with open(rp_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "date",
                "amount",
                "settlement_id",
                "payment_id",
                "description",
            ],
        )
        writer.writeheader()
        writer.writerows(noisy_batch.razorpay_rows)

    ledger_path = "data/samples/internal_ledger.csv"
    with open(ledger_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["date", "amount", "order_id", "customer_name", "status"],
        )
        writer.writeheader()
        writer.writerows(noisy_batch.ledger_rows)

    held_out_path = "data/testset/held_out.json"
    with open(held_out_path, "w", encoding="utf-8") as f:
        json.dump(noisy_batch.ground_truth[:20], f, indent=2)

    print(f"=== Synthetic Data Generated (Seed: {seed}, Count: {count}) ===")
    print(f"Bank Statement rows:     {len(noisy_batch.bank_rows)}")
    print(f"Settlement Report rows:  {len(noisy_batch.razorpay_rows)}")
    print(f"Internal Ledger rows:    {len(noisy_batch.ledger_rows)}")
    print(f"Held-out Testset items:  {len(noisy_batch.ground_truth[:20])}")
    print(f"CSVs saved to data/samples/ and held_out to {held_out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate synthetic reconciliation data"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for reproducibility"
    )
    parser.add_argument(
        "--count", type=int, default=100, help="Base records count"
    )
    args = parser.parse_args()
    generate_data(seed=args.seed, count=args.count)
