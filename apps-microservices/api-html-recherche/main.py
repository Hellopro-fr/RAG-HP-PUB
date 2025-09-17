from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import httpx
import logging
import os
import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from middlewares.auth import AuthMiddleware

app = FastAPI()

# Config logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auth")

# Static & templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ORDRE IMPORTANT : SessionMiddleware EN PREMIER, puis AuthMiddleware
app.add_middleware(AuthMiddleware)
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("JWT_SECRET"))

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
        "login.html",
        {"request": request, "error": error, "username": username}
    )

@app.post("/login")
async def login_action(request: Request, username: str = Form(...), password: str = Form(...)):
    async with httpx.AsyncClient() as client:
        response = await client.post("https://www.hellopro.fr/partenaires_externes/info_produit/auth/auth.php", data={"login": username, "password": password})

    logger.info(f"XHR status={response.status_code}, raw={response.text}")

    try:
        res = response.json()
    except Exception as e:
        logger.error(f"Impossible de parser le JSON: {e}")
        request.session["error"] = "Erreur d'authentification"
        return RedirectResponse(url="/login", status_code=303)

    if response.status_code == 200 and res.get("success"):
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
    return templates.TemplateResponse(f"{item_id}.html", {"request": request})

# Route générique à la fin
@app.get("/{page}", response_class=HTMLResponse)
async def get_page(request: Request, page: str):
    user = request.session.get("user")
    return templates.TemplateResponse(f"{page}.html", {"request": request, "user": user})