from typing import List, Optional, Dict, Union
from pydantic import BaseModel, HttpUrl, Field, model_validator
from datetime import datetime
import uuid

class ImageInput(BaseModel):
    id: Optional[str] = Field(None, description="Unique identifier. If not provided, one will be generated.")
    url: Optional[HttpUrl] = Field(None, description="Publicly accessible URL of the image")
    content: Optional[str] = Field(None, description="Base64 encoded image content. Use this if the image is already downloaded.")

    @model_validator(mode='after')
    def check_source_exists(self) -> 'ImageInput':
        if not self.url and not self.content:
            raise ValueError('Either "url" or "content" (base64) must be provided.')
        # Auto-generate ID if missing
        if not self.id:
            if self.url:
                # Use a predictable hash of the URL if possible, or random
                self.id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(self.url)))
            else:
                self.id = str(uuid.uuid4())
        return self

class CompareRequest(BaseModel):
    job_id: Optional[str] = Field(None, description="Unique identifier for this comparison job. If missing, one is generated.")
    images: List[ImageInput] = Field(..., description="List of images to compare")
    threshold: Optional[float] = Field(90.0, description="Similarity percentage threshold (0-100)")
    sync: Optional[bool] = Field(False, description="If True, the request waits for completion and returns the result.")

class JobResponse(BaseModel):
    message: str
    job_id: str

class SimilarityPair(BaseModel):
    image_a_id: str
    image_a_url: Optional[HttpUrl] = Field(None, description="URL of image A (if available)")
    
    image_b_id: str
    image_b_url: Optional[HttpUrl] = Field(None, description="URL of image B (if available)")
    
    score: float = Field(..., description="Similarity score (0-100)")
    method_details: Optional[Dict[str, float]] = Field(None, description="Breakdown of scores")

class FailedImage(BaseModel):
    id: str
    url: Optional[HttpUrl] = None

class JobInput(BaseModel):
    id: str
    url: Optional[HttpUrl] = None
    source: str = Field("pending", description="Feature source: pending | cached | fresh | failed")

class ComparisonResult(BaseModel):
    job_id: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime]
    total_images: int
    matches_found: int
    similar_pairs: List[SimilarityPair]
    failed_images: List[FailedImage] = Field(default_factory=list)
    inputs: Optional[List[JobInput]] = None

class JobStatus(BaseModel):
    job_id: str
    status: str = Field(..., description="queued, processing, finished, failed")
    progress: float = Field(0.0, description="0 to 100")
    error: Optional[str] = None
    inputs: Optional[List[JobInput]] = None

class JobListResponse(BaseModel):
    total_jobs: int
    jobs: List[JobStatus]

class CapacityResponse(BaseModel):
    global_running_jobs: int
    local_running_jobs: int
    local_max_jobs: int
    is_local_full: bool