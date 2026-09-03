from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from backend.db.engine import engine
from backend.db.tables import Base
from backend.routers.ingest import router as ingest_router
from backend.routers.qa import router as qa_router
from backend.routers.report import router as report_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing FinController database schema...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables initialized successfully.")
    except Exception as e:
        logger.warning(
            f"DB initialization notice (check SUPABASE_DB_URL in .env if DB is not connected): {e}"
        )
    yield
    logger.info("Shutting down FinController engine...")
    await engine.dispose()
    logger.info("Engine disposed.")


app = FastAPI(
    title="fincontroller - AI Finance Controller",
    description="Batch financial reconciliation agent for Razorpay AI Buildathon 2026",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest_router)
app.include_router(report_router)
app.include_router(qa_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "fincontroller"}
