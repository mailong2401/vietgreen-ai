import logging
import time
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
from config import DB_CONFIG

logger = logging.getLogger("vietgreen_db")
pg_pool = None


def _create_schema(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS esg_metrics (
            id SERIAL PRIMARY KEY,

            -- company
            company_name VARCHAR(255),
            tax_code VARCHAR(50),
            industry VARCHAR(150),
            industry_code VARCHAR(50),
            facility_name VARCHAR(255),
            employee_count INT,
            revenue_vnd NUMERIC(20, 2),
            production_output_ton NUMERIC(15, 2),

            -- reporting
            reporting_year INT,
            reporting_period VARCHAR(50),
            reporting_standard VARCHAR(150),
            baseline_year INT,

            -- VGPI breakdown (DERIVED)
            vgpi_score FLOAT,
            energy_efficiency FLOAT,
            co2_reduction FLOAT,
            waste_circularity FLOAT,
            renewable_energy_pct FLOAT,
            supply_chain_sustainability FLOAT,

            -- emissions
            scope1_tco2e FLOAT,
            scope2_tco2e FLOAT,
            scope3_tco2e FLOAT,
            total_tco2e FLOAT,
            baseline_total_tco2e FLOAT,
            reduction_pct FLOAT,
            intensity_tco2e_per_ton FLOAT,

            -- energy
            total_kwh FLOAT,
            grid_kwh FLOAT,
            renewable_kwh FLOAT,
            energy_renewable_pct FLOAT,
            energy_intensity_kwh_per_ton FLOAT,

            -- water
            water_consumption_m3 FLOAT,
            water_recycled_m3 FLOAT,
            water_recycling_rate FLOAT,

            -- waste
            waste_total_ton FLOAT,
            waste_recycled_ton FLOAT,
            waste_landfill_ton FLOAT,
            hazardous_waste_ton FLOAT,
            waste_recycling_rate FLOAT,

            -- supply chain
            local_sourcing_pct FLOAT,
            certified_suppliers_count INT,
            total_suppliers_count INT,
            sustainable_packaging_pct FLOAT,

            -- audit
            audit_by VARCHAR(255),
            audit_standard VARCHAR(150),
            audit_report_number VARCHAR(150),
            audit_date DATE,
            audit_valid_until DATE,
            verification_level VARCHAR(50),

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS certificates (
            id SERIAL PRIMARY KEY,
            metric_id INT REFERENCES esg_metrics(id) ON DELETE CASCADE,
            cert_type VARCHAR(150),
            cert_number VARCHAR(150),
            expiry_date DATE
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id BIGSERIAL PRIMARY KEY,
            action VARCHAR(100),
            entity_type VARCHAR(50),
            entity_id INT,
            detail JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_esg_tax_code ON esg_metrics(tax_code);
        CREATE INDEX IF NOT EXISTS idx_esg_industry ON esg_metrics(industry);
        CREATE INDEX IF NOT EXISTS idx_esg_year ON esg_metrics(reporting_year);
        CREATE INDEX IF NOT EXISTS idx_esg_company ON esg_metrics(company_name);
        CREATE INDEX IF NOT EXISTS idx_esg_vgpi ON esg_metrics(vgpi_score DESC);
        CREATE INDEX IF NOT EXISTS idx_cert_metric ON certificates(metric_id);
        CREATE INDEX IF NOT EXISTS idx_cert_expiry ON certificates(expiry_date);
    """)


def init_postgres_db(max_retries: int = 5, delay: int = 3):
    global pg_pool
    for attempt in range(1, max_retries + 1):
        try:
            pg_pool = psycopg2.pool.SimpleConnectionPool(1, 10, **DB_CONFIG)
            conn = pg_pool.getconn()
            with conn.cursor() as cur:
                _create_schema(cur)
            conn.commit()
            pg_pool.putconn(conn)
            logger.info("PostgreSQL schema sẵn sàng.")
            return
        except Exception as e:
            logger.warning(f"Lần {attempt}/{max_retries} - Lỗi kết nối: {e}")
            if attempt == max_retries:
                logger.error("Hết retry, PostgreSQL không khả dụng.")
                pg_pool = None
            else:
                time.sleep(delay)


@contextmanager
def get_pg_conn():
    if pg_pool is None:
        raise RuntimeError("PostgreSQL chưa được khởi tạo.")
    conn = pg_pool.getconn()
    try:
        yield conn
    finally:
        pg_pool.putconn(conn)
