from fastapi import FastAPI, UploadFile, File, HTTPException
from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from functools import partial
import ollama
import json, io, logging, uuid, anyio, re, os, time

from config import (
    QDRANT_HOST, QDRANT_PORT, QDRANT_COLLECTION, EMBED_DIM,
    OLLAMA_EXTRACT_MODEL, OLLAMA_EMBED_MODEL,
    MAX_TEXT_CHARS_FOR_LLM, CHUNK_SIZE, MAX_CHUNKS, EMBED_CONCURRENCY,
    OCR_MIN_TEXT_CHARS_PER_PAGE, ENABLE_OCR_FALLBACK,
    DEBUG_DUMP_TEXT_SAMPLE, DEBUG_DUMP_DIR, RELEVANCE_NUM_BUCKETS,
)
from db import init_postgres_db, get_pg_conn
from schemas import EsgExtraction
from prompt import EXTRACTION_PROMPT_TEMPLATE
from prompt_multi import (
    PROMPT_COMPANY,
    PROMPT_EMISSIONS_ENERGY,
    PROMPT_WATER_WASTE,
    PROMPT_SUPPLY_AUDIT,
)
from formulas import compute_all_derived
from validators import validate_consistency

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vietgreen_pipeline")

app = FastAPI(title="VietGreen Data Ingestion Pipeline")

qdrant_client = QdrantClient(QDRANT_HOST, port=QDRANT_PORT)
if not qdrant_client.collection_exists(QDRANT_COLLECTION):
    qdrant_client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
    )

init_postgres_db()


# ============================================================
# HELPERS
# ============================================================
def _call_llm_for_json(prompt: str, label: str) -> dict:
    """Gọi LLM với streaming — in token realtime ra log."""
    try:
        raw = ""
        chunk_count = 0
        start_time = time.time()
        last_log_time = start_time

        # Header
        print(f"\n{'='*70}", flush=True)
        print(f"[{label}] 🚀 BẮT ĐẦU GỌI LLM (streaming)", flush=True)
        print(f"{'='*70}", flush=True)

        # ✅ Bật stream=True
        stream = ollama.generate(
            model=OLLAMA_EXTRACT_MODEL,
            prompt=prompt,
            format="json",
            stream=True,
            options={
                "temperature": 0.0,
                "num_ctx": 32768,
                "num_predict": 3072,
            },
        )

        # ✅ In từng chunk realtime
        print("", end="", flush=True)
        for chunk in stream:
            token = chunk.get("response", "")
            raw += token
            chunk_count += 1

            # In token ra stdout ngay (dùng end="" để không xuống dòng)
            print(token, end="", flush=True)

            # Cứ 50 chunks → log tiến độ
            now = time.time()
            if chunk_count % 50 == 0 or (now - last_log_time) > 5:
                logger.info(
                    f"[{label}] ... đang sinh: {chunk_count} chunks, "
                    f"{len(raw)} ký tự, {now - start_time:.1f}s"
                )
                last_log_time = now

            if chunk.get("done", False):
                break

        elapsed = time.time() - start_time

        # Footer
        print(f"\n{'='*70}", flush=True)
        print(f"[{label}] ✅ XONG: {chunk_count} chunks, {len(raw)} ký tự, {elapsed:.2f}s", flush=True)
        print(f"{'='*70}\n", flush=True)

        logger.info(
            f"[{label}] LLM RAW (len={len(raw)}, chunks={chunk_count}, {elapsed:.2f}s)"
        )

        if not raw or len(raw) < 10:
            logger.warning(f"[{label}] LLM trả rỗng")
            return {}

        parsed = _parse_json_safely(raw)
        return parsed if isinstance(parsed, dict) else {}

    except Exception as e:
        logger.error(f"[{label}] Lỗi: {type(e).__name__}: {e}")
        return {}

_DIGIT_RE = re.compile(r"\d")

