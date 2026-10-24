"""Phase 4 - PIPELINE: raw files -> silver (clean tables) -> KPI result files.

Run from this folder:
    python 04_pipeline.py                 all steps
    python 04_pipeline.py --skip-clean    reuse the existing silver.db, only rebuild the KPIs

Steps
    1. CLEAN       run 02_clean.py       raw csv/json  ->  silver/*.csv + silver/silver.db
    2. CHECK SILVER                      keys unique, no broken links, no impossible values
    3. BUILD KPIs  run sql/*.sql         silver.db  ->  kpi_outputs/*.csv
    4. CHECK KPIs                        totals tie together, row counts as expected
    5. SUMMARY                           what was written, how long it took

Every step writes to pipeline.log. If a check fails the pipeline stops with an error (no silent bad numbers).
The raw files are never changed. silver.db is only read by steps 2-4."""
import argparse
import logging
import subprocess
import sys
import time

import pandas as pd

import kpi_lib as k

BASE = k.BASE
LOG_FILE = BASE / 'pipeline.log'

RAW_FILES = ['customers.csv', 'products.csv', 'orders.csv', 'order_items.csv',
             'payments.csv', 'returns.csv', 'suppliers_json.txt']

# row counts we got when the cleaning rules were finished (a different number = rules changed, so we warn)
EXPECTED_SILVER_ROWS = {'customers': 158, 'products': 70, 'suppliers': 18, 'orders': 320,
                        'order_items': 769, 'payments': 317, 'returns': 58}

# table -> primary key column
PRIMARY_KEYS = {'customers': 'customer_id', 'products': 'product_id', 'suppliers': 'supplier_id',
                'orders': 'order_id', 'order_items': 'order_item_id', 'payments': 'payment_id',
                'returns': 'return_id'}

# each query returns the number of BAD rows, we expect 0
SILVER_RULES = {
    'order_items without an order':
        "SELECT COUNT(*) FROM order_items WHERE order_id NOT IN (SELECT order_id FROM orders)",
    'order_items without a product':
        "SELECT COUNT(*) FROM order_items WHERE product_id NOT IN (SELECT product_id FROM products)",
    'payments without an order':
        "SELECT COUNT(*) FROM payments WHERE order_id NOT IN (SELECT order_id FROM orders)",
    'returns without an order line':
        "SELECT COUNT(*) FROM returns WHERE order_item_id NOT IN (SELECT order_item_id FROM order_items)",
    'orders with unknown customer that are NOT flagged':
        "SELECT COUNT(*) FROM orders WHERE customer_id NOT IN (SELECT customer_id FROM customers) AND customer_orphan = 0",
    'order_items with quantity <= 0':
        "SELECT COUNT(*) FROM order_items WHERE quantity <= 0",
    'order_items with discount outside 0-100':
        "SELECT COUNT(*) FROM order_items WHERE discount_pct < 0 OR discount_pct > 100",
    'order_items with missing line_total':
        "SELECT COUNT(*) FROM order_items WHERE line_total IS NULL",
    'orders with missing date':
        "SELECT COUNT(*) FROM orders WHERE order_date IS NULL",
    'supplier ratings outside 0-5':
        "SELECT COUNT(*) FROM suppliers WHERE rating < 0 OR rating > 5",
}

log = logging.getLogger('pipeline')


