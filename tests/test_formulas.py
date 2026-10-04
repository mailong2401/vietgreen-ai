import pytest
from formulas import (
    compute_total_emissions, compute_reduction_pct,
    compute_renewable_pct, compute_water_recycling_pct,
    compute_waste_recycling_pct, compute_vgpi,
    compute_all_derived,
)


def test_total_emissions():
    e = {"scope1_tco2e": 100, "scope2_tco2e": 200, "scope3_tco2e": 300}
    assert compute_total_emissions(e) == 600.0


def test_reduction_pct():
    e = {"baseline_total_tco2e": 1000}
    assert compute_reduction_pct(e, 700) == 30.0
    assert compute_reduction_pct(e, 1000) == 0.0
    assert compute_reduction_pct({"baseline_total_tco2e": 0}, 500) == 0.0


def test_renewable_pct():
    assert compute_renewable_pct({"total_kwh": 1000, "renewable_kwh": 250}) == 25.0
    assert compute_renewable_pct({"total_kwh": 0, "renewable_kwh": 100}) == 0.0


def test_water_recycling_pct():
    assert compute_water_recycling_pct({"consumption_m3": 1000, "recycled_m3": 600}) == 60.0


def test_waste_recycling_pct():
    assert compute_waste_recycling_pct({"total_ton": 100, "recycled_ton": 80}) == 80.0


def test_vgpi_formula():
    """VGPI = 0.20*E + 0.25*C + 0.20*W + 0.15*R + 0.20*S"""
    vgpi = compute_vgpi(
        energy_efficiency_score=80,
        carbon_reduction_score=90,
        waste_circularity_score=70,
        renewable_energy_score=50,
        supply_chain_score=60,
    )
    expected = 0.20*80 + 0.25*90 + 0.20*70 + 0.15*50 + 0.20*60
    assert vgpi == round(expected, 2)
    # = 16 + 22.5 + 14 + 7.5 + 12 = 72.0


def test_compute_all_derived_full():
    raw = {
        "company": {
            "name": "Test Corp",
            "production_output_ton": 1000,
        },
        "reporting": {"year": 2026},
        "emissions": {
            "scope1_tco2e": 100,
            "scope2_tco2e": 200,
            "scope3_tco2e": 300,
            "baseline_total_tco2e": 1000,
        },
        "energy": {
            "total_kwh": 10000,
            "renewable_kwh": 3000,
        },
        "water": {"consumption_m3": 5000, "recycled_m3": 3000},
        "waste": {"total_ton": 100, "recycled_ton": 80, "landfill_ton": 20},
        "supply_chain": {
            "local_sourcing_pct": 60,
            "certified_suppliers_count": 5,
            "total_suppliers_count": 10,
            "sustainable_packaging_pct": 40,
        },
    }
    result = compute_all_derived(raw)

    # Kiểm tra
    assert result["total_tco2e"] == 600.0
    assert result["reduction_pct"] == 40.0
    assert result["renewable_pct"] == 30.0
    assert result["water_recycling_rate"] == 60.0
    assert result["waste_recycling_rate"] == 80.0
    assert result["certified_supplier_pct"] == 50.0
    assert 0 <= result["vgpi_score"] <= 100
