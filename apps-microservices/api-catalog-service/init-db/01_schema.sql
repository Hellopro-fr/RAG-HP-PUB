CREATE DATABASE IF NOT EXISTS catalog_db;
USE catalog_db;

CREATE TABLE IF NOT EXISTS catalog_services (
  id              CHAR(36)     PRIMARY KEY,
  name            VARCHAR(128) NOT NULL,
  base_url        VARCHAR(512) NOT NULL,
  protocols       JSON         NOT NULL,
  source          ENUM('env','manual','scan') NOT NULL,
  status          ENUM('active','deprecated','down') NOT NULL DEFAULT 'active',
  description     TEXT,
  owner           VARCHAR(128),
  tags            JSON,
  api_info_url    VARCHAR(512),
  grpc_address    VARCHAR(512),
  last_scanned_at DATETIME,
  last_scan_ok    TINYINT(1),
  last_scan_error TEXT,
  created_by      VARCHAR(255),
  auth_policy     TINYINT      NOT NULL DEFAULT 1,
  public_paths    JSON         NULL,
  created_at      DATETIME     NOT NULL,
  updated_at      DATETIME     NOT NULL,
  UNIQUE KEY uniq_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS catalog_endpoints (
  id           CHAR(36) PRIMARY KEY,
  service_id   CHAR(36) NOT NULL,
  protocol     ENUM('rest','ws','grpc') NOT NULL,
  method       VARCHAR(16),
  path         VARCHAR(512) NOT NULL,
  summary      VARCHAR(512),
  operation_id VARCHAR(255),
  tags         JSON,
  deprecated   TINYINT(1) NOT NULL DEFAULT 0,
  auth_policy  TINYINT NULL,
  CONSTRAINT fk_endpoint_service FOREIGN KEY (service_id) REFERENCES catalog_services(id) ON DELETE CASCADE,
  KEY idx_endpoint_service (service_id),
  KEY idx_endpoint_proto   (service_id, protocol),
  KEY idx_endpoint_policy  (service_id, auth_policy)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