def setup_logging():
    fmt = logging.Formatter('%(asctime)s | %(levelname)-7s | %(message)s', '%H:%M:%S')
    for handler in (logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8'), logging.StreamHandler(sys.stdout)):
        handler.setFormatter(fmt)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


# ------------------------------------------------------------------ step 1
def step_clean():
    log.info('STEP 1 - CLEAN: raw -> silver')
    missing = [f for f in RAW_FILES if not (BASE / f).exists()]
    if missing:
        raise FileNotFoundError(f'raw files missing in {BASE}: {missing}')
    result = subprocess.run([sys.executable, '02_clean.py'], cwd=BASE, capture_output=True, text=True)
    if result.returncode != 0:
        log.error(result.stderr[-1500:])
        raise RuntimeError('02_clean.py failed, see message above')
    log.info('cleaning finished, silver.db written')


# ------------------------------------------------------------------ step 2
def step_check_silver():
    log.info('STEP 2 - CHECK SILVER')
    conn = k.connect()
    for table, key in PRIMARY_KEYS.items():
        n, distinct, nulls = conn.execute(
            f'SELECT COUNT(*), COUNT(DISTINCT {key}), SUM({key} IS NULL) FROM {table}').fetchone()
        if n == 0:
            raise AssertionError(f'{table} is empty')
        if n != distinct or nulls:
            raise AssertionError(f'{table}.{key} is not unique / has NULLs ({n} rows, {distinct} distinct, {nulls} null)')
        expected = EXPECTED_SILVER_ROWS[table]
        level = log.info if n == expected else log.warning
        level(f'{table:12s} rows={n:4d} (expected {expected}) key {key} unique')
    for name, sql in SILVER_RULES.items():
        bad = conn.execute(sql).fetchone()[0]
        if bad:
            raise AssertionError(f'silver rule failed: {name} -> {bad} rows')
        log.info(f'rule ok: {name}')
    conn.close()


# ------------------------------------------------------------------ step 3
def step_build_kpis():
    log.info('STEP 3 - BUILD KPIs')
    conn = k.connect()
    k.build_views(conn)
    params = k.get_params(conn)
    log.info(f'parameters: {params}')

    results = {}
    for out_name, sql_name in k.KPI_JOBS:
        df = k.q(conn, k.read_sql_file(sql_name), params)
        if out_name == 'kpi_08_orphan_payments':
            df = df.drop(columns='record_json')
        k.save(df, out_name)
        results[out_name] = df
        log.info(f'{out_name:40s} rows={len(df):4d}')

    # two small extra tables (same as in the notebook)
    results['kpi_08_payment_reconciliation_summary'] = k.summarize_recon(results['kpi_08_payment_reconciliation'])
    k.save(results['kpi_08_payment_reconciliation_summary'], 'kpi_08_payment_reconciliation_summary')

    m = results['kpi_09_margin_risk_by_product']
    results['kpi_09_margin_risk_total'] = pd.DataFrame({
        'products_affected': [len(m)], 'lines_affected': [m.lines_affected.sum()],
        'units_affected': [m.units_affected.sum()], 'revenue_exposed': [m.revenue_exposed.sum()],
        'total_loss': [m.total_loss.sum()]})
    k.save(results['kpi_09_margin_risk_total'], 'kpi_09_margin_risk_total')
    conn.close()
    return results, params


# ------------------------------------------------------------------ step 4
def step_check_kpis(results, params):
    log.info('STEP 4 - CHECK KPIs')
    conn = k.connect()
    n_orders = conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
    n_revenue_orders = conn.execute("SELECT COUNT(*) FROM orders WHERE order_status IN ('Completed','Returned')").fetchone()[0]
    n_customers = conn.execute('SELECT COUNT(*) FROM customers').fetchone()[0]
    conn.close()

    r1, r2, r3 = results['kpi_01_net_revenue_by_category_month'], results['kpi_02_top10_customers_ltv'], results['kpi_03_segment_profile']
    r4, r5, r6 = results['kpi_04_channel_mom_growth'], results['kpi_05_product_return_rate'], results['kpi_06_supplier_scorecard']
    r7, r8 = results['kpi_07_repeat_purchase_rate'], results['kpi_08_payment_reconciliation']

    k.check('KPI1 gross - refunds = net', (abs(r1.gross_revenue - r1.approved_refunds - r1.net_revenue) < 0.02).all())
    k.check('KPI2 has 10 customers, sorted', len(r2) == 10 and r2.net_lifetime_value.is_monotonic_decreasing)
    k.check('KPI3 customers add up to customer table', r3.customers.sum() == n_customers)
    k.check('KPI4 revenue total = KPI1 revenue total', abs(r4.net_revenue.sum() - r1.net_revenue.sum()) < 1)
    k.check('KPI4 order total = all revenue orders', r4.orders.sum() == n_revenue_orders)
    k.check('KPI5 has 20 rows, all above minimum volume', len(r5) == 20 and (r5.ordered_qty >= params['min_units']).all())
    ranked = r6[r6.rank_no.notna()]
    k.check('KPI6 weights = 1 and scores 0-100', abs(params['w_revenue'] + params['w_return'] + params['w_rating'] - 1) < 1e-9
            and ranked.score.between(0, 100).all())
    k.check('KPI6 Unknown supplier not ranked', r6[r6.supplier_id == 'UNKNOWN'].rank_no.isna().all())
    k.check('KPI7 rate between 0 and 100', 0 <= r7.repeat_rate_pct[0] <= 100)
    k.check('KPI8 one row per order', len(r8) == n_orders and r8.order_id.is_unique)
    k.check('KPI8 summary adds up to all orders', results['kpi_08_payment_reconciliation_summary'].orders.sum() == n_orders)
    k.check('KPI8 8 orphan payments listed', len(results['kpi_08_orphan_payments']) == 8)
    k.check('Stretch all losses positive', (results['kpi_09_margin_risk_by_product'].total_loss > 0).all())
    log.info('all KPI checks passed')


# ------------------------------------------------------------------ step 5
def step_summary(results, started):
    log.info('STEP 5 - SUMMARY')
    r1 = results['kpi_01_net_revenue_by_category_month']
    r7 = results['kpi_07_repeat_purchase_rate'].iloc[0]
    m = results['kpi_09_margin_risk_total'].iloc[0]
    log.info(f'total net revenue          : {r1.net_revenue.sum():,.2f}')
    log.info(f'repeat-purchase rate (90d) : {r7.repeat_rate_pct}%')
    log.info(f'margin-risk loss (stretch) : {m.total_loss:,.2f}')
    log.info(f'files in {k.OUT_DIR.name}/ : {len(list(k.OUT_DIR.glob("*.csv")))}')
    log.info(f'finished in {time.time() - started:.1f} seconds')


def main():
    parser = argparse.ArgumentParser(description='ShopSphere pipeline: raw -> silver -> KPIs')
    parser.add_argument('--skip-clean', action='store_true', help='reuse existing silver.db')
    args = parser.parse_args()

    setup_logging()
    started = time.time()
    log.info('PIPELINE START')
    try:
        if args.skip_clean:
            log.info('STEP 1 - CLEAN: skipped (--skip-clean)')
        else:
            step_clean()
        step_check_silver()
        results, params = step_build_kpis()
        step_check_kpis(results, params)
        step_summary(results, started)
    except Exception as exc:
        log.error(f'PIPELINE FAILED: {exc}')
        sys.exit(1)
    log.info('PIPELINE OK')


if __name__ == '__main__':
    main()
