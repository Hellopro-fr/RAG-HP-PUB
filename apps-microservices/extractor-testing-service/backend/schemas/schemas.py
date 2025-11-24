from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class RequestData(BaseModel):
    text: Optional[str] = None
    url: Optional[str] = None


class FullRequestData(BaseModel):
    data: Optional[RequestData] = None


class RequestModel(BaseModel):
    raw_html: Optional[str] = Field(
        None, description="Raw HTML content as a string.")
    json_data: Optional[FullRequestData] = Field(
        None, description="The full JSON object structure.")


class ResultItem(BaseModel):
    content: str
    char_count: int
    error: Optional[str] = None


ResponseModel = Dict[str, ResultItem]
