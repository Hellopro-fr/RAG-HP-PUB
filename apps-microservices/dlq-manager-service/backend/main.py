import asyncio
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.es_client import get_es_client

app = FastAPI(title="DLQ Manager Service")

# IMPORTANT: The API router must be included BEFORE the static files mount.
# This ensures that API calls are routed correctly and not treated as file requests.
app.include_router(api_router, prefix="/api")

# Define the directory where the built React app's static files are located.
# The Dockerfile copies the entire 'build' folder into this 'static' directory.
static_dir = Path(__file__).parent / "static"

# Mount the static files at the root.
# This will catch all routes not handled by the API router above.
# Requests to `/static/js/...` will be correctly served from the nested `/app/static/static/js/...` directory.
# The `html=True` argument configures it to serve `index.html` for any path that
# doesn't match a file, which is perfect for Single-Page Applications like React.
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

async def background_rule_processor():
    """
    Periodically checks for active rules and applies them to auto-archive noise messages.
    """
    es_client = get_es_client()
    while True:
        try:
            # Wait 60 seconds before each cycle
            await asyncio.sleep(60)
            
            # Ensure the index exists and fetch only active rules
            await es_client.ensure_rules_index()
            active_rules = await es_client.get_rules(only_active=True)
            
            for rule in active_rules:
                # Apply the rule and get how many documents were updated
                updated_count = await es_client.apply_auto_archive_rule(rule)
                if updated_count > 0:
                    print(f"🤖 Rule '{rule.get('name')}' completed an auto-archive pass. Total processed this cycle: {updated_count} messages.")
                    
        except Exception as e:
            print(f"Background rule processor encountered an error: {e}")

@app.on_event("startup")
async def startup_event():
    # Start the periodic background rule processor safely without blocking the server
    asyncio.create_task(background_rule_processor())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8560)