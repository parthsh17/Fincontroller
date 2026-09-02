# fincontroller — Build Plan
## Track 04 · AI Finance Controller · Razorpay AI Buildathon 2026

---

## Context for Agent

You are building `fincontroller` — a batch financial reconciliation agent for the Razorpay AI Buildathon (Track 04: AI Finance Controller). The merchant context is **BrewBox**, a fictional D2C coffee subscription brand.

**What the system does:**
Ingests 3 CSV files (bank statement, Razorpay settlement report, internal ledger), matches records across two passes (exact → fuzzy/LLM), produces a reconciliation report with `match_rate`, `false_match_rate`, and an exception list with reason codes. Also exposes a Settlement Q&A agent over the reconciled data.

**Hard constraints — never violate these:**
- Database: Supabase (hosted PostgreSQL). Use `asyncpg` driver. Connection via `SUPABASE_DB_URL` from `.env`.
- No Docker. All services run locally via CLI.
- Pydantic v2 syntax only — never v1.
- Never use `eval()` or `json.loads()` on raw LLM output — always parse through a Pydantic model.
- LLM node (Groq) must only fire for ambiguous records, not all records.
- Every matched result must have a `confidence` score. Every exception must have a `reason_code`.

---

## Repo Structure

Create this exact structure at project root:

```
fincontroller/
├── backend/
│   ├── main.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── ingest.py
│   │   ├── report.py
│   │   └── qa.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── record.py
│   │   ├── match.py
│   │   └── batch.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── tables.py
│   │   └── migrations/
│   │       └── env.py
│   └── config.py
├── agent/
│   ├── __init__.py
│   ├── graph.py
│   ├── state.py
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── normalize.py
│   │   ├── match_exact.py
│   │   ├── match_fuzzy.py
│   │   ├── match_llm.py
│   │   ├── exception.py
│   │   └── report.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── groq_client.py
│   │   └── fuzzy.py
│   └── qa/
│       ├── __init__.py
│       ├── ingest_docs.py
│       └── qa_chain.py
├── data/
│   ├── generators/
│   │   ├── generate_batch.py
│   │   └── noise.py
│   ├── samples/
│   │   ├── bank_statement.csv
│   │   ├── settlement_report.csv
│   │   └── internal_ledger.csv
│   └── testset/
│       └── held_out.json
├── eval/
│   ├── run_eval.py
│   ├── metrics.py
│   └── test_pipeline.py
├── ui/
│   └── dashboard.py
├── .env.example
├── requirements.txt
├── alembic.ini
└── README.md
```

---

## requirements.txt

Create this file exactly:

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
pydantic==2.7.0
pydantic-settings==2.3.0
sqlalchemy[asyncio]==2.0.30
asyncpg==0.29.0
alembic==1.13.1
langgraph==0.2.0
langchain==0.2.0
langchain-groq==0.1.6
groq==0.9.0
rapidfuzz==3.9.0
pandas==2.2.2
chromadb==0.5.3
sentence-transformers==3.0.1
faker==26.0.0
streamlit==1.36.0
reportlab==4.2.2
pytest==8.2.2
pytest-asyncio==0.23.7
python-dotenv==1.0.1
httpx==0.27.0
rich==13.7.1
loguru==0.7.2
```

---

## .env.example

Create this file exactly:

```
SUPABASE_DB_URL=postgresql+asyncpg://postgres:<password>@<host>:5432/postgres
GROQ_API_KEY=
CHROMA_PATH=./chroma_data
CHROMA_COLLECTION=settlement_docs
LLM_MODEL=llama3-70b-8192
LLM_MAX_RETRIES=3
FUZZY_THRESHOLD=75
FUZZY_AMOUNT_TOLERANCE_PCT=5.0
FUZZY_AMOUNT_TOLERANCE_ABS=200
FUZZY_DATE_WINDOW_DAYS=2
LLM_CONFIDENCE_THRESHOLD=0.75
```

---

## M0 — Scaffold + Config

**Files to create:** `backend/config.py`, `backend/main.py`, `backend/db/engine.py`

### backend/config.py
```python
# Use pydantic-settings BaseSettings.
# Load all env vars from .env using python-dotenv.
# Fields: supabase_db_url, groq_api_key, chroma_path, chroma_collection,
#         llm_model, llm_max_retries (int), fuzzy_threshold (float),
#         fuzzy_amount_tolerance_pct (float), fuzzy_amount_tolerance_abs (float),
#         fuzzy_date_window_days (int), llm_confidence_threshold (float).
# Export a single `settings` instance.
```

### backend/db/engine.py
```python
# Create SQLAlchemy async engine using settings.supabase_db_url.
# Use asyncpg driver (already in the URL scheme).
# Create async_sessionmaker bound to the engine.
# Export: engine, async_session_maker, get_db (FastAPI dependency — yields AsyncSession).
```

### backend/main.py
```python
# FastAPI app with lifespan:
#   on startup: run alembic upgrade head programmatically, log "DB migrations applied"
#   on shutdown: dispose engine
# Include routers: ingest, report, qa (prefix /api)
# Add GET /health → { "status": "ok", "service": "fincontroller" }
# CORS: allow all origins (local dev)
# Use loguru for all logging — not Python's built-in logging
```

### alembic.ini + backend/db/migrations/env.py
```
# Configure alembic.ini to point script_location = backend/db/migrations
# In env.py: import engine from backend.db.engine, use run_async_migrations pattern
# target_metadata = Base.metadata (import Base from backend.db.tables)
```

**Verification:** `uvicorn backend.main:app --reload` starts, `GET /health` returns 200.

---

## M1 — Data Models + DB Tables

**Files to create:** `backend/db/tables.py`, `backend/models/record.py`, `backend/models/match.py`, `backend/models/batch.py`

### backend/db/tables.py
```python
# SQLAlchemy 2.0 declarative Base with async support.
# All UUIDs use uuid.uuid4 default. All datetimes are UTC.

