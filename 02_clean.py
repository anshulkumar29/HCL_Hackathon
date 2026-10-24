"""Phase 2 - cleaning: raw -> silver. Run: python 02_clean.py
Outputs: silver/*.csv, silver/silver.db (sqlite), silver/rejects.csv,
         before_after_counts.csv, 02_cleaning_report.md
Raw files are never modified."""
import pandas as pd, numpy as np, re, json, sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent
SILVER = BASE / 'silver'; SILVER.mkdir(exist_ok=True)
NULL_TOKENS = {'', 'na', 'n/a', 'none', 'null', 'nan', 'unknown', '-'}
rejects, fixes, raw_stats = [], [], {}

# ---------------------------------------------------------------- helpers
def rd(name):
    df = pd.read_csv(BASE / f'{name}.csv', dtype=str, keep_default_na=False, encoding='utf-8')
    return df.apply(lambda s: s.str.strip())

def nullify(s):
    return s.mask(s.str.lower().isin(NULL_TOKENS))

def nulls_raw(df):
    return int(df.apply(lambda c: c.astype(str).str.strip().str.lower().isin(NULL_TOKENS)).sum().sum())

def fix(table, what, n):
    fixes.append((table, what, int(n)))

def log(table, df, key, reason, action):
    for _, r in df.iterrows():
        rec = {k: (None if pd.isna(v) else str(v)) for k, v in r.items() if not str(k).startswith('_')}
        rejects.append(dict(table=table, record_key=rec.get(key), reason=reason, action=action,
                            record_json=json.dumps(rec, ensure_ascii=False)))

def _pd(v):
    """parse one date string -> (Timestamp|NaT, ambiguous)"""
    if not isinstance(v, str): return (pd.NaT, False)
    s = v.strip()
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', s): return (pd.Timestamp(s), False)
        if re.fullmatch(r'\d{2}-[A-Za-z]{3}-\d{4}', s): return (pd.to_datetime(s, format='%d-%b-%Y'), False)
        m = re.fullmatch(r'(\d{2})/(\d{2})/(\d{4})', s)
        if m:
            a, b, y = map(int, m.groups())
            if a > 12: return (pd.Timestamp(y, b, a), False)      # DD/MM/YYYY (day > 12)
            if b > 12: return (pd.Timestamp(y, a, b), False)      # MM/DD/YYYY (day > 12)
            return (pd.Timestamp(y, a, b), a != b)                # ambiguous -> MM/DD default
    except Exception:
        pass
    return (pd.NaT, False)

def parse_dates(s):
    t = s.map(_pd)
    return pd.to_datetime(t.map(lambda x: x[0])), t.map(lambda x: x[1]).astype(bool)

def parse_amount(s):
    def f(v):
        if not isinstance(v, str): return np.nan
        t = re.sub(r'[^\d.\-]', '', v)
        return float(t) if re.fullmatch(r'-?\d+(\.\d+)?', t) else np.nan
    return s.map(f).astype(float)

BOOL = {'y': True, 'yes': True, 'true': True, '1': True, 'n': False, 'no': False, 'false': False, '0': False}
def to_bool(s):
    return s.astype(str).str.strip().str.lower().map(BOOL).astype(object)

def dedupe(df, key, table, prefer=None):
    df = df.copy()
    cols = [c for c in df.columns if not c.startswith('_')]
    df['_score'] = df[cols].notna().sum(axis=1)
    exact = df.duplicated(subset=cols, keep='first')
    log(table, df[exact], key, 'EXACT_DUPLICATE', 'dropped')
    df = df[~exact]
    df = df.sort_values((prefer or []) + ['_score'], ascending=False, kind='stable')
    conf = df.duplicated(subset=[key], keep='first')
    log(table, df[conf], key, 'CONFLICTING_DUPLICATE', 'dropped')
    df = df[~conf].sort_index().drop(columns='_score')
    return df, int(exact.sum()), int(conf.sum())

def drop_cols(df):
    return df[[c for c in df.columns if not c.startswith('_')]].reset_index(drop=True)

def reject_where(df, mask, key, table, reason):
    log(table, df[mask], key, reason, 'quarantined')
    return df[~mask]

