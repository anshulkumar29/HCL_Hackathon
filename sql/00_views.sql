-- Shared helper views (TEMP = they exist only while the connection is open, silver.db is not changed)

DROP VIEW IF EXISTS temp.v_refund_per_item;
DROP VIEW IF EXISTS temp.v_sales_lines;
DROP VIEW IF EXISTS temp.v_product_sales;
DROP VIEW IF EXISTS temp.v_customer_repeat;

-- 1) Approved refund per order line (blank refund = 0). Rejected / Pending returns are ignored.
CREATE TEMP VIEW v_refund_per_item AS
SELECT order_item_id,
       SUM(COALESCE(refund_amount, 0)) AS refund_amount
FROM returns
WHERE return_status = 'Approved'
GROUP BY order_item_id;

-- 2) One row per SOLD order line: only Completed and Returned orders count as revenue.
--    refund is capped at line_total, so a bad refund can never make revenue negative.
CREATE TEMP VIEW v_sales_lines AS
SELECT oi.order_item_id,
       oi.order_id,
       oi.product_id,
       oi.quantity,
       oi.line_total,
       o.customer_id,
       o.customer_orphan,
       o.order_date,
       o.order_date_ambiguous,
       SUBSTR(o.order_date, 1, 7)                            AS order_month,
       o.order_status,
       o.channel,
       p.category,
       p.supplier_id,
       CASE WHEN r.order_item_id IS NULL THEN 0 ELSE 1 END   AS is_returned,
       MIN(COALESCE(r.refund_amount, 0), oi.line_total)      AS refund,
       oi.line_total - MIN(COALESCE(r.refund_amount, 0), oi.line_total) AS net_revenue
FROM order_items oi
JOIN orders   o ON o.order_id   = oi.order_id
JOIN products p ON p.product_id = oi.product_id
LEFT JOIN v_refund_per_item r ON r.order_item_id = oi.order_item_id
WHERE o.order_status IN ('Completed', 'Returned');

-- 3) One row per product: units ordered, units returned, return rate (used by KPI 5 and KPI 6)
CREATE TEMP VIEW v_product_sales AS
SELECT product_id,
       SUM(quantity)                                              AS ordered_qty,
       SUM(CASE WHEN is_returned = 1 THEN quantity ELSE 0 END)    AS returned_qty,
       1.0 * SUM(CASE WHEN is_returned = 1 THEN quantity ELSE 0 END) / SUM(quantity) AS return_rate,
       SUM(line_total)                                            AS gross_revenue,
       SUM(net_revenue)                                           AS net_revenue
FROM v_sales_lines
GROUP BY product_id;

-- 4) One row per customer with at least one Completed order: first order, second order, days between (KPI 7)
CREATE TEMP VIEW v_customer_repeat AS
WITH seq AS (
    SELECT customer_id,
           order_date,
           order_date_ambiguous,
           ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS order_no,
           LEAD(order_date)           OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS next_order_date,
           LEAD(order_date_ambiguous) OVER (PARTITION BY customer_id ORDER BY order_date, order_id) AS next_ambiguous
    FROM orders
    WHERE order_status = 'Completed'
      AND customer_orphan = 0
)
SELECT customer_id,
       order_date      AS first_order_date,
       next_order_date AS second_order_date,
       CASE WHEN next_order_date IS NULL THEN NULL
            ELSE CAST(JULIANDAY(next_order_date) - JULIANDAY(order_date) AS INTEGER) END AS days_to_second_order,
       MAX(order_date_ambiguous, COALESCE(next_ambiguous, 0)) AS uses_ambiguous_date
FROM seq
WHERE order_no = 1;
