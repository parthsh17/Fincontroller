import argparse
import json
import os
import sys
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from eval.metrics import (
    f1,
    false_match_rate,
    match_rate,
    precision,
    recall,
    throughput,
)


def run_evaluation(batch_id: str, held_out_path: str = "data/testset/held_out.json"):
    console = Console()

    if not os.path.exists(held_out_path):
        console.print(f"[red]Held out dataset not found at {held_out_path}[/red]")
        sys.exit(1)

    with open(held_out_path, "r", encoding="utf-8") as f:
        ground_truth: list[dict] = json.load(f)

    # Fetch report from local API
    url = f"http://localhost:8000/api/report/{batch_id}"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                console.print(
                    f"[red]Failed to fetch report for batch {batch_id} (Status: {resp.status_code})[/red]"
                )
                sys.exit(1)
            report = resp.json()
    except Exception as e:
        console.print(f"[red]Could not connect to FastAPI server: {e}[/red]")
        sys.exit(1)

    matches = report.get("matches", [])
    exceptions = report.get("exceptions", [])
    summary = report.get("summary", {})

    # Build reference lookup
    matched_refs = set()
    for m in matches:
        for r in (m.get("bank_record"), m.get("razorpay_record"), m.get("ledger_record")):
            if r and r.get("ref_id"):
                matched_refs.add(r.get("ref_id"))

    exception_refs = set()
    for e in exceptions:
        raw_map = e.get("raw_records", {})
        for src, raw in raw_map.items():
            if isinstance(raw, dict):
                ref = (
                    raw.get("ref_id")
                    or raw.get("settlement_id")
                    or raw.get("order_id")
                )
                if ref:
                    exception_refs.add(ref)

    tp = 0
    fp = 0
    fn = 0
    tn = 0

    for item in ground_truth:
        ref = item.get("record_ref")
        expected = item.get("expected")

        is_matched = ref in matched_refs
        is_exception = ref in exception_refs or (not is_matched)

        if expected == "match":
            if is_matched:
                tp += 1
            else:
                fn += 1
        else:  # expected == 'exception'
            if is_matched:
                fp += 1  # False positive / False match
            else:
                tn += 1

    total_eval = len(ground_truth)
    total_matched_eval = tp + fp
    total_records = summary.get("total_records", total_eval)
    duration = summary.get("duration_seconds", 1.0)

    m_rate = match_rate(tp + tn, total_eval)
    fm_rate = false_match_rate(fp, total_matched_eval)
    prec = precision(tp, fp)
    rec = recall(tp, fn)
    f1_score = f1(prec, rec)
    tp_rate = throughput(total_records, duration)

    # Render results table
    table = Table(title="FinController Reconciliation Benchmark", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan", width=28)
    table.add_column("Value", style="bold green", justify="right", width=18)

    table.add_row("Held-out test records", str(total_eval))
    table.add_row("True matches (TP)", str(tp))
    table.add_row("False matches (FP) [Critical]", f"[bold red]{fp}[/bold red]" if fp > 0 else str(fp))
    table.add_row("Missed matches (FN)", str(fn))
    table.add_row("True exceptions (TN)", str(tn))
    table.add_section()
    table.add_row("Accuracy / Overall Match Rate", f"{m_rate:.1%}")
    table.add_row("False Match Rate (FMR)", f"{fm_rate:.2%}")
    table.add_row("Precision", f"{prec:.4f}")
    table.add_row("Recall", f"{rec:.4f}")
    table.add_row("F1 Score", f"{f1_score:.4f}")
    table.add_row("Throughput", f"{tp_rate:.2f} rec/sec")

    console.print(Panel(table, title="[bold blue]Evaluation Summary[/bold blue]", expand=False))

    if m_rate < 0.80:
        console.print("[bold red]EVAL FAILED: Match rate below 80% threshold[/bold red]")
        sys.exit(1)
    else:
        console.print("[bold green]EVAL PASSED: Match rate satisfies benchmark criteria (>= 80%)[/bold green]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run evaluation against held out dataset")
    parser.add_argument("--batch_id", type=str, required=True, help="Batch ID to evaluate")
    parser.add_argument("--held_out", type=str, default="data/testset/held_out.json")
    args = parser.parse_args()
    run_evaluation(batch_id=args.batch_id, held_out_path=args.held_out)