CITY = {'mumbai': 'Mumbai', 'bangalore': 'Bangalore', 'bengaluru': 'Bangalore', 'delhi': 'Delhi', 'new delhi': 'Delhi'}
def city(s):
    return s.str.lower().map(CITY).fillna(s.str.title())

dstats = {}
before_distinct = {}

# ---------------------------------------------------------------- suppliers
sup = pd.DataFrame(json.load(open(BASE / 'suppliers_json.txt', encoding='utf-8'))).astype(object)
raw_stats['suppliers'] = dict(raw=len(sup), nulls=int(sup.isna().sum().sum()) + int((sup.country == 'Unknown').sum()))
sup['country'] = sup.country.map(lambda v: np.nan if v is None or str(v).strip().lower() in NULL_TOKENS else str(v).strip())
sup['rating_raw'] = pd.to_numeric(sup.rating, errors='coerce')
sup['rating_scale_raw'] = np.where(sup.rating_raw > 5, '0-10', '0-5')
sup['rating'] = np.where(sup.rating_raw > 5, sup.rating_raw / 2, sup.rating_raw).round(2)
fix('suppliers', 'rating >5 treated as 0-10 scale and halved to 0-5', (sup.rating_raw > 5).sum())
sup['is_preferred'] = to_bool(sup.is_preferred.map(lambda v: str(v)))
sup['contract_start_date'], sup['contract_date_ambiguous'] = parse_dates(sup.contract_start_date.astype(str))
sup['supplier_name'] = sup.supplier_name.str.strip()
sup, e, c = dedupe(sup, 'supplier_id', 'suppliers')
dstats['suppliers'] = dict(exact=e, conf=c)
suppliers = drop_cols(sup)

# ---------------------------------------------------------------- customers
cu_raw = rd('customers')
raw_stats['customers'] = dict(raw=len(cu_raw), nulls=nulls_raw(cu_raw))
before_distinct['customers'] = {k: cu_raw[k].nunique() for k in ['customer_segment', 'city', 'is_active']}
c = cu_raw.copy()
for col in c.columns: c[col] = nullify(c[col])
c['email'] = c.email.str.lower()
SEG = {'glod': 'Gold', 'gold': 'Gold', 'broze': 'Bronze', 'bronze': 'Bronze', 'silver': 'Silver', 'silverr': 'Silver', 'platinum': 'Platinum'}
c['customer_segment'] = c.customer_segment.str.lower().map(SEG)
c['city'] = city(c.city)
c['state'] = c.state.str.title()
def clean_phone(v):
    if pd.isna(v): return np.nan
    d = re.sub(r'\D', '', v)
    if len(d) == 12 and d.startswith('91'): d = d[2:]
    elif len(d) == 11 and d.startswith('0'): d = d[1:]
    return d if len(d) == 10 else np.nan
ph = c.phone.map(clean_phone); fix('customers', 'phone not a valid 10-digit number -> NULL', (ph.isna() & c.phone.notna()).sum()); c['phone'] = ph
zp = c.zip_code.where(c.zip_code.str.fullmatch(r'\d{6}', na=False)); fix('customers', 'zip not 6 digits (N/A etc) -> NULL', (zp.isna() & c.zip_code.notna()).sum()); c['zip_code'] = zp
c['is_active'] = to_bool(c.is_active)
c['signup_date'], c['signup_date_ambiguous'] = parse_dates(c.signup_date)
fix('customers', 'ambiguous dd/mm vs mm/dd dates parsed as MM/DD', c.signup_date_ambiguous.sum())
c, e, cf = dedupe(c, 'customer_id', 'customers')
dstats['customers'] = dict(exact=e, conf=cf)
customers = drop_cols(c)

