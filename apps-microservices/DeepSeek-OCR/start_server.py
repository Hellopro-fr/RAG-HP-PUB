#!/usr/bin/env python3
"""
DeepSeek-OCR vLLM Server
FastAPI wrapper with dynamic batching for concurrent requests
"""

import os
import sys
import asyncio
import io
import gc
import tempfile
from typing import List, Optional, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from queue import Queue
import threading
import time

import logging

import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Form
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import torch
import fitz  # PyMuPDF
from PIL import Image

LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("deepseek-ocr")

# Add current directory to Python path
sys.path.insert(0, '/app/DeepSeek-OCR-vllm')

# Set environment variables for vLLM compatibility
if torch.version.cuda == '11.8':
    os.environ["TRITON_PTXAS_PATH"] = "/usr/local/cuda-11.8/bin/ptxas"
os.environ['VLLM_USE_V1'] = '0'
if "CUDA_VISIBLE_DEVICES" not in os.environ:
    os.environ["CUDA_VISIBLE_DEVICES"] = '0'

# Import DeepSeek-OCR components
from config import INPUT_PATH, OUTPUT_PATH, PROMPT, CROP_MODE, MAX_CONCURRENCY, NUM_WORKERS
MODEL_PATH = os.environ.get('MODEL_PATH', 'deepseek-ai/DeepSeek-OCR')
from deepseek_ocr import DeepseekOCRForCausalLM
from process.image_process import DeepseekOCRProcessor
from vllm import LLM, SamplingParams
from vllm.model_executor.models.registry import ModelRegistry

# Register the custom model
ModelRegistry.register_model("DeepseekOCRForCausalLM", DeepseekOCRForCausalLM)

# Thread pool executor for CPU operations
cpu_executor = ThreadPoolExecutor(max_workers=NUM_WORKERS)

