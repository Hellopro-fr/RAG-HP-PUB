from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # env vars are already named in full (no prefix stripping)
    model_config = SettingsConfigDict(env_prefix="")

    mcp_gateway_url: str
    mcp_gateway_admin_token: str
    runner_admin_token: str
    # 8595 = mcp-google-templates-runner, 8596 = mcp-zoho-service,
    # 8597 = mcp-hellodata-service: 8598 is the next free MCP port.
    runner_port: int = 8598
    # The Google runner owns 15000-15099; this runner takes the next block.
    runner_instance_port_start: int = 15100
    runner_instance_port_end: int = 15199
    runner_host: str = "0.0.0.0"
    runner_reconcile_interval_sec: int = 300
    runner_reconcile_retry_sec: int = 15
    # Connectivity check run before an admin-requested spawn (create/rotate).
    neo4j_precheck_timeout_sec: float = 5.0


settings = Settings()
