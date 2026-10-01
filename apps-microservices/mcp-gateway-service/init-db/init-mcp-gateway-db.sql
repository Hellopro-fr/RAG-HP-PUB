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
  (slug, name, description, icon, stdio_command, stdio_args, default_env, required_extra_env, tool_prefix, tags, kind, is_active, created_at, updated_at)
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
   'stdio',
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
   'stdio',
   1,
   NOW(3), NOW(3)),
  ('custom-http',
   'Serveur HTTP (import Sheets)',
   'Importe des serveurs MCP HTTP en masse depuis une feuille Google Sheets.',
   '',
   '',
   '[]',
   '{}',
   '[]',
   '',
   '["http","custom"]',
   'http_batch',
   1,
   NOW(3), NOW(3)),
  ('zoho-crm',
   'Zoho CRM (import Sheets)',
   'Importe les serveurs Zoho CRM par utilisateur depuis une feuille Google Sheets. Chaque ligne crée une entrée dans la table zoho_imports consommée par mcp-zoho-service pour le routage par utilisateur.',
   '/images/servers/zoho.svg',
   '',
   '[]',
   '{}',
   '[]',
   'zoho',
   '["zoho","crm","http"]',
   'http_batch',
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
  kind=VALUES(kind),
  updated_at=NOW(3);

-- Neo4j template (runner = mcp-template-neo4j-service). Separate statement
-- because only this row sets `runner`; the rows above get 'google' from the
-- column default. NEO4J_READ_ONLY defaults to "true" and is overridden per
-- instance from the "Lecture seule" checkbox. tool_prefix is empty on purpose:
-- each instance must choose its own (the static mcp-neo4j-service owns "neo4j"),
-- which handleCreateInstance enforces.
INSERT INTO templates
  (slug, name, description, icon, stdio_command, stdio_args, default_env, required_extra_env, tool_prefix, tags, kind, runner, is_active, created_at, updated_at)
VALUES
  ('neo4j',
   'Neo4j',
   'MCP wrapper exposing Cypher queries and schema inspection on one Neo4j database (read-only by default).',
   '/images/servers/neo4j.svg',
   'mcp-neo4j-cypher',
   '[]',
   '{"NEO4J_READ_ONLY": "true"}',
   '[{"key":"NEO4J_READ_ONLY","label":"Lecture seule","required":false}]',
   '',
   '["database","neo4j","graph"]',
   'stdio',
   'neo4j',
   1,
   NOW(3), NOW(3))
ON DUPLICATE KEY UPDATE
  name=VALUES(name),
  description=VALUES(description),
  icon=VALUES(icon),
  stdio_command=VALUES(stdio_command),
  stdio_args=VALUES(stdio_args),
  default_env=VALUES(default_env),
  required_extra_env=VALUES(required_extra_env),
  tool_prefix=VALUES(tool_prefix),
  tags=VALUES(tags),
  kind=VALUES(kind),
  runner=VALUES(runner),
  updated_at=NOW(3);
