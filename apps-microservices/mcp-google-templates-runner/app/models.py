from pydantic import BaseModel, Field


class SpawnRequest(BaseModel):
    instance_id: str = Field(..., min_length=1, max_length=128)
    template_slug: str = Field(..., min_length=1, max_length=64)
    stdio_command: str = Field(..., min_length=1, max_length=256)
    stdio_args: list[str] = Field(default_factory=list, max_length=64)
    env: dict[str, str] = Field(default_factory=dict, max_length=64)
    credentials_json: str = Field(..., max_length=65536)
    credentials_hash: str = Field(..., min_length=1, max_length=128)


class SpawnResponse(BaseModel):
    port: int
    pid: int


class InstanceStatus(BaseModel):
    id: str
    port: int
    pid: int
    status: str
    uptime_s: int
    last_error: str | None = None
    stderr_tail: str | None = None


class InstanceListResponse(BaseModel):
    instances: list[InstanceStatus]


class ReconcileRequest(BaseModel):
    desired_instances: list[SpawnRequest]
