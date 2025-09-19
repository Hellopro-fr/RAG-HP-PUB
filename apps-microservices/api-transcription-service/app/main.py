# app/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api import endpoints

# Create FastAPI app instance
app = FastAPI(
    title="Real-Time Transcription API",
    description="A streaming audio transcription service using FastAPI and Google Speech-to-Text.",
    version="1.0.0",
)

# Include the WebSocket router
app.include_router(endpoints.router)

# Mount the 'static' directory to serve frontend files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", include_in_schema=False)
async def read_index():
    """Serves the main HTML page for testing the WebSocket."""
    return FileResponse('static/index.html')