#danh sách keyword
_RELEVANCE_KEYWORDS = [
    # ============================================================
    # 1. EMISSIONS — Phát thải khí nhà kính
    # ============================================================
    # Scope
    "scope 1", "scope 2", "scope 3",
    "scope1", "scope2", "scope3",
    "phạm vi 1", "phạm vi 2", "phạm vi 3",
    "phạm vi phát thải 1", "phạm vi phát thải 2", "phạm vi phát thải 3",
    # GHG
    "phát thải", "khí nhà kính", "khi nha kinh", "ghg",
    "phát thải khí nhà kính", "phat thai",
    "kiểm kê khí nhà kính", "kiểm kê phat thai",
    "giảm phát thải", "cắt giảm phát thải",
    "phát thải ròng", "net zero", "net-zero", "carbon neutral",
    # Đơn vị đo
    "tco2", "tco2e", "tco₂", "tco₂e", "co2e", "co₂e", "co2", "co₂",
    "tấn co2", "tấn co₂", "tấn co2e", "tấn co₂e",
    "tấn co2 tương đương", "tấn co₂ tương đương",
    "carbon", "dấu chân carbon", "carbon footprint",
    "cường độ carbon", "carbon intensity",
    "cường độ phát thải",
    # Trực tiếp / gián tiếp
    "phát thải trực tiếp", "phát thải gián tiếp",
    "trực tiếp", "gián tiếp",

    # ============================================================
    # 2. ENERGY — Năng lượng
    # ============================================================
    # Đơn vị
    "kwh", "mwh", "gwh", "gj", "tj", "mj",
    "kilowatt", "megawatt", "gigawatt",
    # Loại năng lượng
    "điện năng", "điện năng tiêu thụ", "điện tiêu thụ",
    "tổng điện", "tổng điện năng", "tổng tiêu thụ điện",
    "năng lượng", "tổng năng lượng", "năng lượng tiêu thụ",
    "tiêu thụ năng lượng", "sử dụng năng lượng",
    "điện lưới", "grid", "điện quốc gia",
    # Năng lượng tái tạo
    "năng lượng tái tạo", "năng lượng tái sinh", "renewable",
    "điện mặt trời", "điện mặt trời áp mái", "solar", "solar rooftop",
    "điện gió", "wind", "phong điện",
    "sinh khối", "biomass", "biogas",
    "thủy điện", "hydro", "hydrogen", "hydrogen xanh",
    # Hiệu quả
    "hiệu quả năng lượng", "tiết kiệm năng lượng",
    "cường độ năng lượng", "energy intensity",
    "re100", "chứng nhận năng lượng",

    # ============================================================
    # 3. WATER — Nước
    # ============================================================
    # Đơn vị
    "m3", "m³", "mét khối", "mét khối nước", "lít", "lit", "liter",
    # Loại nước
    "nước", "tổng nước", "tổng lượng nước",
    "nước tiêu thụ", "nước sử dụng", "nước cấp",
    "tiêu thụ nước", "sử dụng nước",
    "nước ngầm", "nước mặt", "nước mưa",
    "khai thác nước", "lượng nước khai thác",
    # Tái chế
    "nước tái chế", "nước tái sử dụng", "nước tuần hoàn",
    "tái chế nước", "tái sử dụng nước",
    "recycled water", "nước thu hồi", "nước quay vòng",
    # Xử lý
    "nước thải", "xử lý nước thải", "wastewater",
    "xả thải nước", "nước xả",

    # ============================================================
    # 4. WASTE — Chất thải
    # ============================================================
    # Đơn vị
    "tấn", "tân", "ton", "tấn/năm", "kg", "kilogram",
    # Chất thải nói chung
    "chất thải", "rác thải", "chất thải rắn", "chất thải sinh hoạt",
    "chất thải công nghiệp", "chất thải sản xuất",
    "phát sinh chất thải", "tổng chất thải",
    # Chất thải nguy hại
    "chất thải nguy hại", "ctnh", "hazardous waste",
    "chất thải y tế", "chất thải độc hại",
    # Tái chế / tuần hoàn
    "tái chế", "thu hồi", "recycle", "tái sử dụng",
    "tuần hoàn", "kinh tế tuần hoàn", "circular economy",
    "tái chế chất thải", "tỷ lệ tái chế",
    # Xử lý
    "chôn lấp", "landfill", "đổ thải",
    "đốt", "incineration", "đốt rác",
    "ủ phân", "compost", "phân hủy sinh học",

    # ============================================================
    # 5. SUPPLY CHAIN — Chuỗi cung ứng
    # ============================================================
    # Nhà cung cấp
    "nhà cung cấp", "ncc", "supplier", "vendors",
    "đối tác cung ứng", "chuỗi cung ứng", "supply chain",
    "nhà cung ứng", "nhà thầu",
    "đánh giá nhà cung cấp", "đánh giá ncc",
    # Nguyên liệu
    "nguyên liệu", "nguyên vật liệu", "vật liệu đầu vào",
    "raw material", "nguyên liệu đầu vào",
    "nguyên liệu nội địa", "local sourcing",
    "nguyên liệu bền vững", "sustainable material",
    "nguyên liệu tái chế", "recycled material",
    "nguyên liệu sinh học", "bio material",
    # Bao bì
    "bao bì", "packaging", "bao bì bền vững",
    "bao bì tái chế", "bao bì thân thiện môi trường",
    "bao bì sinh học", "biodegradable packaging",
    # Chứng nhận NCC
    "chứng nhận nhà cung cấp", "certified supplier",
    "ncc được chứng nhận", "ncc xanh",

    # ============================================================
    # 6. AUDIT — Kiểm toán
    # ============================================================
    # Kiểm toán
    "kiểm toán", "audit", "kiểm toán độc lập",
    "kiểm toán bên thứ ba", "third party audit",
    "xác minh", "verification", "chứng thực",
    "đánh giá độc lập",
    # Đơn vị kiểm toán
    "deloitte", "kpmg", "pwc", "ernst & young", "ey",
    "bsi", "tüv", "tuv", "tüv rheinland", "tüv norde",
    "sgs", "bureau veritas", "intertek", "dnv",
    "quatest", "quacert", "vinacontrol",
    # Chuẩn
    "iso 14064", "iso 14001", "iso 14067", "iso 14044", "iso 14046",
    "iso 50001", "iso 9001", "iso 45001",
    "gri", "gri standards", "gri 2021",
    "aa1000", "aa1000as",
    "ghg protocol", "ghg protocol corporate",
    "tcfd", "sasb", "csrd", "cbam",
    "tcvn", "tcvn iso",
    # Chứng nhận
    "chứng nhận", "certificate", "certified", "certification",
    "chứng chỉ", "chứng nhận xanh", "green certification",
    "ok compost", "tüv austria ok compost",
    "fda", "reach", "rohs",

    # ============================================================
    # 7. COMPANY — Thông tin doanh nghiệp
    # ============================================================
    # Sản lượng
    "sản lượng", "tổng sản lượng", "sản lượng sản xuất",
    "sản lượng tiêu thụ", "sản lượng bán",
    "sản xuất", "tổng sản xuất", "sản phẩm sản xuất",
    "công suất", "công suất thiết kế", "công suất thực tế",
    "output", "production output",
    # Doanh thu
    "doanh thu", "tổng doanh thu", "doanh thu thuần",
    "net revenue", "revenue",
    "doanh thu hợp nhất", "doanh thu năm",
    # Nhân viên
    "nhân viên", "số nhân viên", "tổng nhân viên",
    "lao động", "số lao động", "người lao động",
    "employees", "headcount", "nhân sự",
    # Khác
    "mã số thuế", "mst", "tax code",
    "ngành nghề", "lĩnh vực kinh doanh", "ngành",
    "nhà máy", "cơ sở sản xuất", "chi nhánh",
    "vốn điều lệ", "vốn chủ sở hữu",
    "tổng tài sản", "lợi nhuận",

    # ============================================================
    # 8. BÁO CÁO / CHUẨN MỰC
    # ============================================================
    "báo cáo thường niên", "báo cáo phát triển bền vững",
    "báo cáo esg", "esg report", "sustainability report",
    "annual report", "báo cáo tài chính hợp nhất",
    "gri", "gri index", "chỉ số gri",
    "mục tiêu phát triển bền vững", "sdg", "17 sdg",
    "net zero", "net zero 2050", "phát thải ròng bằng 0",
    "cam kết khí hậu", "paris agreement", "thỏa thuận paris",
    "kiểm kê khí nhà kính", "ghg inventory",
    "lộ trình giảm phát thải", "lộ trình net zero",
    "kế hoạch hành động", "action plan",
    "đóng góp do quốc gia tự quyết định", "ndc",
]