# Table: batches
#   id: UUID PK
#   status: String — 'pending' | 'running' | 'done' | 'failed'
#   total_records: Integer default 0
#   matched_exact: Integer default 0
#   matched_fuzzy: Integer default 0
#   matched_llm: Integer default 0
#   total_exceptions: Integer default 0
#   match_rate: Float nullable
#   false_match_rate: Float nullable
#   llm_calls_made: Integer default 0
#   avg_llm_latency_ms: Float nullable
#   started_at: DateTime nullable
#   completed_at: DateTime nullable
#   created_at: DateTime default utcnow

# Table: normalized_records
#   id: UUID PK
#   batch_id: UUID FK → batches.id
#   source: String — 'bank' | 'razorpay' | 'ledger'
#   amount: Numeric(10,2)
#   date: Date
#   ref_id: String nullable
#   description: String nullable
#   raw: JSONB  (store original CSV row as dict)
#   created_at: DateTime default utcnow

# Table: match_results
#   id: UUID PK
#   batch_id: UUID FK → batches.id
#   bank_record_id: UUID FK → normalized_records.id nullable
#   razorpay_record_id: UUID FK → normalized_records.id nullable
#   ledger_record_id: UUID FK → normalized_records.id nullable
#   match_type: String — 'exact' | 'fuzzy' | 'llm'
#   confidence: Float
#   notes: String nullable

# Table: exception_records
#   id: UUID PK
#   batch_id: UUID FK → batches.id
#   record_ids: JSONB  (list of UUID strings)
#   reason_code: String — one of:
#     'AMOUNT_MISMATCH' | 'MISSING_IN_BANK' | 'MISSING_IN_RAZORPAY' |
#     'DUPLICATE_DETECTED' | 'DATE_MISMATCH' | 'UNIDENTIFIED'
#   description: String
#   raw_records: JSONB  (dict of source → raw row)

# Table: qa_logs
#   id: UUID PK
#   batch_id: UUID FK → batches.id
#   question: String
#   answer: String
#   sources: JSONB  (list of source chunk strings)
#   created_at: DateTime default utcnow
```

### backend/models/record.py
```python
# Pydantic v2 models (not SQLAlchemy — these are API/agent-layer schemas):

# RawRecord: source (Literal['bank','razorpay','ledger']), raw_row (dict)

# NormalizedRecord:
#   id: UUID
#   batch_id: UUID
#   source: Literal['bank','razorpay','ledger']
#   amount: Decimal
#   date: date
#   ref_id: str | None
#   description: str | None
#   raw: dict
#
# Validators (field_validator, pydantic v2):
#   amount: strip '₹', ',', ' ' then cast to Decimal
#   date: parse both 'dd-mm-yyyy' and 'yyyy-mm-dd' formats
#   ref_id: strip whitespace, set None if empty string
```

### backend/models/match.py
```python
# Pydantic v2:

# MatchResult:
#   id: UUID
#   batch_id: UUID
#   bank_record: NormalizedRecord | None
#   razorpay_record: NormalizedRecord | None
#   ledger_record: NormalizedRecord | None
#   match_type: Literal['exact','fuzzy','llm']
#   confidence: float  (0.0–1.0)
#   notes: str | None

# ExceptionRecord:
#   id: UUID
#   batch_id: UUID
#   record_ids: list[UUID]
#   reason_code: Literal['AMOUNT_MISMATCH','MISSING_IN_BANK','MISSING_IN_RAZORPAY',
#                        'DUPLICATE_DETECTED','DATE_MISMATCH','UNIDENTIFIED']
#   description: str
#   raw_records: dict

