import uuid
from typing import Any, Literal
from pydantic import BaseModel, Field
from backend.models.record import NormalizedRecord

ReasonCodeType = Literal[
    "AMOUNT_MISMATCH",
    "MISSING_IN_BANK",
    "MISSING_IN_RAZORPAY",
    "DUPLICATE_DETECTED",
    "DATE_MISMATCH",
    "UNIDENTIFIED",
]

MatchType = Literal["exact", "fuzzy", "llm"]


class MatchResult(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    batch_id: uuid.UUID
    bank_record: NormalizedRecord | None = None
    razorpay_record: NormalizedRecord | None = None
    ledger_record: NormalizedRecord | None = None
    bank_record_id: uuid.UUID | None = None
    razorpay_record_id: uuid.UUID | None = None
    ledger_record_id: uuid.UUID | None = None
    match_type: MatchType
    confidence: float
    notes: str | None = None


class ExceptionRecord(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    batch_id: uuid.UUID
    record_ids: list[uuid.UUID] = Field(default_factory=list)
    reason_code: ReasonCodeType
    description: str
    raw_records: dict[str, Any] = Field(default_factory=dict)


class LLMMatchDecision(BaseModel):
    matched: bool
    confidence: float
    reason: str
    match_type: str = "llm"
