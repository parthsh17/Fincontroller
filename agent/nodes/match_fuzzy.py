import uuid
from datetime import datetime
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


def to_date_obj(d_val):
    if hasattr(d_val, "year"):
        return d_val
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(d_val).strip(), fmt).date()
        except ValueError:
            pass
    return datetime.fromisoformat(str(d_val).strip()).date()


def parse_dec(val: str | float | int | Decimal | None) -> Decimal:
    if val is None:
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    clean = str(val).replace("₹", "").replace(",", "").strip()
    return Decimal(clean)


async def fuzzy_match_node(state: BatchState) -> BatchState:
    batch_id = state["batch_id"]
    pending = state.get("pending_records", [])
    matched_ids = set(state.get("matched_ids", set()))
    match_results = list(state.get("match_results", []))
    ambiguous_pairs: list[dict] = []
    new_fuzzy_matches: list[dict] = []

    pending_bank = [r for r in pending if r.get("source") == "bank" and str(r["id"]) not in matched_ids]
    pending_razorpay = [r for r in pending if r.get("source") == "razorpay" and str(r["id"]) not in matched_ids]
    pending_ledger = [r for r in pending if r.get("source") == "ledger" and str(r["id"]) not in matched_ids]

    # Collect duplicate references across all sources
    all_recs_map = state.get("all_records", {})
    dup_refs = set()
    for rec_list in [all_recs_map.get("bank", []), all_recs_map.get("razorpay", []), all_recs_map.get("ledger", [])]:
        counts: dict[str, int] = {}
        for r in rec_list:
            ref = (r.get("ref_id") or "").strip()
            if ref:
                counts[ref] = counts.get(ref, 0) + 1
        for ref, cnt in counts.items():
            if cnt > 1:
                dup_refs.add(ref)

    threshold = settings.fuzzy_threshold
    date_window = settings.fuzzy_date_window_days

    for l_rec in pending_ledger:
        l_id = str(l_rec["id"])
        if l_id in matched_ids:
            continue

        l_amt = parse_dec(l_rec.get("amount"))
        l_date = to_date_obj(l_rec.get("date"))
        l_desc = l_rec.get("description") or ""
        l_ref = (l_rec.get("ref_id") or "").strip()

        if l_ref and l_ref in dup_refs:
            continue

        found_match = False

        for b_rec in pending_bank:
            b_id = str(b_rec["id"])
            if b_id in matched_ids:
                continue

            b_ref = (b_rec.get("ref_id") or "").strip()
            if b_ref and b_ref in dup_refs:
                continue

            b_amt = parse_dec(b_rec.get("amount"))
            b_date = to_date_obj(b_rec.get("date"))
            b_desc = b_rec.get("description") or ""

            # For fuzzy matching, amounts must match (settlement lag has identical amount with T+1/T+2 date shift)
            amt_exact_lb = (l_amt == b_amt)
            date_ok_lb = date_within_window(l_date, b_date, date_window)

            if not (amt_exact_lb and date_ok_lb):
                continue

            desc_score_lb = fuzzy_score(l_desc, b_desc)
            if l_ref and b_ref and l_ref == b_ref:
                desc_score_lb = max(desc_score_lb, 1.0)
            elif not l_desc or not b_desc:
                if l_amt == b_amt and l_date == b_date:
                    desc_score_lb = 0.9

            score_pct_lb = desc_score_lb * 100.0

            if score_pct_lb >= threshold:
                for r_rec in pending_razorpay:
                    r_id = str(r_rec["id"])
                    if r_id in matched_ids:
                        continue

                    r_ref = (r_rec.get("ref_id") or "").strip()
                    if r_ref and r_ref in dup_refs:
                        continue

                    r_amt = parse_dec(r_rec.get("amount"))
                    r_date = to_date_obj(r_rec.get("date"))
                    r_desc = r_rec.get("description") or ""

                    amt_exact_lr = (l_amt == r_amt)
                    date_ok_lr = date_within_window(l_date, r_date, date_window)

                    if not (amt_exact_lr and date_ok_lr):
                        continue

                    desc_score_lr = fuzzy_score(l_desc, r_desc)
                    if l_ref and r_ref and l_ref == r_ref:
                        desc_score_lr = max(desc_score_lr, 1.0)
                    elif not l_desc or not r_desc:
                        if l_amt == r_amt and abs((l_date - r_date).days) <= 1:
                            desc_score_lr = 0.9

                    score_pct_lr = desc_score_lr * 100.0

                    if score_pct_lr >= threshold:
                        avg_desc_score = (desc_score_lb + desc_score_lr) / 2.0
                        confidence = min(0.95, round(avg_desc_score * 0.95, 2))
                        if confidence < 0.70:
                            confidence = 0.85

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
                            "match_type": "fuzzy",
                            "confidence": confidence,
                            "notes": (
                                f"Fuzzy matched with date delta (T+{abs((l_date - r_date).days)}) "
                                f"and amt tolerance (diff {abs(l_amt - b_amt):.2f})"
                            ),
                        }
                        matched_ids.update([l_id, b_id, r_id])
                        match_results.append(match_data)
                        new_fuzzy_matches.append(match_data)
                        found_match = True
                        break

                if found_match:
                    break

            elif 50.0 <= score_pct_lb < threshold:
                ambiguous_pairs.append({
                    "record_a": l_rec,
                    "record_b": b_rec,
                    "reason": f"Ambiguous fuzzy similarity score: {score_pct_lb:.1f}%",
                })

    new_pending = [r for r in pending if str(r["id"]) not in matched_ids]

    state["matched_ids"] = matched_ids
    state["match_results"] = match_results
    state["ambiguous_pairs"] = ambiguous_pairs
    state["pending_records"] = new_pending

    try:
        async with async_session_maker() as session:
            for m in new_fuzzy_matches:
                match_db = MatchResultDB(
                    id=uuid.UUID(m["id"]),
                    batch_id=uuid.UUID(batch_id),
                    bank_record_id=uuid.UUID(m["bank_record_id"]),
                    razorpay_record_id=uuid.UUID(m["razorpay_record_id"]),
                    ledger_record_id=uuid.UUID(m["ledger_record_id"]),
                    match_type="fuzzy",
                    confidence=m["confidence"],
                    notes=m["notes"],
                )
                session.add(match_db)

            await session.execute(
                update(Batch)
                .where(Batch.id == uuid.UUID(batch_id))
                .values(matched_fuzzy=len(new_fuzzy_matches))
            )
            await session.commit()
    except Exception as e:
        logger.error(f"Error persisting fuzzy matches to DB: {e}")

    logger.info(
        f"Batch {batch_id} [Fuzzy Match] | Matches: {len(new_fuzzy_matches)} | "
        f"Ambiguous pairs: {len(ambiguous_pairs)} | Pending records: {len(new_pending)}"
    )

    return state