# ---------------------------------------------------------------- products
p = rd('products'); oi_raw = rd('order_items')
raw_stats['products'] = dict(raw=len(p), nulls=nulls_raw(p))
before_distinct['products'] = {k: p[k].nunique() for k in ['category', 'is_active']}
oi_price = pd.to_numeric(oi_raw.unit_price, errors='coerce')
price_seen = set(zip(oi_raw.product_id, oi_price.round(2)))
for col in p.columns: p[col] = nullify(p[col])
p['unit_price'] = parse_amount(p.unit_price)
p['cost_price'] = pd.to_numeric(p.cost_price, errors='coerce')
p['_price_valid'] = p.unit_price > 0
p['unit_price'] = p.unit_price.where(p._price_valid)
p['_in_orders'] = [(a, round(b, 2)) in price_seen if pd.notna(b) else False for a, b in zip(p.product_id, p.unit_price)]
p['_revised'] = p.product_name.str.contains(r'\(Revised\)\s*$', na=False)
p['product_name'] = p.product_name.str.replace(r'\s*\(Revised\)\s*$', '', regex=True)
CAT = {'home and kitchen': 'Home & Kitchen', 'home & kitchen': 'Home & Kitchen', 'electornics': 'Electronics'}
lc = p.category.str.lower()
p['category'] = lc.map(CAT).fillna(p.category.str.title())
p['is_active'] = to_bool(p.is_active)
p['launch_date'], p['launch_date_ambiguous'] = parse_dates(p.launch_date)
p, e, cf = dedupe(p, 'product_id', 'products', prefer=['_price_valid', '_in_orders', '_revised'])
dstats['products'] = dict(exact=e, conf=cf)
submap = p.dropna(subset=['category']).groupby('sub_category').category.agg(lambda s: s.mode().iat[0])
miss = p.category.isna()
p.loc[miss, 'category'] = p.loc[miss, 'sub_category'].map(submap)
p['category_inferred'] = miss & p.category.notna(); fix('products', 'blank category inferred from sub_category', p.category_inferred.sum())
modal = oi_raw.assign(pr=oi_price)[lambda d: d.pr > 0].groupby('product_id').pr.agg(lambda s: s.mode().iat[0])
mp = p.unit_price.isna()
p.loc[mp, 'unit_price'] = p.loc[mp, 'product_id'].map(modal)
p['price_imputed'] = mp & p.unit_price.notna(); fix('products', 'invalid price (<=0) replaced by modal order-line price', p.price_imputed.sum())
p['negative_margin'] = p.cost_price > p.unit_price
valid_sup = set(suppliers.supplier_id)
orph = ~p.supplier_id.isin(valid_sup)
log('products', p[orph], 'product_id', 'ORPHAN_SUPPLIER', 'flagged_kept')
p['supplier_id_raw'] = p.supplier_id
p.loc[orph, 'supplier_id'] = np.nan
products = drop_cols(p)

# ---------------------------------------------------------------- orders
o = rd('orders')
raw_stats['orders'] = dict(raw=len(o), nulls=nulls_raw(o))
before_distinct['orders'] = {k: o[k].nunique() for k in ['order_status', 'channel', 'promo_code']}
for col in o.columns: o[col] = nullify(o[col])
def status(v):
    if pd.isna(v): return np.nan
    v = v.lower()
    for k, n in [('comp', 'Completed'), ('ret', 'Returned'), ('pend', 'Pending'), ('canc', 'Cancelled')]:
        if v.startswith(k): return n
    return np.nan
o['order_status'] = o.order_status.map(status)
o['channel'] = o.channel.str.lower().map(lambda v: np.nan if pd.isna(v) else ('App' if v == 'app' else 'Web' if v == 'web' else 'Store'))
o['promo_code'] = o.promo_code.str.upper()
o['shipping_city'] = city(o.shipping_city)
o['order_date'], o['order_date_ambiguous'] = parse_dates(o.order_date)
fix('orders', 'ambiguous dd/mm vs mm/dd dates parsed as MM/DD', o.order_date_ambiguous.sum())
o, e, cf = dedupe(o, 'order_id', 'orders')
dstats['orders'] = dict(exact=e, conf=cf)
o['customer_orphan'] = ~o.customer_id.isin(customers.customer_id)
log('orders', o[o.customer_orphan], 'order_id', 'ORPHAN_CUSTOMER', 'flagged_kept')
orders = drop_cols(o)

