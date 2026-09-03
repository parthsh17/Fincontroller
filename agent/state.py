from typing import Any, TypedDict


class BatchState(TypedDict):
    batch_id: str
    all_records: dict[str, list[dict[str, Any]]]
    matched_ids: set[str]
    match_results: list[dict[str, Any]]
    ambiguous_pairs: list[dict[str, Any]]
    pending_records: list[dict[str, Any]]
    unmatched_after_llm: list[dict[str, Any]]
    exception_records: list[dict[str, Any]]
    metrics: dict[str, Any]
