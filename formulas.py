"""Công thức tính toán cho VietGreen.
Mọi chỉ số phái sinh đều tính ở đây, KHÔNG copy từ LLM.
"""
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger("vietgreen_formulas")


# ============================================================
# 1. EMISSIONS
# ============================================================
def compute_total_emissions(e: Dict[str, float]) -> float:
    """Tổng phát thải = Scope 1 + Scope 2 + Scope 3."""
    return round(
        e.get("scope1_tco2e", 0)
        + e.get("scope2_tco2e", 0)
        + e.get("scope3_tco2e", 0),
        2
    )


def compute_reduction_pct(e: Dict[str, float], total: float) -> float:
    """% giảm phát thải so với baseline."""
    baseline = e.get("baseline_total_tco2e", 0)
    if baseline <= 0:
        return 0.0
    return round((baseline - total) / baseline * 100, 2)


def compute_carbon_intensity(total_tco2e: float, output_ton: float) -> float:
    """Cường độ carbon (tCO2e/tấn sản phẩm)."""
    if output_ton <= 0:
        return 0.0
    return round(total_tco2e / output_ton, 4)


# ============================================================
# 2. ENERGY
# ============================================================
def compute_renewable_pct(en: Dict[str, float]) -> float:
    """% năng lượng tái tạo."""
    total = en.get("total_kwh", 0)
    if total <= 0:
        return 0.0
    renewable = en.get("renewable_kwh", 0)
    return round(renewable / total * 100, 2)


def compute_energy_intensity(total_kwh: float, output_ton: float) -> float:
    """Cường độ năng lượng (kWh/tấn)."""
    if output_ton <= 0:
        return 0.0
    return round(total_kwh / output_ton, 2)


# ============================================================
# 3. WATER
# ============================================================
def compute_water_recycling_pct(w: Dict[str, float]) -> float:
    """% nước tái chế."""
    consumed = w.get("consumption_m3", 0)
    if consumed <= 0:
        return 0.0
    recycled = w.get("recycled_m3", 0)
    return round(recycled / consumed * 100, 2)


# ============================================================
# 4. WASTE
# ============================================================
def compute_waste_recycling_pct(ws: Dict[str, float]) -> float:
    """% chất thải tái chế."""
    total = ws.get("total_ton", 0)
    if total <= 0:
        return 0.0
    recycled = ws.get("recycled_ton", 0)
    return round(recycled / total * 100, 2)


def compute_landfill_rate(ws: Dict[str, float]) -> float:
    """% chất thải chôn lấp."""
    total = ws.get("total_ton", 0)
    if total <= 0:
        return 0.0
    landfill = ws.get("landfill_ton", 0)
    return round(landfill / total * 100, 2)


# ============================================================
# 5. SUPPLY CHAIN
# ============================================================
def compute_certified_supplier_pct(sc: Dict[str, Any]) -> float:
    """% nhà cung cấp có chứng nhận."""
    total = sc.get("total_suppliers_count", 0)
    if total <= 0:
        return 0.0
    certified = sc.get("certified_suppliers_count", 0)
    return round(certified / total * 100, 2)