def _extract_relevant_text(
    text: str,
    max_chars: int = 40000,
    num_buckets: int = RELEVANCE_NUM_BUCKETS,
) -> str:
    """Lọc đoạn có keyword ESG — lấy mẫu TRẢI ĐỀU toàn văn bản (stratified
    theo vị trí), trong mỗi vùng ưu tiên đoạn có nhiều chữ số (khả năng
    chứa số liệu thật) thay vì chỉ lấy các đoạn xuất hiện sớm trong tài
    liệu rồi dừng (bug cũ: `break` khi vừa đủ max_chars khiến các báo cáo
    dài bị cắt mất toàn bộ phần sau, nơi thường chứa bảng số liệu)."""
    lines = text.split("\n")
    n_lines = len(lines)
    if n_lines == 0:
        return text[:max_chars]

    seen_spans = set()
    candidates = []  # (bucket_idx, digit_score, snippet)

    for i, line in enumerate(lines):
        if any(kw in line.lower() for kw in _RELEVANCE_KEYWORDS):
            start = max(0, i - 5)
            end = min(n_lines, i + 6)
            span = (start, end)
            if span in seen_spans:
                continue
            seen_spans.add(span)
            snippet = "\n".join(lines[start:end])
            digit_score = len(_DIGIT_RE.findall(snippet))
            bucket = min(num_buckets - 1, int(i / n_lines * num_buckets))
            candidates.append((bucket, digit_score, snippet))

    if not candidates:
        logger.info(f"Không tìm thấy keyword → dùng {max_chars} ký tự đầu")
        return text[:max_chars]

    total_chars = sum(len(c[2]) for c in candidates)
    if total_chars <= max_chars:
        result_snippets = [c[2] for c in candidates]
        logger.info(
            f"Lọc relevant: {len(result_snippets)} đoạn, {total_chars} ký tự "
            f"(lấy toàn bộ, không cần cắt)"
        )
        return "\n---\n".join(result_snippets)

    # --- Stratified sampling theo vị trí + ưu tiên mật độ số trong từng vùng ---
    buckets = {b: [] for b in range(num_buckets)}
    for b, score, snippet in candidates:
        buckets[b].append((score, snippet))
    for b in buckets:
        buckets[b].sort(key=lambda x: x[0], reverse=True)  # nhiều số trước

    per_bucket_budget = max_chars // num_buckets
    result_snippets = []
    char_count = 0
    leftover = 0

    for b in range(num_buckets):
        budget = per_bucket_budget + leftover
        used = 0
        remaining = []
        for score, snippet in buckets[b]:
            if used + len(snippet) <= budget and char_count + len(snippet) <= max_chars:
                result_snippets.append(snippet)
                used += len(snippet)
                char_count += len(snippet)
            else:
                remaining.append((score, snippet))
        leftover = budget - used  # ngân sách dư của vùng này chuyển sang vùng sau
        buckets[b] = remaining

    # Vòng 2: nếu còn dư ngân sách tổng, lấy thêm phần chưa dùng,
    # ưu tiên điểm mật độ số cao nhất trên toàn tài liệu
    if char_count < max_chars:
        leftover_all = []
        for b in range(num_buckets):
            leftover_all.extend(buckets[b])
        leftover_all.sort(key=lambda x: x[0], reverse=True)
        for score, snippet in leftover_all:
            if char_count + len(snippet) <= max_chars:
                result_snippets.append(snippet)
                char_count += len(snippet)

    logger.info(
        f"Lọc relevant: {len(result_snippets)}/{len(candidates)} đoạn, "
        f"{char_count} ký tự (stratified, {num_buckets} vùng vị trí, ưu tiên mật độ số)"
    )
    return "\n---\n".join(result_snippets)


