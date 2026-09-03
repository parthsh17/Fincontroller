# FinController — AI Finance Controller

> Automated batch 3-way financial reconciliation agent with deterministic exact matching, fuzzy lag-tolerance, Groq LLM disambiguation, exception reason-coding, and ChromaDB-powered settlement Q&A.

---

## What It Does

- **3-Way Multi-Source Ingestion**: Ingests Bank Statements, Razorpay Settlement Reports, and Internal Ledgers, normalizing dates, currencies, and reference identifiers across varying schemas.
- **Hierarchical Two-Pass Reconciliation DAG**: Executes fast deterministic matching (Pass 1: Exact), followed by date/amount tolerance fuzzy matching (Pass 2), with Groq LLM fallback reserved strictly for ambiguous records.
- **Automated Exception Triage & Q&A**: Flags discrepancies with granular reason codes (`AMOUNT_MISMATCH`, `MISSING_IN_BANK`, `DUPLICATE_DETECTED`, `DATE_MISMATCH`), produces downloadable PDF audit reports, and provides an interactive RAG Q&A interface.

---

## Architecture

```
                                  [CSV Files]
                       (Bank / Razorpay / Ledger)
                                     │
                                     ▼
                        [FastAPI POST /api/ingest]
                                     │
                                     ▼
                ┌─────────────────────────────────────────┐
                │        LangGraph Reconciliation DAG     │
                │                                         │
                │  1. normalize_node                      │
                │         │                               │
                │  2. match_exact_node (Pass 1)           │
                │         │                               │
                │  3. match_fuzzy_node (Pass 2)           │
                │         │                               │
                │  4. match_llm_node (Groq Ambiguity)     │
                │         │                               │
                │  5. exception_node (Reason Coding)      │
                │         │                               │
                │  6. report_node (Metrics & Aggregation) │
                └────────────────────┬────────────────────┘
                                     │
                 ┌───────────────────┴───────────────────┐
                 ▼                                       ▼
    [PostgreSQL (Supabase)]                     [ChromaDB Embeddings]
       (asyncpg / SQLAlchemy)                     (SentenceTransformers)
                 │                                       │
                 ▼                                       ▼
       [Report & PDF APIs]                      [Settlement Q&A Chain]
                 │                                       │
                 └───────────────────┬───────────────────┘
                                     ▼
                       [Streamlit UI Dashboard]
```

---

## Tech Stack

| Component | Technology / Library | Purpose |
|---|---|---|
| **Agent Orchestration** | LangGraph, LangChain | Stateful DAG with dynamic record routing |
| **LLM Inference** | Groq (`openai/gpt-oss-120b`) | Candidate disambiguation & Q&A |
| **Backend Framework** | FastAPI, Uvicorn | Async REST API & background task execution |
| **Database & ORM** | PostgreSQL (Supabase), SQLAlchemy 2.0, asyncpg | Async persistence of batches, matches, exceptions |
| **Vector Database** | ChromaDB, Sentence-Transformers | Semantic settlement document search & RAG |
| **Fuzzy Matching** | RapidFuzz | Levenshtein token sort similarity |
| **Data Processing** | Pandas, Pydantic v2 | High-performance CSV ingestion & validation |
| **Reporting & UI** | Streamlit, ReportLab | Interactive dashboard & PDF generation |
| **Testing & Evaluation** | Pytest, Pytest-asyncio, Rich | Automated test suite & benchmark reporting |

---

## Quickstart

### 1. Clone & Setup Environment

```bash
git clone https://github.com/your-org/fincontroller.git
cd fincontroller

# Create and activate virtual environment
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy the template configuration and specify your database and Groq credentials:

```bash
cp .env.example .env
```

Edit `.env`:
```env
SUPABASE_DB_URL=postgresql+asyncpg://postgres:<password>@<host>:5432/postgres
GROQ_API_KEY=gsk_...
CHROMA_PATH=./chroma_data
CHROMA_COLLECTION=settlement_docs
LLM_MODEL=openai/gpt-oss-120b
LLM_MAX_RETRIES=3
FUZZY_THRESHOLD=75
FUZZY_AMOUNT_TOLERANCE_PCT=5.0
FUZZY_AMOUNT_TOLERANCE_ABS=200
FUZZY_DATE_WINDOW_DAYS=2
LLM_CONFIDENCE_THRESHOLD=0.75
```

### 3. Generate Synthetic Benchmark Dataset

```bash
python data/generators/generate_batch.py --seed 42 --count 100
```

### 4. Run Migrations & Start Backend

```bash
alembic upgrade head
uvicorn backend.main:app --reload --port 8000
```

### 5. Launch Streamlit UI

```bash
streamlit run ui/dashboard.py
```

---

## Evaluation Benchmark

Run the evaluation against the held-out ground truth testset:

```bash
python eval/run_eval.py --batch_id <BATCH_ID>
```

### Benchmark Results (Seed 42 Benchmark)

| Metric | Target | Result |
|---|---|---|
| **Overall Match Rate** | $\ge 80.0\%$ | **88.5%** |
| **False Match Rate (FMR)** | $\le 2.0\%$ | **0.0%** |
| **Precision** | $\ge 0.95$ | **1.0000** |
| **Recall** | $\ge 0.85$ | **0.8850** |
| **F1 Score** | $\ge 0.90$ | **0.9390** |
| **Throughput** | $\ge 50\text{ rec/s}$ | **~110 rec/sec** |

---

## Running Automated Tests

```bash
pytest eval/test_pipeline.py -v
```

---

## API Reference

### 1. Ingest Batch
```bash
curl -X POST "http://localhost:8000/api/ingest" \
  -F "bank_file=@data/samples/bank_statement.csv" \
  -F "razorpay_file=@data/samples/settlement_report.csv" \
  -F "ledger_file=@data/samples/internal_ledger.csv"
```

### 2. Poll Status
```bash
curl "http://localhost:8000/api/batch/{batch_id}/status"
```

### 3. Get Reconciliation Report
```bash
curl "http://localhost:8000/api/report/{batch_id}"
```

### 4. Download PDF Audit Report
```bash
curl -O "http://localhost:8000/api/report/{batch_id}/pdf"
```

### 5. Ask Settlement Question
```bash
curl -X POST "http://localhost:8000/api/qa" \
  -H "Content-Type: application/json" \
  -d '{"question": "Why was there an amount mismatch?", "batch_id": "{batch_id}"}'
```

---

## Project Structure

```
fincontroller/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── routers/
│   │   ├── ingest.py
│   │   ├── report.py
│   │   └── qa.py
│   ├── models/
│   │   ├── record.py
│   │   ├── match.py
│   │   └── batch.py
│   └── db/
│       ├── engine.py
│       ├── tables.py
│       └── migrations/
├── agent/
│   ├── graph.py
│   ├── state.py
│   ├── nodes/
│   │   ├── normalize.py
│   │   ├── match_exact.py
│   │   ├── match_fuzzy.py
│   │   ├── match_llm.py
│   │   ├── exception.py
│   │   └── report.py
│   ├── tools/
│   │   ├── groq_client.py
│   │   └── fuzzy.py
│   └── qa/
│       ├── ingest_docs.py
│       └── qa_chain.py
├── data/
│   ├── generators/
│   │   ├── generate_batch.py
│   │   └── noise.py
│   ├── samples/
│   └── testset/
├── eval/
│   ├── run_eval.py
│   ├── metrics.py
│   └── test_pipeline.py
├── ui/
│   └── dashboard.py
├── alembic.ini
├── requirements.txt
├── .env.example
├── README.md
└── SUBMISSION.md
```
