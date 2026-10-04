"""Kiểm tra tính nhất quán của dữ liệu sau khi tính toán."""
import logging
import re
from typing import Dict, Any, List, Tuple

logger = logging.getLogger("vietgreen_validators")

# Ngưỡng "hợp lý tối đa" cho từng chỉ số tuyệt đối — hào phóng cho cả nhà máy
# quy mô lớn. Vượt ngưỡng này thường là dấu hiệu LLM nối nhầm số từ bảng bị
# pypdf xáo trộn thứ tự cột/dòng, chứ không phải số liệu thật.
_PLAUSIBLE_MAX = {
    "water_consumption_m3": 20_000_000,
    "waste_total_ton": 2_000_000,
    "total_kwh": 5_000_000_000,
    "scope1_tco2e": 50_000_000,
    "scope2_tco2e": 50_000_000,
    "scope3_tco2e": 50_000_000,
}

# Trường có giá trị nhỏ/phần trăm — KHÔNG đưa vào kiểm tra "trùng số giữa 2
# nhóm", vì các số nhỏ (0, 100, 50...) trùng nhau là chuyện bình thường,
# không phải dấu hiệu lấy nhầm.
_COLLISION_MIN_VALUE = 1000


def _collect_large_fields(computed: Dict[str, Any]) -> List[Tuple[str, float, str]]:
    """Gom các trường số RAW có giá trị > _COLLISION_MIN_VALUE, kèm tên nhóm,
    để dò trùng khớp chính xác giữa các nhóm khác nhau (dấu hiệu LLM lấy nhầm
    số của trường này gán cho trường khác)."""
    groups = {
        "emissions": computed.get("emissions_raw", {}),
        "energy": computed.get("energy_raw", {}),
        "water": computed.get("water_raw", {}),
        "waste": computed.get("waste_raw", {}),
    }
    out = []
    for gname, gdata in groups.items():
        for field, val in gdata.items():
            if isinstance(val, (int, float)) and val > _COLLISION_MIN_VALUE:
                out.append((f"{gname}.{field}", float(val), gname))
    return out


def _check_company_name_merge(name: str) -> str | None:
    """Heuristic tổng quát: tên doanh nghiệp có ngoặc đơn chứa cụm từ khác hẳn
    phần tên chính — khả năng LLM đã gộp nhầm 2 doanh nghiệp khác nhau (dùng
    kiến thức ngoài để "đoán" tên đầy đủ thay vì chỉ copy từ báo cáo)."""
    if not name or name == "Unknown":
        return None
    m = re.search(r"^(.*?)\(([^)]+)\)", name)
    if not m:
        return None
    outside = re.sub(r"[^A-Za-zÀ-ỹ]", "", m.group(1)).lower()
    inside = re.sub(r"[^A-Za-zÀ-ỹ]", "", m.group(2)).lower()
    if not outside or not inside:
        return None
    # Nếu phần trong ngoặc không chia sẻ chuỗi con nào (>=3 ký tự) với phần
    # ngoài ngoặc → khả năng cao là 2 thực thể không liên quan bị gộp lại.
    shares_substring = any(
        outside[i:i + 3] in inside for i in range(len(outside) - 2)
    )
    if not shares_substring:
        return (
            f"company.name = \"{name}\" — phần trong ngoặc có vẻ không liên quan "
            f"tới phần tên chính, nghi LLM tự gộp/suy luận thêm tên doanh nghiệp "
            f"khác (dùng kiến thức ngoài báo cáo) — cần đối chiếu thủ công với PDF gốc"
        )
    return None