# ---------------------------------------------------------------- order_items
oi = rd('order_items')
raw_stats['order_items'] = dict(raw=len(oi), nulls=nulls_raw(oi))
for col in oi.columns: oi[col] = nullify(oi[col])
for col in ['quantity', 'unit_price', 'discount_pct', 'line_total']: oi[col] = pd.to_numeric(oi[col], errors='coerce')
oi = oi.rename(columns={'line_total': 'line_total_raw'})
oi, e, cf = dedupe(oi, 'order_item_id', 'order_items')
dstats['order_items'] = dict(exact=e, conf=cf)
oi = reject_where(oi, ~oi.order_id.isin(orders.order_id), 'order_item_id', 'order_items', 'ORPHAN_ORDER')
oi = reject_where(oi, ~oi.product_id.isin(products.product_id), 'order_item_id', 'order_items', 'ORPHAN_PRODUCT')
oi = reject_where(oi, ~(oi.quantity > 0), 'order_item_id', 'order_items', 'INVALID_QUANTITY')
bad = oi.unit_price.isna() | (oi.unit_price <= 0)
oi['price_imputed'] = bad
oi.loc[bad, 'unit_price'] = oi.loc[bad, 'product_id'].map(products.set_index('product_id').unit_price)
fix('order_items', 'missing/negative unit_price replaced by product list price', bad.sum())
oi = reject_where(oi, oi.unit_price.isna() | (oi.unit_price <= 0), 'order_item_id', 'order_items', 'UNPRICEABLE')
badd = oi.discount_pct.isna() | (oi.discount_pct < 0) | (oi.discount_pct > 100)
oi['discount_invalid'] = badd
oi.loc[badd, 'discount_pct'] = 0
fix('order_items', 'discount outside 0-100 -> 0', badd.sum())
oi['line_total'] = (oi.quantity * oi.unit_price * (1 - oi.discount_pct / 100)).round(2)
oi['line_total_mismatch'] = oi.line_total_raw.isna() | ((oi.line_total - oi.line_total_raw).abs() > 0.01)
fix('order_items', 'stored line_total did not reconcile; recomputed value trusted', oi.line_total_mismatch.sum())
order_items = drop_cols(oi)

# ---------------------------------------------------------------- payments
pm = rd('payments')
raw_stats['payments'] = dict(raw=len(pm), nulls=nulls_raw(pm))
before_distinct['payments'] = {'payment_status': pm.payment_status.nunique()}
for col in pm.columns: pm[col] = nullify(pm[col])
pm['amount_currency_raw'] = np.where(pm.amount.str.contains('$', regex=False, na=False), 'USD',
                             np.where(pm.amount.str.contains('\u20b9', regex=False, na=False), 'INR', 'none/INR'))
pm['amount'] = parse_amount(pm.amount)
def pstat(v):
    if pd.isna(v): return np.nan
    v = v.lower()
    for k, n in [('succ', 'Success'), ('pend', 'Pending'), ('fail', 'Failed'), ('refund', 'Refunded')]:
        if v.startswith(k): return n
    return np.nan
pm['payment_status'] = pm.payment_status.map(pstat)
pm['payment_date'], pm['payment_date_ambiguous'] = parse_dates(pm.payment_date)
fix('payments', 'ambiguous dd/mm vs mm/dd dates parsed as MM/DD', pm.payment_date_ambiguous.sum())
fix('payments', 'amounts with $ symbol (no FX conversion applied)', (pm.amount_currency_raw == 'USD').sum())
pm, e, cf = dedupe(pm, 'payment_id', 'payments')
dstats['payments'] = dict(exact=e, conf=cf)
pm = reject_where(pm, ~pm.order_id.isin(orders.order_id), 'payment_id', 'payments', 'ORPHAN_ORDER')
payments = drop_cols(pm)

tot = order_items.groupby('order_id').line_total.sum()
d = payments[payments.payment_status == 'Success'].copy()
d['order_total'] = d.order_id.map(tot)
d['match'] = ((d.amount - d.order_total).abs() <= 0.01 * d.order_total)
fx_diag = d.groupby('amount_currency_raw').match.agg(['mean', 'count']).round(3)

