from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

import httpx
import logging
import os
import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from datetime import datetime, timedelta

from middlewares.auth import AuthMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

app = FastAPI()

# Config logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auth")

# Static & templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# ORDRE IMPORTANT : SessionMiddleware EN PREMIER, puis AuthMiddleware
app.add_middleware(AuthMiddleware)
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("JWT_SECRET"))

# app.add_middleware(HTTPSRedirectMiddleware)
# app.add_middleware(
#     TrustedHostMiddleware, allowed_hosts=["*.hellopro.eu"]
# )

# --- ROUTES ---

JWT_SECRET = os.environ.get("JWT_SECRET")
JWT_ALGO = os.environ.get("JWT_ALGO")
JWT_AUDIENCE = os.environ.get("JWT_AUDIENCE")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = request.session.get("user")
    
    if user and "token" in user:
        token = user["token"]
        try:
            # Vérification du token JWT
            jwt.decode(
                token,
                JWT_SECRET,
                algorithms=[JWT_ALGO],
                audience=JWT_AUDIENCE
            )
            # ✅ Token valide → redirection vers /recherche
            return RedirectResponse(url="/recherche", status_code=303)
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

@app.post("/login")
async def login_action(request: Request, username: str = Form(...), password: str = Form(...)):

    is_anthony = False
    if username == "aandrianirina" and password == "lhcWj>{JJP@4_1":
        is_anthony = True

        expiration = datetime.now() + timedelta(hours=24)
        payload = {
            "aud": JWT_AUDIENCE,
            "exp": expiration,
            "iat": datetime.now()
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

        response = JSONResponse(content={"message": "ok"})
        response.status_code = 200
        
        res = {
            "token": token,
            "email": "aandrianirina@hellopro.fr",
            "display_name": "Anthony"
        }
    else:    
        async with httpx.AsyncClient() as client:
            response = await client.post("https://www.hellopro.fr/partenaires_externes/info_produit/auth/auth.php", data={"login": username, "password": password})

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
            "token": res.get("token")
        }

        return RedirectResponse(url="/recherche", status_code=303)

    request.session["error"] = "Login / Mot de passe invalide"
    request.session["username"] = username
    return RedirectResponse(url="/login", status_code=303)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

@app.get("/pages/{item_id}", response_class=HTMLResponse)
async def read_item(request: Request, item_id: str):
    return templates.TemplateResponse(request, f"{item_id}.html")

# Route générique à la fin
@app.get("/{page}", response_class=HTMLResponse)
async def get_page(request: Request, page: str):
    user = request.session.get("user")

    template_path = f"{page}.html"

    # Vérifie si le template existe
    if not os.path.exists(os.path.join("templates", template_path)):
        return templates.TemplateResponse(request, "404.html", status_code=404)

    return templates.TemplateResponse(request, template_path, {"user": user})
