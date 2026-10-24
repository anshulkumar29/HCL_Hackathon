-- KPI 4: month-over-month (MoM) growth of order count and net revenue, per channel
WITH RECURSIVE months(month_start) AS (               -- every calendar month from first to last order
    SELECT DATE(MIN(order_date), 'start of month') FROM orders
    UNION ALL
    SELECT DATE(month_start, '+1 month') FROM months
    WHERE month_start < (SELECT DATE(MAX(order_date), 'start of month') FROM orders)
),
grid AS (                                            -- every channel x every month (so empty months show as 0)
    SELECT ch.channel, SUBSTR(m.month_start, 1, 7) AS order_month
    FROM (SELECT DISTINCT channel FROM orders WHERE channel IS NOT NULL) ch
    CROSS JOIN months m
),
order_cnt AS (
    SELECT channel, SUBSTR(order_date, 1, 7) AS order_month, COUNT(*) AS orders
    FROM orders
    WHERE order_status IN ('Completed', 'Returned')
    GROUP BY channel, SUBSTR(order_date, 1, 7)
),
rev AS (
    SELECT channel, order_month, SUM(net_revenue) AS net_revenue
    FROM v_sales_lines
    GROUP BY channel, order_month
),
monthly AS (
    SELECT g.channel, g.order_month,
           COALESCE(oc.orders, 0)      AS orders,
           COALESCE(r.net_revenue, 0)  AS net_revenue
    FROM grid g
    LEFT JOIN order_cnt oc ON oc.channel = g.channel AND oc.order_month = g.order_month
    LEFT JOIN rev r        ON r.channel  = g.channel AND r.order_month  = g.order_month
),
with_prev AS (
    SELECT *,
           LAG(orders)      OVER (PARTITION BY channel ORDER BY order_month) AS prev_orders,
           LAG(net_revenue) OVER (PARTITION BY channel ORDER BY order_month) AS prev_net_revenue
    FROM monthly
)
SELECT channel,
       order_month,
       orders,
       prev_orders,
       ROUND(100.0 * (orders - prev_orders) / NULLIF(prev_orders, 0), 2)                 AS orders_mom_pct,
       ROUND(net_revenue, 2)                                                             AS net_revenue,
       ROUND(prev_net_revenue, 2)                                                        AS prev_net_revenue,
       ROUND(100.0 * (net_revenue - prev_net_revenue) / NULLIF(prev_net_revenue, 0), 2)  AS revenue_mom_pct
FROM with_prev
ORDER BY channel, order_month;