def _ocr_pages(pdf_bytes: bytes, page_indices: list) -> str:
    """OCR các trang nghi là ảnh/scan bằng pytesseract. Lỗi mềm — không raise,
    chỉ log cảnh báo và trả chuỗi rỗng nếu thiếu dependency hoặc OCR fail."""
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
    except ImportError:
        logger.warning(
            "⚠️  Thiếu pytesseract/pdf2image → không OCR được các trang nghi scan. "
            "Cài: pip install pytesseract pdf2image  +  "
            "apt install tesseract-ocr tesseract-ocr-vie poppler-utils"
        )
        return ""

    try:
        images = convert_from_bytes(pdf_bytes, dpi=200)
    except Exception as e:
        logger.error(f"OCR: lỗi convert PDF→ảnh: {e}")
        return ""

    ocr_chunks = []
    for idx in page_indices:
        if idx >= len(images):
            continue
        try:
            ocr_text = pytesseract.image_to_string(images[idx], lang="vie+eng")
            if ocr_text.strip():
                ocr_chunks.append(ocr_text)
                logger.info(f"  OCR trang {idx + 1}: {len(ocr_text)} ký tự")
        except Exception as e:
            logger.error(f"  OCR trang {idx + 1} lỗi: {e}")

    return "\n".join(ocr_chunks)


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    if pdf_bytes.startswith(b"<!DOC") or pdf_bytes.startswith(b"<html"):
        raise HTTPException(400, "File upload là HTML, không phải PDF.")
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise HTTPException(400, "PDF bảo vệ bằng mật khẩu.")

        text = ""
        scanned_pages = []
        for idx, page in enumerate(reader.pages):
            t = page.extract_text() or ""
            # Trang gần như không có text trích được → nghi ảnh/scan
            if len(t.strip()) < OCR_MIN_TEXT_CHARS_PER_PAGE:
                scanned_pages.append(idx)
            text += t + "\n"

        if scanned_pages:
            logger.warning(
                f"⚠️  {len(scanned_pages)}/{len(reader.pages)} trang có vẻ là ảnh/scan "
                f"(< {OCR_MIN_TEXT_CHARS_PER_PAGE} ký tự text/trang): "
                f"{scanned_pages[:20]}{'...' if len(scanned_pages) > 20 else ''}"
            )
            if ENABLE_OCR_FALLBACK:
                ocr_text = _ocr_pages(pdf_bytes, scanned_pages)
                if ocr_text:
                    text += "\n" + ocr_text
                    logger.info(f"  → OCR bổ sung {len(ocr_text)} ký tự")
            else:
                logger.warning(
                    "ENABLE_OCR_FALLBACK=false → bỏ qua OCR. Số liệu nằm trong "
                    "các trang này (nếu có) sẽ KHÔNG được trích xuất."
                )

        return text
    except HTTPException:
        raise
    except (PdfReadError, PdfStreamError) as e:
        raise HTTPException(400, f"PDF không hợp lệ: {e}")
    except Exception as e:
        raise HTTPException(400, f"Lỗi đọc PDF: {e}")


