from pydantic import BaseModel


class SpawnRequest(BaseModel):
    instance_id: str
    template_slug: str
    stdio_command: str
    stdio_args: list[str] = []
    env: dict[str, str] = {}
    credentials_json: str
    credentials_hash: str


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
