"""Multi-pass extraction — chia nhỏ prompt, không có value mẫu để tránh LLM copy."""

COMMON_HEADER = """Đọc báo cáo doanh nghiệp dưới đây và trích số liệu.

BÁO CÁO:
<BAO_CAO>
{report_text}
</BAO_CAO>

"""

# ============================================================
# PASS 1: COMPANY + REPORTING
# ============================================================
PROMPT_COMPANY = COMMON_HEADER + """NHIỆM VỤ: Trích thông tin doanh nghiệp và kỳ báo cáo.

QUY TẮC TUYỆT ĐỐI:
- CHỈ trích dữ liệu CÓ THẬT trong báo cáo trên.
- Nếu không tìm thấy → dùng null (KHÔNG được copy giá trị mẫu).
- KHÔNG trả các chuỗi như "tên doanh nghiệp", "mã số thuế", "tiêu chuẩn" — đây là tên field, không phải giá trị.
- Tất cả trường số phải là number.

⚠️  QUAN TRỌNG VỀ TÊN DOANH NGHIỆP — đọc kỹ, đây là lỗi hay gặp nhất:
- Chỉ lấy TÊN CHÍNH XÁC xuất hiện trên trang bìa hoặc phần giới thiệu của báo cáo —
  copy nguyên văn, không diễn giải, không dịch, không viết lại.
- TUYỆT ĐỐI KHÔNG dùng kiến thức bên ngoài (kiến thức bạn đã học trước đó) để "giải
  thích thêm" hay "đầy đủ hoá" tên viết tắt. Ví dụ: nếu báo cáo ghi "ACB" thì name
  PHẢI là đúng những gì báo cáo ghi (ví dụ "Ngân hàng TMCP Á Châu (ACB)" NẾU báo cáo
  có ghi tên đầy đủ đó) — KHÔNG được tự thêm "Agribank" hay bất kỳ tên ngân hàng/doanh
  nghiệp nào khác mà BẠN nghĩ là tương ứng, dù nghe có vẻ liên quan.
- TUYỆT ĐỐI KHÔNG gộp 2 tên doanh nghiệp khác nhau vào 1 trường "name". Nếu bạn
  không chắc chắn 100% rằng cụm trong ngoặc là tên đầy đủ CHÍNH THỨC của CÙNG một
  doanh nghiệp xuất hiện trong báo cáo (không phải suy luận của bạn) → bỏ phần
  trong ngoặc đó đi, chỉ giữ tên ngắn/viết tắt xuất hiện trong văn bản.
- Nếu không chắc chắn về tên đầy đủ → thà trả tên viết tắt/ngắn gọn xuất hiện
  trong báo cáo, còn hơn đoán và gộp nhầm.

Trả JSON với các KEY sau (giữ nguyên tên key):

{{
  "company": {{
    "name": <tên doanh nghiệp THẬT, đúng nguyên văn xuất hiện trong báo cáo, ví dụ "Công ty Cổ phần Sữa Việt Nam">,
    "tax_code": <mã số thuế, ví dụ "0300588569", hoặc null>,
    "industry": <ngành nghề, ví dụ "Sản xuất thực phẩm">,
    "industry_code": <mã VSIC, hoặc null>,
    "facility_name": <tên nhà máy chính, hoặc null>,
    "employee_count": <số nhân viên, number, hoặc null>,
    "revenue_vnd": <tổng doanh thu năm, đơn vị VND, number, hoặc null>,
    "production_output_ton": <tổng sản lượng năm, đơn vị tấn, number, hoặc null>
  }},
  "reporting": {{
    "year": <năm báo cáo, number>,
    "period": <kỳ báo cáo, ví dụ "01/01/2024 - 31/12/2024", hoặc null>,
    "standard": <chuẩn áp dụng, ví dụ "GRI 2021", "ISO 14064-1", hoặc null>,
    "baseline_year": <năm cơ sở để so sánh, number, hoặc null>
  }}
}}

GỢI Ý TÌM KIẾM:
- "sản lượng", "tổng sản lượng", "sản xuất", "công suất" → production_output_ton
- "doanh thu", "tổng doanh thu", "net revenue" → revenue_vnd
- "nhân viên", "lao động", "employees" → employee_count

Chỉ trả JSON, không markdown, không giải thích. Bắt đầu trả JSON:
"""


