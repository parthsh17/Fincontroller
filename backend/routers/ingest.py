import io
import uuid
import pandas as pd
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.engine import get_db
from backend.db.tables import Batch, NormalizedRecordDB
from backend.models.batch import BatchStatus
from agent.graph import run_graph
from agent.nodes.normalize import normalize_record

router = APIRouter(prefix="/api", tags=["Ingest"])


@router.post("/ingest")
async def ingest_files(
    background_tasks: BackgroundTasks,
    bank_file: UploadFile = File(...),
    razorpay_file: UploadFile = File(...),
    ledger_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        # Create new Batch record
        batch_id = uuid.uuid4()
        batch_obj = Batch(id=batch_id, status="pending", total_records=0)
        db.add(batch_obj)
        await db.commit()

        # Read CSV files into pandas
        bank_content = await bank_file.read()
        rp_content = await razorpay_file.read()
        ledger_content = await ledger_file.read()

        df_bank = pd.read_csv(io.BytesIO(bank_content))
        df_rp = pd.read_csv(io.BytesIO(rp_content))
        df_ledger = pd.read_csv(io.BytesIO(ledger_content))

        normalized_db_records: list[NormalizedRecordDB] = []

        # Process bank records
        for _, row in df_bank.iterrows():
            row_dict = row.to_dict()
            norm = normalize_record(row_dict, "bank", batch_id)
            if norm:
                normalized_db_records.append(
                    NormalizedRecordDB(
                        id=norm.id,
                        batch_id=norm.batch_id,
                        source=norm.source,
                        amount=norm.amount,
                        date=norm.date,
                        ref_id=norm.ref_id,
                        description=norm.description,
                        raw=norm.raw,
                    )
                )

        # Process razorpay records
        for _, row in df_rp.iterrows():
            row_dict = row.to_dict()
            norm = normalize_record(row_dict, "razorpay", batch_id)
            if norm:
                normalized_db_records.append(
                    NormalizedRecordDB(
                        id=norm.id,
                        batch_id=norm.batch_id,
                        source=norm.source,
                        amount=norm.amount,
                        date=norm.date,
                        ref_id=norm.ref_id,
                        description=norm.description,
                        raw=norm.raw,
                    )
                )

        # Process ledger records
        for _, row in df_ledger.iterrows():
            row_dict = row.to_dict()
            norm = normalize_record(row_dict, "ledger", batch_id)
            if norm:
                normalized_db_records.append(
                    NormalizedRecordDB(
                        id=norm.id,
                        batch_id=norm.batch_id,
                        source=norm.source,
                        amount=norm.amount,
                        date=norm.date,
                        ref_id=norm.ref_id,
                        description=norm.description,
                        raw=norm.raw,
                    )
                )

        # Bulk insert records
        db.add_all(normalized_db_records)
        batch_obj.total_records = len(normalized_db_records)
        await db.commit()

        logger.info(
            f"Batch {batch_id} created with {len(normalized_db_records)} records. "
            "Dispatching background reconciliation graph."
        )

        # Dispatch graph in background
        background_tasks.add_task(run_graph, str(batch_id))

        return {
            "batch_id": str(batch_id),
            "total_records": len(normalized_db_records),
            "status": "pending",
        }

    except Exception as e:
        logger.error(f"Error during file ingest: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/batch/{batch_id}/status", response_model=BatchStatus)
async def get_batch_status(batch_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    stmt = select(Batch).where(Batch.id == batch_id)
    res = await db.execute(stmt)
    batch = res.scalar_one_or_none()

    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    total_matched = (
        (batch.matched_exact or 0)
        + (batch.matched_fuzzy or 0)
        + (batch.matched_llm or 0)
    )

    return BatchStatus(
        id=batch.id,
        status=batch.status,
        total_records=batch.total_records,
        matched=total_matched,
        exceptions=batch.total_exceptions or 0,
    )
