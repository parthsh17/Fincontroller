# FinController - AI Finance Controller

[![Python 3.11+](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-orange.svg)](https://github.com/langchain-ai/langgraph)
[![Groq](https://img.shields.io/badge/LLM-Groq%20LPU-f55036.svg)](https://groq.com)
[![Streamlit](https://img.shields.io/badge/Frontend-Streamlit-FF4B4B.svg?logo=streamlit)](https://streamlit.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **FinController** is an automated batch 3-way financial reconciliation system designed for modern D2C merchants (e.g., **BrewBox**). It ingests Bank Statements, Payment Gateway Settlement Reports (Razorpay), and Internal ERP Ledgers, runs a multi-pass hierarchical reconciliation pipeline (Exact -> Fuzzy -> Groq LLM Disambiguation), categorizes discrepancies with granular reason codes, generates downloadable executive PDF reports, and provides an interactive ChromaDB-powered Settlement Q&A assistant.

---

## Table of Contents

- [What It Does](#what-it-does)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Quickstart Guide](#quickstart-guide)
  - [1. Prerequisites](#1-prerequisites)
  - [2. Clone and Setup Virtual Environment](#2-clone-and-setup-virtual-environment)
  - [3. Install Dependencies](#3-install-dependencies)
  - [4. Configure Environment Variables](#4-configure-environment-variables)
  - [5. Generate Benchmark Synthetic Data](#5-generate-benchmark-synthetic-data)
  - [6. Run Database Migrations and Start Backend](#6-run-database-migrations-and-start-backend)
  - [7. Launch Streamlit Web UI](#7-launch-streamlit-web-ui)
- [How to Use (End-to-End Workflow)](#how-to-use-end-to-end-workflow)
- [API Reference](#api-reference)
- [Evaluation and Benchmarks](#evaluation-and-benchmarks)
- [Running Automated Tests](#running-automated-tests)
- [Project Directory Structure](#project-directory-structure)
- [Troubleshooting and FAQ](#troubleshooting-and-faq)
- [License](#license)

---

## What It Does

1. **Multi-Source Ingestion and Normalization**: Automatically standardizes varying schema formats, currency symbols (INR / Rs), date structures (`DD-MM-YYYY` / `YYYY-MM-DD`), and transaction identifiers across Bank Statements, Gateway Reports, and ERP Ledgers.
2. **3-Pass Hierarchical Reconciliation DAG**:
   - **Pass 1 (Exact Match)**: Instant 3-way matching on exact amount, date, and reference keys with zero LLM compute cost (deterministic scan).
   - **Pass 2 (Fuzzy Match)**: Tolerates payout settlement lags (T+1/T+2) and minor description noise using RapidFuzz token scoring within configurable tolerance windows.
   - **Pass 3 (Groq LLM Disambiguation)**: Selectively triggers Groq (`llama-3.3-70b-versatile`) **strictly for ambiguous candidate pairs** (50-75% similarity), returning strictly validated Pydantic JSON decisions.
3. **Automated Exception Root-Cause Triage**: Unmatched transactions are audited and tagged with explicit reason codes:
   - `AMOUNT_MISMATCH`: Partial refunds or gateway fee deductions.
   - `MISSING_IN_BANK`: Settlement logged in gateway and ERP but absent from bank statement.
   - `MISSING_IN_RAZORPAY`: Bank deposit without matching payment gateway trace.
   - `DUPLICATE_DETECTED`: Duplicate orders or double charges.
   - `DATE_MISMATCH`: Timing discrepancies exceeding settlement windows.
   - `UNIDENTIFIED`: Uncorrelated entries flagged for manual review.
4. **Interactive Audit Reports and PDF Streaming**: Generates executive-ready PDF audit reports with summary metrics, match distribution breakdowns, and exception audit trails.
5. **Settlement Q&A Agent**: A semantic RAG assistant powered by ChromaDB and SentenceTransformers allowing finance teams to ask natural language questions about settlement details and exceptions.

---

## Architecture

```
                                  [CSV Files]
                       (Bank / Razorpay / Ledger)
                                     |
                                     v
                        [FastAPI POST /api/ingest]
                                     |
                                     v
                +-----------------------------------------+
                |        LangGraph Reconciliation DAG     |
                |                                         |
                |  1. normalize_node                      |
                |         |                               |
                |  2. match_exact_node (Pass 1)           |
                |         |                               |
                |  3. match_fuzzy_node (Pass 2)           |
                |         |                               |
                |  4. match_llm_node (Groq Disambiguate)  |
                |         |                               |
                |  5. exception_node (Reason Coding)      |
                |         |                               |
                |  6. report_node (Metrics & Aggregation) |
                +--------------------+--------------------+
                                     |
                 +-------------------+-------------------+
                 |                                       |
                 v                                       v
    [PostgreSQL (Supabase)]                     [ChromaDB Embeddings]
       (asyncpg / SQLAlchemy)                     (SentenceTransformers)
                 |                                       |
                 v                                       v
       [Report & PDF APIs]                      [Settlement Q&A Chain]
                 |                                       |
                 +-------------------+-------------------+
                                     |
                                     v
                       [Streamlit UI Dashboard]
```

---

## Tech Stack

| Component | Technology | Description |
|---|---|---|
| **Agent Orchestration** | LangGraph, LangChain | Stateful Directed Acyclic Graph (DAG) with per-record conditional state routing |
| **LLM Inference** | Groq (`llama-3.3-70b-versatile`) | Ultra-fast LPU inference for ambiguous candidate matching and Q&A |
| **Backend Framework** | FastAPI, Uvicorn | High-performance asynchronous REST API with non-blocking background workers |
| **Database and ORM** | Supabase (PostgreSQL), SQLAlchemy 2.0, asyncpg | Fully asynchronous persistence for batches, match records, exceptions, and audit logs |
| **Vector Database** | ChromaDB, Sentence-Transformers | Local vector store with `all-MiniLM-L6-v2` embeddings for settlement RAG Q&A |
| **Fuzzy Matching** | RapidFuzz | C++ accelerated string metric token similarity scoring |
| **Data Processing** | Pandas, Pydantic v2 | High-performance CSV parsing, type validation, and serialization |
| **Frontend and Reports** | Streamlit, ReportLab | Interactive 3-page web dashboard and downloadable PDF report generator |
| **Testing and Evaluation** | Pytest, Pytest-asyncio, Rich | Automated pipeline unit testing and rich terminal benchmarking |

---

## Quickstart Guide

### 1. Prerequisites

- **Python**: Version `3.11` or `3.12`
- **Git**: Installed on your system
- **Supabase Account**: A free Supabase PostgreSQL database URL (or local PostgreSQL)
- **Groq API Key**: A free API key from [console.groq.com](https://console.groq.com)

---

### 2. Clone and Setup Virtual Environment

```bash
# Clone the repository
git clone https://github.com/parthsh17/Fincontroller.git
cd Fincontroller

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Windows (CMD):
.\venv\Scripts\activate.bat
# macOS / Linux:
source venv/bin/activate
```

---

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

### 4. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
# Windows PowerShell:
Copy-Item .env.example .env

# macOS / Linux:
cp .env.example .env
```

Edit your `.env` file with your credentials:

```env
# Supabase PostgreSQL asyncpg connection string
SUPABASE_DB_URL=postgresql+asyncpg://postgres:<YOUR_PASSWORD>@<YOUR_HOST>:5432/postgres

# Groq API Key
GROQ_API_KEY=gsk_your_actual_groq_api_key

# Model and Vector DB configurations (defaults work out-of-the-box)
CHROMA_PATH=./chroma_data
CHROMA_COLLECTION=settlement_docs
LLM_MODEL=llama-3.3-70b-versatile
LLM_MAX_RETRIES=3
FUZZY_THRESHOLD=75
FUZZY_AMOUNT_TOLERANCE_PCT=5.0
FUZZY_AMOUNT_TOLERANCE_ABS=200
FUZZY_DATE_WINDOW_DAYS=2
LLM_CONFIDENCE_THRESHOLD=0.75
```

> **Note on Database URL**: The backend automatically normalizes `postgresql://` or `postgres://` to `postgresql+asyncpg://` so standard Supabase URLs connect seamlessly.

---

### 5. Generate Benchmark Synthetic Data

Generate 100 sample transactions with controlled discrepancy noise (exact matches, T+1 settlement lags, amount mismatches, missing records, duplicates):

```bash
python data/generators/generate_batch.py --seed 42 --count 100
```

This creates:
- `data/samples/bank_statement.csv`
- `data/samples/settlement_report.csv`
- `data/samples/internal_ledger.csv`
- `data/testset/held_out.json` (Ground truth for evaluation)

---

### 6. Run Database Migrations and Start Backend

Apply database migrations:

```bash
alembic upgrade head
```

Start the FastAPI application:

```bash
uvicorn backend.main:app --reload --port 8000
```

- **Interactive API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

### 7. Launch Streamlit Web UI

Open a **separate terminal window**, activate your virtual environment, and run:

```bash
# Windows:
.\venv\Scripts\Activate.ps1
streamlit run ui/dashboard.py
```

The web dashboard will open automatically in your browser at **[http://localhost:8501](http://localhost:8501)**.

---

## How to Use (End-to-End Workflow)

```
 [1. Upload CSVs] ---> [2. Run Agent DAG] ---> [3. Audit Results & PDF] ---> [4. Ask Q&A]
```

### 1. Upload and Ingest
1. Go to the **"1. Upload & Run"** tab in the Streamlit UI.
2. Select the three generated CSV files from `data/samples/`:
   - `bank_statement.csv`
   - `settlement_report.csv`
   - `internal_ledger.csv`
3. Click **"Run Reconciliation"**.
4. The backend ingests the records and runs the LangGraph DAG asynchronously in the background.
5. The live progress bar will track status from `PENDING` -> `RUNNING` -> `DONE`.

### 2. Inspect Audit Results and Download PDF
1. Navigate to the **"2. Reconciliation Results"** tab.
2. View matched transactions color-coded by match stage:
   - **Exact (Pass 1)**
   - **Fuzzy (Pass 2)**
   - **LLM Disambiguated (Pass 3)**
3. View the **Exceptions & Reason Codes** panel with grouped expandable error explanations.
4. Click **"Download PDF Report"** to export the formal audit report.

### 3. Ask Settlement Q&A
1. In your terminal, index the batch records into the ChromaDB vector database:
   ```bash
   python agent/qa/ingest_docs.py --batch_id <YOUR_BATCH_ID>
   ```
2. On the **"3. Settlement Q&A"** tab, ask natural language questions or use the quick chips:
   - *"Why was there an amount mismatch?"*
   - *"How many records are missing from the bank?"*
   - *"List all DUPLICATE_DETECTED exceptions"*

---

## API Reference

### 1. Ingest 3-Way CSV Files
```bash
curl -X POST "http://localhost:8000/api/ingest" \
  -F "bank_file=@data/samples/bank_statement.csv" \
  -F "razorpay_file=@data/samples/settlement_report.csv" \
  -F "ledger_file=@data/samples/internal_ledger.csv"
```
**Response:**
```json
{
  "batch_id": "8f8c47d3-d8ea-4819-86a3-6b3a0eef8851",
  "total_records": 298,
  "status": "pending"
}
```

### 2. Poll Batch Status
```bash
curl "http://localhost:8000/api/batch/8f8c47d3-d8ea-4819-86a3-6b3a0eef8851/status"
```
**Response:**
```json
{
  "id": "8f8c47d3-d8ea-4819-86a3-6b3a0eef8851",
  "status": "done",
  "total_records": 298,
  "matched": 76,
  "exceptions": 18
}
```

### 3. Get Full Reconciliation JSON Report
```bash
curl "http://localhost:8000/api/report/8f8c47d3-d8ea-4819-86a3-6b3a0eef8851"
```

### 4. Download PDF Audit Report
```bash
curl -O "http://localhost:8000/api/report/8f8c47d3-d8ea-4819-86a3-6b3a0eef8851/pdf"
```

### 5. Settlement Q&A Query
```bash
curl -X POST "http://localhost:8000/api/qa" \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"Why was there an amount mismatch?\", \"batch_id\": \"8f8c47d3-d8ea-4819-86a3-6b3a0eef8851\"}"
```

---

## Evaluation and Benchmarks

The project includes an evaluation suite that validates reconciliation performance against ground truth records in `data/testset/held_out.json`.

Run the benchmark evaluation:

```bash
python eval/run_eval.py --batch_id <YOUR_BATCH_ID>
```

### Benchmark Results (Seed 42 Dataset)

| Metric | Target | Result | Status |
|---|---|---|---|
| **Overall Match Rate** | >= 80.0% | **88.5%** | PASSED |
| **False Match Rate (FMR)** | <= 2.0% | **0.0%** | PASSED |
| **Precision** | >= 0.95 | **1.0000** | PASSED |
| **Recall** | >= 0.85 | **0.8850** | PASSED |
| **F1 Score** | >= 0.90 | **0.9390** | PASSED |
| **Reconciliation Throughput** | >= 50 rec/s | **~110 rec/sec** | PASSED |

---

## Running Automated Tests

Run the Pytest suite covering exact matches, settlement lag, amount mismatch, duplicate detection, and LLM guard validation:

```bash
pytest eval/test_pipeline.py -v
```

**Expected Output:**
```
eval/test_pipeline.py::test_exact_match PASSED                           [ 16%]
eval/test_pipeline.py::test_settlement_lag PASSED                        [ 33%]
eval/test_pipeline.py::test_amount_mismatch PASSED                       [ 50%]
eval/test_pipeline.py::test_duplicate_detected PASSED                    [ 66%]
eval/test_pipeline.py::test_llm_validation_guard PASSED                  [ 83%]
eval/test_pipeline.py::test_batch_throughput PASSED                      [100%]

============================= 6 passed in 17.67s ==============================
```

---

## Project Directory Structure

```
Fincontroller/
|-- backend/
|   |-- main.py                  # FastAPI application entrypoint & lifecycle
|   |-- config.py                # Pydantic Settings configuration loader
|   |-- routers/
|   |   |-- ingest.py            # POST /api/ingest & GET /api/batch/{id}/status
|   |   |-- report.py            # GET /api/report/{id} & PDF generator
|   |   `-- qa.py                # POST /api/qa Q&A endpoint
|   |-- models/
|   |   |-- record.py            # NormalizedRecord & RawRecord Pydantic models
|   |   |-- match.py             # MatchResult, ExceptionRecord, LLMMatchDecision
|   |   `-- batch.py             # BatchJob, BatchStatus, BatchReport schemas
|   `-- db/
|       |-- engine.py            # Async SQLAlchemy engine & session maker
|       |-- tables.py            # Database tables (batches, matches, exceptions, logs)
|       `-- migrations/          # Alembic async migration environment
|-- agent/
|   |-- graph.py                 # Compiled LangGraph StateGraph & runner
|   |-- state.py                 # BatchState TypedDict schema
|   |-- nodes/
|   |   |-- normalize.py         # DB record loading & schema normalization
|   |   |-- match_exact.py       # Pass 1: Deterministic 3-way exact matching
|   |   |-- match_fuzzy.py       # Pass 2: RapidFuzz similarity with T+1 tolerance
|   |   |-- match_llm.py         # Pass 3: Groq LLM disambiguation
|   |   |-- exception.py         # Exception reasoning & classification
|   |   `-- report.py            # Metric calculation & batch finalization
|   |-- tools/
|   |   |-- groq_client.py       # Async Groq SDK wrapper with backoff retries
|   |   `-- fuzzy.py             # RapidFuzz similarity & tolerance helpers
|   `-- qa/
|       |-- ingest_docs.py       # ChromaDB document indexing CLI
|       `-- qa_chain.py          # Vector retrieval & RAG answer synthesis
|-- data/
|   |-- generators/
|   |   |-- generate_batch.py    # Synthetic dataset generator CLI
|   |   `-- noise.py             # Controlled financial discrepancy noise rules
|   |-- samples/                 # Sample CSV files (Bank, Razorpay, Ledger)
|   `-- testset/                 # Held-out evaluation ground truth JSON
|-- eval/
|   |-- run_eval.py              # Rich terminal evaluation benchmark tool
|   |-- metrics.py               # Precision, Recall, F1, FMR pure metric functions
|   `-- test_pipeline.py         # Pytest unit & integration test suite
|-- ui/
|   `-- dashboard.py             # Streamlit 3-page web application
|-- requirements.txt             # Project dependencies
|-- .env.example                 # Environment configuration template
`-- README.md                    # Project documentation
```