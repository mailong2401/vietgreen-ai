EXTRACTION_PROMPT_TEMPLATE = """Trích xuất số liệu từ báo cáo doanh nghiệp và trả về JSON.

BÁO CÁO:
<BAO_CAO>
{report_text}
</BAO_CAO>

Hãy tìm và trích các số liệu sau. Nếu không tìm thấy → null.

{{
  "company": {{
    "name": "tên doanh nghiệp",
    "tax_code": "mã số thuế",
    "industry": "ngành nghề",
    "employee_count": 0,
    "revenue_vnd": 0,
    "production_output_ton": 0
  }},
  "reporting": {{
    "year": 2024,
    "period": "Q1-Q4/2024",
    "baseline_year": 2020
  }},
  "emissions": {{
    "scope1_tco2e": 0,
    "scope2_tco2e": 0,
    "scope3_tco2e": 0,
    "baseline_total_tco2e": 0
  }},
  "energy": {{
    "total_kwh": 0,
    "grid_kwh": 0,
    "renewable_kwh": 0
  }},
  "water": {{
    "consumption_m3": 0,
    "recycled_m3": 0
  }},
  "waste": {{
    "total_ton": 0,
    "recycled_ton": 0,
    "landfill_ton": 0,
    "hazardous_ton": 0
  }},
  "supply_chain": {{
    "local_sourcing_pct": 0,
    "certified_suppliers_count": 0,
    "total_suppliers_count": 0,
    "sustainable_packaging_pct": 0
  }},
  "audit": {{
    "audit_by": "đơn vị kiểm toán",
    "standard": "tiêu chuẩn",
    "audit_date": "YYYY-MM-DD",
    "valid_until": "YYYY-MM-DD",
    "certificates": []
  }}
}}

Chỉ trả JSON, không giải thích. Bắt đầu:
"""