def _chunk_by_paragraphs(text: str, chunk_size: int) -> list:
    """Chunk text theo đoạn văn, không cắt giữa câu."""
    chunks = []
    current = ""
    for para in text.split("\n"):
        if len(current) + len(para) + 1 > chunk_size:
            if current.strip():
                chunks.append(current.strip())
            current = para + "\n"
        else:
            current += para + "\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _safe_float(v):
    try:
        if v is None:
            return 0.0
        if isinstance(v, str):
            v = re.sub(r"[^\d.\-]", "", v) or 0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(v):
    try:
        if v is None:
            return None
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _parse_date(v):
    if not v or v == "Unknown":
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(v), fmt).date()
        except ValueError:
            continue
    return None


def _serialize_row(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, (date, datetime)):
            out[k] = v.isoformat()
        elif isinstance(v, Decimal):
            out[k] = float(v)
        else:
            out[k] = v
    return out


# ============================================================
# LLM EXTRACT — chỉ trích RAW
# ============================================================
def _parse_json_safely(raw: str) -> dict:
    """Parse JSON, tự sửa nếu bị cắt."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON lỗi lần 1: {e}")

    try:
        last_brace = raw.rfind("}")
        if last_brace > 0:
            return json.loads(raw[:last_brace + 1])
    except json.JSONDecodeError:
        pass

    try:
        open_b = raw.count("{") - raw.count("}")
        open_k = raw.count("[") - raw.count("]")
        fixed = raw.rstrip().rstrip(",")
        if fixed.count('"') % 2 == 1:
            fixed += '"'
        fixed += "]" * max(0, open_k)
        fixed += "}" * max(0, open_b)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    raise HTTPException(500, f"Không parse được JSON. Cuối: {raw[-200:]!r}")


def _debug_dump_text_sample(text_sample: str) -> None:
    """Ghi text_sample thực tế đưa cho LLM ra file, để kiểm tra bằng mắt
    xem có chứa số liệu thật hay không. Bật qua .env: DEBUG_DUMP_TEXT_SAMPLE=true"""
    if not DEBUG_DUMP_TEXT_SAMPLE:
        return
    try:
        os.makedirs(DEBUG_DUMP_DIR, exist_ok=True)
        fname = os.path.join(
            DEBUG_DUMP_DIR, f"text_sample_{datetime.now():%Y%m%d_%H%M%S}.txt"
        )
        with open(fname, "w", encoding="utf-8") as f:
            f.write(text_sample)
        logger.info(f"🔍 DEBUG: đã dump text_sample ra {fname} ({len(text_sample)} ký tự)")
    except Exception as e:
        logger.warning(f"DEBUG dump text_sample lỗi: {e}")


def extract_esg_json(text: str) -> dict:
    """Multi-pass: gọi LLM 4 lần cho 4 nhóm field."""
    text_sample = _extract_relevant_text(text, MAX_TEXT_CHARS_FOR_LLM)
    _debug_dump_text_sample(text_sample)

    logger.info("=" * 60)
    logger.info(f"Multi-pass extraction: 4 lần gọi LLM (text={len(text_sample)} chars)")
    logger.info("=" * 60)

    # Pass 1: company + reporting
    r1 = _call_llm_for_json(
        PROMPT_COMPANY.format(report_text=text_sample),
        label="1/4 company+reporting",
    )

    # Pass 2: emissions + energy
    r2 = _call_llm_for_json(
        PROMPT_EMISSIONS_ENERGY.format(report_text=text_sample),
        label="2/4 emissions+energy",
    )

    # Pass 3: water + waste
    r3 = _call_llm_for_json(
        PROMPT_WATER_WASTE.format(report_text=text_sample),
        label="3/4 water+waste",
    )

    # Pass 4: supply_chain + audit
    r4 = _call_llm_for_json(
        PROMPT_SUPPLY_AUDIT.format(report_text=text_sample),
        label="4/4 supply+audit",
    )

    # Merge
    merged = {
        "company": r1.get("company", {}),
        "reporting": r1.get("reporting", {}),
        "emissions": r2.get("emissions", {}),
        "energy": r2.get("energy", {}),
        "water": r3.get("water", {}),
        "waste": r3.get("waste", {}),
        "supply_chain": r4.get("supply_chain", {}),
        "audit": r4.get("audit", {}),
    }

    # Đảm bảo nested là dict
    for key in merged:
        if not isinstance(merged[key], dict):
            merged[key] = {}

    # Validate Pydantic
    validated = EsgExtraction(**merged).model_dump()

    # Đếm số nhóm có dữ liệu
    def _has_value(d: dict) -> bool:
        for v in d.values():
            if isinstance(v, (int, float)) and v > 0:
                return True
            if isinstance(v, str) and v and v != "Unknown":
                return True
        return False

    filled = sum(1 for k in ("company", "reporting", "emissions",
                              "energy", "water", "waste",
                              "supply_chain", "audit")
                 if _has_value(validated.get(k, {})))

    logger.info("=" * 60)
    logger.info(f"✅ Multi-pass xong: {filled}/8 nhóm có dữ liệu")
    logger.info(f"   company={validated['company']['name']}")
    logger.info(f"   scope1={validated['emissions']['scope1_tco2e']} tCO2e")
    logger.info(f"   total_kwh={validated['energy']['total_kwh']} kWh")
    logger.info(f"   water={validated['water']['consumption_m3']} m3")
    logger.info(f"   waste={validated['waste']['total_ton']} tấn")
    logger.info("=" * 60)

    return validated

# ============================================================
# SAVE POSTGRES — lưu RAW + DERIVED
# ============================================================
def save_to_postgres(raw_data: dict) -> tuple:
    """
    1. Tính derived từ raw
    2. Validate consistency
    3. Lưu RAW + DERIVED vào DB
    Returns: (metric_id, computed_data, warnings)
    """
    # --- Tính toán ---
    computed = compute_all_derived(raw_data)

    # --- Validate ---
    warnings = validate_consistency(computed)
    if warnings:
        logger.warning(f"Có {len(warnings)} cảnh báo consistency")

    c = computed["company"]
    r = computed["reporting"]
    a = computed["audit"]

    try:
        with get_pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO esg_metrics (
                        -- company
                        company_name, tax_code, industry, industry_code,
                        facility_name, employee_count, revenue_vnd, production_output_ton,
                        -- reporting
                        reporting_year, reporting_period, reporting_standard, baseline_year,
                        -- VGPI breakdown (DERIVED)
                        vgpi_score, energy_efficiency, co2_reduction,
                        waste_circularity, renewable_energy_pct, supply_chain_sustainability,
                        -- emissions (RAW + DERIVED)
                        scope1_tco2e, scope2_tco2e, scope3_tco2e, total_tco2e,
                        baseline_total_tco2e, reduction_pct, intensity_tco2e_per_ton,
                        -- energy
                        total_kwh, grid_kwh, renewable_kwh,
                        energy_renewable_pct, energy_intensity_kwh_per_ton,
                        -- water
                        water_consumption_m3, water_recycled_m3, water_recycling_rate,
                        -- waste
                        waste_total_ton, waste_recycled_ton, waste_landfill_ton,
                        hazardous_waste_ton, waste_recycling_rate,
                        -- supply chain (RAW)
                        local_sourcing_pct, certified_suppliers_count,
                        total_suppliers_count, sustainable_packaging_pct,
                        -- audit
                        audit_by, audit_standard, audit_report_number,
                        audit_date, audit_valid_until, verification_level
                    ) VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,
                        %s,%s,%s,
                        %s,%s,%s,%s,%s,
                        %s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s
                    ) RETURNING id;
                """, (
                    c["name"], c.get("tax_code"), c.get("industry"), c.get("industry_code"),
                    c.get("facility_name"), _safe_int(c.get("employee_count")),
                    _safe_float(c.get("revenue_vnd")), _safe_float(c.get("production_output_ton")),

                    _safe_int(r.get("year")), r.get("period"), r.get("standard"),
                    _safe_int(r.get("baseline_year")),

                    computed["vgpi_score"], computed["energy_efficiency"],
                    computed["co2_reduction"], computed["waste_circularity"],
                    computed["renewable_energy_pct"], computed["supply_chain_sustainability"],

                    _safe_float(computed["emissions_raw"].get("scope1_tco2e")),
                    _safe_float(computed["emissions_raw"].get("scope2_tco2e")),
                    _safe_float(computed["emissions_raw"].get("scope3_tco2e")),
                    _safe_float(computed["total_tco2e"]),
                    _safe_float(computed["emissions_raw"].get("baseline_total_tco2e")),
                    _safe_float(computed["reduction_pct"]),
                    _safe_float(computed["intensity_tco2e_per_ton"]),

                    _safe_float(computed["energy_raw"].get("total_kwh")),
                    _safe_float(computed["energy_raw"].get("grid_kwh")),
                    _safe_float(computed["energy_raw"].get("renewable_kwh")),
                    _safe_float(computed["renewable_pct"]),
                    _safe_float(computed["intensity_kwh_per_ton"]),

                    _safe_float(computed["water_raw"].get("consumption_m3")),
                    _safe_float(computed["water_raw"].get("recycled_m3")),
                    _safe_float(computed["water_recycling_rate"]),

                    _safe_float(computed["waste_raw"].get("total_ton")),
                    _safe_float(computed["waste_raw"].get("recycled_ton")),
                    _safe_float(computed["waste_raw"].get("landfill_ton")),
                    _safe_float(computed["waste_raw"].get("hazardous_ton")),
                    _safe_float(computed["waste_recycling_rate"]),

                    _safe_float(computed["supply_chain_raw"].get("local_sourcing_pct")),
                    _safe_int(computed["supply_chain_raw"].get("certified_suppliers_count")),
                    _safe_int(computed["supply_chain_raw"].get("total_suppliers_count")),
                    _safe_float(computed["supply_chain_raw"].get("sustainable_packaging_pct")),

                    a.get("audit_by", "Unknown"), a.get("standard"),
                    a.get("report_number"),
                    _parse_date(a.get("audit_date")),
                    _parse_date(a.get("valid_until")),
                    a.get("verification_level"),
                ))

                metric_id = cur.fetchone()[0]

                # Certificates
                for cert in a.get("certificates", []):
                    cur.execute("""
                        INSERT INTO certificates (metric_id, cert_type, cert_number, expiry_date)
                        VALUES (%s, %s, %s, %s);
                    """, (
                        metric_id,
                        cert.get("type", "Unknown"),
                        cert.get("number"),
                        _parse_date(cert.get("expiry")),
                    ))

                # Audit log — lưu cả RAW + DERIVED + warnings
                cur.execute("""
                    INSERT INTO audit_logs (action, entity_type, entity_id, detail)
                    VALUES ('insert', 'esg_metrics', %s, %s);
                """, (metric_id, json.dumps({
                    "raw": raw_data,
                    "derived": {k: v for k, v in computed.items()
                                if k not in ("company", "reporting", "audit",
                                             "emissions_raw", "energy_raw",
                                             "water_raw", "waste_raw",
                                             "supply_chain_raw")},
                    "warnings": warnings,
                }, ensure_ascii=False)))

            conn.commit()
            logger.info(f"Đã lưu metric_id={metric_id} | VGPI={computed['vgpi_score']}")
            return metric_id, computed, warnings

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Lỗi lưu PostgreSQL")
        raise HTTPException(500, f"Lỗi lưu PostgreSQL: {e}")