# LLMMatchDecision (used to parse Groq output — never raw JSON):
#   matched: bool
#   confidence: float
#   reason: str
#   match_type: str
```

### backend/models/batch.py
```python
# Pydantic v2:

# BatchJob: mirrors batches table — used for API responses
# BatchStatus: id, status, total_records, matched (sum of exact+fuzzy+llm), exceptions
# BatchReport: full report response shape:
#   batch_id, status, summary (dict with all metrics), 
#   matches (list[MatchResult]), exceptions (list[ExceptionRecord])
```

**Verification:** `alembic revision --autogenerate -m "init"` detects all 5 tables. `alembic upgrade head` creates them in Supabase.

---

## M2 — Synthetic Data Generator

**Files to create:** `data/generators/noise.py`, `data/generators/generate_batch.py`

### data/generators/noise.py
```python
# NoisyBatch dataclass:
#   bank_rows: list[dict]
#   razorpay_rows: list[dict]
#   ledger_rows: list[dict]
#   ground_truth: list[dict]  (for held_out.json)

# inject_noise(base_records, seed) → NoisyBatch
# Apply these noise rules to base_records (list of clean 3-way matches):
#
# Rule 1 — EXACT (60% of records):
#   All 3 sources have identical amount, date, ref_id. No modification.
#
# Rule 2 — SETTLEMENT_LAG (15% of records):
#   razorpay date = ledger date + 1 day. Bank date = ledger date.
#   Simulate T+1 payout delay.
#
# Rule 3 — AMOUNT_MISMATCH (10% of records):
#   Bank amount = original - random.uniform(50, 200).
#   Razorpay and ledger keep original. Simulate fee deduction / partial refund.
#
# Rule 4 — MISSING_IN_BANK (8% of records):
#   Record exists in razorpay + ledger but NOT added to bank_rows.
#
# Rule 5 — DUPLICATE_DETECTED (5% of records):
#   Same ledger row added twice with different UUID.
#
# Rule 6 — UNIDENTIFIED (2% of records):
#   All ref_ids randomized, description randomized. No match signal.
#
# ground_truth entry per record:
#   { "record_ref": str, "expected": "match" | "exception", "reason": str }
```

### data/generators/generate_batch.py
```python
# CLI: python data/generators/generate_batch.py --seed 42 --count 100
#
# Generates base_records (count clean 3-way match dicts):
#   amount: random Decimal between 499 and 14999 (Indian merchant range)
#   date: random date in October 2026
#   ref_id: f"REF{random 6-digit int}"
#   description: one of ["Coffee subscription", "BrewBox Premium", 
#                        "BrewBox Starter", "BrewBox Connoisseur", "Refund"]
#
# Column names per source:
#   bank_statement.csv:      date, amount, ref_id, description
#   settlement_report.csv:   date, amount, settlement_id, payment_id, description
#   internal_ledger.csv:     date, amount, order_id, customer_name, status
#
# Pass through inject_noise(base_records, seed).
# Save CSVs to data/samples/.
# Save ground_truth as data/testset/held_out.json (first 20 records only).
# Print summary: total rows per file, noise distribution counts.
# --seed flag makes all random calls deterministic (use random.seed + numpy.random.seed).
```

**Verification:** Running with `--seed 42` twice produces identical files. Noise counts roughly match percentages. `held_out.json` has 20 entries each with `expected` field.

---

## M3 — Ingest + Normalize

**Files to create:** `backend/routers/ingest.py`, `agent/nodes/normalize.py`

### backend/routers/ingest.py
```python
# Router prefix: /api
# POST /ingest
#   Request: multipart/form-data
#   Fields: 
#     bank_file: UploadFile (CSV)
#     razorpay_file: UploadFile (CSV)
#     ledger_file: UploadFile (CSV)
#
#   Steps:
#   1. Create BatchJob row in DB with status='pending'
#   2. Read each CSV into pandas DataFrame
#   3. For each row in each DataFrame, call normalize_record(row, source, batch_id)
#      from agent/nodes/normalize.py
#   4. Bulk insert all NormalizedRecord rows to normalized_records table
#   5. Update BatchJob.total_records = total inserted
#   6. Trigger agent graph as FastAPI BackgroundTask: 
#      background_tasks.add_task(run_graph, batch_id)
#      (run_graph imported from agent/graph.py)
#   7. Return: { "batch_id": str, "total_records": int, "status": "pending" }
#
# GET /batch/{batch_id}/status
#   Query batches table, return BatchStatus model.
```

### agent/nodes/normalize.py
```python
# normalize_record(raw_row: dict, source: str, batch_id: UUID) → NormalizedRecord
#
# Column mapping per source (handle case-insensitive column names):
#   bank:     date='date', amount='amount', ref_id='ref_id', description='description'
#   razorpay: date='date', amount='amount', ref_id='settlement_id', description='description'
#   ledger:   date='date', amount='amount', ref_id='order_id', description='customer_name'
#
# Use NormalizedRecord Pydantic model — validators handle:
#   amount cleaning (strip ₹, comma)
#   date parsing (dd-mm-yyyy and yyyy-mm-dd)
#   ref_id whitespace stripping
#
# On ValidationError: log warning with loguru, return None.
# Caller (ingest.py) must filter out None values before bulk insert.
```

**Verification:** POST `/api/ingest` with 3 sample CSVs creates a batch, inserts ~300 normalized records, returns batch_id. GET `/api/batch/{id}/status` returns `pending` then `running`.

---

## M4 — Match Pass 1 (Exact)

**File to create:** `agent/nodes/match_exact.py`

### agent/nodes/match_exact.py
```python
# exact_match_node(state: BatchState) → BatchState
#
# Input: state.all_records (dict keyed by source: list[NormalizedRecord])
# 
# Algorithm:
#   For each ledger record L:
#     For each bank record B (not in matched_ids):
#       For each razorpay record R (not in matched_ids):
#         Check all 3 conditions:
#           1. L.amount == B.amount == R.amount  (Decimal equality)
#           2. L.date == B.date == R.date  (exact date equality)
#           3. If all 3 have ref_id: L.ref_id == B.ref_id or R.ref_id 
#              (ref_ids differ across sources — only check within source pairs)
#         If all match:
#           Create MatchResult(match_type='exact', confidence=1.0)
#           Add L.id, B.id, R.id to state.matched_ids
#           Append to state.match_results
#           Break inner loops
#
#   After loop:
#     state.pending_records = all records NOT in state.matched_ids
#     Write all MatchResult objects to match_results table (bulk insert)
#     Update BatchJob.matched_exact in DB
#
# Return updated state.
# Use loguru to log: exact matches found, pending count.
```

**Verification:** On the synthetic batch (seed 42), exact matches should cover ~60% of records. `state.pending_records` should have ~40% remaining.

---

## M5 — Match Pass 2 (Fuzzy + LLM)

**Files to create:** `agent/tools/fuzzy.py`, `agent/tools/groq_client.py`, `agent/nodes/match_fuzzy.py`, `agent/nodes/match_llm.py`

### agent/tools/fuzzy.py
```python
# fuzzy_score(a: str, b: str) → float
#   Use rapidfuzz.fuzz.token_sort_ratio(a, b) / 100.0
#   Handle None inputs: return 0.0 if either is None
#
# amount_within_tolerance(a: Decimal, b: Decimal, pct: float, abs_tol: float) → bool
#   Return True if abs(a - b) <= max(a * pct/100, abs_tol)
#
# date_within_window(a: date, b: date, window_days: int) → bool
#   Return True if abs((a - b).days) <= window_days
```

### agent/tools/groq_client.py
```python
# GroqClient class:
#   __init__: init Groq SDK client with settings.groq_api_key
#   
#   async match_records(record_a: dict, record_b: dict) → LLMMatchDecision:
#     System prompt:
#       "You are a financial reconciliation assistant. Given two financial 
#        records from different sources, determine if they represent the same 
#        transaction. Respond ONLY with valid JSON matching this exact schema:
#        { \"matched\": boolean, \"confidence\": float 0-1, 
#          \"reason\": string, \"match_type\": string }
#        Do not include any text outside the JSON."
#     User prompt: f"Record A: {json.dumps(record_a)}\nRecord B: {json.dumps(record_b)}"
#     Call settings.llm_model with max_tokens=200
#     Parse response.choices[0].message.content through LLMMatchDecision Pydantic model
#     On ValidationError or JSONDecodeError: return None (caller routes to exception)
#     Retry up to settings.llm_max_retries with exponential backoff (1s, 2s, 4s)
#     Log: call latency, input/output tokens, matched decision
#     Track total calls and cumulative latency for metrics
```

### agent/nodes/match_fuzzy.py
```python
# fuzzy_match_node(state: BatchState) → BatchState
#
# Input: state.pending_records (records not matched in Pass 1)
# Group pending by source: pending_bank, pending_razorpay, pending_ledger
#
# Algorithm:
#   For each ledger record L in pending_ledger:
#     For each bank record B in pending_bank (not in matched_ids):
#       desc_score = fuzzy_score(L.description, B.description)
#       amt_ok = amount_within_tolerance(L.amount, B.amount, ...)
#       date_ok = date_within_window(L.date, B.date, ...)
#       
#       If desc_score >= FUZZY_THRESHOLD and amt_ok and date_ok:
#         Find matching razorpay record R with same criteria
#         If R found:
#           confidence = (desc_score / 100) * 0.95  # cap at 0.95
#           Create MatchResult(match_type='fuzzy', confidence=confidence)
#           Add to matched_ids, match_results
#       
#       Elif desc_score >= 50 (ambiguous — possible match):
#         Add (L, B) pair to state.ambiguous_pairs for LLM node
#
# Write fuzzy matches to DB. Update BatchJob.matched_fuzzy.
# Update state.pending_records: remove newly matched records.
# Return updated state.
```

### agent/nodes/match_llm.py
```python
# llm_match_node(state: BatchState) → BatchState
#
# Input: state.ambiguous_pairs (list of record pairs from fuzzy node)
# 
# For each (record_a, record_b) pair:
#   Call groq_client.match_records(record_a.dict(), record_b.dict())
#   If result is None: route pair to state.unmatched_after_llm
#   If result.matched and result.confidence > LLM_CONFIDENCE_THRESHOLD:
#     Find corresponding third record (razorpay) via fuzzy scan
#     Create MatchResult(match_type='llm', confidence=result.confidence, notes=result.reason)
#     Add to matched_ids, match_results
#   Else:
#     Add records to state.unmatched_after_llm
#
# Write LLM matches to DB. Update BatchJob.matched_llm, llm_calls_made, avg_llm_latency_ms.
# Update state.pending_records: only truly unmatched remain.
# Return updated state.
#
# IMPORTANT: LLM is only called for ambiguous_pairs — never called on all records.
```

**Verification:** After both passes, `state.pending_records` should be ~10-12% of original batch (exceptions only). LLM call count should be much lower than total records.

---

## M6 — Exception Handler + LangGraph DAG

**Files to create:** `agent/nodes/exception.py`, `agent/nodes/report.py`, `agent/state.py`, `agent/graph.py`

### agent/state.py
```python
# BatchState as TypedDict (LangGraph requires TypedDict, not dataclass):
#
# batch_id: str
# all_records: dict[str, list]       # source → list of NormalizedRecord dicts
# matched_ids: set[str]              # UUIDs of all matched records
# match_results: list[dict]          # accumulated MatchResult dicts
# ambiguous_pairs: list[tuple]       # (record_a, record_b) for LLM node
# pending_records: list[dict]        # unmatched after each pass
# unmatched_after_llm: list[dict]    # final unmatched → go to exception node
# exception_records: list[dict]      # accumulated ExceptionRecord dicts
# metrics: dict                      # running metrics dict
#
# Note: Use dict representations, not Pydantic objects, inside state
# (LangGraph serializes state — Pydantic objects cause issues)
```

### agent/nodes/exception.py
```python
# exception_node(state: BatchState) → BatchState
#
# Input: state.unmatched_after_llm + any remaining state.pending_records
# Combine both lists into final_unmatched
#
# For each unmatched record, determine reason_code:
#   Load all_records for comparison
#   Check: does an amount match exist in other sources? → AMOUNT_MISMATCH
#   Check: record in ledger + razorpay, missing from bank? → MISSING_IN_BANK
#   Check: record in ledger + bank, missing from razorpay? → MISSING_IN_RAZORPAY
#   Check: same ref_id appears twice in same source? → DUPLICATE_DETECTED
#   Check: amount matches but date diff > 3 days? → DATE_MISMATCH
#   None of above → UNIDENTIFIED
#
# Build human-readable description per reason_code:
#   AMOUNT_MISMATCH: "Amount differs by ₹{diff} across sources"
#   MISSING_IN_BANK: "Transaction found in Razorpay and ledger but absent from bank statement"
#   etc.
#
# Write ExceptionRecord to DB.
# Update BatchJob.total_exceptions.
# Return updated state.
```

### agent/nodes/report.py
```python
# report_node(state: BatchState) → BatchState
#
# Compute final metrics and update BatchJob:
#   total_records = BatchJob.total_records
#   total_matched = matched_exact + matched_fuzzy + matched_llm
#   match_rate = total_matched / total_records
#   exception_rate = total_exceptions / total_records
#   completed_at = utcnow()
#   status = 'done'
#
# Update BatchJob row in DB with all metric fields.
# Log final summary with rich/loguru:
#   "Batch {id} complete | match_rate={:.1%} | exceptions={}"
# Return state.
```

### agent/graph.py
```python
# Build LangGraph StateGraph with BatchState.
#
# Add nodes:
#   "normalize"    → normalize_node (loads records from DB into state)
#   "match_exact"  → exact_match_node
#   "match_fuzzy"  → fuzzy_match_node
#   "match_llm"    → llm_match_node
#   "exception"    → exception_node
#   "report"       → report_node
#
# Add edges:
#   START → "normalize"
#   "normalize" → "match_exact"
#   "match_exact" → "match_fuzzy"
#   "match_fuzzy" → "match_llm"
#   "match_llm" → "exception"
#   "exception" → "report"
#   "report" → END
#
# Compile graph: app = graph.compile()
#
# async def run_graph(batch_id: str):
#   Update BatchJob.status = 'running', started_at = utcnow()
#   initial_state = { "batch_id": batch_id, "matched_ids": set(), 
#                     "match_results": [], "ambiguous_pairs": [],
#                     "pending_records": [], "unmatched_after_llm": [],
#                     "exception_records": [], "metrics": {},
#                     "all_records": {} }
#   try:
#     await app.ainvoke(initial_state)
#   except Exception as e:
#     Update BatchJob.status = 'failed'
#     loguru.error(f"Graph failed: {e}")
```

**Verification:** `POST /api/ingest` triggers the full graph in background. After ~30 seconds, `GET /api/batch/{id}/status` returns `done`. All tables have data.

---

## M7 — Report API

**File to create:** `backend/routers/report.py`

### backend/routers/report.py
```python
# GET /api/report/{batch_id}
#   Query DB: BatchJob + all MatchResults + all ExceptionRecords for batch
#   Return BatchReport:
#   {
#     "batch_id": str,
#     "status": str,
#     "summary": {
#       "total_records": int,
#       "matched_exact": int,
#       "matched_fuzzy": int,
#       "matched_llm": int,
#       "total_matched": int,
#       "total_exceptions": int,
#       "match_rate": float,
#       "exception_rate": float,
#       "llm_calls_made": int,
#       "avg_llm_latency_ms": float,
#       "duration_seconds": float   # completed_at - started_at
#     },
#     "exception_breakdown": [
#       { "reason_code": str, "count": int, "records": [...] }
#     ],
#     "matches": [ MatchResult dicts ],
#     "exceptions": [ ExceptionRecord dicts ]
#   }
#
# GET /api/report/{batch_id}/pdf
#   Generate PDF using reportlab.
#   Sections:
#     1. Header: "BrewBox — Reconciliation Report" + batch_id + generated timestamp
#     2. Summary table: all metrics from summary dict
#     3. Match breakdown: exact / fuzzy / llm counts with % each
#     4. Exception breakdown: one row per reason_code with count + description
#     5. Exception detail: table of exception records (amount, date, reason_code)
#   Return as StreamingResponse with content-type application/pdf
#   Filename: f"fincontroller_report_{batch_id[:8]}.pdf"
```

**Verification:** GET `/api/report/{id}` returns all fields. PDF downloads and renders all 5 sections correctly.

---

## M8 — Settlement Q&A Agent

**Files to create:** `agent/qa/ingest_docs.py`, `agent/qa/qa_chain.py`, `backend/routers/qa.py`

### agent/qa/ingest_docs.py
```python
# CLI: python agent/qa/ingest_docs.py --batch_id <id>
#
# Steps:
# 1. Load settlement_report.csv from data/samples/
# 2. Load reconciliation report JSON from GET /api/report/{batch_id}
#    (call the local FastAPI endpoint via httpx)
# 3. Create text chunks:
#    Per settlement row: 
#      f"Settlement {row['settlement_id']} on {row['date']}: 
#        ₹{row['amount']} — {row['description']}"
#    Per exception record:
#      f"Exception on {record['date']}: ₹{record['amount']} — 
#        {record['reason_code']}: {record['description']}"
#    Summary chunk:
#      f"Batch {batch_id} reconciliation: match_rate={x}%, 
#        {n} exceptions, {m} matched records"
# 4. Embed chunks using sentence-transformers nomic-embed-text-v1
# 5. Store in ChromaDB collection settings.chroma_collection
#    Metadata per chunk: { batch_id, date, amount, chunk_type }
# 6. Print: "Embedded {n} chunks into ChromaDB"
```

### agent/qa/qa_chain.py
```python
# async def answer_question(question: str, batch_id: str) → dict:
#
# 1. Query ChromaDB: top 5 chunks where metadata.batch_id == batch_id
#    Query text: question
# 2. Build context string from chunk documents
# 3. Call Groq with:
#    System: "You are a financial reconciliation assistant for BrewBox. 
#             Answer questions about settlements and reconciliation results 
#             using ONLY the context provided. Be specific with ₹ amounts 
#             and dates. If the answer is not in the context, respond: 
#             'I don't have that information in the reconciliation data.'"
#    User: f"Context:\n{context}\n\nQuestion: {question}"
# 4. Return:
#    { "answer": str, "sources": list[str], "batch_id": str }
#    sources = the chunk texts used as context
```

### backend/routers/qa.py
```python
# POST /api/qa
#   Request: { "question": str, "batch_id": str }
#   Call answer_question(question, batch_id) from qa_chain
#   Log interaction to qa_logs table
#   Return qa_chain response
```

**Verification:** After running ingest_docs.py, POST `/api/qa` with "Why was ₹2,847 missing?" returns a grounded answer citing specific records, not a hallucinated response.

---

## M9 — Eval Framework

**Files to create:** `eval/metrics.py`, `eval/run_eval.py`, `eval/test_pipeline.py`

### eval/metrics.py
```python
# Pure functions — no DB access, no imports from backend:

