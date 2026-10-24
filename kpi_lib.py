"""Shared helpers for the KPI step.
Used by 03_kpis.ipynb (notebook) and 04_pipeline.py (pipeline), so both give the same numbers.
Rule: we never write into silver.db here. Helper views are TEMP (they live only while the connection is open)."""
import math
import sqlite3
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
SILVER_DB = BASE / 'silver' / 'silver.db'
SQL_DIR = BASE / 'sql'
OUT_DIR = BASE / 'kpi_outputs'

# Fixed assumptions. Change them here only; notebook and pipeline both read them.
PARAMS = {
    'w_revenue': 0.40,           # KPI 6 weight: net revenue
    'w_return': 0.30,            # KPI 6 weight: return rate (lower is better)
    'w_rating': 0.30,            # KPI 6 weight: supplier rating
    'repeat_window_days': 90,    # KPI 7: second order must come within this many days
    'pay_tolerance': 0.01,       # KPI 8: 1% difference is still "Matched"
}

# (output name, sql file name). Output CSV = kpi_outputs/<output name>.csv, SQL = sql/<sql file>.sql
KPI_JOBS = [
    ('kpi_01_net_revenue_by_category_month', 'kpi_01_net_revenue_by_category_month'),
    ('kpi_02_top10_customers_ltv',           'kpi_02_top10_customers_ltv'),
    ('kpi_03_segment_profile',               'kpi_03_segment_profile'),
    ('kpi_04_channel_mom_growth',            'kpi_04_channel_mom_growth'),
    ('kpi_05_product_return_rate',           'kpi_05_product_return_rate'),
    ('kpi_06_supplier_scorecard',            'kpi_06_supplier_scorecard'),
    ('kpi_07_repeat_purchase_rate',          'kpi_07_repeat_purchase_rate'),
    ('kpi_07_repeat_purchase_detail',        'kpi_07b_repeat_purchase_detail'),
    ('kpi_08_payment_reconciliation',        'kpi_08_payment_reconciliation'),
    ('kpi_08_orphan_payments',               'kpi_08b_orphan_payments'),
    ('kpi_09_margin_risk_by_product',        'kpi_09_margin_risk_by_product'),
]


def connect():
    """Open silver.db."""
    return sqlite3.connect(SILVER_DB)


def read_sql_file(name):
    return (SQL_DIR / f'{name}.sql').read_text(encoding='utf-8')


def build_views(conn):
    """Create the shared TEMP views (see sql/00_views.sql)."""
    conn.executescript(read_sql_file('00_views'))


def q(conn, sql, params=None):
    """Run a SELECT and return a DataFrame. Named parameters (:name) come from `params`."""
    df = pd.read_sql_query(sql, conn, params=params if params is not None else PARAMS)
    for col in ('rank_no', 'days_to_second_order', 'prev_orders'):      # whole numbers that contain NULL come back as floats
        if col in df.columns:
            df[col] = df[col].astype('Int64')
    return df


def suggest_min_units(conn):
    """KPI 5 minimum volume = 25th percentile of units ordered per product (rounded up).
    Meaning: ignore the 25% least-sold products, because 1 return out of 2 units = 50% is just noise."""
    s = q(conn, 'SELECT ordered_qty FROM v_product_sales')['ordered_qty']
    return int(math.ceil(s.quantile(0.25)))


def get_params(conn):
    p = dict(PARAMS)
    p['min_units'] = suggest_min_units(conn)
    return p


def save(df, name):
    OUT_DIR.mkdir(exist_ok=True)
    path = OUT_DIR / f'{name}.csv'
    df.to_csv(path, index=False)
    return path


def check(name, condition):
    """Tiny test helper: prints PASS, or stops with an error so a wrong number never goes unnoticed."""
    if not bool(condition):
        raise AssertionError(f'CHECK FAILED: {name}')
    print(f'PASS  {name}')


def summarize_recon(df):
    """KPI 8 summary: one line per reconciliation status."""
    g = (df.groupby('recon_status')
           .agg(orders=('order_id', 'count'),
                expected_total=('expected_total', 'sum'),
                paid_success=('paid_success', 'sum'))
           .round(2).reset_index().sort_values('orders', ascending=False))
    return g
