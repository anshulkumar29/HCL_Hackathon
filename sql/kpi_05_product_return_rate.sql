-- KPI 5: product return rate = returned units / ordered units. Top 10 and bottom 10, minimum volume applied.
WITH base AS (
    SELECT ps.product_id, p.product_name, p.category,
           ps.ordered_qty, ps.returned_qty, ps.return_rate
    FROM v_product_sales ps
    JOIN products p ON p.product_id = ps.product_id
    WHERE ps.ordered_qty >= :min_units
),
ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (ORDER BY return_rate DESC, ordered_qty DESC, product_id) AS rank_top,
           ROW_NUMBER() OVER (ORDER BY return_rate ASC,  ordered_qty DESC, product_id) AS rank_bottom
    FROM base
)
SELECT 'Top 10 - highest return rate' AS list_name, rank_top AS rank_no,
       product_id, product_name, category, ordered_qty, returned_qty,
       ROUND(100.0 * return_rate, 2) AS return_rate_pct
FROM ranked WHERE rank_top <= 10
UNION ALL
SELECT 'Bottom 10 - lowest return rate', rank_bottom,
       product_id, product_name, category, ordered_qty, returned_qty,
       ROUND(100.0 * return_rate, 2)
FROM ranked WHERE rank_bottom <= 10
ORDER BY list_name DESC, rank_no;
