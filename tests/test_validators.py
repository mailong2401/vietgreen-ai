from validators import validate_consistency


def test_no_warnings_for_clean_data():
    computed = {
        "emissions_raw": {"scope1_tco2e": 100, "scope2_tco2e": 200, "scope3_tco2e": 300},
        "total_tco2e": 600,
        "reduction_pct": 40,
        "energy_raw": {"total_kwh": 1000, "renewable_kwh": 300},
        "water_raw": {"consumption_m3": 100, "recycled_m3": 60},
        "waste_raw": {"total_ton": 100, "recycled_ton": 80, "landfill_ton": 20},
        "vgpi_score": 75,
        "company": {"production_output_ton": 1000},
    }
    assert validate_consistency(computed) == []


def test_warns_scope_mismatch():
    computed = {
        "emissions_raw": {"scope1_tco2e": 100, "scope2_tco2e": 200, "scope3_tco2e": 300},
        "total_tco2e": 1000,  # Sai — phải là 600
        "reduction_pct": 40,
        "energy_raw": {}, "water_raw": {}, "waste_raw": {},
        "vgpi_score": 75, "company": {},
    }
    warnings = validate_consistency(computed)
    assert any("Scope" in w for w in warnings)


def test_warns_renewable_exceeds_total():
    computed = {
        "emissions_raw": {},
        "total_tco2e": 0,
        "reduction_pct": 0,
        "energy_raw": {"total_kwh": 100, "renewable_kwh": 200},  # Sai
        "water_raw": {}, "waste_raw": {},
        "vgpi_score": 50, "company": {},
    }
    warnings = validate_consistency(computed)
    assert any("renewable_kwh" in w for w in warnings)
