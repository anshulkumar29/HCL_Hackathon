-- KPI 6: supplier scorecard. Score = weights x (revenue, 1 - return rate, rating), each scaled 0..1 (min-max)
WITH supplier_sales AS (
    SELECT COALESCE(p.supplier_id, 'UNKNOWN') AS supplier_id,
           COUNT(*)                           AS products_sold,
           SUM(ps.net_revenue)                AS net_revenue,
           AVG(ps.return_rate)                AS avg_return_rate
    FROM v_product_sales ps
    JOIN products p ON p.product_id = ps.product_id
    GROUP BY COALESCE(p.supplier_id, 'UNKNOWN')
),
joined AS (
    SELECT ss.supplier_id,
           COALESCE(s.supplier_name, 'Unknown supplier') AS supplier_name,
           s.country, s.rating,
           ss.products_sold, ss.net_revenue, ss.avg_return_rate
    FROM supplier_sales ss
    LEFT JOIN suppliers s ON s.supplier_id = ss.supplier_id
),
bounds AS (                                          -- min and max over the real suppliers only
    SELECT MIN(net_revenue) AS rev_min, MAX(net_revenue) AS rev_max,
           MIN(avg_return_rate) AS ret_min, MAX(avg_return_rate) AS ret_max,
           MIN(rating) AS rat_min, MAX(rating) AS rat_max
    FROM joined WHERE supplier_id <> 'UNKNOWN'
),
scaled AS (
    SELECT j.*,
           (j.net_revenue     - b.rev_min) / NULLIF(b.rev_max - b.rev_min, 0)       AS revenue_scaled,
           1 - (j.avg_return_rate - b.ret_min) / NULLIF(b.ret_max - b.ret_min, 0)   AS return_scaled,
           (j.rating          - b.rat_min) / NULLIF(b.rat_max - b.rat_min, 0)       AS rating_scaled
    FROM joined j CROSS JOIN bounds b
    WHERE j.supplier_id <> 'UNKNOWN'
),
scored AS (
    SELECT *,
           100 * (:w_revenue * revenue_scaled + :w_return * return_scaled + :w_rating * rating_scaled) AS score
    FROM scaled
)
SELECT * FROM (
    SELECT RANK() OVER (ORDER BY score DESC) AS rank_no,
           supplier_id, supplier_name, country, products_sold,
           ROUND(net_revenue, 2)          AS net_revenue,
           ROUND(100 * avg_return_rate, 2) AS avg_return_rate_pct,
           rating,
           ROUND(revenue_scaled, 3) AS revenue_scaled,
           ROUND(return_scaled, 3)  AS return_scaled,
           ROUND(rating_scaled, 3)  AS rating_scaled,
           ROUND(score, 2)          AS score
    FROM scored
    UNION ALL                                        -- products with no known supplier: shown, but not ranked
    SELECT NULL, supplier_id, supplier_name, NULL, products_sold,
           ROUND(net_revenue, 2), ROUND(100 * avg_return_rate, 2),
           NULL, NULL, NULL, NULL, NULL
    FROM joined WHERE supplier_id = 'UNKNOWN'
)
ORDER BY rank_no IS NULL, rank_no;
