from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mcp_gateway_url: str
    mcp_gateway_admin_token: str
    runner_admin_token: str
    runner_port: int = 8595
    runner_instance_port_start: int = 15000
    runner_instance_port_end: int = 15099
    runner_host: str = "0.0.0.0"
    secrets_dir: str = "/tmp/secrets"
    # Background reconcile loop: converge local instances to the gateway's
    # desired set on this cadence. Settles to the long interval after a
    # successful reconcile; retries on the short interval while the gateway is
    # unreachable (e.g. DNS not yet resolvable at boot). Self-heals empty state
    # and port drift without restarting healthy instances.
    runner_reconcile_interval_sec: int = 300
    runner_reconcile_retry_sec: int = 15

    class Config:
        env_prefix = ""  # env vars are already named in full (no prefix stripping)


settings = Settings()