# Initialize FastAPI app
app = FastAPI(
    title="DeepSeek-OCR API",
    description="High-performance OCR service using DeepSeek-OCR with vLLM",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Upload safety limits
MAX_UPLOAD_SIZE_MB = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "100"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/tiff", "image/bmp", "image/webp"}
ALLOWED_PDF_TYPES = {"application/pdf"}
ALLOWED_TYPES = ALLOWED_IMAGE_TYPES | ALLOWED_PDF_TYPES
MAX_BATCH_FILES = int(os.environ.get("MAX_BATCH_FILES", "50"))

# Global variables for the model
llm = None
sampling_params = None
processor = None

class OCRResponse(BaseModel):
    success: bool
    result: Optional[str] = None
    error: Optional[str] = None
    page_count: Optional[int] = None

class BatchOCRResponse(BaseModel):
    success: bool
    results: List[OCRResponse]
    total_pages: int
    filename: str

@dataclass
class BatchRequest:
    """Represents a batch of images to process"""
    request_items: List[dict]
    future: asyncio.Future
    request_id: str

class DynamicBatchProcessor:
    """Handles dynamic batching of requests to vLLM"""
    
    def __init__(self, batch_timeout: float = 0.05, max_batch_size: int = None):
        self.batch_timeout = batch_timeout  # Wait 50ms to collect requests
        self.max_batch_size = max_batch_size or MAX_CONCURRENCY
        self.queue = asyncio.Queue()
        self.processing = False
        self.request_counter = 0
        
    async def add_request(self, request_items: List[dict]) -> List[str]:
        """Add a request and wait for results"""
        request_id = f"req_{self.request_counter}"
        self.request_counter += 1
        
        # Create a future for this request
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        
        batch_req = BatchRequest(
            request_items=request_items,
            future=future,
            request_id=request_id
        )
        
        logger.debug("Request %s added to queue with %d items", request_id, len(request_items))
        await self.queue.put(batch_req)
        
        # Wait for result
        result = await future
        return result
    
    async def process_loop(self):
        """Main processing loop - collects and batches requests"""
        logger.debug("Dynamic batch processor started")
        
        while True:
            try:
                # Collect requests for a batch
                batch_requests = []
                total_items = 0
                start_time = time.time()
                
                # Get first request (blocking)
                first_req = await self.queue.get()
                batch_requests.append(first_req)
                total_items += len(first_req.request_items)
                
                # Try to collect more requests within timeout
                while (time.time() - start_time) < self.batch_timeout:
                    if total_items >= self.max_batch_size:
                        break
                    
                    try:
                        req = await asyncio.wait_for(
                            self.queue.get(), 
                            timeout=self.batch_timeout - (time.time() - start_time)
                        )
                        
                        if total_items + len(req.request_items) <= self.max_batch_size:
                            batch_requests.append(req)
                            total_items += len(req.request_items)
                        else:
                            # Put it back if it doesn't fit
                            await self.queue.put(req)
                            break
                    except asyncio.TimeoutError:
                        break
                
                logger.debug("Processing batch: %d requests, %d total items", len(batch_requests), total_items)
                
                # Process the batch
                await self._process_batch(batch_requests)
                
            except Exception as e:
                logger.error("Batch processor error: %s", e, exc_info=True)
    
    async def _process_batch(self, batch_requests: List[BatchRequest]):
        """Process a collected batch"""
        # Flatten all request items
        all_items = []
        item_counts = []
        
        for req in batch_requests:
            item_counts.append(len(req.request_items))
            all_items.extend(req.request_items)
        
        logger.debug("Sending %d items to vLLM", len(all_items))
        
        try:
            # Run vLLM in executor
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,  # Use default executor
                self._vllm_generate,
                all_items
            )
            
            # Split results back to original requests
            start_idx = 0
            for i, req in enumerate(batch_requests):
                count = item_counts[i]
                req_results = results[start_idx:start_idx + count]
                start_idx += count
                
                # Set result
                if not req.future.done():
                    req.future.set_result(req_results)
                    logger.debug("Request %s completed with %d results", req.request_id, len(req_results))
            
        except Exception as e:
            logger.error("vLLM processing failed: %s", e, exc_info=True)
            # Propagate error to all futures
            for req in batch_requests:
                if not req.future.done():
                    req.future.set_exception(e)
    
    def _vllm_generate(self, request_items: List[dict]) -> List[str]:
        """Synchronous vLLM generation (runs in thread pool)"""
        logger.debug("vLLM generating %d items", len(request_items))
        
        outputs = llm.generate(request_items, sampling_params=sampling_params)
        
        results = []
        for output in outputs:
            result = output.outputs[0].text
            
            # Clean up result
            if '<｜end▁of▁sentence｜>' in result:
                result = result.replace('<｜end▁of▁sentence｜>', '')
            
            results.append(result)
        
        # Libération mémoire après inférence
        del outputs
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        logger.debug("vLLM generation complete: %d results", len(results))
        return results

# Global batch processor
batch_processor = None

def initialize_model():
    """Initialize the vLLM model"""
    global llm, sampling_params, processor
    
    if llm is None:
        logger.info("Initializing DeepSeek-OCR model...")
        
        # Initialize processor once
        processor = DeepseekOCRProcessor()
        
        # Initialize vLLM engine
        llm = LLM(
            model=MODEL_PATH,
            hf_overrides={"architectures": ["DeepseekOCRForCausalLM"]},
            block_size=256,
            enforce_eager=False,
            # NOTE: swap_space passé de 0 à 4 pour permettre au KV-cache de paginer en swap
            trust_remote_code=True,
            max_model_len=8192,
            swap_space=4,
            max_num_seqs=MAX_CONCURRENCY,
            tensor_parallel_size=1,
            gpu_memory_utilization=0.85,
            disable_mm_preprocessor_cache=True
        )
        
        # Set up sampling parameters
        from process.ngram_norepeat import NoRepeatNGramLogitsProcessor
        logits_processors = [NoRepeatNGramLogitsProcessor(ngram_size=20, window_size=50, whitelist_token_ids={128821, 128822})]
        
        sampling_params = SamplingParams(
            temperature=0.0,
            max_tokens=8192,
            logits_processors=logits_processors,
            skip_special_tokens=False,
            include_stop_str_in_output=True,
        )
        
        logger.info("Model initialization complete!")

