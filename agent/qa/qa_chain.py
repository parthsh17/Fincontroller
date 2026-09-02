import chromadb
from groq import AsyncGroq
from loguru import logger
from sentence_transformers import SentenceTransformer
from backend.config import settings

_embedding_model = None


def get_embedder():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


async def answer_question(question: str, batch_id: str) -> dict:
    try:
        client = chromadb.PersistentClient(path=settings.chroma_path)
        collection = client.get_or_create_collection(name=settings.chroma_collection)

        embedder = get_embedder()
        q_emb = embedder.encode([question]).tolist()

        # Query top 5 chunks matching batch_id if available
        results = collection.query(
            query_embeddings=q_emb,
            n_results=5,
            where={"batch_id": batch_id} if batch_id else None,
        )

        sources = []
        if results and "documents" in results and results["documents"]:
            sources = results["documents"][0]

        context_str = "\n".join(f"- {s}" for s in sources) if sources else "No matching documents found."

        system_prompt = (
            "You are a financial reconciliation assistant for BrewBox. "
            "Answer questions about settlements and reconciliation results "
            "using ONLY the context provided. Be specific with ₹ amounts "
            "and dates. If the answer is not in the context, respond: "
            "'I don't have that information in the reconciliation data.'"
        )

        user_prompt = f"Context:\n{context_str}\n\nQuestion: {question}"

        # Call Groq
        if settings.groq_api_key:
            groq_async = AsyncGroq(api_key=settings.groq_api_key)
            resp = await groq_async.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=300,
                temperature=0.0,
            )
            answer = resp.choices[0].message.content or "No response generated."
        else:
            answer = (
                f"[Grounded Context Retrieval]\nBased on reconciliation records:\n{context_str}"
            )

        return {
            "answer": answer,
            "sources": sources,
            "batch_id": batch_id,
        }

    except Exception as e:
        logger.error(f"Error in QA chain: {e}")
        return {
            "answer": f"Error answering question: {str(e)}",
            "sources": [],
            "batch_id": batch_id,
        }
