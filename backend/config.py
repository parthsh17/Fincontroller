from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    supabase_db_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/postgres",
        alias="SUPABASE_DB_URL",
    )
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    chroma_path: str = Field(default="./chroma_data", alias="CHROMA_PATH")
    chroma_collection: str = Field(
        default="settlement_docs", alias="CHROMA_COLLECTION"
    )
    llm_model: str = Field(default="llama3-70b-8192", alias="LLM_MODEL")
    llm_max_retries: int = Field(default=3, alias="LLM_MAX_RETRIES")
    fuzzy_threshold: float = Field(default=75.0, alias="FUZZY_THRESHOLD")
    fuzzy_amount_tolerance_pct: float = Field(
        default=5.0, alias="FUZZY_AMOUNT_TOLERANCE_PCT"
    )
    fuzzy_amount_tolerance_abs: float = Field(
        default=200.0, alias="FUZZY_AMOUNT_TOLERANCE_ABS"
    )
    fuzzy_date_window_days: int = Field(
        default=2, alias="FUZZY_DATE_WINDOW_DAYS"
    )
    llm_confidence_threshold: float = Field(
        default=0.75, alias="LLM_CONFIDENCE_THRESHOLD"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


settings = Settings()
