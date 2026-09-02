import time
import httpx
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="BrewBox — AI Finance Controller",
    page_icon="☕",
    layout="wide",
    initial_sidebar_state="expanded",
)

API_BASE_URL = "http://localhost:8000/api"

# Custom styling
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border-radius: 8px;
        padding: 1rem;
        border: 1px solid #E2E8F0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Navigation
st.sidebar.title("☕ BrewBox FinController")
st.sidebar.markdown("**AI-Powered 3-Way Reconciliation**")
nav_page = st.sidebar.radio(
    "Navigation",
    ["1. Upload & Run", "2. Reconciliation Results", "3. Settlement Q&A"],
)

if "batch_id" not in st.session_state:
    st.session_state["batch_id"] = None
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []


# PAGE 1: Upload & Run
if nav_page == "1. Upload & Run":
    st.markdown('<div class="main-header">Batch Financial Ingestion</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Upload Bank Statement, Razorpay Settlement Report, and Internal Ledger CSV files.</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("🏦 Bank Statement")
        bank_file = st.file_uploader("Upload Bank Statement (CSV)", type=["csv"], key="bank")
    with col2:
        st.subheader("💳 Razorpay Settlement")
        rp_file = st.file_uploader("Upload Settlement Report (CSV)", type=["csv"], key="rp")
    with col3:
        st.subheader("📖 Internal Ledger")
        ledger_file = st.file_uploader("Upload Ledger (CSV)", type=["csv"], key="ledger")

    st.markdown("---")

    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        run_btn = st.button("🚀 Run Reconciliation", type="primary", use_container_width=True)

    if run_btn:
        if not (bank_file and rp_file and ledger_file):
            st.error("⚠️ Please upload all 3 CSV files before running reconciliation.")
        else:
            with st.spinner("Uploading records and initiating reconciliation DAG..."):
                try:
                    files = {
                        "bank_file": (bank_file.name, bank_file.getvalue(), "text/csv"),
                        "razorpay_file": (rp_file.name, rp_file.getvalue(), "text/csv"),
                        "ledger_file": (ledger_file.name, ledger_file.getvalue(), "text/csv"),
                    }
                    with httpx.Client(timeout=30.0) as client:
                        resp = client.post(f"{API_BASE_URL}/ingest", files=files)
                        if resp.status_code == 200:
                            data = resp.json()
                            batch_id = data.get("batch_id")
                            st.session_state["batch_id"] = batch_id
                            st.success(f"Batch created! ID: `{batch_id}`")

                            # Polling status
                            progress_bar = st.progress(0, text="Running multi-pass reconciliation...")
                            status = "pending"
                            for step in range(30):
                                time.sleep(1.5)
                                status_resp = client.get(f"{API_BASE_URL}/batch/{batch_id}/status")
                                if status_resp.status_code == 200:
                                    s_data = status_resp.json()
                                    status = s_data.get("status")
                                    matched = s_data.get("matched", 0)
                                    exc_count = s_data.get("exceptions", 0)
                                    progress_bar.progress(
                                        min(95, (step + 1) * 7),
                                        text=f"Status: {status.upper()} | Matches: {matched} | Exceptions: {exc_count}",
                                    )
                                    if status in ["done", "failed"]:
                                        break

                            progress_bar.progress(100, text=f"Reconciliation Complete: {status.upper()}")

                            if status == "done":
                                # Fetch final report
                                rep_resp = client.get(f"{API_BASE_URL}/report/{batch_id}")
                                if rep_resp.status_code == 200:
                                    rep = rep_resp.json()
                                    s = rep.get("summary", {})

                                    st.markdown("### 📊 Batch Summary")
                                    mcol1, mcol2, mcol3, mcol4 = st.columns(4)
                                    mcol1.metric("Match Rate", f"{s.get('match_rate', 0.0):.1%}")
                                    mcol2.metric("Total Matched", s.get("total_matched", 0))
                                    mcol3.metric("Total Exceptions", s.get("total_exceptions", 0))
                                    mcol4.metric("Pipeline Duration", f"{s.get('duration_seconds', 0.0)}s")
                        else:
                            st.error(f"Ingest failed: {resp.text}")
                except Exception as e:
                    st.error(f"Failed to connect to API server: {e}")


# PAGE 2: Results
elif nav_page == "2. Reconciliation Results":
    st.markdown('<div class="main-header">Reconciliation Results & Audit</div>', unsafe_allow_html=True)
    batch_id = st.session_state.get("batch_id")

    col_input, col_pdf = st.columns([3, 1])
    with col_input:
        active_id = st.text_input("Active Batch ID:", value=batch_id or "", placeholder="Enter Batch UUID...")
    if active_id:
        st.session_state["batch_id"] = active_id

    if not st.session_state.get("batch_id"):
        st.info("ℹ️ No active batch found. Upload files in '1. Upload & Run' or enter a Batch ID above.")
    else:
        current_id = st.session_state["batch_id"]
        try:
            with httpx.Client(timeout=15.0) as client:
                rep_resp = client.get(f"{API_BASE_URL}/report/{current_id}")
                if rep_resp.status_code == 200:
                    report = rep_resp.json()
                    summary = report.get("summary", {})

                    with col_pdf:
                        st.markdown("<br>", unsafe_allow_html=True)
                        st.link_button(
                            "📥 Download PDF Report",
                            f"{API_BASE_URL}/report/{current_id}/pdf",
                            type="secondary",
                            use_container_width=True,
                        )

                    # Metric row
                    r1, r2, r3, r4 = st.columns(4)
                    r1.metric("Match Rate", f"{summary.get('match_rate', 0.0):.1%}")
                    r2.metric("Total Matched Groups", summary.get("total_matched", 0))
                    r3.metric("Exceptions Flagged", summary.get("total_exceptions", 0))
                    r4.metric("LLM Calls", summary.get("llm_calls_made", 0))

                    st.markdown("---")

                    # Section 1: Matched Records
                    st.subheader("✅ Matched Transactions")
                    matches = report.get("matches", [])
                    if matches:
                        table_rows = []
                        for m in matches:
                            bk = m.get("bank_record") or {}
                            table_rows.append({
                                "Match Stage": m.get("match_type", "").upper(),
                                "Confidence": f"{m.get('confidence', 0.0):.2f}",
                                "Amount (₹)": bk.get("amount") or "N/A",
                                "Date": bk.get("date") or "N/A",
                                "Ref ID": bk.get("ref_id") or "N/A",
                                "Notes": m.get("notes") or "",
                            })
                        df_matches = pd.DataFrame(table_rows)
                        df_matches = df_matches.sort_values(by="Confidence", ascending=True)

                        def style_match_type(val):
                            if val == "EXACT":
                                return "background-color: #d4edda; color: #155724;"
                            elif val == "FUZZY":
                                return "background-color: #fff3cd; color: #856404;"
                            elif val == "LLM":
                                return "background-color: #fde8d8; color: #8a3b00;"
                            return ""

                        styled_df = df_matches.style.map(style_match_type, subset=["Match Stage"])
                        st.dataframe(styled_df, use_container_width=True, height=350)
                    else:
                        st.write("No matched records found.")

                    # Section 2: Exceptions
                    st.subheader("⚠️ Exceptions & Reason Codes")
                    exceptions = report.get("exceptions", [])
                    breakdown = report.get("exception_breakdown", [])

                    for item in breakdown:
                        with st.expander(f"📌 {item.get('reason_code')} ({item.get('count')} records)"):
                            for rec in item.get("records", []):
                                st.markdown(f"**Description:** {rec.get('description')}")
                                st.json(rec.get("raw_records", {}))
                                st.markdown("---")

                else:
                    st.error(f"Failed to fetch report for batch `{current_id}` (Status: {rep_resp.status_code})")
        except Exception as e:
            st.error(f"Error loading report: {e}")


# PAGE 3: Settlement Q&A
elif nav_page == "3. Settlement Q&A":
    st.markdown('<div class="main-header">Settlement Q&A Assistant</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Ask natural language questions about your reconciliations, settlements, and exceptions.</div>', unsafe_allow_html=True)

    batch_id = st.session_state.get("batch_id") or ""
    current_id = st.text_input("Active Batch ID for Q&A Context:", value=batch_id)

    st.markdown("##### 💡 Suggested Questions")
    q_col1, q_col2 = st.columns(2)
    sample_q = None
    with q_col1:
        if st.button("Why was there an amount mismatch?", use_container_width=True):
            sample_q = "Why was there an amount mismatch?"
        if st.button("How many records are missing from bank?", use_container_width=True):
            sample_q = "How many records are missing from bank?"
    with q_col2:
        if st.button("What is our match rate this batch?", use_container_width=True):
            sample_q = "What is our match rate this batch?"
        if st.button("List all DUPLICATE_DETECTED exceptions", use_container_width=True):
            sample_q = "List all DUPLICATE_DETECTED exceptions"

    user_query = st.chat_input("Ask a question about your reconciliation results...") or sample_q

    if user_query:
        with st.spinner("Analyzing reconciliation knowledge base..."):
            try:
                payload = {"question": user_query, "batch_id": current_id}
                with httpx.Client(timeout=30.0) as client:
                    qa_res = client.post(f"{API_BASE_URL}/qa", json=payload)
                    if qa_res.status_code == 200:
                        qa_data = qa_res.json()
                        st.session_state["chat_history"].append({
                            "question": user_query,
                            "answer": qa_data.get("answer", ""),
                            "sources": qa_data.get("sources", []),
                        })
                    else:
                        st.error(f"QA endpoint error: {qa_res.text}")
            except Exception as e:
                st.error(f"Failed to query QA endpoint: {e}")

    # Display chat history
    for entry in reversed(st.session_state["chat_history"]):
        with st.chat_message("user"):
            st.write(entry["question"])
        with st.chat_message("assistant"):
            st.write(entry["answer"])
            if entry.get("sources"):
                with st.expander("📚 Sources & Evidence"):
                    for src in entry["sources"]:
                        st.markdown(f"- {src}")