# match_rate(total_matched: int, total_records: int) → float
# false_match_rate(false_positives: int, total_matched: int) → float
# exception_rate(total_exceptions: int, total_records: int) → float
# throughput(total_records: int, elapsed_seconds: float) → float
# precision(tp: int, fp: int) → float
# recall(tp: int, fn: int) → float
# f1(precision: float, recall: float) → float
```

### eval/run_eval.py
```python
# python eval/run_eval.py --batch_id <id>
#
# 1. Load data/testset/held_out.json (20 labeled records)
# 2. Fetch GET /api/report/{batch_id} (httpx, local)
# 3. For each held_out record:
#    Find corresponding match_result or exception_record in report
#    Compare to expected: 'match' or 'exception'
#    Count: tp, fp, fn, tn
#    (tp = expected match, got match)
#    (fp = expected exception, got match — FALSE MATCH, most critical)
#    (fn = expected match, got exception)
# 4. Compute all metrics via metrics.py
# 5. Print formatted report using rich:
#
#   ╔══════════════════════════════════════╗
#   ║   FINCONTROLLER EVAL REPORT          ║
#   ╠══════════════════════════════════════╣
#   ║ Held-out records:        20          ║
#   ║ True matches (TP):       xx          ║
#   ║ False matches (FP):      xx  ← key  ║
#   ║ Missed matches (FN):     xx          ║
#   ╠══════════════════════════════════════╣
#   ║ match_rate:          xx.x%           ║
#   ║ false_match_rate:     x.x%           ║
#   ║ exception_rate:      xx.x%           ║
#   ║ precision:           x.xxx           ║
#   ║ recall:              x.xxx           ║
#   ║ f1:                  x.xxx           ║
#   ║ throughput:          x.xx rec/sec    ║
#   ╚══════════════════════════════════════╝
#
# Exit code 1 if match_rate < 0.80 (signals failure to CI)
```

### eval/test_pipeline.py
```python
# pytest suite — 6 tests, use pytest-asyncio for async tests
# All tests use --seed 42 synthetic data
# Tests call local FastAPI via httpx (assume server running on :8000)
#
# test_exact_match:
#   Pick 3 known-exact records from held_out.json
#   Assert match_type == 'exact', confidence == 1.0
#
# test_settlement_lag:
#   Pick records with T+1 date offset (SETTLEMENT_LAG noise category)
#   Assert match_type == 'fuzzy', NOT in exception_records
#
# test_amount_mismatch:
#   Pick records with AMOUNT_MISMATCH noise
#   Assert in exception_records with reason_code == 'AMOUNT_MISMATCH'
#
# test_duplicate_detected:
#   Pick records with DUPLICATE_DETECTED noise
#   Assert reason_code == 'DUPLICATE_DETECTED'
#
# test_llm_validation_guard:
#   Mock groq_client.match_records to return malformed JSON string
#   Assert: result routed to exception_records, not a crash
#   Assert: reason_code == 'UNIDENTIFIED'
#
# test_batch_throughput:
#   Run full pipeline on 100-record batch
#   Assert: completes in < 120 seconds
#   Assert: total_matched + total_exceptions == total_records
```

**Verification:** `pytest eval/test_pipeline.py -v` — all 6 pass. `python eval/run_eval.py --batch_id <id>` prints report. match_rate ≥ 85%.

---

## M10 — Streamlit Dashboard

**File to create:** `ui/dashboard.py`

### ui/dashboard.py
```python
# streamlit run ui/dashboard.py
# Assumes FastAPI running on localhost:8000
# Uses httpx for all API calls
# Store batch_id in st.session_state
#
# Sidebar: navigation between 3 pages
#
# Page 1 — "Upload & Run":
#   st.title("BrewBox Reconciliation")
#   3 file uploaders: bank_statement, settlement_report, internal_ledger
#   Button: "Run Reconciliation"
#   On click: POST /api/ingest with files
#   Poll GET /api/batch/{id}/status every 2 seconds
#   Show st.progress bar while status == 'running'
#   On done: show 3 metric cards (st.metric):
#     match_rate | exception_rate | total_matched
#   Button: "View Results →"
#
# Page 2 — "Results":
#   If no batch_id in session: show "Run a batch first"
#   Fetch GET /api/report/{batch_id}
#   Section: "Matched Records"
#     st.dataframe with columns: match_type, confidence, amount, date, notes
#     Color coding via st.dataframe styling:
#       exact → green (#d4edda), fuzzy → yellow (#fff3cd), llm → orange (#fde8d8)
#     Sort by confidence ascending (lowest confidence first)
#   Section: "Exceptions"
#     st.dataframe grouped by reason_code
#     Expand each reason_code with record details
#   Button: "Download PDF Report" → GET /api/report/{batch_id}/pdf
#
# Page 3 — "Q&A":
#   st.title("Ask About Your Settlements")
#   Sample question chips (st.button for each):
#     "Why was there an amount mismatch?"
#     "How many records are missing from bank?"
#     "What is our match rate this batch?"
#     "List all DUPLICATE_DETECTED exceptions"
#   Text input: "Ask a question..."
#   On submit: POST /api/qa, display answer + sources in st.info box
#   Show chat history in st.session_state (list of Q&A pairs)
```

**Verification:** `streamlit run ui/dashboard.py` — full upload → run → results → Q&A flow works end to end without page reload errors.

---

## M11 — README + Submission

**Files to create:** `README.md`, `SUBMISSION.md`

### README.md
```
Sections (in order):
1. One-line description
2. What it does (3 bullet points, non-technical)
3. Architecture (ASCII diagram — ingest → normalize → match_exact → match_fuzzy 
   → match_llm → exception → report, with Supabase and ChromaDB labeled)
