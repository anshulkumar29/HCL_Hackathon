-- KPI 3: customer segment profile = customers + average order value (AOV)
WITH order_value AS (
    SELECT order_id,
           SUM(line_total)  AS gross_value,
           SUM(net_revenue) AS net_value
    FROM v_sales_lines
    GROUP BY order_id
)
SELECT COALESCE(c.customer_segment, 'Unknown')             AS segment,
       COUNT(DISTINCT c.customer_id)                       AS customers,
       COUNT(DISTINCT o.customer_id)                       AS customers_with_completed_order,
       COUNT(o.order_id)                                   AS completed_orders,
       ROUND(SUM(COALESCE(ov.gross_value, 0)), 2)          AS total_order_value,
       ROUND(SUM(COALESCE(ov.gross_value, 0)) / NULLIF(COUNT(o.order_id), 0), 2) AS avg_order_value,
       ROUND(SUM(COALESCE(ov.net_value, 0))   / NULLIF(COUNT(o.order_id), 0), 2) AS avg_order_value_after_returns
FROM customers c
LEFT JOIN orders o       ON o.customer_id = c.customer_id AND o.order_status = 'Completed'
LEFT JOIN order_value ov ON ov.order_id   = o.order_id
GROUP BY COALESCE(c.customer_segment, 'Unknown')
ORDER BY avg_order_value DESC;
