import json
import os
import sys
import uuid
import pytest
from backend.config import Settings
from unittest.mock import AsyncMock, patch

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agent.nodes.exception import exception_node
from agent.nodes.match_exact import exact_match_node
from agent.nodes.match_fuzzy import fuzzy_match_node
from agent.nodes.match_llm import llm_match_node
from agent.state import BatchState
from agent.tools.fuzzy import fuzzy_score
from agent.tools.groq_client import GroqClient
from data.generators.noise import inject_noise


@pytest.fixture
def sample_noisy_batch():
    from datetime import date
    from decimal import Decimal

    base_records = [
        {
            "amount": Decimal("1299.00"),
            "date": date(2026, 10, 5),
            "ref_id": "REF100001",
            "description": "BrewBox Premium",
            "customer_name": "Aditya Sharma",
        },
        {
            "amount": Decimal("899.00"),
            "date": date(2026, 10, 6),
            "ref_id": "REF100002",
            "description": "Coffee subscription",
            "customer_name": "Priya Patel",
        },
        {
            "amount": Decimal("2499.00"),
            "date": date(2026, 10, 7),
            "ref_id": "REF100003",
            "description": "BrewBox Connoisseur",
            "customer_name": "Rohan Gupta",
        },
    ]
    return inject_noise(base_records, seed=42)


@pytest.mark.asyncio
async def test_exact_match():
    batch_id = str(uuid.uuid4())
    all_recs = {
        "bank": [{
            "id": str(uuid.uuid4()),
            "source": "bank",
            "amount": "1499.00",
            "date": "2026-10-12",
            "ref_id": "REF888001",
            "description": "BrewBox Premium",
            "raw": {},
        }],
        "razorpay": [{
            "id": str(uuid.uuid4()),
            "source": "razorpay",
            "amount": "1499.00",
            "date": "2026-10-12",
            "ref_id": "REF888001",
            "description": "BrewBox Premium",
            "raw": {},
        }],
        "ledger": [{
            "id": str(uuid.uuid4()),
            "source": "ledger",
            "amount": "1499.00",
            "date": "2026-10-12",
            "ref_id": "REF888001",
            "description": "BrewBox Premium",
            "raw": {},
        }],
    }

    state: BatchState = {
        "batch_id": batch_id,
        "all_records": all_recs,
        "matched_ids": set(),
        "match_results": [],
        "ambiguous_pairs": [],
        "pending_records": [],
        "unmatched_after_llm": [],
        "exception_records": [],
        "metrics": {},
    }

    with patch("backend.db.engine.async_session_maker") as mock_session:
        # Mock DB context manager
        mock_ctx = AsyncMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        res_state = await exact_match_node(state)
        assert len(res_state["match_results"]) == 1
        match = res_state["match_results"][0]
        assert match["match_type"] == "exact"
        assert match["confidence"] == 1.0
        assert len(res_state["pending_records"]) == 0


@pytest.mark.asyncio
async def test_settlement_lag():
    batch_id = str(uuid.uuid4())
    # Bank & Ledger on 2026-10-10, Razorpay settled on 2026-10-11 (T+1)
    b_id = str(uuid.uuid4())
    r_id = str(uuid.uuid4())
    l_id = str(uuid.uuid4())

    pending_records = [
        {
            "id": b_id,
            "source": "bank",
            "amount": "1999.00",
            "date": "2026-10-10",
            "ref_id": "REF777002",
            "description": "Coffee subscription",
            "raw": {},
        },
        {
            "id": r_id,
            "source": "razorpay",
            "amount": "1999.00",
            "date": "2026-10-11",
            "ref_id": "REF777002",
            "description": "Coffee subscription",
            "raw": {},
        },
        {
            "id": l_id,
            "source": "ledger",
            "amount": "1999.00",
            "date": "2026-10-10",
            "ref_id": "REF777002",
            "description": "Coffee subscription",
            "raw": {},
        },
    ]

    state: BatchState = {
        "batch_id": batch_id,
        "all_records": {
            "bank": [pending_records[0]],
            "razorpay": [pending_records[1]],
            "ledger": [pending_records[2]],
        },
        "matched_ids": set(),
        "match_results": [],
        "ambiguous_pairs": [],
        "pending_records": pending_records,
        "unmatched_after_llm": [],
        "exception_records": [],
        "metrics": {},
    }

    with patch("backend.db.engine.async_session_maker") as mock_session:
        mock_ctx = AsyncMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        res_state = await fuzzy_match_node(state)
        assert len(res_state["match_results"]) == 1
        match = res_state["match_results"][0]
        assert match["match_type"] == "fuzzy"
        assert match["confidence"] >= 0.85
        assert len(res_state["pending_records"]) == 0


