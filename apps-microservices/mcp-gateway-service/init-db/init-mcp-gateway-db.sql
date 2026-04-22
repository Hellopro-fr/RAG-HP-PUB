-- gateway_user already gets full privileges on MYSQL_DATABASE (gateway_db)
-- via Docker's MYSQL_USER / MYSQL_DATABASE env vars.
-- This script is kept as a safety net for custom setups.
GRANT ALL PRIVILEGES ON `gateway_db`.* TO 'gateway_user'@'%';
FLUSH PRIVILEGES;

-- -------------------------------------------------------------------
-- Templates catalog seed (Google MCP templates feature)
-- -------------------------------------------------------------------
-- Apply AFTER the gateway has booted once and GORM AutoMigrate has
-- created the `templates` table. Idempotent: re-running refreshes the
-- metadata columns without touching created_at or is_active.
--
--   docker compose exec mysql mysql -u root -p<pw> gateway_db \
--     < apps-microservices/mcp-gateway-service/init-db/init-mcp-gateway-db.sql
-- -------------------------------------------------------------------
INSERT INTO templates
  (slug, name, description, icon, stdio_command, stdio_args, default_env, required_extra_env, tool_prefix, tags, is_active, created_at, updated_at)
VALUES
  ('ga',
   'Google Analytics 4',
   'MCP wrapper exposing GA4 accounts, properties, and reports (read-only).',
   '',
   'analytics-mcp',
   '[]',
   '{"GOOGLE_APPLICATION_CREDENTIALS": "/tmp/secrets/{instance_id}/service_account_credentials.json"}',
   '[{"key":"GOOGLE_PROJECT_ID","label":"GCP project ID","required":true}]',
   'ga',
   '["analytics","google"]',
   1,
   NOW(3), NOW(3)),
  ('gsc',
   'Google Search Console',
   'MCP wrapper for Search Console search analytics and URL inspection.',
   '',
   'mcp-gsc',
   '[]',
   '{"GOOGLE_APPLICATION_CREDENTIALS": "/tmp/secrets/{instance_id}/service_account_credentials.json", "GSC_SKIP_OAUTH": "true"}',
   '[{"key":"GSC_SITE_URL","label":"Search Console property URL","required":true}]',
   'gsc',
   '["seo","google","search-console"]',
   1,
   NOW(3), NOW(3))
ON DUPLICATE KEY UPDATE
  name=VALUES(name),
  description=VALUES(description),
  stdio_command=VALUES(stdio_command),
  stdio_args=VALUES(stdio_args),
  default_env=VALUES(default_env),
  required_extra_env=VALUES(required_extra_env),
  tool_prefix=VALUES(tool_prefix),
  tags=VALUES(tags),
  updated_at=NOW(3);