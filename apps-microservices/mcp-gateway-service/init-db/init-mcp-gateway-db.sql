-- gateway_user already gets full privileges on MYSQL_DATABASE (gateway_db)
-- via Docker's MYSQL_USER / MYSQL_DATABASE env vars.
-- This script is kept as a safety net for custom setups.
GRANT ALL PRIVILEGES ON `gateway_db`.* TO 'gateway_user'@'%';
FLUSH PRIVILEGES;