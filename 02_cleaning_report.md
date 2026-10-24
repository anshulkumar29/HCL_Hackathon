# Phase 2 - Cleaning report

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

## Before / after row counts
| table | raw_rows | exact_dups_dropped | conflicting_dups_dropped | quarantined | flagged_kept | silver_rows | raw_null_cells | silver_null_cells |
|---|---|---|---|---|---|---|---|---|
| customers | 163 | 5 | 0 | 0 | 0 | 158 | 17 | 19 |
| products | 75 | 0 | 5 | 0 | 4 | 70 | 7 | 6 |
| suppliers | 19 | 0 | 1 | 0 | 0 | 18 | 4 | 3 |
| orders | 323 | 3 | 0 | 0 | 15 | 320 | 228 | 227 |
| order_items | 802 | 5 | 0 | 28 | 0 | 769 | 5 | 0 |
| payments | 329 | 4 | 0 | 8 | 0 | 317 | 10 | 10 |
| returns | 68 | 3 | 0 | 7 | 0 | 58 | 4 | 4 |

## Distinct values before / after
| table | column | distinct_before | distinct_after | values_after |
|---|---|---|---|---|
| customers | customer_segment | 15 | 4 | Bronze, Gold, Platinum, Silver |
| customers | city | 18 | 10 | Ahmedabad, Bangalore, Chennai, Delhi, Hyderabad, Jaipur, Kolkata, Lucknow, Mumba |
| customers | is_active | 9 | 2 | False, True |
| products | category | 16 | 5 | Electronics, Fashion, Grocery, Home & Kitchen, Sports |
| products | is_active | 9 | 2 | False, True |
| orders | order_status | 13 | 4 | Cancelled, Completed, Pending, Returned |
| orders | channel | 10 | 3 | App, Store, Web |
| orders | promo_code | 25 | 20 | PROMO1, PROMO10, PROMO11, PROMO12, PROMO13, PROMO14, PROMO15, PROMO16, PROMO17,  |
| payments | payment_status | 11 | 4 | Failed, Pending, Refunded, Success |
| returns | return_reason | 11 | 5 | Damaged, Defective, Not As Described, Size Issue, Wrong Item |
| returns | return_status | 6 | 3 | Approved, Pending, Rejected |

## Fixes applied
| table | fix | rows_affected |
|---|---|---|
| suppliers | rating >5 treated as 0-10 scale and halved to 0-5 | 4 |
| customers | phone not a valid 10-digit number -> NULL | 0 |
| customers | zip not 6 digits (N/A etc) -> NULL | 3 |
| customers | ambiguous dd/mm vs mm/dd dates parsed as MM/DD | 30 |
| products | blank category inferred from sub_category | 5 |
| products | invalid price (<=0) replaced by modal order-line price | 2 |
| orders | ambiguous dd/mm vs mm/dd dates parsed as MM/DD | 65 |
| order_items | missing/negative unit_price replaced by product list price | 15 |
| order_items | discount outside 0-100 -> 0 | 6 |
| order_items | stored line_total did not reconcile; recomputed value trusted | 50 |
| payments | ambiguous dd/mm vs mm/dd dates parsed as MM/DD | 57 |
| payments | amounts with $ symbol (no FX conversion applied) | 29 |
| returns | ambiguous dd/mm vs mm/dd dates parsed as MM/DD | 10 |
| returns | refund_amount blank (kept NULL, flagged) | 4 |
| returns | refund greater than recomputed line_total (flagged) | 4 |
| returns | return_date earlier than order_date (flagged) | 28 |

## Rejects summary
| table | reason | action | rows |
|---|---|---|---|
| customers | EXACT_DUPLICATE | dropped | 5 |
| order_items | EXACT_DUPLICATE | dropped | 5 |
| order_items | INVALID_QUANTITY | quarantined | 10 |
| order_items | ORPHAN_ORDER | quarantined | 10 |
| order_items | ORPHAN_PRODUCT | quarantined | 8 |
| orders | EXACT_DUPLICATE | dropped | 3 |
| orders | ORPHAN_CUSTOMER | flagged_kept | 15 |
| payments | EXACT_DUPLICATE | dropped | 4 |
| payments | ORPHAN_ORDER | quarantined | 8 |
| products | CONFLICTING_DUPLICATE | dropped | 5 |
| products | ORPHAN_SUPPLIER | flagged_kept | 4 |
| returns | EXACT_DUPLICATE | dropped | 3 |
| returns | ORPHAN_ORDER_ITEM | quarantined | 7 |
| suppliers | CONFLICTING_DUPLICATE | dropped | 1 |

## $ amount check (Success payments: share where amount == order total within 1%, no conversion)
| amount_currency_raw | mean | count |
|---|---|---|
| INR | 0.681 | 47 |
| USD | 0.6 | 15 |
| none/INR | 0.581 | 160 |

Files: silver/*.csv, silver/silver.db, silver/rejects.csv
