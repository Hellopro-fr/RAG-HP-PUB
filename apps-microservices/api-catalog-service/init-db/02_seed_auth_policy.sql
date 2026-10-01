USE catalog_db;

-- Backfill PUBLIC (=1) on rows that pre-date the column.
UPDATE catalog_services SET auth_policy = 1 WHERE auth_policy = 0;

-- Restore the legacy /dlq/queues bypass for graphdlq-service.
UPDATE catalog_services
SET public_paths = JSON_ARRAY('/dlq/queues')
WHERE name = 'graphdlq-service'
  AND (public_paths IS NULL OR JSON_LENGTH(public_paths) = 0);
