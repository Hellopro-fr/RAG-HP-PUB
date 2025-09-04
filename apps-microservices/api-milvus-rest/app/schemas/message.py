
from typing import Annotated, Any, Dict, List, Optional
from pydantic import ConfigDict, BaseModel, Field


class ErrorResponse(BaseModel):
    code: str
    status: str


class MessageResponse(ErrorResponse):
    message: Annotated[str, Field(title="Le contenu du message")]


class Status(BaseModel):
    message: Annotated[str, Field(title="Le contenu du message")]
    model_config = ConfigDict(exclude=True)


class PostResponse(MessageResponse):
    details: Dict[str, Any]


class GetResponse(ErrorResponse):
    data: Annotated[List[Any] | Any, Any]
    info: Dict[str, Any]


class GetUniqueResponse(ErrorResponse):
    data: Any = None


class GetEmptyResponse(ErrorResponse):
    info: Dict[str, Any]


class IntegrityErrorResponse(Exception):
    def __init__(self, message):
        self.message = message
