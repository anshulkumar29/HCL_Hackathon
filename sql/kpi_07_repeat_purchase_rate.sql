-- KPI 7: repeat-purchase rate = customers whose 2nd Completed order is within N days of their 1st
SELECT COUNT(*) AS customers_with_completed_order,
       SUM(CASE WHEN days_to_second_order <= :repeat_window_days THEN 1 ELSE 0 END) AS repeat_customers,
       ROUND(100.0 * SUM(CASE WHEN days_to_second_order <= :repeat_window_days THEN 1 ELSE 0 END) / COUNT(*), 2) AS repeat_rate_pct,
       SUM(CASE WHEN days_to_second_order <= :repeat_window_days AND uses_ambiguous_date = 1 THEN 1 ELSE 0 END) AS repeat_customers_with_ambiguous_dates
FROM v_customer_repeat;
