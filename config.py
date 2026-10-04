import os
import warnings
from dotenv import load_dotenv

load_dotenv()

# ---------- Qdrant ----------
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "vietgreen_documents")
QDRANT_BATCH_SIZE = int(os.getenv("QDRANT_BATCH_SIZE", "50"))
EMBED_DIM = int(os.getenv("EMBED_DIM", "768"))

# ---------- Ollama ----------
OLLAMA_EXTRACT_MODEL = os.getenv("OLLAMA_EXTRACT_MODEL", "vietgreen-ai")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "vietgreen-ai")

# ---------- PostgreSQL ----------
DB_CONFIG = {
    "dbname": os.getenv("PG_DBNAME", "vietgreen_db"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", "yourpassword"),
    "host": os.getenv("PG_HOST", "localhost"),
    "port": os.getenv("PG_PORT", "5432"),
}

# ---------- Pipeline tuning ----------
# num_ctx của model đang là 32768 token. Văn bản tiếng Việt (nhiều dấu)
# trung bình ~2.5-3.5 ký tự/token, nên 70.000 ký tự ≈ 20.000-28.000 token
# — vẫn còn dư chỗ cho phần prompt instructions + num_predict=3072.
# Nếu đổi model/num_ctx, hãy tính lại và chỉnh qua biến môi trường thay vì sửa code.
MAX_TEXT_CHARS_FOR_LLM = int(os.getenv("MAX_TEXT_CHARS_FOR_LLM", "70000"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
MAX_CHUNKS = int(os.getenv("MAX_CHUNKS", "200"))
EMBED_CONCURRENCY = int(os.getenv("EMBED_CONCURRENCY", "4"))

# Số vùng (bucket) chia văn bản theo vị trí khi lấy mẫu trải đều (stratified)
# trong _extract_relevant_text — xem pipeline.py
RELEVANCE_NUM_BUCKETS = int(os.getenv("RELEVANCE_NUM_BUCKETS", "10"))

# ---------- OCR fallback cho trang PDF dạng ảnh/scan ----------
# Trang có ít hơn ngần này ký tự text trích được qua pypdf sẽ bị nghi là
# ảnh/scan và (nếu bật) được OCR lại bằng pytesseract.
OCR_MIN_TEXT_CHARS_PER_PAGE = int(os.getenv("OCR_MIN_TEXT_CHARS_PER_PAGE", "50"))
ENABLE_OCR_FALLBACK = os.getenv("ENABLE_OCR_FALLBACK", "true").lower() == "true"

# ---------- Debug ----------
# Bật để ghi text_sample (đoạn văn bản thật sự đưa cho LLM) ra file,
# kiểm tra bằng mắt xem có chứa số liệu thật không.
DEBUG_DUMP_TEXT_SAMPLE = os.getenv("DEBUG_DUMP_TEXT_SAMPLE", "false").lower() == "true"
DEBUG_DUMP_DIR = os.getenv("DEBUG_DUMP_DIR", "/tmp/vietgreen_debug")

# ---------- RAG ----------
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))
RAG_SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0.5"))

# ---------- Validate ----------
if DB_CONFIG["password"] in ("yourpassword", "CHANGE_ME", "CHANGE_ME_STRONG_PASSWORD", ""):
    warnings.warn(
        "⚠️  PG_PASSWORD đang dùng giá trị mặc định — KHÔNG an toàn cho production!",
        stacklevel=2,
    )
