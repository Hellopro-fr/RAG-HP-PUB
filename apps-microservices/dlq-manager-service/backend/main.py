import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router

app = FastAPI(title="DLQ Manager Service")

# IMPORTANT: The API router must be included BEFORE the static files mount.
# This ensures that API calls are routed correctly and not treated as file requests.
app.include_router(api_router, prefix="/api")

# Define the directory where the built React app's static files are located.
# The Dockerfile copies the entire 'build' folder into this 'static' directory.
static_dir = os.path.join(os.path.dirname(__file__), "static")

# Mount the static files at the root.
# This will catch all routes not handled by the API router above.
# Requests to `/static/js/...` will be correctly served from the nested `/app/static/static/js/...` directory.
# The `html=True` argument configures it to serve `index.html` for any path that
# doesn't match a file, which is perfect for Single-Page Applications like React.
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8560)