def validate_consistency(computed: Dict[str, Any]) -> List[str]:
    """
    Trả về list cảnh báo (rỗng = không có vấn đề).
    """
    warnings = []

    # --- 1. Tổng Scope = Total ---
    e = computed.get("emissions_raw", {})
    s1, s2, s3 = (
        e.get("scope1_tco2e", 0),
        e.get("scope2_tco2e", 0),
        e.get("scope3_tco2e", 0),
    )
    total = computed.get("total_tco2e", 0)
    if total > 0 and abs((s1 + s2 + s3) - total) > 1:
        warnings.append(
            f"Tổng Scope 1+2+3 ({s1+s2+s3}) ≠ tổng tính được ({total})"
        )

    # --- 2. Reduction % không âm vô lý ---
    reduction = computed.get("reduction_pct", 0)
    if reduction < -100 or reduction > 100:
        warnings.append(f"reduction_pct={reduction}% nằm ngoài [-100, 100]")

    # --- 3. Renewable kWh ≤ Total kWh ---
    en = computed.get("energy_raw", {})
    if en.get("renewable_kwh", 0) > en.get("total_kwh", 0) + 0.01:
        warnings.append(
            f"renewable_kwh ({en.get('renewable_kwh')}) > total_kwh ({en.get('total_kwh')})"
        )

    # --- 4. Recycled ≤ Total (nước, rác) ---
    w = computed.get("water_raw", {})
    if w.get("recycled_m3", 0) > w.get("consumption_m3", 0) + 0.01:
        warnings.append("recycled_m3 > consumption_m3")

    ws = computed.get("waste_raw", {})
    if ws.get("recycled_ton", 0) > ws.get("total_ton", 0) + 0.01:
        warnings.append("recycled_ton > total_ton")

    if ws.get("landfill_ton", 0) > ws.get("total_ton", 0) + 0.01:
        warnings.append("landfill_ton > total_ton")

    # --- 5. VGPI trong [0, 100] ---
    vgpi = computed.get("vgpi_score", 0)
    if vgpi < 0 or vgpi > 100:
        warnings.append(f"VGPI={vgpi} nằm ngoài [0, 100]")

    # --- 6. Không có sản lượng → VGPI có thể sai ---
    if not computed.get("company", {}).get("production_output_ton"):
        warnings.append(
            "Thiếu production_output_ton → intensity & VGPI có thể không chính xác"
        )

    # --- 7. Giá trị tuyệt đối vượt ngưỡng hợp lý (nghi LLM nối nhầm số) ---
    _flat_values = {
        "water_consumption_m3": w.get("consumption_m3", 0),
        "waste_total_ton": ws.get("total_ton", 0),
        "total_kwh": en.get("total_kwh", 0),
        "scope1_tco2e": s1,
        "scope2_tco2e": s2,
        "scope3_tco2e": s3,
    }
    for key, val in _flat_values.items():
        limit = _PLAUSIBLE_MAX.get(key)
        if limit and val and val > limit:
            warnings.append(
                f"{key}={val:,.0f} vượt ngưỡng hợp lý ({limit:,.0f}) — nghi LLM "
                f"trích nhầm (nối số từ bảng bị pypdf xáo trộn), nên đối chiếu "
                f"lại với text_sample gốc (DEBUG_DUMP_TEXT_SAMPLE=true)"
            )

    # --- 8. Tỷ lệ tái chế bất thường thấp (< 0.1%) nhưng vẫn > 0
    #        → dấu hiệu total_ton bị lấy nhầm thành số rất lớn của trường khác ---
    if ws.get("total_ton", 0) > 0:
        waste_rate = ws.get("recycled_ton", 0) / ws.get("total_ton", 1) * 100
        if 0 < waste_rate < 0.1:
            warnings.append(
                f"waste recycling rate = {waste_rate:.3f}% — bất thường thấp, "
                f"nghi waste.total_ton bị lấy nhầm số của trường khác"
            )

    # --- 9. baseline_total_tco2e trùng với scope1/2/3 hoặc tổng hiện tại
    #        → dấu hiệu LLM điền tạm thay vì null khi không tìm thấy baseline ---
    baseline = e.get("baseline_total_tco2e", 0)
    if baseline > 0 and baseline in (s1, s2, s3, s1 + s2 + s3):
        warnings.append(
            f"baseline_total_tco2e ({baseline}) trùng với scope1/2/3 hoặc tổng "
            f"phát thải năm hiện tại — nghi LLM điền nhầm thay vì để null "
            f"(baseline phải là số liệu RIÊNG của năm cơ sở)"
        )

    # --- 10. Trùng số chính xác giữa 2 nhóm chỉ số khác nhau (tổng quát) —
    #         bắt mọi kiểu "lấy nhầm số của trường A gán cho trường B",
    #         không riêng gì waste/energy ---
    large_fields = _collect_large_fields(computed)
    for i in range(len(large_fields)):
        path_a, val_a, group_a = large_fields[i]
        for j in range(i + 1, len(large_fields)):
            path_b, val_b, group_b = large_fields[j]
            if group_a != group_b and abs(val_a - val_b) < 0.01:
                warnings.append(
                    f"{path_a} = {path_b} = {val_a:,.0f} — trùng CHÍNH XÁC giữa "
                    f"2 nhóm chỉ số khác nhau, khả năng rất cao LLM lấy nhầm số "
                    f"của trường này gán cho trường kia"
                )

    # --- 11. Tên doanh nghiệp nghi bị gộp nhầm 2 thực thể khác nhau ---
    name_warning = _check_company_name_merge(computed.get("company", {}).get("name", ""))
    if name_warning:
        warnings.append(name_warning)

    for w_ in warnings:
        logger.warning(f"⚠️  {w_}")

    return warnings