@pytest.mark.asyncio
async def test_amount_mismatch():
    batch_id = str(uuid.uuid4())
    b_id = str(uuid.uuid4())
    r_id = str(uuid.uuid4())
    l_id = str(uuid.uuid4())

    b_rec = {
        "id": b_id,
        "source": "bank",
        "amount": "1400.00",
        "date": "2026-10-15",
        "ref_id": "REF999003",
        "description": "BrewBox Connoisseur",
        "raw": {"amount": "1400.00"},
    }
    r_rec = {
        "id": r_id,
        "source": "razorpay",
        "amount": "1500.00",
        "date": "2026-10-15",
        "ref_id": "REF999003",
        "description": "BrewBox Connoisseur",
        "raw": {"amount": "1500.00"},
    }
    l_rec = {
        "id": l_id,
        "source": "ledger",
        "amount": "1500.00",
        "date": "2026-10-15",
        "ref_id": "REF999003",
        "description": "BrewBox Connoisseur",
        "raw": {"amount": "1500.00"},
    }

    state: BatchState = {
        "batch_id": batch_id,
        "all_records": {
            "bank": [b_rec],
            "razorpay": [r_rec],
            "ledger": [l_rec],
        },
        "matched_ids": set(),
        "match_results": [],
        "ambiguous_pairs": [],
        "pending_records": [b_rec, r_rec, l_rec],
        "unmatched_after_llm": [b_rec, r_rec, l_rec],
        "exception_records": [],
        "metrics": {},
    }

    with patch("backend.db.engine.async_session_maker") as mock_session:
        mock_ctx = AsyncMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        res_state = await exception_node(state)
        assert len(res_state["exception_records"]) >= 1
        exc = res_state["exception_records"][0]
        assert exc["reason_code"] == "AMOUNT_MISMATCH"


@pytest.mark.asyncio
async def test_duplicate_detected():
    batch_id = str(uuid.uuid4())
    l_id1 = str(uuid.uuid4())
    l_id2 = str(uuid.uuid4())

    l_rec1 = {
        "id": l_id1,
        "source": "ledger",
        "amount": "1000.00",
        "date": "2026-10-18",
        "ref_id": "REF555004",
        "description": "Starter Pack",
        "raw": {},
    }
    l_rec2 = {
        "id": l_id2,
        "source": "ledger",
        "amount": "1000.00",
        "date": "2026-10-18",
        "ref_id": "REF555004",
        "description": "Starter Pack Dup",
        "raw": {},
    }

    state: BatchState = {
        "batch_id": batch_id,
        "all_records": {
            "bank": [],
            "razorpay": [],
            "ledger": [l_rec1, l_rec2],
        },
        "matched_ids": set(),
        "match_results": [],
        "ambiguous_pairs": [],
        "pending_records": [l_rec1, l_rec2],
        "unmatched_after_llm": [l_rec1, l_rec2],
        "exception_records": [],
        "metrics": {},
    }

    with patch("backend.db.engine.async_session_maker") as mock_session:
        mock_ctx = AsyncMock()
        mock_session.return_value.__aenter__.return_value = mock_ctx

        res_state = await exception_node(state)
        assert len(res_state["exception_records"]) >= 1
        exc = res_state["exception_records"][0]
        assert exc["reason_code"] == "DUPLICATE_DETECTED"


@pytest.mark.asyncio
async def test_llm_validation_guard():
    client = GroqClient(api_key="test_key")
    # Mock groq client API call with invalid/malformed response
    mock_resp = AsyncMock()
    mock_resp.choices = [
        AsyncMock(message=AsyncMock(content="Malformed Non-JSON String !!!"))
    ]

    with patch.object(
        client.client.chat.completions, "create", return_value=mock_resp
    ):
        result = await client.match_records({"amt": 100}, {"amt": 200})
        # Must return None safely without unhandled exceptions
        assert result is None


def test_deprecated_groq_models_use_supported_default():
    settings = Settings(
        _env_file=None,
        llm_model="llama3-70b-8192",
    )

    assert settings.llm_model == "openai/gpt-oss-120b"


@pytest.mark.asyncio
async def test_batch_throughput():
    from eval.metrics import throughput

    total_records = 300
    elapsed_seconds = 2.5
    rate = throughput(total_records, elapsed_seconds)
    assert rate == 120.0
