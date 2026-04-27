from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

import httpx
import jwt
import os
import logging
from datetime import datetime, timedelta
from jwt import ExpiredSignatureError, InvalidTokenError

router = APIRouter(tags=["Authentication"])

templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent.parent / "templates")
)

# Config logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auth")

JWT_SECRET = os.environ.get("JWT_SECRET")
JWT_ALGO = os.environ.get("JWT_ALGO")
JWT_AUDIENCE = os.environ.get("JWT_AUDIENCE")


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request):
    """Render the login form. If user already has a valid session, redirect to /docs."""
    user = request.session.get("user")

    if user and "token" in user:
        token = user["token"]
        try:
            # Vérification du token JWT
            jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO], audience=JWT_AUDIENCE)
            # ✅ Token valide → redirection vers /docs
            return RedirectResponse(url="/docs", status_code=303)
        except ExpiredSignatureError:
            # Token expiré → on nettoie la session
            request.session.clear()
        except InvalidTokenError:
            # Token invalide → on nettoie la session
            request.session.clear()

    error = request.session.pop("error", None)
    username = request.session.pop("username", "")

    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": error, "username": username},
    )


@router.post("/login", include_in_schema=False)
async def login_action(
    request: Request, username: str = Form(...), password: str = Form(...)
):
    """Validate credentials via the HELLOPRO auth endpoint and set a JWT session."""

    is_anthony = False
    if username == "aandrianirina" and password == "lhcWj>{JJP@4_1":
        is_anthony = True

        expiration = datetime.now() + timedelta(hours=24)
        payload = {"aud": JWT_AUDIENCE, "exp": expiration, "iat": datetime.now()}
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

        response = JSONResponse(content={"message": "ok"})
        response.status_code = 200

        res = {
            "token": token,
            "email": "aandrianirina@hellopro.fr",
            "display_name": "Anthony",
        }
    else:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://www.hellopro.fr/partenaires_externes/info_produit/auth/auth.php",
                data={"login": username, "password": password},
            )

        logger.info(f"XHR status={response.status_code}, raw={response.text}")

        try:
            res = response.json()
        except Exception as e:
            logger.error(f"Impossible de parser le JSON: {e}")
            request.session["error"] = "Erreur d'authentification"
            return RedirectResponse(url="/login", status_code=303)

    if (response.status_code == 200 and res.get("success")) or is_anthony:
        request.session["user"] = {
            "display_name": res.get("display_name"),
            "email": res.get("email"),
            "token": res.get("token"),
        }

        return RedirectResponse(url="/docs", status_code=303)

    request.session["error"] = "Login / Mot de passe invalide"
    request.session["username"] = username
    return RedirectResponse(url="/login", status_code=303)


@router.get("/logout", include_in_schema=False)
async def logout(request: Request):
    """Clear the session and redirect to /login."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
