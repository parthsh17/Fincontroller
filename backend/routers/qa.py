import uuid
from fastapi import APIRouter, Depends
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.engine import get_db
from backend.db.tables import QALogDB
from agent.qa.qa_chain import answer_question

router = APIRouter(prefix="/api", tags=["Q&A"])


class QARequest(BaseModel):
    question: str
    batch_id: str


class QAResponse(BaseModel):
    answer: str
    sources: list[str]
    batch_id: str


@router.post("/qa", response_model=QAResponse)
async def ask_qa(req: QARequest, db: AsyncSession = Depends(get_db)):
    result = await answer_question(req.question, req.batch_id)

    # Persist log to qa_logs table
    try:
        if req.batch_id:
            qa_log = QALogDB(
                batch_id=uuid.UUID(req.batch_id),
                question=req.question,
                answer=result.get("answer", ""),
                sources=result.get("sources", []),
            )
            db.add(qa_log)
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to persist QA log: {e}")

    return QAResponse(
        answer=result.get("answer", ""),
        sources=result.get("sources", []),
        batch_id=req.batch_id,
    )