# ============================================================
# 6. VGPI — CHỈ SỐ TỔNG HỢP
# Trọng số theo PRD VietGreen:
#   - Hiệu quả Năng lượng:      20%
#   - Giảm Phát thải Carbon:    25%
#   - Chất thải & Tuần hoàn:    20%
#   - Năng lượng Tái tạo:       15%
#   - Chuỗi Cung ứng Bền vững:  20%
# ============================================================
VGPI_WEIGHTS = {
    "energy_efficiency": 0.20,
    "carbon_reduction": 0.25,
    "waste_circularity": 0.20,
    "renewable_energy": 0.15,
    "supply_chain": 0.20,
}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Kẹp giá trị vào [lo, hi]."""
    return max(lo, min(hi, v))


def _score_energy_efficiency(energy_intensity_kwh_per_ton: float,
                              benchmark: float = 4000.0) -> float:
    """
    Điểm hiệu quả năng lượng (0-100).
    Càng ít kWh/tấn → càng cao điểm.
    benchmark = 4000 kWh/tấn (trung bình ngành).
    """
    if energy_intensity_kwh_per_ton <= 0:
        return 0.0
    # 0 kWh/tấn = 100 điểm; >= benchmark = 0 điểm
    score = 100 * (1 - energy_intensity_kwh_per_ton / benchmark)
    return round(_clamp(score), 2)


def _score_carbon_reduction(reduction_pct: float) -> float:
    """
    Điểm giảm phát thải carbon (0-100).
    Giảm 50% so baseline = 100 điểm.
    """
    if reduction_pct <= 0:
        return 0.0
    return round(_clamp(reduction_pct * 2), 2)  # 50% → 100 điểm


def _score_waste_circularity(recycling_pct: float) -> float:
    """Điểm tuần hoàn chất thải (0-100) = % tái chế."""
    return round(_clamp(recycling_pct), 2)


def _score_renewable_energy(renewable_pct: float) -> float:
    """
    Điểm năng lượng tái tạo (0-100).
    RE100 (100% tái tạo) = 100 điểm.
    """
    return round(_clamp(renewable_pct), 2)


def _score_supply_chain(certified_pct: float,
                         local_pct: float,
                         sustainable_pkg_pct: float) -> float:
    """
    Điểm chuỗi cung ứng (0-100).
    = 0.5 * %NCC có chứng nhận + 0.25 * %nội địa + 0.25 * %bao bì bền vững
    """
    score = (
        0.50 * certified_pct
        + 0.25 * local_pct
        + 0.25 * sustainable_pkg_pct
    )
    return round(_clamp(score), 2)


def compute_vgpi(
    energy_efficiency_score: float,
    carbon_reduction_score: float,
    waste_circularity_score: float,
    renewable_energy_score: float,
    supply_chain_score: float,
) -> float:
    """VGPI tổng hợp (0-100)."""
    vgpi = (
        VGPI_WEIGHTS["energy_efficiency"] * energy_efficiency_score
        + VGPI_WEIGHTS["carbon_reduction"] * carbon_reduction_score
        + VGPI_WEIGHTS["waste_circularity"] * waste_circularity_score
        + VGPI_WEIGHTS["renewable_energy"] * renewable_energy_score
        + VGPI_WEIGHTS["supply_chain"] * supply_chain_score
    )
    return round(vgpi, 2)


# ============================================================
# 7. HÀM TỔNG — tính tất cả từ RAW
# ============================================================
def compute_all_derived(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Input: dict với RAW data (company, emissions, energy, water, waste, supply_chain)
    Output: dict với TẤT CẢ chỉ số (raw + derived + vgpi_breakdown)
    """
    company = data.get("company", {})
    emissions = data.get("emissions", {})
    energy = data.get("energy", {})
    water = data.get("water", {})
    waste = data.get("waste", {})
    supply_chain = data.get("supply_chain", {})

    output_ton = company.get("production_output_ton") or 0

    # --- Emissions ---
    total_emissions = compute_total_emissions(emissions)
    reduction_pct = compute_reduction_pct(emissions, total_emissions)
    carbon_intensity = compute_carbon_intensity(total_emissions, output_ton)

    # --- Energy ---
    renewable_pct = compute_renewable_pct(energy)
    energy_intensity = compute_energy_intensity(
        energy.get("total_kwh", 0), output_ton
    )

    # --- Water ---
    water_recycling_pct = compute_water_recycling_pct(water)

    # --- Waste ---
    waste_recycling_pct = compute_waste_recycling_pct(waste)
    landfill_rate = compute_landfill_rate(waste)

    # --- Supply chain ---
    certified_supplier_pct = compute_certified_supplier_pct(supply_chain)

    # --- Điểm 5 trụ cột ---
    score_energy = _score_energy_efficiency(energy_intensity)
    score_carbon = _score_carbon_reduction(reduction_pct)
    score_waste = _score_waste_circularity(waste_recycling_pct)
    score_renewable = _score_renewable_energy(renewable_pct)
    score_supply = _score_supply_chain(
        certified_supplier_pct,
        supply_chain.get("local_sourcing_pct", 0),
        supply_chain.get("sustainable_packaging_pct", 0),
    )

    # --- VGPI ---
    vgpi_score = compute_vgpi(
        score_energy, score_carbon, score_waste, score_renewable, score_supply
    )

    logger.info(
        f"VGPI={vgpi_score} | E={score_energy} C={score_carbon} "
        f"W={score_waste} R={score_renewable} S={score_supply}"
    )

    return {
        # RAW
        "company": company,
        "reporting": data.get("reporting", {}),
        "emissions_raw": emissions,
        "energy_raw": energy,
        "water_raw": water,
        "waste_raw": waste,
        "supply_chain_raw": supply_chain,
        "audit": data.get("audit", {}),

        # DERIVED
        "total_tco2e": total_emissions,
        "reduction_pct": reduction_pct,
        "intensity_tco2e_per_ton": carbon_intensity,
        "renewable_pct": renewable_pct,
        "intensity_kwh_per_ton": energy_intensity,
        "water_recycling_rate": water_recycling_pct,
        "waste_recycling_rate": waste_recycling_pct,
        "landfill_rate": landfill_rate,
        "certified_supplier_pct": certified_supplier_pct,

        # VGPI BREAKDOWN
        "vgpi_score": vgpi_score,
        "energy_efficiency": score_energy,
        "co2_reduction": score_carbon,
        "waste_circularity": score_waste,
        "renewable_energy_pct": score_renewable,
        "supply_chain_sustainability": score_supply,
    }
