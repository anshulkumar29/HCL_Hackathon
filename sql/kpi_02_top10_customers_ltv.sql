-- KPI 2: top 10 customers by net lifetime value (Completed orders only, orphan customers excluded)
SELECT c.customer_id,
       c.first_name || ' ' || c.last_name AS customer_name,
       c.customer_segment                 AS segment,
       c.city,
       COUNT(DISTINCT s.order_id)         AS completed_orders,
       ROUND(SUM(s.line_total), 2)        AS gross_value,
       ROUND(SUM(s.refund), 2)            AS approved_refunds,
       ROUND(SUM(s.net_revenue), 2)       AS net_lifetime_value
FROM v_sales_lines s
JOIN customers c ON c.customer_id = s.customer_id
WHERE s.order_status = 'Completed'
  AND s.customer_orphan = 0
GROUP BY c.customer_id
ORDER BY net_lifetime_value DESC, c.customer_id
LIMIT 10;
