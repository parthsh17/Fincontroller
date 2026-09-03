import uuid
from datetime import datetime
from decimal import Decimal
from loguru import logger
from sqlalchemy import update
from backend.db.engine import async_session_maker
from backend.db.tables import Batch, ExceptionRecordDB
from agent.state import BatchState


def parse_dec(val: str | float | int | Decimal | None) -> Decimal:
    if val is None:
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    clean = str(val).replace("₹", "").replace(",", "").strip()
    return Decimal(clean)


def to_date_obj(d_val):
    if hasattr(d_val, "year"):
        return d_val
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(d_val).strip(), fmt).date()
        except ValueError:
            pass
    return datetime.fromisoformat(str(d_val).strip()).date()


async def exception_node(state: BatchState) -> BatchState:
    batch_id = state["batch_id"]
    all_records = state.get("all_records", {})
    matched_ids = set(state.get("matched_ids", set()))

    unmatched_list = []
    seen_ids = set()

    for r in state.get("unmatched_after_llm", []) + state.get("pending_records", []):
        r_id = str(r.get("id"))
        if r_id not in matched_ids and r_id not in seen_ids:
            seen_ids.add(r_id)
            unmatched_list.append(r)

    bank_all = all_records.get("bank", [])
    rp_all = all_records.get("razorpay", [])
    ledger_all = all_records.get("ledger", [])

    ledger_ref_counts: dict[str, list[dict]] = {}
    for r in ledger_all:
        ref = (r.get("ref_id") or "").strip()
        if ref:
            ledger_ref_counts.setdefault(ref, []).append(r)

    bank_ref_counts: dict[str, list[dict]] = {}
    for r in bank_all:
        ref = (r.get("ref_id") or "").strip()
        if ref:
            bank_ref_counts.setdefault(ref, []).append(r)

    rp_ref_counts: dict[str, list[dict]] = {}
    for r in rp_all:
        ref = (r.get("ref_id") or "").strip()
        if ref:
            rp_ref_counts.setdefault(ref, []).append(r)

    exception_records: list[dict] = []
    processed_exception_ids = set()

    for rec in unmatched_list:
        rec_id = str(rec.get("id"))
        if rec_id in processed_exception_ids:
            continue

        source = rec.get("source")
        amount = parse_dec(rec.get("amount"))
        rec_date = to_date_obj(rec.get("date"))
        ref_id = (rec.get("ref_id") or "").strip()

        reason_code = "UNIDENTIFIED"
        description = "Transaction could not be correlated across sources."
        related_ids = [rec_id]
        raw_map = {source: rec.get("raw", {})}

        if ref_id and (
            len(ledger_ref_counts.get(ref_id, [])) > 1
            or len(bank_ref_counts.get(ref_id, [])) > 1
            or len(rp_ref_counts.get(ref_id, [])) > 1
        ):
            reason_code = "DUPLICATE_DETECTED"
            description = f"Duplicate reference ID '{ref_id}' found in records."
            dup_records = (
                ledger_ref_counts.get(ref_id, [])
                + bank_ref_counts.get(ref_id, [])
                + rp_ref_counts.get(ref_id, [])
            )
            for d in dup_records:
                d_id = str(d.get("id"))
                if d_id not in related_ids:
                    related_ids.append(d_id)
                raw_map[f"{d.get('source')}_{d_id[:6]}"] = d.get("raw", {})
                processed_exception_ids.add(d_id)

        elif (
            ref_id
            and (ref_id in rp_ref_counts)
            and (ref_id in ledger_ref_counts)
            and (ref_id not in bank_ref_counts)
        ):
            reason_code = "MISSING_IN_BANK"
            description = (
                f"Transaction '{ref_id}' found in Razorpay settlement and internal ledger "
                "but missing in bank statement."
            )
            rp_match = rp_ref_counts[ref_id][0]
            ld_match = ledger_ref_counts[ref_id][0]
            related_ids = list(
                set([rec_id, str(rp_match.get("id")), str(ld_match.get("id"))])
            )
            raw_map["razorpay"] = rp_match.get("raw", {})
            raw_map["ledger"] = ld_match.get("raw", {})
            for rid in related_ids:
                processed_exception_ids.add(rid)

        elif (
            ref_id
            and (ref_id in bank_ref_counts)
            and (ref_id in ledger_ref_counts)
            and (ref_id not in rp_ref_counts)
        ):
            reason_code = "MISSING_IN_RAZORPAY"
            description = (
                f"Transaction '{ref_id}' found in bank statement and internal ledger "
                "but missing in Razorpay report."
            )
            bk_match = bank_ref_counts[ref_id][0]
            ld_match = ledger_ref_counts[ref_id][0]
            related_ids = list(
                set([rec_id, str(bk_match.get("id")), str(ld_match.get("id"))])
            )
            raw_map["bank"] = bk_match.get("raw", {})
            raw_map["ledger"] = ld_match.get("raw", {})
            for rid in related_ids:
                processed_exception_ids.add(rid)

        elif ref_id and (
            (ref_id in bank_ref_counts and ref_id in rp_ref_counts)
            or (ref_id in bank_ref_counts and ref_id in ledger_ref_counts)
            or (ref_id in rp_ref_counts and ref_id in ledger_ref_counts)
        ):
            b_item = bank_ref_counts.get(ref_id, [None])[0]
            r_item = rp_ref_counts.get(ref_id, [None])[0]
            l_item = ledger_ref_counts.get(ref_id, [None])[0]

            amounts = []
            if b_item:
                amounts.append(("bank", parse_dec(b_item.get("amount")), b_item))
            if r_item:
                amounts.append(("razorpay", parse_dec(r_item.get("amount")), r_item))
            if l_item:
                amounts.append(("ledger", parse_dec(l_item.get("amount")), l_item))

            amt_vals = [a[1] for a in amounts]
            if len(set(amt_vals)) > 1:
                diff = max(amt_vals) - min(amt_vals)
                reason_code = "AMOUNT_MISMATCH"
                description = (
                    f"Amount mismatch for reference '{ref_id}': differs by {diff:.2f} "
                    f"({', '.join(f'{src}: {amt:.2f}' for src, amt, _ in amounts)})."
                )
                for src, _, item in amounts:
                    i_id = str(item.get("id"))
                    if i_id not in related_ids:
                        related_ids.append(i_id)
                    raw_map[src] = item.get("raw", {})
                    processed_exception_ids.add(i_id)
            else:
                reason_code = "DATE_MISMATCH"
                description = f"Date discrepancy exceeds threshold for reference '{ref_id}'."

        else:
            other_recs = []
            for other_src, other_list in [
                ("bank", bank_all),
                ("razorpay", rp_all),
                ("ledger", ledger_all),
            ]:
                if other_src != source:
                    for o in other_list:
                        if parse_dec(o.get("amount")) == amount:
                            other_recs.append(o)

            date_mismatch_found = False
            for o in other_recs:
                o_date = to_date_obj(o.get("date"))
                date_diff = abs((rec_date - o_date).days)
                if date_diff > 3:
                    reason_code = "DATE_MISMATCH"
                    description = (
                        f"Matching amount {amount:.2f} found but transaction date "
                        f"differs by {date_diff} days."
                    )
                    o_id = str(o.get("id"))
                    if o_id not in related_ids:
                        related_ids.append(o_id)
                    raw_map[o.get("source")] = o.get("raw", {})
                    processed_exception_ids.add(o_id)
                    date_mismatch_found = True
                    break

            if not date_mismatch_found:
                reason_code = "UNIDENTIFIED"
                description = (
                    f"Unidentified entry in {source} for {amount:.2f} on {rec_date}. "
                    "No corresponding records found."
                )

        processed_exception_ids.add(rec_id)

        exc_obj = {
            "id": str(uuid.uuid4()),
            "batch_id": batch_id,
            "record_ids": related_ids,
            "reason_code": reason_code,
            "description": description,
            "raw_records": raw_map,
        }
        exception_records.append(exc_obj)

    state["exception_records"] = exception_records

    try:
        async with async_session_maker() as session:
            for exc in exception_records:
                exc_db = ExceptionRecordDB(
                    id=uuid.UUID(exc["id"]),
                    batch_id=uuid.UUID(batch_id),
                    record_ids=exc["record_ids"],
                    reason_code=exc["reason_code"],
                    description=exc["description"],
                    raw_records=exc["raw_records"],
                )
                session.add(exc_db)

            await session.execute(
                update(Batch)
                .where(Batch.id == uuid.UUID(batch_id))
                .values(total_exceptions=len(exception_records))
            )
            await session.commit()
    except Exception as e:
        logger.error(f"Error persisting exception records to DB: {e}")

    logger.info(
        f"Batch {batch_id} [Exception Handler] | Total exceptions categorized: {len(exception_records)}"
    )

    return state
