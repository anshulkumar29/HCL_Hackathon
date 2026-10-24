-- KPI 8: payment reconciliation. Expected = sum of line_total of the order, Paid = sum of Success payments
WITH expected AS (
    SELECT order_id, SUM(line_total) AS expected_total
    FROM order_items
    GROUP BY order_id
),
paid AS (
    SELECT order_id,
           SUM(CASE WHEN payment_status = 'Success' THEN amount ELSE 0 END)           AS paid_success,
           SUM(CASE WHEN payment_status = 'Success'  THEN 1 ELSE 0 END)               AS n_success,
           COUNT(DISTINCT CASE WHEN payment_status = 'Success' THEN ROUND(amount, 2) END) AS n_distinct_success_amounts,
           SUM(CASE WHEN payment_status = 'Failed'   THEN 1 ELSE 0 END)               AS n_failed,
           SUM(CASE WHEN payment_status = 'Refunded' THEN 1 ELSE 0 END)               AS n_refunded,
           COUNT(*)                                                                   AS n_payments
    FROM payments
    GROUP BY order_id
),
joined AS (
    SELECT o.order_id, o.customer_id, o.order_date, o.order_status, o.channel,
           ROUND(e.expected_total, 2)           AS expected_total,
           ROUND(COALESCE(p.paid_success, 0), 2) AS paid_success,
           COALESCE(p.n_success, 0)                    AS n_success,
           COALESCE(p.n_distinct_success_amounts, 0)   AS n_distinct_success_amounts,
           COALESCE(p.n_failed, 0)                     AS n_failed,
           COALESCE(p.n_refunded, 0)                   AS n_refunded,
           COALESCE(p.n_payments, 0)                   AS n_payments
    FROM orders o
    LEFT JOIN expected e ON e.order_id = o.order_id
    LEFT JOIN paid p     ON p.order_id = o.order_id
)
SELECT order_id, customer_id, order_date, order_status, channel,
       expected_total, paid_success,
       ROUND(paid_success - COALESCE(expected_total, 0), 2) AS difference,
       CASE
           WHEN order_status = 'Cancelled' AND paid_success > 0 THEN 'Payment on cancelled order'
           WHEN order_status = 'Cancelled'                      THEN 'Cancelled - no payment (OK)'
           WHEN expected_total IS NULL                          THEN 'Order has no items'
           WHEN paid_success = 0 AND order_status = 'Pending'   THEN 'Pending - not paid yet (OK)'
           WHEN paid_success = 0                                THEN 'No successful payment'
           WHEN paid_success < expected_total * (1 - :pay_tolerance) THEN 'Underpaid'
           WHEN paid_success > expected_total * (1 + :pay_tolerance) THEN 'Overpaid'
           ELSE 'Matched'
       END AS recon_status,
       CASE WHEN n_success > 1 AND n_distinct_success_amounts = 1 THEN 1 ELSE 0 END AS duplicate_success_payment,
       CASE WHEN n_distinct_success_amounts > 1                   THEN 1 ELSE 0 END AS conflicting_success_amounts,
       n_success, n_failed, n_refunded, n_payments
FROM joined
ORDER BY order_id;