# ============================================================
# PASS 2: EMISSIONS + ENERGY
# ============================================================
PROMPT_EMISSIONS_ENERGY = COMMON_HEADER + """NHIỆM VỤ: Trích số liệu phát thải khí nhà kính và năng lượng.

QUY TẮC TUYỆT ĐỐI:
- CHỈ trích dữ liệu CÓ THẬT. Không có → null.
- KHÔNG copy giá trị mẫu.
- Tất cả trường số phải là number.
- Đơn vị chuẩn hóa:
    * Emissions: tấn CO₂ tương đương (tCO₂e). Nếu báo cáo ghi "nghìn tấn" → nhân 1000.
    * Energy: kWh. Nếu báo cáo ghi MWh → nhân 1000. Nếu ghi GJ → nhân 277.78.

⚠️  QUAN TRỌNG VỀ baseline_total_tco2e — đọc kỹ, đây là lỗi hay gặp nhất:
- baseline_total_tco2e là TỔNG PHÁT THẢI của NĂM CƠ SỞ (năm gốc để so sánh, thường
  là 2019 hoặc 2020), được báo cáo công bố RIÊNG BIỆT, KHÁC với số liệu Scope 1/2/3
  của năm báo cáo hiện tại.
- baseline_total_tco2e LUÔN PHẢI KHÁC scope1_tco2e, scope2_tco2e, scope3_tco2e của
  năm báo cáo hiện tại. Đây là 2 khái niệm hoàn toàn khác nhau (năm cơ sở vs năm
  hiện tại) — KHÔNG BAO GIỜ bằng nhau theo đúng ý nghĩa dữ liệu, trừ trường hợp
  cực hiếm trùng ngẫu nhiên.
- Nếu báo cáo KHÔNG ghi rõ số liệu phát thải của một năm cơ sở cụ thể (không có
  đoạn nào nói "so với năm 20xx, phát thải là...") → baseline_total_tco2e = null.
  TUYỆT ĐỐI KHÔNG lấy scope1/scope2/scope3 của năm hiện tại để điền tạm vào
  baseline_total_tco2e.

Trả JSON với các KEY sau:

{{
  "emissions": {{
    "scope1_tco2e": <phát thải trực tiếp CỦA NĂM BÁO CÁO HIỆN TẠI, number>,
    "scope2_tco2e": <phát thải gián tiếp từ điện CỦA NĂM BÁO CÁO HIỆN TẠI, number>,
    "scope3_tco2e": <phát thải chuỗi cung ứng CỦA NĂM BÁO CÁO HIỆN TẠI, number>,
    "baseline_total_tco2e": <tổng phát thải CỦA RIÊNG NĂM CƠ SỞ (năm gốc, khác năm
                              hiện tại), hoặc null nếu báo cáo không ghi rõ>
  }},
  "energy": {{
    "total_kwh": <tổng điện năng tiêu thụ, number>,
    "grid_kwh": <điện lưới, number>,
    "renewable_kwh": <điện tái tạo (mặt trời, gió, sinh khối), number>
  }}
}}

GỢI Ý TÌM KIẾM — thuật ngữ có thể viết khác:
- Phát thải: "phát thải", "khí nhà kính", "GHG", "CO₂", "CO2",
             "tCO₂e", "tCO2e", "tấn CO₂ tương đương", "tấn CO2e"
- Scope: "Scope 1", "Scope 2", "Scope 3", "phạm vi 1", "phạm vi 2", "phạm vi 3",
         "phát thải trực tiếp", "phát thải gián tiếp"
- Baseline: "năm cơ sở", "năm gốc", "baseline year", "so với năm", "base year"
- Năng lượng: "kWh", "MWh", "GJ", "điện năng tiêu thụ", "tổng điện",
              "năng lượng", "năng lượng tái tạo", "điện mặt trời", "solar"

Chỉ trả JSON, không markdown, không giải thích. Bắt đầu trả JSON:
"""


