#!/usr/bin/env python3
"""
DeepSeek-OCR vLLM Server
Fully asynchronous FastAPI wrapper for DeepSeek-OCR with vLLM backend
to handle multiple concurrent users without blocking.
"""

import os
import sys
import asyncio
import io
import tempfile
from typing import List, Optional
from pathlib import Path

import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import torch
import fitz  # PyMuPDF
from PIL import Image
from tqdm import tqdm

from config import INPUT_PATH, OUTPUT_PATH, PROMPT, CROP_MODE, MAX_CONCURRENCY, NUM_WORKERS , MODEL_PATH

# Add current directory to Python path
sys.path.insert(0, '/app/DeepSeek-OCR-vllm')

# Set environment variables for vLLM compatibility
if torch.version.cuda == '11.8':
    os.environ["TRITON_PTXAS_PATH"] = "/usr/local/cuda-11.8/bin/ptxas"
os.environ['VLLM_USE_V1'] = '0'
os.environ["CUDA_VISIBLE_DEVICES"] = '0'

from deepseek_ocr import DeepseekOCRForCausalLM
from process.image_process import DeepseekOCRProcessor
from vllm import LLM, SamplingParams
from vllm.model_executor.models.registry import ModelRegistry

# Register the custom model
ModelRegistry.register_model("DeepseekOCRForCausalLM", DeepseekOCRForCausalLM)

# Initialize FastAPI app
app = FastAPI(
    title="DeepSeek-OCR API (Async)",
    description="High-performance asynchronous OCR service using DeepSeek-OCR with vLLM",
    version="1.1.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables for the model
llm = None
sampling_params = None

class OCRResponse(BaseModel):
    success: bool
    result: Optional[str] = None
    error: Optional[str] = None
    page_num: Optional[int] = None

class BatchOCRResponse(BaseModel):
    success: bool
    results: List[OCRResponse]
    total_pages: int
    filename: str
    error: Optional[str] = None

def initialize_model():
    """Initialize the vLLM model (this remains synchronous as it runs once at startup)"""
    global llm, sampling_params
    
    if llm is None:
        print("Initializing DeepSeek-OCR model...")
        
        llm = LLM(
            model=MODEL_PATH,
            hf_overrides={"architectures": ["DeepseekOCRForCausalLM"]},
            block_size=16,
            enforce_eager=False,
            trust_remote_code=True,
            max_model_len=4096,
            swap_space=0,
            max_num_seqs=MAX_CONCURRENCY,
            tensor_parallel_size=1,
            gpu_memory_utilization=0.85,
            disable_mm_preprocessor_cache=True
        )
        
        from process.ngram_norepeat import NoRepeatNGramLogitsProcessor
        logits_processors = [NoRepeatNGramLogitsProcessor(ngram_size=20, window_size=50, whitelist_token_ids={128821, 128822})]
        
        sampling_params = SamplingParams(
            temperature=0.0,
            max_tokens=4096,
            logits_processors=logits_processors,
            skip_special_tokens=False,
            include_stop_str_in_output=True,
        )
        
        print("Model initialization complete!")

# --- Asynchronous Helper Functions ---

async def pdf_to_images_async(pdf_data: bytes, dpi: int = 144) -> List[Image.Image]:
    """Asynchronously convert PDF bytes to high-quality PIL Images."""
    def blocking_pdf_conversion():
        images = []
        try:
            pdf_document = fitz.open(stream=pdf_data, filetype="pdf")
            zoom = dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)
            
            for page in pdf_document:
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                img_data = pixmap.tobytes("png")
                img = Image.open(io.BytesIO(img_data))
                images.append(img)
            
            pdf_document.close()
        except Exception as e:
            print(f"[ERROR] Failed to convert PDF: {e}")
            raise
        return images

    # Run the blocking PyMuPDF code in a separate thread
    return await asyncio.to_thread(blocking_pdf_conversion)

async def process_single_image_async(image: Image.Image, prompt: str = PROMPT) -> str:
    """Asynchronously process a single image with DeepSeek-OCR."""
    def blocking_ocr_inference():
        # This part is CPU-bound (tokenization) and GPU-bound (inference)
        request_item = {
            "prompt": prompt,
            "multi_modal_data": {
                "image": DeepseekOCRProcessor().tokenize_with_images(
                    prompt=prompt,
                    images=[image],
                    bos=True,
                    eos=True,
                    cropping=CROP_MODE
                )
            }
        }
        
        # The llm.generate call is synchronous and the main blocking part
        outputs = llm.generate([request_item], sampling_params=sampling_params)
        result = outputs[0].outputs[0].text
        
        if '<｜end of sentence｜>' in result:
            result = result.replace('<｜end of sentence｜>', '')
        
        return result

    # Run the blocking inference code in a separate thread
    return await asyncio.to_thread(blocking_ocr_inference)

