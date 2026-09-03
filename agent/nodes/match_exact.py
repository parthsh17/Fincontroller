import uuid
from decimal import Decimal
from loguru import logger
from sqlalchemy import select, update
from backend.db.engine import async_session_maker
from backend.db.tables import Batch, MatchResultDB
from agent.state import BatchState


def parse_dec(val: str | float | int | Decimal | None) -> Decimal:
    if val is None:
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    clean = str(val).replace("₹", "").replace(",", "").strip()
    return Decimal(clean)


async def exact_match_node(state: BatchState) -> BatchState:
    batch_id = state["batch_id"]
    all_records = state.get("all_records", {})
    bank_records = all_records.get("bank", [])
    razorpay_records = all_records.get("razorpay", [])
    ledger_records = all_records.get("ledger", [])

    matched_ids = set(state.get("matched_ids", set()))
    match_results = list(state.get("match_results", []))
    new_exact_matches: list[dict] = []
    # Identify references that appear more than once in the same source
    dup_refs = set()
    for rec_list in [bank_records, razorpay_records, ledger_records]:
        counts: dict[str, int] = {}
        for r in rec_list:
            ref = (r.get("ref_id") or "").strip()
            if ref:
                counts[ref] = counts.get(ref, 0) + 1
        for ref, cnt in counts.items():
            if cnt > 1:
                dup_refs.add(ref)

    for l_rec in ledger_records:
        l_id = str(l_rec["id"])
        if l_id in matched_ids:
            continue

        l_amt = parse_dec(l_rec.get("amount"))
        l_date = str(l_rec.get("date"))
        l_ref = (l_rec.get("ref_id") or "").strip()

        # If reference is duplicate in any source, skip exact matching so it goes to exception triage
        if l_ref and l_ref in dup_refs:
            continue

        found_match = False

        for b_rec in bank_records:
            b_id = str(b_rec["id"])
            if b_id in matched_ids:
                continue

            b_ref = (b_rec.get("ref_id") or "").strip()
            if b_ref and b_ref in dup_refs:
                continue

            b_amt = parse_dec(b_rec.get("amount"))
            b_date = str(b_rec.get("date"))
            b_ref = (b_rec.get("ref_id") or "").strip()

            if l_amt != b_amt or l_date != b_date:
                continue

            for r_rec in razorpay_records:
                r_id = str(r_rec["id"])
                if r_id in matched_ids:
                    continue

                r_amt = parse_dec(r_rec.get("amount"))
                r_date = str(r_rec.get("date"))
                r_ref = (r_rec.get("ref_id") or "").strip()

                if l_amt != r_amt or l_date != r_date:
                    continue

                ref_check_passed = True
                if l_ref and b_ref and r_ref:
                    ref_check_passed = (l_ref == b_ref) or (l_ref == r_ref) or (b_ref == r_ref)

                if ref_check_passed:
                    match_id = str(uuid.uuid4())
                    match_data = {
                        "id": match_id,
                        "batch_id": batch_id,
                        "bank_record": b_rec,
                        "razorpay_record": r_rec,
                        "ledger_record": l_rec,
                        "bank_record_id": b_id,
                        "razorpay_record_id": r_id,
                        "ledger_record_id": l_id,
                        "match_type": "exact",
                        "confidence": 1.0,
                        "notes": "Exact 3-way match on amount, date, and reference",
                    }
                    matched_ids.update([l_id, b_id, r_id])
                    match_results.append(match_data)
                    new_exact_matches.append(match_data)
                    found_match = True
                    break

            if found_match:
                break

    pending_records = []
    for source, rec_list in [
        ("bank", bank_records),
        ("razorpay", razorpay_records),
        ("ledger", ledger_records),
    ]:
        for r in rec_list:
            if str(r["id"]) not in matched_ids:
                pending_records.append(r)

    state["matched_ids"] = matched_ids
    state["match_results"] = match_results
    state["pending_records"] = pending_records

    try:
        async with async_session_maker() as session:
            for m in new_exact_matches:
                match_db = MatchResultDB(
                    id=uuid.UUID(m["id"]),
                    batch_id=uuid.UUID(batch_id),
                    bank_record_id=uuid.UUID(m["bank_record_id"]),
                    razorpay_record_id=uuid.UUID(m["razorpay_record_id"]),
                    ledger_record_id=uuid.UUID(m["ledger_record_id"]),
                    match_type="exact",
                    confidence=1.0,
                    notes=m["notes"],
                )
                session.add(match_db)

            await session.execute(
                update(Batch)
                .where(Batch.id == uuid.UUID(batch_id))
                .values(matched_exact=len(new_exact_matches))
            )
            await session.commit()
    except Exception as e:
        logger.error(f"Error persisting exact matches to DB: {e}")

    logger.info(
        f"Batch {batch_id} [Exact Match] | Matches: {len(new_exact_matches)} | "
        f"Pending records: {len(pending_records)}"
    )

    return state
