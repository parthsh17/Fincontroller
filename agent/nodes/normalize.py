import uuid
from typing import Any
from loguru import logger
from pydantic import ValidationError
from backend.models.record import NormalizedRecord


def normalize_record(
    raw_row: dict[str, Any], source: str, batch_id: uuid.UUID
) -> NormalizedRecord | None:
    row_lower = {str(k).lower().strip(): v for k, v in raw_row.items()}

    date_val = None
    amount_val = None
    ref_id_val = None
    desc_val = None

    if source == "bank":
        date_val = row_lower.get("date")
        amount_val = row_lower.get("amount")
        ref_id_val = row_lower.get("ref_id")
        desc_val = row_lower.get("description")
    elif source == "razorpay":
        date_val = row_lower.get("date")
        amount_val = row_lower.get("amount")
        ref_id_val = row_lower.get("settlement_id") or row_lower.get("payment_id")
        desc_val = row_lower.get("description")
    elif source == "ledger":
        date_val = row_lower.get("date")
        amount_val = row_lower.get("amount")
        ref_id_val = row_lower.get("order_id")
        desc_val = row_lower.get("customer_name") or row_lower.get("description")
    else:
        logger.warning(f"Unknown source: {source}")
        return None

    try:
        norm = NormalizedRecord(
            batch_id=batch_id,
            source=source,
            amount=amount_val,
            date=date_val,
            ref_id=ref_id_val,
            description=desc_val,
            raw=raw_row,
        )
        return norm
    except (ValidationError, ValueError, Exception) as e:
        logger.warning(
            f"Failed to normalize row from {source} (batch {batch_id}): {e} | Row: {raw_row}"
        )
        return None