def pdf_to_images_high_quality(pdf_data: bytes, dpi: int = 144) -> List[Image.Image]:
    """Convert PDF bytes to high-quality PIL Images"""
    images = []
    
    # Save PDF data to temporary file
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_pdf:
        temp_pdf.write(pdf_data)
        temp_pdf_path = temp_pdf.name
    
    try:
        pdf_document = fitz.open(temp_pdf_path)
        zoom = dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)
        
        for page_num in range(pdf_document.page_count):
            page = pdf_document[page_num]
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            
            # Convert to PIL Image
            img_data = pixmap.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            images.append(img)
            del pixmap, img_data  # Libérer immédiatement les données brutes
        
        pdf_document.close()
    finally:
        # Clean up temporary file
        os.unlink(temp_pdf_path)
    
    return images

def prepare_image_request(image: Image.Image, prompt: str) -> dict:
    """Prepare image request (CPU-bound operation)"""
    return {
        "prompt": prompt,
        "multi_modal_data": {
            "image": processor.tokenize_with_images(
                prompt=prompt,
                images=[image],
                bos=True,
                eos=True,
                cropping=CROP_MODE
            )
        }
    }

async def process_images(images: List[Image.Image], prompt: str = PROMPT) -> List[str]:
    """Process multiple images using dynamic batching"""
    logger.debug("process_images called with %d images", len(images))
    
    if not images:
        return []
    
    # Step 1: Prepare all requests in parallel (CPU-bound)
    loop = asyncio.get_event_loop()
    prepare_tasks = [
        loop.run_in_executor(cpu_executor, prepare_image_request, img, prompt)
        for img in images
    ]
    request_items = await asyncio.gather(*prepare_tasks)
    
    logger.debug("All %d requests prepared", len(request_items))
    
    # Step 2: Send to dynamic batch processor
    results = await batch_processor.add_request(request_items)
    
    logger.debug("Received %d results", len(results))
    return results

@app.on_event("startup")
async def startup_event():
    """Initialize the model on startup"""
    global batch_processor
    
    initialize_model()
    
    # Start dynamic batch processor
    batch_processor = DynamicBatchProcessor(
        batch_timeout=0.05,  # 50ms window to collect requests
        max_batch_size=MAX_CONCURRENCY
    )
    
    # Start background processing loop
    asyncio.create_task(batch_processor.process_loop())
    logger.info("Dynamic batch processor started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    cpu_executor.shutdown(wait=True)

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"message": "DeepSeek-OCR API is running", "status": "healthy"}

@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "model_loaded": llm is not None,
        "model_path": MODEL_PATH,
        "cuda_available": torch.cuda.is_available(),
        "cuda_device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
        "max_concurrency": MAX_CONCURRENCY,
        "num_workers": NUM_WORKERS,
        "queue_size": batch_processor.queue.qsize() if batch_processor else 0
    }

@app.post("/ocr/image", response_model=OCRResponse)
async def process_image_endpoint(file: UploadFile = File(...), prompt: Optional[str] = Form(None)):
    """Process a single image file with optional custom prompt"""
    try:
        logger.debug("Image endpoint called for file: %s", file.filename)

        # Read image data
        image_data = await file.read()

        if len(image_data) > MAX_UPLOAD_SIZE_BYTES:
            return OCRResponse(success=False, error=f"File too large: {len(image_data)} bytes (max {MAX_UPLOAD_SIZE_MB} MB)")

        if file.content_type and file.content_type not in ALLOWED_IMAGE_TYPES:
            return OCRResponse(success=False, error=f"Unsupported image type: {file.content_type}")
        
        # Convert to PIL Image
        image = Image.open(io.BytesIO(image_data)).convert('RGB')
        logger.debug("Image size: %s", image.size)
        
        # Use provided prompt or default
        use_prompt = prompt if prompt else PROMPT
        
        # Process with DeepSeek-OCR
        results = await process_images([image], use_prompt)
        result = results[0]
        
        # Fermeture explicite de l'image PIL
        image.close()
        del image
        
        logger.debug("OCR complete, output length: %d", len(result))
        
        return OCRResponse(
            success=True,
            result=result,
            page_count=1
        )
        
    except Exception as e:
        logger.error("Image endpoint failed: %s", e, exc_info=True)
        return OCRResponse(
            success=False,
            error=str(e)
        )

