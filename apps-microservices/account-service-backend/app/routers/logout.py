from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/logout", tags=["oauth"], response_class=HTMLResponse)
async def logout_page(post_logout_redirect_uri: str | None = Query(None)):
    target = post_logout_redirect_uri or "/"
    return HTMLResponse(
        f"""<!doctype html>
<html><body>
<p>You are now logged out.</p>
<p><a href="{target}">Continue</a></p>
<script>setTimeout(() => location.assign("{target}"), 1500);</script>
</body></html>"""
    )
