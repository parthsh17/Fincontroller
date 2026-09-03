import io
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.engine import get_db
from backend.db.tables import (
    Batch,
    ExceptionRecordDB,
    MatchResultDB,
    NormalizedRecordDB,
)
from backend.models.batch import (
    BatchReport,
    BatchReportSummary,
    ExceptionBreakdown,
)
from backend.models.match import ExceptionRecord, MatchResult
from backend.models.record import NormalizedRecord

router = APIRouter(prefix="/api", tags=["Report"])


@router.get("/report/{batch_id}", response_model=BatchReport)
async def get_report(batch_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    stmt = select(Batch).where(Batch.id == batch_id)
    res = await db.execute(stmt)
    batch = res.scalar_one_or_none()

    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    m_stmt = select(MatchResultDB).where(MatchResultDB.batch_id == batch_id)
    m_res = await db.execute(m_stmt)
    matches_db = m_res.scalars().all()

    e_stmt = select(ExceptionRecordDB).where(ExceptionRecordDB.batch_id == batch_id)
    e_res = await db.execute(e_stmt)
    exceptions_db = e_res.scalars().all()

    n_stmt = select(NormalizedRecordDB).where(NormalizedRecordDB.batch_id == batch_id)
    n_res = await db.execute(n_stmt)
    norm_records = {str(r.id): r for r in n_res.scalars().all()}

    def to_pydantic_norm(rec_id):
        if not rec_id or str(rec_id) not in norm_records:
            return None
        r = norm_records[str(rec_id)]
        return NormalizedRecord(
            id=r.id,
            batch_id=r.batch_id,
            source=r.source,
            amount=r.amount,
            date=r.date,
            ref_id=r.ref_id,
            description=r.description,
            raw=r.raw or {},
        )

    matches_list: list[MatchResult] = []
    for m in matches_db:
        matches_list.append(
            MatchResult(
                id=m.id,
                batch_id=m.batch_id,
                bank_record_id=m.bank_record_id,
                razorpay_record_id=m.razorpay_record_id,
                ledger_record_id=m.ledger_record_id,
                bank_record=to_pydantic_norm(m.bank_record_id),
                razorpay_record=to_pydantic_norm(m.razorpay_record_id),
                ledger_record=to_pydantic_norm(m.ledger_record_id),
                match_type=m.match_type,
                confidence=m.confidence,
                notes=m.notes,
            )
        )

    exceptions_list: list[ExceptionRecord] = []
    breakdown_map: dict[str, list[dict]] = {}

    for e in exceptions_db:
        exc_obj = ExceptionRecord(
            id=e.id,
            batch_id=e.batch_id,
            record_ids=[uuid.UUID(rid) for rid in (e.record_ids or [])],
            reason_code=e.reason_code,
            description=e.description,
            raw_records=e.raw_records or {},
        )
        exceptions_list.append(exc_obj)
        breakdown_map.setdefault(e.reason_code, []).append({
            "id": str(e.id),
            "description": e.description,
            "raw_records": e.raw_records,
        })

    exception_breakdown = [
        ExceptionBreakdown(
            reason_code=code, count=len(recs), records=recs
        )
        for code, recs in breakdown_map.items()
    ]

    total_matched = (
        (batch.matched_exact or 0)
        + (batch.matched_fuzzy or 0)
        + (batch.matched_llm or 0)
    )

    duration = 0.0
    if batch.started_at and batch.completed_at:
        duration = (batch.completed_at - batch.started_at).total_seconds()

    summary = BatchReportSummary(
        total_records=batch.total_records or 0,
        matched_exact=batch.matched_exact or 0,
        matched_fuzzy=batch.matched_fuzzy or 0,
        matched_llm=batch.matched_llm or 0,
        total_matched=total_matched,
        total_exceptions=batch.total_exceptions or len(exceptions_list),
        match_rate=batch.match_rate or 0.0,
        exception_rate=(
            (batch.total_exceptions or len(exceptions_list)) / batch.total_records
            if batch.total_records
            else 0.0
        ),
        llm_calls_made=batch.llm_calls_made or 0,
        avg_llm_latency_ms=batch.avg_llm_latency_ms or 0.0,
        duration_seconds=round(duration, 2),
    )

    return BatchReport(
        batch_id=batch.id,
        status=batch.status,
        summary=summary,
        exception_breakdown=exception_breakdown,
        matches=matches_list,
        exceptions=exceptions_list,
    )


@router.get("/report/{batch_id}/pdf")
async def get_report_pdf(batch_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    report_data = await get_report(batch_id, db)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1A365D"),
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#4A5568"),
        spaceAfter=14,
    )
    h2_style = ParagraphStyle(
        "SectionHeader",
        parent=styles["Heading2"],
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#2B6CB0"),
        spaceBefore=12,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#2D3748"),
    )

    elements = []

    # 1. Header
    elements.append(Paragraph("BrewBox - Financial Reconciliation Report", title_style))
    gen_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    elements.append(
        Paragraph(
            f"<b>Batch ID:</b> {report_data.batch_id} &nbsp;|&nbsp; <b>Generated:</b> {gen_time} &nbsp;|&nbsp; <b>Status:</b> {report_data.status.upper()}",
            subtitle_style,
        )
    )
    elements.append(Spacer(1, 8))

    # 2. Summary Table
    elements.append(Paragraph("1. Executive Summary", h2_style))
    s = report_data.summary
    summary_data = [
        ["Total Ingested Records", str(s.total_records), "Match Rate", f"{s.match_rate:.1%}"],
        ["Total Matched Groups", str(s.total_matched), "Exception Rate", f"{s.exception_rate:.1%}"],
        ["Total Exceptions", str(s.total_exceptions), "Pipeline Duration", f"{s.duration_seconds}s"],
        ["LLM Calls Made", str(s.llm_calls_made), "Avg LLM Latency", f"{s.avg_llm_latency_ms:.1f}ms"],
    ]
    summary_table = Table(summary_data, colWidths=[150, 100, 150, 120])
    summary_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7FAFC")),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1A202C")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("ALIGN", (3, 0), (3, -1), "CENTER"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    elements.append(summary_table)
    elements.append(Spacer(1, 10))

    # 3. Match Breakdown
    elements.append(Paragraph("2. Match Distribution Breakdown", h2_style))
    total_m = max(s.total_matched, 1)
    match_data = [
        ["Match Stage", "Count", "Percentage of Matches", "Method Description"],
        [
            "Pass 1: Exact",
            str(s.matched_exact),
            f"{(s.matched_exact / total_m):.1%}",
            "Deterministic 3-way match on Amount, Date, and Reference",
        ],
        [
            "Pass 2: Fuzzy",
            str(s.matched_fuzzy),
            f"{(s.matched_fuzzy / total_m):.1%}",
            "RapidFuzz similarity with T+1 settlement lag tolerance",
        ],
        [
            "Pass 3: LLM Disambiguation",
            str(s.matched_llm),
            f"{(s.matched_llm / total_m):.1%}",
            "Groq LLM evaluation for ambiguous candidate pairs",
        ],
    ]
    match_table = Table(match_data, colWidths=[110, 60, 120, 230])
    match_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2B6CB0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 0), (2, -1), "CENTER"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
        ])
    )
    elements.append(match_table)
    elements.append(Spacer(1, 10))

    # 4. Exception Breakdown
    elements.append(Paragraph("3. Exception Breakdown by Reason Code", h2_style))
    exc_summary = [["Reason Code", "Count", "Impact Summary"]]
    for item in report_data.exception_breakdown:
        exc_summary.append([
            item.reason_code,
            str(item.count),
            f"{item.count} occurrences flagged during multi-pass reconciliation.",
        ])

    exc_table = Table(exc_summary, colWidths=[160, 60, 300])
    exc_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#C53030")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
        ])
    )
    elements.append(exc_table)
    elements.append(Spacer(1, 10))

    # 5. Exception Detail Table (first 10 items)
    elements.append(Paragraph("4. Exception Sample Audit Log (First 10 Items)", h2_style))
    detail_data = [["Reason Code", "Description", "Sources Involved"]]
    for exc in report_data.exceptions[:10]:
        srcs = ", ".join(exc.raw_records.keys()) if exc.raw_records else "N/A"
        desc_p = Paragraph(exc.description, body_style)
        detail_data.append([exc.reason_code, desc_p, srcs])

    detail_table = Table(detail_data, colWidths=[140, 280, 100])
    detail_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4A5568")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    elements.append(detail_table)

    doc.build(elements)
    buffer.seek(0)

    filename = f"fincontroller_report_{str(batch_id)[:8]}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