# --- FastAPI Events ---

@app.on_event("startup")
async def startup_event():
    """Initialize the model on startup"""
    initialize_model()

# --- API Endpoints ---

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "DeepSeek-OCR API (Async) is running", "status": "healthy"}

@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "model_loaded": llm is not None,
        "model_path": MODEL_PATH,
        "cuda_available": torch.cuda.is_available(),
        "cuda_device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0
    }

@app.post("/ocr/image", response_model=OCRResponse)
async def process_image_endpoint(file: UploadFile = File(...), prompt: Optional[str] = Form(None)):
    """Asynchronously process a single image file with optional custom prompt."""
    try:
        image_data = await file.read()
        
        # Run blocking PIL code in a thread
        image = await asyncio.to_thread(Image.open(io.BytesIO(image_data)).convert, 'RGB')
        
        use_prompt = prompt if prompt else PROMPT
        
        result = await process_single_image_async(image, use_prompt)
        
        return OCRResponse(
            success=True,
            result=result,
            page_num=1
        )
        
    except Exception as e:
        print(f"[ERROR] Image endpoint failed: {str(e)}")
        # Using HTTPException for better error handling on the client side
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ocr/pdf", response_model=BatchOCRResponse)
async def process_pdf_endpoint(file: UploadFile = File(...), prompt: Optional[str] = Form(None)):
    """Asynchronously process a PDF file, with concurrent page processing."""
    try:
        pdf_data = await file.read()
        
        images = await pdf_to_images_async(pdf_data, dpi=144)
        
        if not images:
            return BatchOCRResponse(
                success=False,
                results=[],
                total_pages=0,
                filename=file.filename,
                error="No images could be extracted from the PDF."
            )
        
        use_prompt = prompt if prompt else PROMPT
        
        # Create a list of concurrent OCR tasks for all pages
        tasks = [process_single_image_async(image, use_prompt) for image in images]
        
        # Run all page processing tasks in parallel
        ocr_texts = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Format the results
        results = []
        for i, res in enumerate(ocr_texts):
            page_num = i + 1
            if isinstance(res, Exception):
                results.append(OCRResponse(
                    success=False,
                    error=f"Page {page_num} error: {str(res)}",
                    page_num=page_num
                ))
            else:
                results.append(OCRResponse(
                    success=True,
                    result=res,
                    page_num=page_num
                ))
        
        return BatchOCRResponse(
            success=True,
            results=results,
            total_pages=len(images),
            filename=file.filename
        )
        
    except Exception as e:
        print(f"[ERROR] PDF endpoint failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ocr/batch")
async def process_batch_endpoint(files: List[UploadFile] = File(...), prompt: Optional[str] = Form(None)):
    """Asynchronously process multiple files (images and PDFs) with optional custom prompt"""
    
    async def process_file(file: UploadFile, custom_prompt: Optional[str]):
        """Helper to process a single file within the batch."""
        if file.filename.lower().endswith('.pdf'):
            response_model = await process_pdf_endpoint(file, custom_prompt)
        else:
            # For a single image, we wrap the result in a list to match the PDF response structure
            ocr_response = await process_image_endpoint(file, custom_prompt)
            response_model = BatchOCRResponse(
                success=ocr_response.success,
                results=[ocr_response],
                total_pages=1,
                filename=file.filename,
                error=ocr_response.error
            )
        return response_model

    # Create and run concurrent processing tasks for each uploaded file
    tasks = [process_file(file, prompt) for file in files]
    batch_results = await asyncio.gather(*tasks)

    return {"success": True, "results": batch_results}

if __name__ == "__main__":
    print("Starting DeepSeek-OCR API server (Async)...")
    uvicorn.run(
        "start_server:app",  # <-- IMPORTANT: Replace 'your_filename' with the actual name of your Python file
        host="0.0.0.0",
        port=8501,
        reload=False,
        workers=1 # Uvicorn workers are separate processes. For a single GPU model, you typically use 1 worker. Concurrency is handled by asyncio.
    )