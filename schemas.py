"""Schemas chứa RAW DATA — số tuyệt đối trích từ báo cáo.
Các chỉ số phái sinh (VGPI, %, intensity) được tính trong formulas.py.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List


# ============================================================
# COMPANY
# ============================================================
class Company(BaseModel):
    name: str = "Unknown"
    tax_code: Optional[str] = None
    industry: Optional[str] = None
    industry_code: Optional[str] = None
    facility_name: Optional[str] = None
    employee_count: Optional[int] = None
    revenue_vnd: Optional[float] = None
    production_output_ton: Optional[float] = None

    @field_validator("name", mode="before")
    @classmethod
    def default_name(cls, v):
        return v if v else "Unknown"


# ============================================================
# REPORTING
# ============================================================
class Reporting(BaseModel):
    year: Optional[int] = None
    period: Optional[str] = None
    standard: Optional[str] = None
    baseline_year: Optional[int] = None


# ============================================================
# EMISSIONS — CHỈ SỐ TUYỆT ĐỐI (tCO2e)
# Không có reduction_pct, intensity — Python tự tính
# ============================================================
class EmissionsRaw(BaseModel):
    scope1_tco2e: float = 0.0
    scope2_tco2e: float = 0.0
    scope3_tco2e: float = 0.0
    baseline_total_tco2e: float = 0.0

    @field_validator("*", mode="before")
    @classmethod
    def none_to_zero(cls, v):
        return 0.0 if v is None else v


# ============================================================
# ENERGY — CHỈ SỐ TUYỆT ĐỐI (kWh)
# ============================================================
class EnergyRaw(BaseModel):
    total_kwh: float = 0.0
    grid_kwh: float = 0.0
    renewable_kwh: float = 0.0

    @field_validator("*", mode="before")
    @classmethod
    def none_to_zero(cls, v):
        return 0.0 if v is None else v


# ============================================================
# WATER — CHỈ SỐ TUYỆT ĐỐI (m3)
# ============================================================
class WaterRaw(BaseModel):
    consumption_m3: float = 0.0
    recycled_m3: float = 0.0

    @field_validator("*", mode="before")
    @classmethod
    def none_to_zero(cls, v):
        return 0.0 if v is None else v


# ============================================================
# WASTE — CHỈ SỐ TUYỆT ĐỐI (tấn)
# ============================================================
class WasteRaw(BaseModel):
    total_ton: float = 0.0
    recycled_ton: float = 0.0
    landfill_ton: float = 0.0
    hazardous_ton: float = 0.0

    @field_validator("*", mode="before")
    @classmethod
    def none_to_zero(cls, v):
        return 0.0 if v is None else v


# ============================================================
# SUPPLY CHAIN — cần cho trụ cột 5 của VGPI
# ============================================================
class SupplyChainRaw(BaseModel):
    local_sourcing_pct: float = 0.0           # % nguyên liệu nội địa
    certified_suppliers_count: int = 0        # số NCC có chứng nhận
    total_suppliers_count: int = 0            # tổng số NCC
    sustainable_packaging_pct: float = 0.0    # % bao bì bền vững

    @field_validator("*", mode="before")
    @classmethod
    def none_to_zero(cls, v):
        if v is None:
            return 0
        return v


# ============================================================
# AUDIT
# ============================================================
class Certificate(BaseModel):
    type: str = "Unknown"
    number: Optional[str] = None
    expiry: Optional[str] = None

    @field_validator("type", mode="before")
    @classmethod
    def default_type(cls, v):
        return v if v else "Unknown"


class Audit(BaseModel):
    audit_by: str = "Unknown"
    standard: Optional[str] = None
    report_number: Optional[str] = None
    audit_date: Optional[str] = None
    valid_until: Optional[str] = None
    verification_level: Optional[str] = None
    certificates: List[Certificate] = Field(default_factory=list)

    @field_validator("audit_by", mode="before")
    @classmethod
    def default_audit_by(cls, v):
        return v if v else "Unknown"

    @field_validator("certificates", mode="before")
    @classmethod
    def none_to_empty_list(cls, v):
        return v if v else []


# ============================================================
# ROOT — chỉ chứa RAW
# ============================================================
class EsgExtraction(BaseModel):
    """Schema gốc — CHỈ chứa RAW data từ báo cáo.
    Mọi chỉ số phái sinh (VGPI, %, intensity) sẽ tính bằng formulas.py
    """
    company: Company = Field(default_factory=Company)
    reporting: Reporting = Field(default_factory=Reporting)
    emissions: EmissionsRaw = Field(default_factory=EmissionsRaw)
    energy: EnergyRaw = Field(default_factory=EnergyRaw)
    water: WaterRaw = Field(default_factory=WaterRaw)
    waste: WasteRaw = Field(default_factory=WasteRaw)
    supply_chain: SupplyChainRaw = Field(default_factory=SupplyChainRaw)
    audit: Audit = Field(default_factory=Audit)

    @field_validator(
        "company", "reporting", "emissions", "energy",
        "water", "waste", "supply_chain", "audit",
        mode="before",
    )
    @classmethod
    def coerce_none_to_empty_dict(cls, v):
        return {} if v is None else v
