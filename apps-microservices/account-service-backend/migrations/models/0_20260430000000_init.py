from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS `oauth_client` (
            `id` CHAR(36) NOT NULL PRIMARY KEY,
            `client_id` VARCHAR(64) NOT NULL UNIQUE,
            `client_secret_hash` VARCHAR(255) NOT NULL,
            `name` VARCHAR(128) NOT NULL,
            `redirect_uris` JSON NOT NULL,
            `post_logout_redirect_uris` JSON NOT NULL,
            `skip_consent` BOOL NOT NULL DEFAULT 1,
            `is_active` BOOL NOT NULL DEFAULT 1,
            `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            KEY `idx_oauth_clien_client__9e5a21` (`client_id`)
        ) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `authorization_code` (
            `code_hash` VARCHAR(64) NOT NULL PRIMARY KEY,
            `client_id` VARCHAR(64) NOT NULL,
            `sub` VARCHAR(128) NOT NULL,
            `code_challenge` VARCHAR(255) NOT NULL,
            `code_challenge_method` VARCHAR(10) NOT NULL,
            `redirect_uri` VARCHAR(512) NOT NULL,
            `issued_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `expires_at` DATETIME(6) NOT NULL,
            `consumed_at` DATETIME(6),
            `user_email` VARCHAR(255),
            `user_display_name` VARCHAR(255),
            KEY `idx_authorizati_client__0f678c` (`client_id`),
            KEY `idx_authorizati_expires_49a276` (`expires_at`)
        ) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `refresh_token` (
            `id` CHAR(36) NOT NULL PRIMARY KEY,
            `token_hash` VARCHAR(64) NOT NULL UNIQUE,
            `client_id` VARCHAR(64) NOT NULL,
            `sub` VARCHAR(128) NOT NULL,
            `user_email` VARCHAR(255),
            `user_display_name` VARCHAR(255),
            `issued_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `expires_at` DATETIME(6) NOT NULL,
            `revoked_at` DATETIME(6),
            `rotated_from_id` CHAR(36),
            `user_agent` VARCHAR(255),
            `ip` VARCHAR(45),
            KEY `idx_refresh_tok_token_h_317a3e` (`token_hash`),
            KEY `idx_refresh_tok_client__895f9b` (`client_id`),
            KEY `idx_refresh_tok_sub_d4bbd7` (`sub`),
            KEY `idx_refresh_tok_expires_3e54da` (`expires_at`)
        ) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `signing_key` (
            `kid` VARCHAR(64) NOT NULL PRIMARY KEY,
            `private_pem_encrypted` LONGTEXT NOT NULL,
            `public_pem` LONGTEXT NOT NULL,
            `is_active` BOOL NOT NULL DEFAULT 1,
            `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            `rotated_at` DATETIME(6)
        ) CHARACTER SET utf8mb4;
        CREATE TABLE IF NOT EXISTS `aerich` (
            `id` INT NOT NULL PRIMARY KEY AUTO_INCREMENT,
            `version` VARCHAR(255) NOT NULL,
            `app` VARCHAR(100) NOT NULL,
            `content` JSON NOT NULL
        ) CHARACTER SET utf8mb4;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS `oauth_client`;
        DROP TABLE IF EXISTS `authorization_code`;
        DROP TABLE IF EXISTS `refresh_token`;
        DROP TABLE IF EXISTS `signing_key`;
        DROP TABLE IF EXISTS `aerich`;"""