# ---------------------------------------------------------------- returns
rt = rd('returns')
raw_stats['returns'] = dict(raw=len(rt), nulls=nulls_raw(rt))
before_distinct['returns'] = {k: rt[k].nunique() for k in ['return_reason', 'return_status']}
for col in rt.columns: rt[col] = nullify(rt[col])
RSN = {'damged': 'Damaged', 'damaged': 'Damaged'}
rl = rt.return_reason.str.lower()
rt['return_reason'] = rl.map(RSN).fillna(rt.return_reason.str.title())
rt['return_status'] = rt.return_status.str.title()
rt['refund_amount'] = parse_amount(rt.refund_amount)
rt['return_date'], rt['return_date_ambiguous'] = parse_dates(rt.return_date)
fix('returns', 'ambiguous dd/mm vs mm/dd dates parsed as MM/DD', rt.return_date_ambiguous.sum())
rt, e, cf = dedupe(rt, 'return_id', 'returns')
dstats['returns'] = dict(exact=e, conf=cf)
rt = reject_where(rt, ~rt.order_item_id.isin(order_items.order_item_id), 'return_id', 'returns', 'ORPHAN_ORDER_ITEM')
rt['refund_missing'] = rt.refund_amount.isna()
it = order_items.set_index('order_item_id')
rt['refund_exceeds_line_total'] = rt.refund_amount > rt.order_item_id.map(it.line_total) + 0.01
odate = rt.order_item_id.map(it.order_id).map(orders.set_index('order_id').order_date)
rt['return_before_order'] = rt.return_date < odate
fix('returns', 'refund_amount blank (kept NULL, flagged)', rt.refund_missing.sum())
fix('returns', 'refund greater than recomputed line_total (flagged)', rt.refund_exceeds_line_total.sum())
fix('returns', 'return_date earlier than order_date (flagged)', rt.return_before_order.sum())
returns = drop_cols(rt)

# ---------------------------------------------------------------- integrity checks
assert order_items.order_id.isin(orders.order_id).all()
assert order_items.product_id.isin(products.product_id).all()
assert payments.order_id.isin(orders.order_id).all()
assert returns.order_item_id.isin(order_items.order_item_id).all()
for t, k in [(customers, 'customer_id'), (products, 'product_id'), (suppliers, 'supplier_id'), (orders, 'order_id'),
             (order_items, 'order_item_id'), (payments, 'payment_id'), (returns, 'return_id')]:
    assert t[k].is_unique, k

# ---------------------------------------------------------------- write outputs
tables = dict(customers=customers, products=products, suppliers=suppliers, orders=orders,
              order_items=order_items, payments=payments, returns=returns)
def prep(df):
    df = df.copy()
    for col in df.columns:
        if str(df[col].dtype).startswith('datetime'): df[col] = df[col].dt.strftime('%Y-%m-%d')
    return df
con = sqlite3.connect(SILVER / 'silver.db')
for n, df in tables.items():
    q = prep(df); q.to_csv(SILVER / f'{n}.csv', index=False, encoding='utf-8')
    s = q.copy()
    for col in s.columns:
        nn = s[col].dropna()
        if s[col].dtype == object and len(nn) and all(isinstance(x, (bool, np.bool_)) for x in nn):
            s[col] = s[col].map({True: 1, False: 0}).astype('Int64')
        elif s[col].dtype == bool: s[col] = s[col].astype(int)
    s.to_sql(n, con, if_exists='replace', index=False)
rej = pd.DataFrame(rejects, columns=['table', 'record_key', 'reason', 'action', 'record_json'])
rej.to_csv(SILVER / 'rejects.csv', index=False, encoding='utf-8')
rej.to_sql('rejects', con, if_exists='replace', index=False); con.close()

rows = []
for n, df in tables.items():
    r = rej[rej.table == n]
    rows.append(dict(table=n, raw_rows=raw_stats[n]['raw'], exact_dups_dropped=dstats[n]['exact'],
                     conflicting_dups_dropped=dstats[n]['conf'],
                     quarantined=int((r.action == 'quarantined').sum()), flagged_kept=int((r.action == 'flagged_kept').sum()),
                     silver_rows=len(df), raw_null_cells=raw_stats[n]['nulls'], silver_null_cells=int(df.isna().sum().sum())))
ba = pd.DataFrame(rows); ba.to_csv(BASE / 'before_after_counts.csv', index=False)
drows = []
for t, cols in before_distinct.items():
    for col, nb in cols.items():
        drows.append(dict(table=t, column=col, distinct_before=nb, distinct_after=tables[t][col].nunique(),
                          values_after=', '.join(sorted(map(str, tables[t][col].dropna().unique())))[:80]))