# ============================================================
# SAVE QDRANT
# ============================================================
def _embed_chunk(chunk: str):
    return ollama.embeddings(model=OLLAMA_EMBED_MODEL, prompt=chunk)["embedding"]


def save_to_qdrant(doc_id: int, text: str, company_name: str):
    try:
        # Chunk theo đoạn văn (tốt hơn cắt cứng)
        chunks = _chunk_by_paragraphs(text, CHUNK_SIZE)
        chunks = chunks[:MAX_CHUNKS]
        if not chunks:
            logger.warning(f"Không có chunk nào cho doc {doc_id}")
            return

        logger.info(f"Bắt đầu embed {len(chunks)} chunks cho doc {doc_id}...")

        # Embed tuần tự hoặc concurrency thấp
        vectors = []
        for i, chunk in enumerate(chunks):
            try:
                vec = ollama.embeddings(
                    model=OLLAMA_EMBED_MODEL,
                    prompt=chunk,
                )["embedding"]
                vectors.append(vec)
                if (i + 1) % 10 == 0:
                    logger.info(f"  Đã embed {i+1}/{len(chunks)} chunks")
            except Exception as e:
                logger.error(f"  Embed chunk {i} lỗi: {e}")
                vectors.append(None)

        # Tạo points
        points = []
        for idx, (chunk, vec) in enumerate(zip(chunks, vectors)):
            if vec is None or len(vec) != EMBED_DIM:
                continue
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"vietgreen-{doc_id}-{idx}"))
            points.append(PointStruct(
                id=point_id, vector=vec,
                payload={"doc_id": doc_id, "company_name": company_name,
                         "content": chunk, "chunk_index": idx},
            ))

        if not points:
            logger.warning(f"Không có point hợp lệ nào để upsert")
            return

        # ✅ Batch upsert để tránh overload
        batch_size = 20
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            qdrant_client.upsert(
                collection_name=QDRANT_COLLECTION,
                points=batch,
                wait=True,
            )
            logger.info(f"  Đã upsert batch {i//batch_size + 1} ({len(batch)} points)")

        logger.info(f"✅ Đã upsert {len(points)} chunk cho doc {doc_id}")

    except Exception as e:
        logger.exception(f"save_to_qdrant lỗi")
        raise HTTPException(500, f"Lỗi Qdrant: {type(e).__name__}: {e}")


