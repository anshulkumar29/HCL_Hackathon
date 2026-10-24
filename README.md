# ShopSphere - E-Commerce Order & Customer Analytics Pipeline

HCL Hackathon - Data Engineering use case.
Goal: take 7 raw, messy files from 4 source systems and turn them into a clean, trusted analytics layer,
then answer business questions (KPIs) and show them in a dashboard.

**Flow:** raw files -> profile -> clean tables (silver) -> pipeline -> KPIs (SQL) -> Streamlit dashboard

---

## 1. How to run

Needs Python 3.10+ with `pandas`, `numpy`, `scipy`, and `streamlit`. (SQLite comes with Python.)

```bash
python run_project_pipeline.py                     # clean -> validate -> export KPI CSVs -> launch dashboard
python run_project_pipeline.py --no-dashboard      # run data pipeline only
python run_project_pipeline.py --skip-clean         # reuse silver data, rebuild KPIs, then launch dashboard
```

The pipeline stops if a validation fails and writes progress to `pipeline.log`. The dashboard starts only after the pipeline succeeds. Raw source files are not modified. To run only the lower-level data pipeline directly, use `python 04_pipeline.py`.

## 2. Project structure

```
HCL_Hackathon/
|-- customers.csv, products.csv, orders.csv, order_items.csv,
|   payments.csv, returns.csv, suppliers_json.txt   # 7 raw files (never edited)
|-- 01_profile.ipynb          # Phase 1 - profiling (read-only)
|-- 02_clean.py               # Phase 2 - cleaning script (raw -> silver)
|-- 02_cleaning.ipynb         # Phase 2 - same logic, step by step with explanations
|-- 02_cleaning_report.md     # cleaning rules + before/after counts
|-- before_after_counts.csv
|-- silver/                   # clean tables as CSV + silver.db (SQLite) + rejects.csv
|-- sql/                      # one .sql file per KPI + 00_views.sql (helper views)
|-- kpi_lib.py                # shared settings and small helper functions
|-- 03_kpis.ipynb             # Phase 3 - KPIs step by step (markdown + SQL + checks)
|-- 04_pipeline.py            # data steps: clean -> validate -> build and check KPIs
|-- run_project_pipeline.py   # end-to-end entry point: data steps -> Streamlit dashboard
|-- kpi_outputs/              # KPI result files (CSV) - the dashboard reads these
|-- overview_dashboard.py     # Streamlit dashboard: Overview, KPI 1-3, KPI 5, KPI 7, EDA/statistics
|-- dashboard.py              # earlier dashboard version
|-- pipeline.log              # log of the last pipeline run
`-- README.md                 # this file
```

## 3. Progress

| Phase | What | Status |
|---|---|---|
| 1 | Profile the raw data | Done (`01_profile.ipynb`) |
| 2 | Cleaning rules + clean tables | Done (`02_clean.py`, `silver/`) |
| 3 | Data model (star schema / SCD) | **Skipped on purpose** - see section 9 |
| 4 | Pipeline raw -> clean -> KPIs -> dashboard | Done (`run_project_pipeline.py`, `04_pipeline.py`) |
| 5 | 8 KPIs + stretch KPI | Done (`03_kpis.ipynb`, `sql/`, `kpi_outputs/`) |
| 6 | Streamlit dashboard | Done (`overview_dashboard.py`) - Overview, KPI 1, 2, 3, 5, 7, and EDA/statistics |
| 7 | Assumptions + AI usage log | README done; AI usage log: see section 10 |

---

## 4. Phase 1 - Profiling

All files were read as text (`dtype=str`) so nothing was changed. Row counts and how the tables connect:

| Table | Source system | Raw rows | One row = |
|---|---|---|---|
| customers | CRM | 163 | one customer |
| products | Product catalog | 75 | one product |
| suppliers | Procurement (JSON) | 19 | one supplier |
| orders | E-commerce | 323 | one order |
| order_items | E-commerce | 802 | one product line in an order |
| payments | Payment gateway | 329 | one payment |
| returns | E-commerce | 68 | one returned order line |

```
customers --(customer_id)--> orders --(order_id)--> order_items --(product_id)--> products --(supplier_id)--> suppliers
                               |                         |
                       (order_id)                 (order_item_id)
                               v                         v
                           payments                  returns
