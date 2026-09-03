import uuid
from decimal import Decimal
from loguru import logger
from sqlalchemy import update
from backend.config import settings
from backend.db.engine import async_session_maker
from backend.db.tables import Batch, MatchResultDB
from agent.state import BatchState
from agent.tools.fuzzy import (
    amount_within_tolerance,
    date_within_window,
    fuzzy_score,
)
from agent.tools.groq_client import groq_client


def parse_dec(val: str | float | int | Decimal | None) -> Decimal:
    if val is None:
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    clean = str(val).replace("₹", "").replace(",", "").strip()
    return Decimal(clean)


async def llm_match_node(state: BatchState) -> BatchState:
    batch_id = state["batch_id"]
    ambiguous_pairs = state.get("ambiguous_pairs", [])
    matched_ids = set(state.get("matched_ids", set()))
    match_results = list(state.get("match_results", []))
    pending = list(state.get("pending_records", []))
    unmatched_after_llm: list[dict] = []
    new_llm_matches: list[dict] = []

    pending_razorpay = [
        r for r in pending
        if r.get("source") == "razorpay" and str(r["id"]) not in matched_ids
    ]

    llm_calls_made = 0
    pct_tol = settings.fuzzy_amount_tolerance_pct
    abs_tol = settings.fuzzy_amount_tolerance_abs
    threshold = settings.llm_confidence_threshold

    for pair in ambiguous_pairs:
        rec_a = pair.get("record_a", {})
        rec_b = pair.get("record_b", {})
        id_a = str(rec_a.get("id"))
        id_b = str(rec_b.get("id"))

        if id_a in matched_ids or id_b in matched_ids:
            continue

        llm_calls_made += 1
        decision = await groq_client.match_records(rec_a, rec_b)

        if decision and decision.matched and decision.confidence >= threshold:
            l_rec = rec_a if rec_a.get("source") == "ledger" else rec_b
            b_rec = rec_b if rec_b.get("source") == "bank" else rec_a
            l_id = str(l_rec["id"])
            b_id = str(b_rec["id"])

            l_amt = parse_dec(l_rec.get("amount"))

            matched_r_rec = None
            matched_r_id = None

            for r_rec in pending_razorpay:
                r_id = str(r_rec["id"])
                if r_id in matched_ids:
                    continue
                r_amt = parse_dec(r_rec.get("amount"))
                if amount_within_tolerance(l_amt, r_amt, pct_tol, abs_tol):
                    matched_r_rec = r_rec
                    matched_r_id = r_id
                    break

            match_id = str(uuid.uuid4())
            match_data = {
                "id": match_id,
                "batch_id": batch_id,
                "bank_record": b_rec,
                "razorpay_record": matched_r_rec,
                "ledger_record": l_rec,
                "bank_record_id": b_id,
                "razorpay_record_id": matched_r_id,
                "ledger_record_id": l_id,
                "match_type": "llm",
                "confidence": decision.confidence,
                "notes": f"LLM Match: {decision.reason}",
            }

            matched_ids.update(
                [i for i in [l_id, b_id, matched_r_id] if i is not None]
            )
            match_results.append(match_data)
            new_llm_matches.append(match_data)
        else:
            if rec_a and id_a not in matched_ids:
                unmatched_after_llm.append(rec_a)
            if rec_b and id_b not in matched_ids:
                unmatched_after_llm.append(rec_b)

    remaining_pending = [r for r in pending if str(r["id"]) not in matched_ids]
    for r in remaining_pending:
        if not any(str(u.get("id")) == str(r["id"]) for u in unmatched_after_llm):
            unmatched_after_llm.append(r)

    avg_latency = (
        (groq_client.cumulative_latency_ms / groq_client.total_calls)
        if groq_client.total_calls > 0
        else 0.0
    )

    state["matched_ids"] = matched_ids
    state["match_results"] = match_results
    state["pending_records"] = remaining_pending
    state["unmatched_after_llm"] = unmatched_after_llm

    try:
        async with async_session_maker() as session:
            for m in new_llm_matches:
                match_db = MatchResultDB(
                    id=uuid.UUID(m["id"]),
                    batch_id=uuid.UUID(batch_id),
                    bank_record_id=uuid.UUID(m["bank_record_id"]) if m.get("bank_record_id") else None,
                    razorpay_record_id=uuid.UUID(m["razorpay_record_id"]) if m.get("razorpay_record_id") else None,
                    ledger_record_id=uuid.UUID(m["ledger_record_id"]) if m.get("ledger_record_id") else None,
                    match_type="llm",
                    confidence=m["confidence"],
                    notes=m["notes"],
                )
                session.add(match_db)

            await session.execute(
                update(Batch)
                .where(Batch.id == uuid.UUID(batch_id))
                .values(
                    matched_llm=len(new_llm_matches),
                    llm_calls_made=groq_client.total_calls,
                    avg_llm_latency_ms=avg_latency,
                )
            )
            await session.commit()
    except Exception as e:
        logger.error(f"Error persisting LLM matches to DB: {e}")

    logger.info(
        f"Batch {batch_id} [LLM Match] | Matches: {len(new_llm_matches)} | "
        f"LLM calls made: {llm_calls_made} | Unmatched after LLM: {len(unmatched_after_llm)}"
    )

    return state
