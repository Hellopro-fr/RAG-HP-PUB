import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from schemas.schemas import RequestModel, ResponseModel
from core.preprocessor import preprocess_html
from core.extractor import run_all_extractors

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Extractor Testing Service",
    description="A service to test and compare various web content extraction libraries.",
)

# Allow all origins for the testing environment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/test-extractors", response_model=ResponseModel)
async def test_extractors_endpoint(request: RequestModel):
    """
    Accepts raw HTML or a JSON data structure, preprocesses the HTML,
    runs it through a suite of extraction libraries, and returns the results.
    """
    logger.info("Received request for extraction comparison.")
    html_content = ""

    if request.raw_html:
        html_content = request.raw_html
    elif request.json_data and request.json_data.data and request.json_data.data.text:
        html_content = request.json_data.data.text
    
    if not html_content:
        logger.error("Request received with no HTML content.")
        raise HTTPException(status_code=400, detail="No HTML content provided in 'raw_html' or 'json_data.data.text'.")

    logger.info(f"Processing HTML content of length {len(html_content)}.")

    try:
        # 1. Preprocess the HTML
        preprocessed_html = preprocess_html(html_content)
        logger.info(f"HTML preprocessed. New length: {len(preprocessed_html)}.")

        # 2. Run all extractors
        results = await run_all_extractors(preprocessed_html)
        logger.info("All extractors finished processing.")

        return results

    except Exception as e:
        logger.exception("An unexpected error occurred during processing.")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    return {"status": "ok"}