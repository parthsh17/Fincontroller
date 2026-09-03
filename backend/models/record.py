import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator


class RawRecord(BaseModel):
    source: Literal["bank", "razorpay", "ledger"]
    raw_row: dict[str, Any]


class NormalizedRecord(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    batch_id: uuid.UUID
    source: Literal["bank", "razorpay", "ledger"]
    amount: Decimal
    date: date
    ref_id: str | None = None
    description: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("amount", mode="before")
    @classmethod
    def clean_amount(cls, v: Any) -> Decimal:
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float)):
            return Decimal(str(round(v, 2)))
        if isinstance(v, str):
            clean_str = v.replace("₹", "").replace(",", "").strip()
            return Decimal(clean_str)
        raise ValueError(f"Invalid amount value: {v}")

    @field_validator("date", mode="before")
    @classmethod
    def parse_date(cls, v: Any) -> date:
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            v_str = v.strip()
            for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
                try:
                    return datetime.strptime(v_str, fmt).date()
                except ValueError:
                    continue
            try:
                return datetime.fromisoformat(v_str).date()
            except Exception:
                pass
        raise ValueError(f"Invalid date format: {v}")

    @field_validator("ref_id", mode="before")
    @classmethod
    def clean_ref_id(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s and s.lower() != "nan" else None

    @field_validator("description", mode="before")
    @classmethod
    def clean_description(cls, v: Any) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s and s.lower() != "nan" else None
