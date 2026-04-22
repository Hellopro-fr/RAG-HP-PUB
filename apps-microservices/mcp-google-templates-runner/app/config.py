from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mcp_gateway_url: str
    mcp_gateway_admin_token: str
    runner_admin_token: str
    runner_port: int = 8594
    runner_instance_port_start: int = 15000
    runner_instance_port_end: int = 15099
    runner_host: str = "0.0.0.0"
    secrets_dir: str = "/tmp/secrets"

    class Config:
        env_prefix = ""  # env vars are already named in full (no prefix stripping)


settings = Settings()
