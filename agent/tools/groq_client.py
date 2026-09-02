import asyncio
import json
import time
from typing import Any
from groq import AsyncGroq
from loguru import logger
from pydantic import ValidationError
from backend.config import settings
from backend.models.match import LLMMatchDecision


class GroqClient:
    def __init__(self, api_key: str | None = None):
        key = api_key or settings.groq_api_key
        # If key is empty, client might still initialize or error on request
        self.client = AsyncGroq(api_key=key if key else "dummy_key")
        self.total_calls: int = 0
        self.cumulative_latency_ms: float = 0.0

    async def match_records(
        self, record_a: dict[str, Any], record_b: dict[str, Any]
    ) -> LLMMatchDecision | None:
        system_prompt = (
            "You are a financial reconciliation assistant. Given two financial "
            "records from different sources, determine if they represent the same "
            "transaction. Respond ONLY with valid JSON matching this exact schema:\n"
            "{\n"
            '  "matched": boolean,\n'
            '  "confidence": float between 0.0 and 1.0,\n'
            '  "reason": string,\n'
            '  "match_type": "llm"\n'
            "}\n"
            "Do not include any text outside the JSON."
        )

        user_prompt = (
            f"Record A: {json.dumps(record_a, default=str)}\n"
            f"Record B: {json.dumps(record_b, default=str)}"
        )

        backoffs = [1.0, 2.0, 4.0]
        max_retries = settings.llm_max_retries

        for attempt in range(max_retries):
            start_t = time.perf_counter()
            try:
                self.total_calls += 1
                response = await self.client.chat.completions.create(
                    model=settings.llm_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=200,
                    temperature=0.0,
                    response_format={"type": "json_object"},
                )
                latency = (time.perf_counter() - start_t) * 1000.0
                self.cumulative_latency_ms += latency

                content = response.choices[0].message.content or "{}"
                # Safe parse via Pydantic model
                decision_dict = json.loads(content)
                decision = LLMMatchDecision.model_validate(decision_dict)

                logger.info(
                    f"Groq LLM match call (attempt {attempt + 1}) | "
                    f"latency={latency:.1f}ms | matched={decision.matched} | "
                    f"confidence={decision.confidence:.2f}"
                )
                return decision

            except (ValidationError, json.JSONDecodeError) as pe:
                latency = (time.perf_counter() - start_t) * 1000.0
                self.cumulative_latency_ms += latency
                logger.warning(
                    f"Groq output validation failed (attempt {attempt + 1}): {pe}"
                )
                return None

            except Exception as e:
                latency = (time.perf_counter() - start_t) * 1000.0
                self.cumulative_latency_ms += latency
                logger.warning(
                    f"Groq API call error on attempt {attempt + 1}: {e}"
                )
                if attempt < max_retries - 1:
                    wait_sec = backoffs[attempt] if attempt < len(backoffs) else 4.0
                    await asyncio.sleep(wait_sec)
                else:
                    logger.error(
                        f"Groq call failed after {max_retries} attempts: {e}"
                    )
                    return None

        return None


groq_client = GroqClient()