# ============================================================
# ROUTES
# ============================================================
@app.post("/api/v1/process-document")
async def process_document(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Chỉ chấp nhận file PDF.")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(400, "File rỗng.")

    raw_text = extract_text_from_pdf(pdf_bytes)
    if not raw_text.strip():
        raise HTTPException(400, "Không trích xuất được văn bản.")

    logger.info(f"[1/4] PDF text len={len(raw_text)}")

    # Bước 2: LLM extract RAW
    raw_data = await anyio.to_thread.run_sync(extract_esg_json, raw_text)
    logger.info(f"[2/4] LLM extract RAW OK")

    # Bước 3: Tính toán + lưu DB
    db_id, computed, warnings = await anyio.to_thread.run_sync(
        save_to_postgres, raw_data
    )
    logger.info(f"[3/4] Đã tính toán + lưu DB, id={db_id}")

    # Bước 4: Qdrant
    try:
        await anyio.to_thread.run_sync(
            partial(save_to_qdrant, db_id, raw_text, raw_data["company"]["name"])
        )
        logger.info(f"[4/4] Đã lưu Qdrant cho doc_id={db_id}")
    except Exception as e:
        logger.error(f"Qdrant lỗi, rollback PG record_id={db_id}: {e}")
        try:
            with get_pg_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM esg_metrics WHERE id = %s", (db_id,))
                conn.commit()
        except Exception as rb_err:
            logger.error(f"Rollback thất bại: {rb_err}")
        raise HTTPException(500, f"Đã rollback do lỗi Qdrant: {e}")

    return {
        "status": "success",
        "message": "Đã xử lý tài liệu thành công!",
        "record_id": db_id,
        "raw_data": raw_data,          # dữ liệu LLM trích
        "computed": {
            "vgpi_score": computed["vgpi_score"],
            "energy_efficiency": computed["energy_efficiency"],
            "co2_reduction": computed["co2_reduction"],
            "waste_circularity": computed["waste_circularity"],
            "renewable_energy_pct": computed["renewable_energy_pct"],
            "supply_chain_sustainability": computed["supply_chain_sustainability"],
            "total_tco2e": computed["total_tco2e"],
            "reduction_pct": computed["reduction_pct"],
            "intensity_tco2e_per_ton": computed["intensity_tco2e_per_ton"],
            "renewable_pct": computed["renewable_pct"],
            "intensity_kwh_per_ton": computed["intensity_kwh_per_ton"],
            "water_recycling_rate": computed["water_recycling_rate"],
            "waste_recycling_rate": computed["waste_recycling_rate"],
        },
        "warnings": warnings,          # cảnh báo consistency
    }


@app.get("/api/v1/metrics/{metric_id}")
async def get_metric(metric_id: int):
    with get_pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM esg_metrics WHERE id = %s", (metric_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, "Không tìm thấy.")
            cols = [d[0] for d in cur.description]
    return _serialize_row(dict(zip(cols, row)))


@app.get("/api/v1/health")
async def health_check():
    return {
        "status": "ok",
        "qdrant_collection": QDRANT_COLLECTION,
        "postgres_connected": True,
    }
