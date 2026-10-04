from config import (
    QDRANT_HOST, QDRANT_PORT, QDRANT_COLLECTION,
    OLLAMA_EMBED_MODEL, OLLAMA_CHAT_MODEL,
    RAG_TOP_K, RAG_SCORE_THRESHOLD,
)
from qdrant_client import QdrantClient
import ollama, logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vietgreen_query")

client = QdrantClient(QDRANT_HOST, port=QDRANT_PORT)


def ask_rag(question: str) -> str:
    if not question.strip():
        return "Vui lòng nhập câu hỏi."

    query_vector = ollama.embeddings(model=OLLAMA_EMBED_MODEL, prompt=question)["embedding"]

    resp = client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=query_vector,
        limit=RAG_TOP_K,
        score_threshold=RAG_SCORE_THRESHOLD,
        with_payload=True,
    )

    hits = resp.points or []
    if not hits:
        return "Tôi không biết (không tìm thấy thông tin)."

    context = "\n---\n".join(h.payload.get("content", "") for h in hits)

    prompt = f"""Dựa vào thông tin dưới đây, hãy trả lời câu hỏi.
Nếu không có thông tin, trả lời: "Tôi không biết".

Thông tin tham khảo:
{context}

Câu hỏi: {question}
"""

    try:
        response = ollama.generate(model=OLLAMA_CHAT_MODEL, prompt=prompt)
        return response.get("response", "").strip() or "Tôi không biết."
    except Exception as e:
        logger.exception("Lỗi Ollama chat")
        return f"Lỗi: {e}"


if __name__ == "__main__":
    print(ask_rag("Điểm VGPI của Công ty VinFast là bao nhiêu?"))