dd = pd.DataFrame(drows)
fx = pd.DataFrame(fixes, columns=['table', 'fix', 'rows_affected'])
rs = rej.groupby(['table', 'reason', 'action']).size().reset_index(name='rows')

def md(df): return '| ' + ' | '.join(map(str, df.columns)) + ' |\n|' + '---|' * len(df.columns) + '\n' + ''.join('| ' + ' | '.join(map(str, r)) + ' |\n' for r in df.itertuples(index=False))
RULES = """
## Cleaning rules (decided before coding)
**Text / labels** - trim, lower-case compare, then map to one canonical label. Typos fixed with an explicit map (Glod->Gold, Broze->Bronze, Silverr->Silver, Complted->Completed, Canceled/Cancled->Cancelled, Succeded->Success, Electornics->Electronics, Damged->Damaged). Channels: app/App/APP->App, web->Web, store/In-store/Instore->Store. Cities: Bengaluru/BANGALORE->Bangalore, New Delhi->Delhi (matches orders.shipping_city). Null tokens (blank, NA, N/A, None, null, unknown, '-') become real NULL. promo_code NULL = no promo.
**Booleans** - Y/yes/true/1 -> TRUE, N/no/false/0 -> FALSE.
**Dates** - ISO and DD-Mon-YYYY are unambiguous. For dd/mm/yyyy: first part >12 -> DD/MM; second part >12 -> MM/DD; both <=12 -> ambiguous, **default MM/DD**, and a `*_date_ambiguous` flag column is kept so any KPI can exclude or audit them. Unparseable ('unknown', blank) -> NULL.
**Amounts** - strip currency symbols, thousand separators and ' INR' suffix. **$ amounts: no FX conversion** - magnitudes are the same as the INR rows (see check at the bottom), so the symbol is treated as a formatting error; original marker kept in `amount_currency_raw`.
**Phone / zip** - phone normalised to 10 digits (strip +91, leading 0, punctuation) else NULL; zip must be 6 digits else NULL.
**Exact duplicates** - dropped (logged in rejects).
**Conflicting duplicates (winner rule)** - customers: most complete record after email lower-casing (the 5 duplicate pairs differ only in email case, so they become exact dups); suppliers (S004): most complete record (real country beats 'Unknown'); products: (1) valid price >0, (2) price that actually appears in order_items for that product, (3) the '(Revised)' row (latest), (4) most complete. '(Revised)' suffix removed from the name.
**Orphans** - child rows whose parent does not exist are **quarantined** in `rejects` (orders->items, products->items, orders->payments, items->returns; cascades in that order). Orders whose customer does not exist are **kept but flagged** (`customer_orphan=TRUE`): the revenue is real, so revenue KPIs include them; **KPI 2 (customer-level) excludes them** (they cannot be attributed to a customer or segment). Products with an unknown supplier id keep the row, supplier_id set NULL (raw kept in supplier_id_raw).
**order_items** - quantity <=0 -> quarantined; unit_price missing/<=0 -> replaced with product list price; discount outside 0-100 -> 0 (flagged). **line_total is recomputed = qty x unit_price x (1 - discount/100) and the recomputed value is trusted**; stored value kept as line_total_raw with a mismatch flag.
**Products** - price <=0 with no valid duplicate -> modal order-line price; blank category inferred from sub_category; cost_price > unit_price flagged as negative_margin (kept, real business signal).
**Suppliers** - ratings >5 are on a 0-10 scale and are halved to 0-5 (a 10-scale value <=5 cannot be detected; documented limitation).
**Returns** - blank refund stays NULL (flagged, not guessed); refund > line_total and return before order are flagged, not deleted.
"""
rep = f"# Phase 2 - Cleaning report\n{RULES}\n## Before / after row counts\n{md(ba)}\n## Distinct values before / after\n{md(dd)}\n## Fixes applied\n{md(fx)}\n## Rejects summary\n{md(rs)}\n## $ amount check (Success payments: share where amount == order total within 1%, no conversion)\n{md(fx_diag.reset_index())}\nFiles: silver/*.csv, silver/silver.db, silver/rejects.csv\n"
(BASE / '02_cleaning_report.md').write_text(rep, encoding='utf-8')
print(rep)
