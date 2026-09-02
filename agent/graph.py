import uuid
from datetime import datetime, timezone
from langgraph.graph import END, START, StateGraph
from loguru import logger
from sqlalchemy import select, update
from backend.db.engine import async_session_maker
from backend.db.tables import Batch, NormalizedRecordDB
from agent.nodes.exception import exception_node
from agent.nodes.match_exact import exact_match_node
from agent.nodes.match_fuzzy import fuzzy_match_node
from agent.nodes.match_llm import llm_match_node
from agent.nodes.report import report_node
from agent.state import BatchState


async def normalize_node(state: BatchState) -> BatchState:
    """Loads normalized records from the database into state.all_records."""
    batch_id = state["batch_id"]

    try:
        async with async_session_maker() as session:
            stmt = select(NormalizedRecordDB).where(
                NormalizedRecordDB.batch_id == uuid.UUID(batch_id)
            )
            res = await session.execute(stmt)
            records = res.scalars().all()

            all_records: dict[str, list[dict]] = {
                "bank": [],
                "razorpay": [],
                "ledger": [],
            }

            for rec in records:
                rec_dict = {
                    "id": str(rec.id),
                    "batch_id": str(rec.batch_id),
                    "source": rec.source,
                    "amount": str(rec.amount),
                    "date": rec.date.isoformat() if rec.date else None,
                    "ref_id": rec.ref_id,
                    "description": rec.description,
                    "raw": rec.raw or {},
                }
                if rec.source in all_records:
                    all_records[rec.source].append(rec_dict)

            state["all_records"] = all_records
            logger.info(
                f"Batch {batch_id} [Normalize Node] | Loaded {len(records)} records from DB "
                f"(Bank: {len(all_records['bank'])}, Razorpay: {len(all_records['razorpay'])}, Ledger: {len(all_records['ledger'])})"
            )
    except Exception as e:
        logger.error(f"Error loading records from DB in normalize_node: {e}")

    return state


# Build graph
workflow = StateGraph(BatchState)

workflow.add_node("normalize", normalize_node)
workflow.add_node("match_exact", exact_match_node)
workflow.add_node("match_fuzzy", fuzzy_match_node)
workflow.add_node("match_llm", llm_match_node)
workflow.add_node("exception", exception_node)
workflow.add_node("report", report_node)

workflow.add_edge(START, "normalize")
workflow.add_edge("normalize", "match_exact")
workflow.add_edge("match_exact", "match_fuzzy")
workflow.add_edge("match_fuzzy", "match_llm")
workflow.add_edge("match_llm", "exception")
workflow.add_edge("exception", "report")
workflow.add_edge("report", END)

app_graph = workflow.compile()


async def run_graph(batch_id: str):
    """Executes the reconciliation graph asynchronously as a background task."""
    logger.info(f"Starting reconciliation graph for batch {batch_id}")

    try:
        async with async_session_maker() as session:
            await session.execute(
                update(Batch)
                .where(Batch.id == uuid.UUID(batch_id))
                .values(status="running", started_at=datetime.now(timezone.utc))
            )
            await session.commit()

        initial_state: BatchState = {
            "batch_id": batch_id,
            "all_records": {"bank": [], "razorpay": [], "ledger": []},
            "matched_ids": set(),
            "match_results": [],
            "ambiguous_pairs": [],
            "pending_records": [],
            "unmatched_after_llm": [],
            "exception_records": [],
            "metrics": {},
        }

        await app_graph.ainvoke(initial_state)
        logger.info(f"Reconciliation graph completed successfully for batch {batch_id}")

    except Exception as e:
        logger.error(f"Reconciliation graph failed for batch {batch_id}: {e}")
        try:
            async with async_session_maker() as session:
                await session.execute(
                    update(Batch)
                    .where(Batch.id == uuid.UUID(batch_id))
                    .values(status="failed")
                )
                await session.commit()
        except Exception as db_err:
            logger.error(f"Failed to update batch status to failed: {db_err}")