4. Tech stack table
5. Quickstart:
   git clone ...
   cd fincontroller
   python -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env  # fill in SUPABASE_DB_URL and GROQ_API_KEY
   alembic upgrade head
   python data/generators/generate_batch.py --seed 42
   uvicorn backend.main:app --reload --port 8000
   streamlit run ui/dashboard.py
6. Run eval: python eval/run_eval.py --batch_id <id>
7. Run tests: pytest eval/test_pipeline.py -v
8. Eval results table (fill after M9 — use real numbers)
9. API reference: curl examples for /ingest, /batch/{id}/status, 
   /report/{id}, /report/{id}/pdf, /qa
10. Project structure (tree)
```

### SUBMISSION.md
```
Sections:
1. Problem (3 lines): what finance ops problem this solves for merchants
2. What the agent does (bullet points): exact match → fuzzy → LLM → exception → report
3. Eval results (fill with real numbers after M9):
   | Metric | Value |
   |---|---|
   | match_rate | xx.x% |
   | false_match_rate | x.x% |
   | precision | x.xxx |
   | recall | x.xxx |
   | throughput | x.xx rec/sec |
4. Architecture decisions:
   - Why LangGraph: stateful DAG allows per-record routing — LLM only fires for ambiguous cases
   - Why two-pass: exact match is O(n²) but free (no LLM cost); LLM only for ~15-20% of records
   - Why Groq: sub-500ms latency per LLM call — critical for batch throughput
   - Why Supabase: hosted Postgres with JSONB for flexible exception storage
