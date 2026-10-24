-- Stretch: margin risk = sold lines where cost price is higher than the price after discount
SELECT p.product_id, p.product_name, p.category,
       COUNT(*)                         AS lines_affected,
       SUM(oi.quantity)                 AS units_affected,
       ROUND(SUM(oi.line_total), 2)     AS revenue_exposed,
       ROUND(SUM(oi.quantity * (p.cost_price - oi.unit_price * (1 - oi.discount_pct / 100.0))), 2) AS total_loss
FROM order_items oi
JOIN orders   o ON o.order_id   = oi.order_id
JOIN products p ON p.product_id = oi.product_id
WHERE o.order_status IN ('Completed', 'Returned')
  AND p.cost_price > oi.unit_price * (1 - oi.discount_pct / 100.0)
GROUP BY p.product_id, p.product_name, p.category
ORDER BY total_loss DESC;
