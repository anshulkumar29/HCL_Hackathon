-- KPI 8 extra: payments that were quarantined in cleaning because their order does not exist
SELECT record_key                              AS payment_id,
       reason,
       json_extract(record_json, '$.order_id') AS order_id_in_payment,
       json_extract(record_json, '$.amount')   AS raw_amount,
       json_extract(record_json, '$.payment_status') AS raw_status,
       record_json
FROM rejects
WHERE "table" = 'payments' AND reason = 'ORPHAN_ORDER'
ORDER BY record_key;
