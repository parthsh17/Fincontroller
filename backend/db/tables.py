import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Numeric,
    Date,
    DateTime,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Batch(Base):
    __tablename__ = "batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(String, default="pending", nullable=False)
    total_records = Column(Integer, default=0, nullable=False)
    matched_exact = Column(Integer, default=0, nullable=False)
    matched_fuzzy = Column(Integer, default=0, nullable=False)
    matched_llm = Column(Integer, default=0, nullable=False)
    total_exceptions = Column(Integer, default=0, nullable=False)
    match_rate = Column(Float, nullable=True)
    false_match_rate = Column(Float, nullable=True)
    llm_calls_made = Column(Integer, default=0, nullable=False)
    avg_llm_latency_ms = Column(Float, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    normalized_records = relationship(
        "NormalizedRecordDB",
        back_populates="batch",
        cascade="all, delete-orphan",
    )
    match_results = relationship(
        "MatchResultDB",
        back_populates="batch",
        cascade="all, delete-orphan",
    )
    exception_records = relationship(
        "ExceptionRecordDB",
        back_populates="batch",
        cascade="all, delete-orphan",
    )
    qa_logs = relationship(
        "QALogDB",
        back_populates="batch",
        cascade="all, delete-orphan",
    )


class NormalizedRecordDB(Base):
    __tablename__ = "normalized_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    source = Column(String, nullable=False)  # 'bank' | 'razorpay' | 'ledger'
    amount = Column(Numeric(10, 2), nullable=False)
    date = Column(Date, nullable=False)
    ref_id = Column(String, nullable=True)
    description = Column(String, nullable=True)
    raw = Column(JSONB, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    batch = relationship("Batch", back_populates="normalized_records")


class MatchResultDB(Base):
    __tablename__ = "match_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    bank_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey("normalized_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    razorpay_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey("normalized_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    ledger_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey("normalized_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    match_type = Column(String, nullable=False)  # 'exact' | 'fuzzy' | 'llm'
    confidence = Column(Float, nullable=False)
    notes = Column(String, nullable=True)

    batch = relationship("Batch", back_populates="match_results")


class ExceptionRecordDB(Base):
    __tablename__ = "exception_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    record_ids = Column(JSONB, nullable=False, default=list)
    reason_code = Column(String, nullable=False)
    description = Column(String, nullable=False)
    raw_records = Column(JSONB, nullable=False, default=dict)

    batch = relationship("Batch", back_populates="exception_records")


class QALogDB(Base):
    __tablename__ = "qa_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("batches.id", ondelete="CASCADE"),
        nullable=False,
    )
    question = Column(String, nullable=False)
    answer = Column(String, nullable=False)
    sources = Column(JSONB, nullable=False, default=list)
    created_at = Column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    batch = relationship("Batch", back_populates="qa_logs")
