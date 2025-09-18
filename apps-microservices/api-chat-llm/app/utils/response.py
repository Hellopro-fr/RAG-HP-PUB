from typing import Any, Dict
from datetime import datetime
from app.schemas.message import MessageResponse, PostResponse
from fastapi import status


def success_response(code: str, message: str, uid: str, status: str):
    details = {
        "date": datetime.now().strftime("%Y-%m-%d-%H-%M-%S"),
        "uid": uid
    }
    res = PostResponse(
        code=code,
        details=details,
        message=message,
        status=status
    )

    return res


def error_response(code: str, message: str, status: str):
    res = MessageResponse(
        code=code,
        status=status,
        message=message
    )

    return res
