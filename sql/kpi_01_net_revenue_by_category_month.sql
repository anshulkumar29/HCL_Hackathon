-- KPI 1: net revenue by product category per month
SELECT order_month,
       category,
       COUNT(DISTINCT order_id)      AS orders,
       SUM(quantity)                 AS units,
       ROUND(SUM(line_total), 2)     AS gross_revenue,
       ROUND(SUM(refund), 2)         AS approved_refunds,
       ROUND(SUM(net_revenue), 2)    AS net_revenue
FROM v_sales_lines
GROUP BY order_month, category
ORDER BY order_month, category;