```

Problems found: duplicate rows, the same label written many ways (`Glod`, `GOLD`, `gold`), 3 date formats,
currency symbols inside amounts, broken links between tables, and stored `line_total` values that do not match quantity x price.

## 5. Phase 2 - Cleaning (raw -> silver)

Row counts:

| Table | Raw | Clean (silver) |
|---|---|---|
| customers | 163 | 158 |
| products | 75 | 70 |
| suppliers | 19 | 18 |
| orders | 323 | 320 |
| order_items | 802 | 769 |
| payments | 329 | 317 |
| returns | 68 | 58 |

Every dropped or quarantined row is kept in `silver/rejects.csv` with the reason (nothing disappears silently).

**Main decisions**

| Area | Decision |
|---|---|
| Labels | Made consistent (segment, city, order status, channel, payment status, category, return reason). Typos fixed with an explicit map. |
| Missing values | `NA`, `N/A`, `None`, `null`, `unknown`, blank -> real NULL. |
| Dates | ISO and `DD-Mon-YYYY` are exact. For `dd/mm/yyyy`: if one part is above 12 it decides the format; if both parts are 12 or less it is **ambiguous**, read as MM/DD, and flagged in a `*_date_ambiguous` column (customers 30, orders 65, payments 57, returns 10). |
| Amounts | Currency symbols, commas and " INR" removed. **$ amounts were not converted**: successful payments match the order total in 68% (INR), 60% ($) and 58% (no symbol) of cases, so $ is just a wrong symbol, not a real currency change. |
| Exact duplicates | Dropped (customers 5, orders 3, order_items 5, payments 4, returns 3). |
| Conflicting duplicates | Products (5 ids with different prices): valid price first, then the price seen on real order lines, then the "(Revised)" row. Supplier S004: the row with a real country wins. |
| Broken links | Items without an order (10) or product (8), payments without an order (8), returns without an item (7) -> **quarantined**. Orders whose customer does not exist (15) -> **kept and flagged** (`customer_orphan = 1`) because the revenue is real. Products with an unknown supplier -> kept, supplier set to NULL. |
| order_items | Quantity 0 or less -> quarantined (10). Missing price -> product list price (15). Discount outside 0-100 -> 0 (6). **`line_total` recomputed** as quantity x price x (1 - discount/100); 50 stored values were wrong. |
| products | Invalid price imputed from the usual order-line price (2). Blank category inferred from sub-category (5). `cost > price` flagged as `negative_margin` (kept, it is a real business signal). |
| suppliers | Ratings above 5 were on a 0-10 scale and were halved (4 rows). |
| returns | Blank refund stays NULL (flagged). Refund above line total flagged (4). Return date before order date flagged (28 of 58), not deleted. |

**Not done on purpose:** no filtering by order or payment status in silver (each KPI decides), no reconciliation of order status "Returned" against the returns table, payment method / names / addresses left as they are.

Details: `02_cleaning_report.md` and `02_cleaning.ipynb`.

## 6. Phase 3/4 - KPIs and pipeline

**Method:** the clean tables sit in SQLite (`silver/silver.db`). Each KPI is a plain SQL query in `sql/`.
`00_views.sql` creates helper views first (for example `v_sales_lines` = one row per sold order line with refund and net revenue),
so the KPI queries stay short. Python (`kpi_lib.py`) only opens the database, runs the query and saves the result as CSV.
`03_kpis.ipynb` shows every KPI step by step: markdown (question, method, assumptions), SQL, result, and a check cell.
Some checks recalculate the KPI in pandas to confirm the SQL answer.

**End-to-end entry point (`run_project_pipeline.py`):** runs `04_pipeline.py` first, then opens `overview_dashboard.py` in Streamlit only if data validation and KPI checks pass. Use `--no-dashboard` to stop after exporting data, or `--skip-clean` to reuse the current silver database.

**Data pipeline (`04_pipeline.py`):**

| Step | What happens |
|---|---|
| 1. Clean | runs `02_clean.py` (raw -> silver) |
| 2. Check silver | keys unique, no broken links, no zero quantities, discounts 0-100, ratings 0-5 |
| 3. Build KPIs | runs `00_views.sql` and each KPI file, saves CSV to `kpi_outputs/` |
| 4. Check KPIs | totals tie together (for example KPI 4 revenue = KPI 1 revenue), row counts as expected |
| 5. Summary | totals and run time written to `pipeline.log` |

The notebook and the pipeline give identical result files (compared byte by byte).

### Shared rules for all KPIs

| Topic | Rule |
|---|---|
| Revenue amount | recomputed `line_total` |
| Revenue orders | **Completed** and **Returned**. Cancelled and Pending are not revenue. |
| Refunds | only **Approved** returns; blank refund = 0; refund capped at the line total |
| Month of a refund | month of the **order** (return dates cannot be trusted: 28 of 58 are before the order) |
| A return | the whole order line (the returns table has no quantity) |
| Orders with unknown customer | counted in revenue KPIs (1, 4); excluded from customer KPIs (2, 3, 7) |
| Ambiguous dates | read as MM/DD; month-based KPIs (1, 4, 7) can shift slightly |

### The KPIs

| # | KPI | Method (short) | Main result |
|---|---|---|---|
| 1 | Net revenue by category per month | sold lines grouped by order month and category, minus approved refunds | Total net revenue 19.29M. Grocery 5.16M, Home & Kitchen 4.83M, Fashion 4.03M, Sports 2.70M, Electronics 2.57M |
| 2 | Top 10 customers by net lifetime value | Completed orders per customer, net of returns, orphan customers excluded | #1 Utkarsh Bhat (C0118) 532K |
| 3 | Segment profile | customers and average order value (AOV = order value / Completed orders) per segment | AOV: Gold 96.8K, Silver 90.5K, Platinum 78.0K, Bronze 77.5K |
| 4 | Month-over-month growth by channel | full month calendar, `LAG()` window, growth % (empty when previous month is 0) | Almost all orders are in 2024-2025, so single months jump a lot; a yearly summary is in the notebook |
| 5 | Product return rate (top 10 / bottom 10) | returned units / ordered units; minimum 18 units (25th percentile of units per product); ties by volume | Highest: P029 Furniture Item 29 (21.4%). Bottom 10 are all 0% |
| 6 | Supplier scorecard | revenue, average return rate (inverted), rating; min-max scaled; weights 40/30/30 | S006 first (84.7), then S007, S015. Equal weights swap S006 and S007 |
| 7 | Repeat-purchase rate | `ROW_NUMBER` / `LEAD`: 2nd Completed order within 90 days of the 1st | 8 of 98 customers = 8.16% (3 depend on an ambiguous date) |
| 8 | Payment reconciliation | per order: sum of line totals vs sum of Success payments (1% tolerance) | Matched 111, no successful payment 63, underpaid 40, overpaid 36, **payment on a cancelled order 35**, pending-unpaid 25, cancelled-unpaid 8, no items 2. The 8 orphan payments are listed separately |
| 9 | Stretch: margin risk | lines where cost price > price after discount | 27 products, 127 lines, 397 units, revenue exposed 3.32M, loss 1.37M (before returns) |

KPI results are in `kpi_outputs/`. KPI 6 weights and the KPI 5 minimum volume are **our assumptions** (not given in the case).

## 7. Phase 6 - Dashboard

`python run_project_pipeline.py` starts the full process and opens `overview_dashboard.py`. The dashboard reads the cleaned and KPI result files; it does not change the raw source files.

| Page | Content |
|---|---|
| Overview | net revenue, refunds, customers, repeat rate, revenue by category, customers by segment |
| KPI 1 | monthly revenue by category with year and category filters |
| KPI 2 | top 10 customers by net lifetime value |
| KPI 3 | customer count and average order value by segment |
| KPI 5 | top and bottom 10 products by return rate (tables only) |
| KPI 7 | 90-day repeat-purchase rate and customer detail (tables only) |
| EDA and Statistics | customer distributions, product price boxplots, and statistical tests |

KPI 4, 6, 8, and the stretch KPI remain available in `kpi_outputs/` and the KPI notebook; they are not currently shown as dashboard pages.

## 8. Findings worth mentioning

- **Orders are concentrated in 2024-2025.** 2020-2023 have only a few orders (2023 has none), so monthly growth numbers are noisy.
- **35 of the 43 cancelled orders still have a successful payment.** This needs a refund or status check in the source system.
- **63 Completed/Returned orders have no successful payment**, and 76 are paid more or less than expected.
- **15 of 58 returns point to Cancelled or Pending orders.** They are ignored (an unsold line cannot be returned).
- **27 products were sold at least once below cost.**
- `line_total` was wrong on 50 rows, so any report built on the raw column would be off.

## 9. Trade-offs and limitations

- **Data model skipped.** We answered the KPIs directly with SQL on the clean tables instead of building a star schema (fact and dimension tables) with SCD Type 2 (slowly changing dimension, keeps customer history). This saves time, but the case study lists a data model and a customer-history note as a deliverable. A production version would add `dim_customer` (with valid-from / valid-to dates), `dim_product`, `dim_supplier`, `dim_date` and `fact_order_items`.
- **Ambiguous dates** are read as MM/DD. If the source actually used DD/MM, month-based KPIs would shift for those rows.
- **No currency conversion** for `$` amounts (evidence-based, see section 5).
- **Supplier rating scale** fix assumes values above 5 are on a 0-10 scale; a 0-10 value of 5 or less cannot be detected.
- **Return rate** treats a return as the whole line, because the returns table has no quantity.
- **KPI weights and thresholds** (40/30/30, 18 units, 90 days, 1% tolerance) are assumptions, kept in one place (`kpi_lib.py`).
- Small data (320 orders), so rates such as the repeat rate rest on few customers.

## 10. AI usage log

*Fill in the tool names and your real prompts before submitting; the corrections below are what actually happened.*

| Item | Entry |
|---|---|
| Tools used | (add: for example Claude for profiling help, cleaning script, SQL and dashboard code) |
| Prompt 1 | (paste your real prompt) |
| Prompt 2 | (paste your real prompt) |
| Prompt 3 | (paste your real prompt) |

**What was checked, corrected or rejected**

1. **Corrected:** the AI first assumed the stored `line_total` was right. A check showed 50 rows did not equal quantity x price x (1 - discount), so it was recomputed and the original kept in `line_total_raw`.
2. **Rejected:** converting `$` amounts with an assumed exchange rate. We tested the amounts against order totals instead; `$` rows matched like the INR rows, so no conversion was applied.
3. **Handled, not guessed:** `dd/mm` versus `mm/dd` dates. A documented rule plus flag columns was used instead of a silent guess.
4. **Verified:** KPI 1, 2 and 7 were recalculated independently in pandas and matched the SQL results; the pipeline output matches the notebook output exactly.
5. **Chosen by us:** the KPI 6 weights, the KPI 5 minimum volume and skipping the data-model phase were our own decisions, written down as assumptions.
