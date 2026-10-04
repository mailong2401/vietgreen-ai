import uuid
import logging
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import ollama

from config import (
    QDRANT_HOST, QDRANT_PORT, QDRANT_COLLECTION,
    OLLAMA_EMBED_MODEL, EMBED_DIM,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vietgreen_ingest")

client = QdrantClient(QDRANT_HOST, port=QDRANT_PORT)


def ensure_collection():
    if not client.collection_exists(collection_name=QDRANT_COLLECTION):
        client.create_collection(
            collection_name=QDRANT_COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
        logger.info(f"Đã tạo collection {QDRANT_COLLECTION}")


def save_chunk_to_db(doc_id: int, text_chunk: str,
                     company_name: str = "Unknown", chunk_index: int = 0):
    if not text_chunk.strip():
        logger.warning("Bỏ qua chunk rỗng")
        return

    embed = ollama.embeddings(model=OLLAMA_EMBED_MODEL, prompt=text_chunk)["embedding"]
    point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"vietgreen-{doc_id}-{chunk_index}"))

    client.upsert(
        collection_name=QDRANT_COLLECTION,
        points=[
            PointStruct(
                id=point_id,
                vector=embed,
                payload={
                    "doc_id": doc_id,
                    "company_name": company_name,
                    "content": text_chunk,
                    "chunk_index": chunk_index,
                },
            )
        ],
    )
    logger.info(f"Đã nạp chunk {chunk_index} của doc {doc_id}")


if __name__ == "__main__":
    ensure_collection()
    save_chunk_to_db(
        doc_id=1,
        text_chunk="Chỉ số VGPI của Doanh nghiệp A năm 2026 đạt 85/100 điểm.",
        company_name="Doanh nghiệp A",
        chunk_index=0,
    )
