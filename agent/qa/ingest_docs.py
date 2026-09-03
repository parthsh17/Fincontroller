import argparse
import csv
import os
import sys
import uuid
import chromadb
import httpx
from sentence_transformers import SentenceTransformer

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.config import settings


def get_embedding_model():
    return SentenceTransformer("all-MiniLM-L6-v2")


def ingest_documents(batch_id: str, csv_path: str = "data/samples/settlement_report.csv"):
    client = chromadb.PersistentClient(path=settings.chroma_path)
    collection = client.get_or_create_collection(
        name=settings.chroma_collection,
        metadata={"hnsw:space": "cosine"},
    )
    model = get_embedding_model()

    documents: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []

    if os.path.exists(csv_path):
        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                doc_text = (
                    f"Settlement {row.get('settlement_id', 'N/A')} on {row.get('date', 'N/A')}: "
                    f"INR {row.get('amount', '0')} - {row.get('description', '')}"
                )
                doc_id = f"{batch_id}_settlement_{idx}"
                documents.append(doc_text)
                metadatas.append({
                    "batch_id": batch_id,
                    "date": str(row.get("date", "")),
                    "amount": str(row.get("amount", "")),
                    "chunk_type": "settlement_row",
                })
                ids.append(doc_id)

    try:
        with httpx.Client(timeout=10.0) as http_client:
            res = http_client.get(f"http://localhost:8000/api/report/{batch_id}")
            if res.status_code == 200:
                report_data = res.json()
                summary = report_data.get("summary", {})
                summary_chunk = (
                    f"Batch {batch_id} reconciliation summary: "
                    f"match_rate={summary.get('match_rate', 0.0) * 100:.1f}%, "
                    f"{summary.get('total_exceptions', 0)} exceptions, "
                    f"{summary.get('total_matched', 0)} matched records, "
                    f"total records={summary.get('total_records', 0)}."
                )
                doc_id = f"{batch_id}_summary"
                documents.append(summary_chunk)
                metadatas.append({
                    "batch_id": batch_id,
                    "date": "N/A",
                    "amount": "0",
                    "chunk_type": "batch_summary",
                })
                ids.append(doc_id)

                for e_idx, exc in enumerate(report_data.get("exceptions", [])):
                    exc_chunk = (
                        f"Exception record for Batch {batch_id}: Reason: {exc.get('reason_code')} | "
                        f"Description: {exc.get('description')}"
                    )
                    documents.append(exc_chunk)
                    metadatas.append({
                        "batch_id": batch_id,
                        "date": "N/A",
                        "amount": "0",
                        "chunk_type": "exception_record",
                    })
                    ids.append(f"{batch_id}_exc_{e_idx}")
    except Exception as e:
        print(f"Notice: Could not fetch /api/report/{batch_id} over HTTP ({e}). Proceeding with CSV chunks.")

    if documents:
        embeddings = model.encode(documents).tolist()
        collection.upsert(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids,
        )
        print(f"Successfully embedded and indexed {len(documents)} chunks into ChromaDB for batch {batch_id}")
    else:
        print(f"No documents found to index for batch {batch_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest batch documents into ChromaDB")
    parser.add_argument("--batch_id", type=str, required=True, help="Reconciliation Batch ID")
    parser.add_argument("--csv_path", type=str, default="data/samples/settlement_report.csv")
    args = parser.parse_args()
    ingest_documents(batch_id=args.batch_id, csv_path=args.csv_path)