5. Known limitations + what you'd improve with more time
6. Demo video link: [placeholder]
```

**Verification:** `git clone` on a fresh machine + fill .env + `alembic upgrade head` + uvicorn works without any other steps.

---

## Milestone Dependency Order

```
M0 (Scaffold + Config)
  └── M1 (Models + Tables)
        ├── M2 (Synthetic Data)        ← run immediately after M1
        └── M3 (Ingest + Normalize)
              ├── M4 (Match Exact)
              │     └── M5 (Fuzzy + LLM)
              │           └── M6 (Exception + DAG)
              │                 └── M7 (Report API)
              │                       └── M9 (Eval)
              └── M8 (Q&A Agent)       ← independent after M3
M10 (Streamlit UI)  ← needs M7 + M8
M11 (README)        ← last, fill real eval numbers
```

**M10 is cuttable.** Core submission = M0 through M9.
**M2 must run before M9** — held_out.json is generated in M2.
**M8 needs M7 done first** — ingest_docs.py calls the report API.

---

## Tuning Guide (if match_rate < 85% after M9)

```
match_rate too low:
  → Increase FUZZY_DATE_WINDOW_DAYS from 2 to 3
  → Increase FUZZY_AMOUNT_TOLERANCE_ABS from 200 to 300
  → Lower FUZZY_THRESHOLD from 75 to 65

false_match_rate too high (> 2%):
  → Raise LLM_CONFIDENCE_THRESHOLD from 0.75 to 0.85
  → Add stricter amount check before accepting fuzzy match
  → Reduce FUZZY_AMOUNT_TOLERANCE_PCT from 5.0 to 3.0

LLM called too often (slow batch):
  → Raise FUZZY_THRESHOLD — fewer records reach ambiguous zone
  → Check match_fuzzy.py: ambiguous condition should be 50–75 range only
```

---

*fincontroller · Razorpay AI Buildathon 2026 · Track 04 · Built with LangGraph + Groq + Supabase*
