from typing import Any, TypedDict


class BatchState(TypedDict):
    batch_id: str
    all_records: dict[str, list[dict[str, Any]]]  # 'bank' | 'razorpay' | 'ledger'
    matched_ids: set[str]  # str(UUID)
    match_results: list[dict[str, Any]]
    ambiguous_pairs: list[dict[str, Any]]  # pairs of dicts with 'record_a', 'record_b'
    pending_records: list[dict[str, Any]]
    unmatched_after_llm: list[dict[str, Any]]
    exception_records: list[dict[str, Any]]
    metrics: dict[str, Any]
