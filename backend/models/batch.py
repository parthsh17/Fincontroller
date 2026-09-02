import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field
from backend.models.match import MatchResult, ExceptionRecord


class BatchJob(BaseModel):
    id: uuid.UUID
    status: str
    total_records: int = 0
    matched_exact: int = 0
    matched_fuzzy: int = 0
    matched_llm: int = 0
    total_exceptions: int = 0
    match_rate: float | None = None
    false_match_rate: float | None = None
    llm_calls_made: int = 0
    avg_llm_latency_ms: float | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None


class BatchStatus(BaseModel):
    id: uuid.UUID
    status: str
    total_records: int = 0
    matched: int = 0
    exceptions: int = 0


class ExceptionBreakdown(BaseModel):
    reason_code: str
    count: int
    records: list[dict[str, Any]] = Field(default_factory=list)


class BatchReportSummary(BaseModel):
    total_records: int = 0
    matched_exact: int = 0
    matched_fuzzy: int = 0
    matched_llm: int = 0
    total_matched: int = 0
    total_exceptions: int = 0
    match_rate: float = 0.0
    exception_rate: float = 0.0
    llm_calls_made: int = 0
    avg_llm_latency_ms: float = 0.0
    duration_seconds: float = 0.0


class BatchReport(BaseModel):
    batch_id: uuid.UUID
    status: str
    summary: BatchReportSummary
    exception_breakdown: list[ExceptionBreakdown] = Field(default_factory=list)
    matches: list[MatchResult] = Field(default_factory=list)
    exceptions: list[ExceptionRecord] = Field(default_factory=list)
