"""Pure metric evaluation functions for FinController reconciliation performance."""


def match_rate(total_matched: int, total_records: int) -> float:
    if total_records <= 0:
        return 0.0
    return float(total_matched) / float(total_records)


def false_match_rate(false_positives: int, total_matched: int) -> float:
    if total_matched <= 0:
        return 0.0
    return float(false_positives) / float(total_matched)


def exception_rate(total_exceptions: int, total_records: int) -> float:
    if total_records <= 0:
        return 0.0
    return float(total_exceptions) / float(total_records)


def throughput(total_records: int, elapsed_seconds: float) -> float:
    if elapsed_seconds <= 0:
        return float(total_records)
    return float(total_records) / float(elapsed_seconds)


def precision(tp: int, fp: int) -> float:
    if (tp + fp) <= 0:
        return 0.0
    return float(tp) / float(tp + fp)


def recall(tp: int, fn: int) -> float:
    if (tp + fn) <= 0:
        return 0.0
    return float(tp) / float(tp + fn)


def f1(prec: float, rec: float) -> float:
    if (prec + rec) <= 0.0:
        return 0.0
    return 2.0 * (prec * rec) / (prec + rec)