@app.post("/ocr/pdf", response_model=BatchOCRResponse)
async def process_pdf_endpoint(file: UploadFile = File(...), prompt: Optional[str] = Form(None)):
    """Process a PDF file with optional custom prompt"""
    try:
        logger.debug("PDF endpoint called for file: %s", file.filename)
        
        # Read PDF data
        pdf_data = await file.read()
        logger.debug("Read %d bytes of PDF data", len(pdf_data))

        if len(pdf_data) > MAX_UPLOAD_SIZE_BYTES:
            return BatchOCRResponse(success=False, results=[], total_pages=0, filename=file.filename,
                                    error=f"File too large: {len(pdf_data)} bytes (max {MAX_UPLOAD_SIZE_MB} MB)")

        if file.content_type and file.content_type not in ALLOWED_PDF_TYPES:
            return BatchOCRResponse(success=False, results=[], total_pages=0, filename=file.filename,
                                    error=f"Unsupported file type: {file.content_type}")
        
        # Convert PDF to images
        loop = asyncio.get_event_loop()
        images = await loop.run_in_executor(cpu_executor, pdf_to_images_high_quality, pdf_data, 144)
        logger.debug("Converted PDF to %d images", len(images))
        
        if not images:
            return BatchOCRResponse(
                success=False,
                results=[],
                total_pages=0,
                filename=file.filename
            )
        
        # Use provided prompt or default
        use_prompt = prompt if prompt else PROMPT
        
        # Process all pages
        results_text = await process_images(images, use_prompt)
        
        # Sauvegarder le nombre de pages avant la libération mémoire
        num_pages = len(images)
        
        # Fermeture explicite des images PIL
        for img in images:
            img.close()
        del images
        gc.collect()
        
        # Convert to response format
        results = [
            OCRResponse(
                success=True,
                result=result,
                page_count=i + 1
            )
            for i, result in enumerate(results_text)
        ]
        
        logger.debug("PDF processing complete: %d pages", len(results))
        return BatchOCRResponse(
            success=True,
            results=results,
            total_pages=num_pages,
            filename=file.filename
        )
        
    except Exception as e:
        logger.error("PDF endpoint failed: %s", e, exc_info=True)
        return BatchOCRResponse(
            success=False,
            results=[OCRResponse(success=False, error=str(e))],
            total_pages=0,
            filename=file.filename
        )

@app.post("/ocr/batch")
async def process_batch_endpoint(files: List[UploadFile] = File(...), prompt: Optional[str] = Form(None)):
    """Process multiple files (images and PDFs) with optional custom prompt"""
    if len(files) > MAX_BATCH_FILES:
        return {"success": False, "error": f"Too many files: {len(files)} (max {MAX_BATCH_FILES})"}

    tasks = []

    for file in files:
        if file.filename.lower().endswith('.pdf'):
            tasks.append(process_pdf_endpoint(file, prompt))
        else:
            tasks.append(process_image_endpoint(file, prompt))
    
    # Process all files concurrently
    results_data = await asyncio.gather(*tasks, return_exceptions=True)
    
    results = []
    for i, result in enumerate(results_data):
        if isinstance(result, Exception):
            results.append({
                "filename": files[i].filename,
                "result": OCRResponse(success=False, error=str(result))
            })
        else:
            results.append({
                "filename": files[i].filename,
                "result": result
            })
    
    return {"success": True, "results": results}

if __name__ == "__main__":
    logger.info("Starting DeepSeek-OCR API server...")
    uvicorn.run(
        "start_server:app",
        host="0.0.0.0",
        port=8501,
        reload=False,
        workers=1
    )