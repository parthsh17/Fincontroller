# Track 04 - AI Finance Controller - Submission

## 1. Problem Statement
High-growth merchants like **BrewBox** experience high transaction volumes across multiple disjoint channels (Bank Statements, Payment Gateway Settlement Reports, and Internal ERP Ledgers). Discrepancies arising from gateway fee deductions, settlement delays (T+1/T+2 payout lags), missing bank deposits, and duplicate entries require hours of manual auditing by finance teams, increasing operational overhead and risk of revenue leakage.

---

## 2. What the Agent Does
- **Multi-Source Ingestion & Robust Normalization**: Ingests 3 distinct CSV sources with different schemas and currency formatting, converting them into structured Pydantic v2 records.
- **2-Pass + LLM Hierarchical Reconciliation DAG**:
  1. *Pass 1 (Deterministic Exact Match)*: Instant 3-way matching on exact amount, date, and reference keys with zero LLM overhead.
  2. *Pass 2 (Fuzzy Match)*: Tolerates payout settlement lags (T+1/T+2) and minor description noise via RapidFuzz similarity.
  3. *Pass 3 (Groq LLM Disambiguation)*: Selectively activates Groq (`llama-3.3-70b-versatile`) strictly for ambiguous edge-case candidates (50-75% similarity), returning strictly validated Pydantic decisions.
- **Automated Exception Root-Cause Analysis**: Identifies and labels exceptions with reason codes (`AMOUNT_MISMATCH`, `MISSING_IN_BANK`, `MISSING_IN_RAZORPAY`, `DUPLICATE_DETECTED`, `DATE_MISMATCH`, `UNIDENTIFIED`).
- **Settlement Q&A Agent**: ChromaDB vector index embedded with SentenceTransformers allowing natural language querying over settlements and audit results.
- **Audit Reports & UI**: Live interactive Streamlit dashboard and professional PDF report generation via ReportLab.

---

## 3. Evaluation Results

Evaluated against held-out benchmark records with injected real-world noise:

| Metric | Target | Value |
|---|---|---|
| **Match Rate** | >= 80.0% | **88.5%** |
| **False Match Rate (FMR)** | <= 2.0% | **0.0%** |
| **Precision** | >= 0.95 | **1.0000** |
| **Recall** | >= 0.85 | **0.8850** |
| **F1 Score** | >= 0.90 | **0.9390** |
| **Reconciliation Throughput** | >= 50 rec/s | **~110 rec/sec** |

---

## 4. Architecture Decisions
- **LangGraph Stateful DAG**: Enables fine-grained per-record state tracking and conditional branch routing, guaranteeing that LLM calls fire only for ambiguous records rather than all records.
- **Two-Pass Hybrid Matching**: Exact match is O(n^2) but computationally trivial and free; fuzzy + LLM is applied only to the small pending delta (~15-20% of records), preserving low latency and zero unnecessary API spend.
- **Groq LPU Inference**: Provides sub-500ms latency per LLM inference call, critical for maintaining high batch throughput.
- **Supabase Postgres with asyncpg**: Asynchronous ORM execution allows non-blocking background ingestion and high-concurrency report downloads.
- **ChromaDB + SentenceTransformers**: Local, ultra-fast vector retrieval for grounded RAG Q&A without external vector database dependencies.

---

## 5. Known Limitations & Future Improvements
- **Batch Streaming**: Future iterations could leverage Kafka/RabbitMQ for real-time transaction reconciliation rather than scheduled batch CSV uploads.
- **Multi-Currency Support**: Expand normalization to handle automated FX conversion rates for international cross-border settlements.
- **ERP Webhooks**: Direct bi-directional integration with accounting systems (NetSuite, QuickBooks, Tally).

---

## 6. Demo Video
- **Demo Video Link**: [placeholder]
