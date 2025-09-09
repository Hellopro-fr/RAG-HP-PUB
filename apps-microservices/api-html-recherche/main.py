from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# Your original route for dynamic pages
@app.get("/pages/{item_id}", response_class=HTMLResponse)
async def read_item(request: Request, item_id: str):
    context = {
        "request": request,
        "item_id": item_id,
        "item_name": "Awesome Gadget",
        "description": "A very useful tool for everyday tasks."
    }
    return templates.TemplateResponse(f"{item_id}.html", context)

# --- ADD THIS NEW ROUTE ---
# A specific route for the search page
@app.get("/{page}", response_class=HTMLResponse)
async def get_search_page(request: Request, page: str):
    context = {
        "request": request,
        # You can add any specific data for the search page here
    }
    # We hardcode the template name since this route is specific
    return templates.TemplateResponse(f"{page}.html", context)