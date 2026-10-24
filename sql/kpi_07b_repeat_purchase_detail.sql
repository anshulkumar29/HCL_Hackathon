-- KPI 7 detail: one row per customer (used to explain the rate)
SELECT customer_id, first_order_date, second_order_date, days_to_second_order,
       CASE WHEN days_to_second_order <= :repeat_window_days THEN 1 ELSE 0 END AS is_repeat_within_window,
       uses_ambiguous_date
FROM v_customer_repeat
ORDER BY customer_id;
