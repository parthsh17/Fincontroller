import uuid
from datetime import datetime, timezone
from loguru import logger
from sqlalchemy import select, update
from backend.db.engine import async_session_maker
from backend.db.tables import Batch
from agent.state import BatchState


async def report_node(state: BatchState) -> BatchState:
    batch_id = state["batch_id"]
    completed_time = datetime.now(timezone.utc)

    total_exact = len([m for m in state.get("match_results", []) if m.get("match_type") == "exact"])
    total_fuzzy = len([m for m in state.get("match_results", []) if m.get("match_type") == "fuzzy"])
    total_llm = len([m for m in state.get("match_results", []) if m.get("match_type") == "llm"])
    total_matched = len(state.get("match_results", []))
    total_exceptions = len(state.get("exception_records", []))

    try:
        async with async_session_maker() as session:
            stmt = select(Batch).where(Batch.id == uuid.UUID(batch_id))
            res = await session.execute(stmt)
            batch = res.scalar_one_or_none()

            total_records = (
                batch.total_records
                if batch and batch.total_records > 0
                else (
                    len(state.get("all_records", {}).get("bank", []))
                    + len(state.get("all_records", {}).get("razorpay", []))
                    + len(state.get("all_records", {}).get("ledger", []))
                )
            )

            matched_record_ids_count = len(state.get("matched_ids", set()))
            match_rate = (
                (matched_record_ids_count / total_records)
                if total_records > 0
                else 0.0
            )
            exception_rate = (
                (total_exceptions / total_records)
                if total_records > 0
                else 0.0
            )

            await session.execute(
                update(Batch)
                .where(Batch.id == uuid.UUID(batch_id))
                .values(
                    status="done",
                    matched_exact=total_exact,
                    matched_fuzzy=total_fuzzy,
                    matched_llm=total_llm,
                    total_exceptions=total_exceptions,
                    match_rate=match_rate,
                    completed_at=completed_time,
                )
            )
            await session.commit()
    except Exception as e:
        logger.error(f"Error updating final batch metrics in DB: {e}")
        match_rate = 0.0
        exception_rate = 0.0

    state["metrics"] = {
        "matched_exact": total_exact,
        "matched_fuzzy": total_fuzzy,
        "matched_llm": total_llm,
        "total_matched": total_matched,
        "total_exceptions": total_exceptions,
        "match_rate": match_rate,
        "exception_rate": exception_rate,
        "completed_at": completed_time.isoformat(),
    }

    logger.info(
        f"--------------------------------------------------\n"
        f"Batch {batch_id} Reconciliation Complete\n"
        f"Total Matched: {total_matched} (Exact: {total_exact}, Fuzzy: {total_fuzzy}, LLM: {total_llm})\n"
        f"Exceptions: {total_exceptions}\n"
        f"Match Rate: {match_rate:.1%}\n"
        f"--------------------------------------------------"
    )

    return state
