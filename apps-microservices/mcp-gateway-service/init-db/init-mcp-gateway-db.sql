-- Crée la base de données mcp_gateway si elle n'existe pas
CREATE DATABASE IF NOT EXISTS mcp_gateway;

-- Donne les droits à l'utilisateur gateway
GRANT ALL PRIVILEGES ON mcp_gateway.* TO 'gateway_user'@'%';
FLUSH PRIVILEGES;
