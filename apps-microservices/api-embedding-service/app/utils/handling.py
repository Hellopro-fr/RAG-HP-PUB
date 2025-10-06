from fastapi import HTTPException


def handling(status, detail):
    raise HTTPException(
        status_code=status,
        detail=detail,
    )
