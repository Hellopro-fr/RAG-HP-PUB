from fastapi import FastAPI

from app.routers import clean

app = FastAPI(
    title="Content Extractor API",
    description="HTML cleaning and header/footer extraction API",
    version="1.0.0",
)

app.include_router(clean.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