# ============================================================
# PASS 3: WATER + WASTE
# ============================================================
PROMPT_WATER_WASTE = COMMON_HEADER + """NHIỆM VỤ: Trích số liệu nước và chất thải.

QUY TẮC TUYỆT ĐỐI:
- CHỈ trích dữ liệu CÓ THẬT. Không có → null.
- KHÔNG copy giá trị mẫu.
- Tất cả trường số phải là number.
- Đơn vị chuẩn hóa:
    * Water: m³. Nếu báo cáo ghi "nghìn m³" → nhân 1000. Nếu ghi "lít" → chia 1000.
    * Waste: tấn. Nếu báo cáo ghi kg → chia 1000. Nếu ghi "nghìn tấn" → nhân 1000.

⚠️  QUAN TRỌNG — KHÔNG NHẦM LẪN GIỮA CÁC NHÓM CHỈ SỐ:
- total_ton (chất thải) và các số liệu năng lượng (kWh) là HAI LOẠI SỐ HOÀN TOÀN
  KHÁC NHAU, đo bằng đơn vị khác nhau, nằm ở ĐOẠN VĂN KHÁC NHAU trong báo cáo.
  TUYỆT ĐỐI KHÔNG lấy nhầm con số đang nói về điện (kWh) để điền vào total_ton,
  dù 2 con số đó xuất hiện gần nhau trong văn bản bị cắt ngắn.
  Trước khi điền total_ton, kiểm tra lại: đoạn văn chứa con số đó CÓ nhắc đến đơn
  vị "tấn" hoặc từ "chất thải"/"rác thải" ngay cạnh con số đó không? Nếu không
  chắc chắn → để null.
- Tương tự, consumption_m3 (nước) phải đi kèm đơn vị "m³"/"m3"/"mét khối", KHÔNG
  được lấy nhầm số liệu của chỉ số khác (năng lượng, phát thải, doanh thu...).

Trả JSON với các KEY sau:

{{
  "water": {{
    "consumption_m3": <tổng nước tiêu thụ trong năm, number>,
    "recycled_m3": <nước tái chế/tái sử dụng, number>
  }},
  "waste": {{
    "total_ton": <tổng chất thải phát sinh, number>,
    "recycled_ton": <chất thải tái chế, number>,
    "landfill_ton": <chất thải chôn lấp, number>,
    "hazardous_ton": <chất thải nguy hại, number>
  }}
}}

GỢI Ý TÌM KIẾM — thuật ngữ có thể viết khác:
- Nước: "nước", "nước tiêu thụ", "nước sử dụng", "nước cấp", "tổng lượng nước",
        "m³", "m3", "mét khối"
- Nước tái chế: "nước tái chế", "nước tái sử dụng", "nước tuần hoàn",
                "recycled water", "nước thu hồi"
- Chất thải: "chất thải", "chất thải rắn", "rác thải", "chất thải sinh hoạt",
             "chất thải công nghiệp", "tấn", "kg"
- Chất thải nguy hại: "chất thải nguy hại", "CTNH", "hazardous waste"
- Tái chế: "tái chế", "thu hồi", "recycle"
- Chôn lấp: "chôn lấp", "landfill", "đổ thải"

Chỉ trả JSON, không markdown, không giải thích. Bắt đầu trả JSON:
"""


# ============================================================
# PASS 4: SUPPLY CHAIN + AUDIT
# ============================================================
PROMPT_SUPPLY_AUDIT = COMMON_HEADER + """NHIỆM VỤ: Trích thông tin chuỗi cung ứng và kiểm toán.

QUY TẮC TUYỆT ĐỐI:
- CHỈ trích thông tin CÓ THẬT. Không có → null.
- KHÔNG copy giá trị mẫu như "đơn vị kiểm toán", "tiêu chuẩn", "số báo cáo", "YYYY-MM-DD".
- Nếu không tìm thấy audit_by → dùng null (KHÔNG dùng chuỗi "đơn vị kiểm toán").

Trả JSON với các KEY sau:

{{
  "supply_chain": {{
    "local_sourcing_pct": <phần trăm nguyên liệu nội địa (0-100), number>,
    "certified_suppliers_count": <số nhà cung cấp có chứng nhận, number>,
    "total_suppliers_count": <tổng số nhà cung cấp, number>,
    "sustainable_packaging_pct": <phần trăm bao bì bền vững (0-100), number>
  }},
  "audit": {{
    "audit_by": <TÊN THẬT của đơn vị kiểm toán, ví dụ "Deloitte Việt Nam", "KPMG", "BSI", "TÜV Rheinland", hoặc null>,
    "standard": <chuẩn kiểm toán, ví dụ "ISO 14064-1:2018", "AA1000AS", hoặc null>,
    "report_number": <số báo cáo kiểm toán, hoặc null>,
    "audit_date": <ngày kiểm toán, format YYYY-MM-DD, hoặc null>,
    "valid_until": <ngày hết hạn, format YYYY-MM-DD, hoặc null>,
    "verification_level": <"limited" hoặc "reasonable", hoặc null>,
    "certificates": <mảng các chứng chỉ, mỗi cái có type, number, expiry; nếu không có → []>
  }}
}}

GỢI Ý TÌM KIẾM:
- Nhà cung cấp: "nhà cung cấp", "supplier", "NCC", "đối tác"
- Nguyên liệu nội địa: "nội địa", "local", "trong nước", "Việt Nam"
- Bao bì: "bao bì", "packaging", "bao bì bền vững", "bao bì tái chế"
- Kiểm toán: "kiểm toán", "audit", "bên thứ ba", "third party"
- Đơn vị kiểm toán: "Deloitte", "KPMG", "PwC", "EY", "BSI", "TÜV", "SGS",
                    "Bureau Veritas", "Intertek"
- Chuẩn: "ISO 14064", "ISO 14001", "ISO 14067", "GRI", "AA1000", "GHG Protocol"
- Chứng nhận: "chứng nhận", "certificate", "certified", "TCVN"

Chỉ trả JSON, không markdown, không giải thích. Bắt đầu trả JSON:
"""
