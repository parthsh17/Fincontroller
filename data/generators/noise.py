import random
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal


@dataclass
class NoisyBatch:
    bank_rows: list[dict] = field(default_factory=list)
    razorpay_rows: list[dict] = field(default_factory=list)
    ledger_rows: list[dict] = field(default_factory=list)
    ground_truth: list[dict] = field(default_factory=list)


def inject_noise(base_records: list[dict], seed: int = 42) -> NoisyBatch:
    random.seed(seed)

    bank_rows: list[dict] = []
    razorpay_rows: list[dict] = []
    ledger_rows: list[dict] = []
    ground_truth: list[dict] = []

    for i, rec in enumerate(base_records):
        amount = rec["amount"]
        dt = rec["date"]
        ref_id = rec["ref_id"]
        desc = rec["description"]
        customer_name = rec.get("customer_name", "Customer")

        # Roll category based on target percentages:
        # 60% EXACT (0..59)
        # 15% SETTLEMENT_LAG (60..74)
        # 10% AMOUNT_MISMATCH (75..84)
        # 8% MISSING_IN_BANK (85..92)
        # 5% DUPLICATE_DETECTED (93..97)
        # 2% UNIDENTIFIED (98..99)
        roll = random.randint(0, 99)

        if roll < 60:
            # Rule 1: EXACT
            bank_rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "amount": f"{amount:.2f}",
                "ref_id": ref_id,
                "description": desc,
            })
            razorpay_rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "amount": f"{amount:.2f}",
                "settlement_id": ref_id,
                "payment_id": f"pay_{ref_id}",
                "description": desc,
            })
            ledger_rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "amount": f"{amount:.2f}",
                "order_id": ref_id,
                "customer_name": customer_name,
                "status": "COMPLETED",
            })
            ground_truth.append({
                "record_ref": ref_id,
                "expected": "match",
                "reason": "EXACT",
            })

        elif roll < 75:
            # Rule 2: SETTLEMENT_LAG (T+1)
            rp_date = dt + timedelta(days=1)
            bank_rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "amount": f"{amount:.2f}",
                "ref_id": ref_id,
                "description": desc,
            })
            razorpay_rows.append({
                "date": rp_date.strftime("%Y-%m-%d"),
                "amount": f"{amount:.2f}",
                "settlement_id": ref_id,
                "payment_id": f"pay_{ref_id}",
                "description": desc,
            })
            ledger_rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "amount": f"{amount:.2f}",
                "order_id": ref_id,
                "customer_name": customer_name,
                "status": "COMPLETED",
            })
            ground_truth.append({
                "record_ref": ref_id,
                "expected": "match",
                "reason": "SETTLEMENT_LAG",
            })

        elif roll < 85:
            # Rule 3: AMOUNT_MISMATCH
            fee = Decimal(str(round(random.uniform(50, 200), 2)))
            bank_amount = amount - fee
            bank_rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "amount": f"{bank_amount:.2f}",
                "ref_id": ref_id,
                "description": desc,
            })
            razorpay_rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "amount": f"{amount:.2f}",
                "settlement_id": ref_id,
                "payment_id": f"pay_{ref_id}",
                "description": desc,
            })
            ledger_rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "amount": f"{amount:.2f}",
                "order_id": ref_id,
                "customer_name": customer_name,
                "status": "COMPLETED",
            })
            ground_truth.append({
                "record_ref": ref_id,
                "expected": "exception",
                "reason": "AMOUNT_MISMATCH",
            })

        elif roll < 93:
            # Rule 4: MISSING_IN_BANK
            # Exists in razorpay + ledger, NOT in bank
            razorpay_rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "amount": f"{amount:.2f}",
                "settlement_id": ref_id,
                "payment_id": f"pay_{ref_id}",
                "description": desc,
            })
            ledger_rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "amount": f"{amount:.2f}",
                "order_id": ref_id,
                "customer_name": customer_name,
                "status": "COMPLETED",
            })
            ground_truth.append({
                "record_ref": ref_id,
                "expected": "exception",
                "reason": "MISSING_IN_BANK",
            })

        elif roll < 98:
            # Rule 5: DUPLICATE_DETECTED
            bank_rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "amount": f"{amount:.2f}",
                "ref_id": ref_id,
                "description": desc,
            })
            razorpay_rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "amount": f"{amount:.2f}",
                "settlement_id": ref_id,
                "payment_id": f"pay_{ref_id}",
                "description": desc,
            })
            # Add ledger row twice
            ledger_rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "amount": f"{amount:.2f}",
                "order_id": ref_id,
                "customer_name": customer_name,
                "status": "COMPLETED",
            })
            ledger_rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "amount": f"{amount:.2f}",
                "order_id": ref_id,
                "customer_name": f"{customer_name} (Dup)",
                "status": "COMPLETED",
            })
            ground_truth.append({
                "record_ref": ref_id,
                "expected": "exception",
                "reason": "DUPLICATE_DETECTED",
            })

        else:
            # Rule 6: UNIDENTIFIED
            rand_ref_b = f"REF{random.randint(100000, 999999)}"
            rand_ref_r = f"REF{random.randint(100000, 999999)}"
            rand_ref_l = f"REF{random.randint(100000, 999999)}"
            bank_rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "amount": f"{amount:.2f}",
                "ref_id": rand_ref_b,
                "description": "Unknown Pos Debit",
            })
            razorpay_rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "amount": f"{(amount + Decimal('13.50')):.2f}",
                "settlement_id": rand_ref_r,
                "payment_id": f"pay_{rand_ref_r}",
                "description": "Adjustment Misc",
            })
            ledger_rows.append({
                "date": (dt + timedelta(days=7)).strftime("%Y-%m-%d"),
                "amount": f"{(amount - Decimal('50.00')):.2f}",
                "order_id": rand_ref_l,
                "customer_name": "Anonymous User",
                "status": "UNKNOWN",
            })
            ground_truth.append({
                "record_ref": ref_id,
                "expected": "exception",
                "reason": "UNIDENTIFIED",
            })

    # Shuffle rows to avoid natural ordering matching
    random.shuffle(bank_rows)
    random.shuffle(razorpay_rows)
    random.shuffle(ledger_rows)

    return NoisyBatch(
        bank_rows=bank_rows,
        razorpay_rows=razorpay_rows,
        ledger_rows=ledger_rows,
        ground_truth=ground_truth,
    )
