from typing import List, Optional, Dict
from pydantic import BaseModel, HttpUrl, Field
from datetime import datetime

class ImageInput(BaseModel):
    id: str = Field(..., description="Unique identifier for the image")
    url: HttpUrl = Field(..., description="Publicly accessible URL of the image")

class CompareRequest(BaseModel):
    job_id: str = Field(..., description="Unique identifier for this comparison job")
    images: List[ImageInput] = Field(..., description="List of images to compare")
    threshold: Optional[float] = Field(90.0, description="Similarity percentage threshold (0-100)")

class JobResponse(BaseModel):
    message: str
    job_id: str

class SimilarityPair(BaseModel):
    image_a_id: str
    image_b_id: str
    score: float = Field(..., description="Similarity score (0-100)")
    method_details: Optional[Dict[str, float]] = Field(None, description="Breakdown of scores")

class ComparisonResult(BaseModel):
    job_id: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime]
    total_images: int
    matches_found: int
    similar_pairs: List[SimilarityPair]
    failed_images: List[str] = Field(default_factory=list)

class JobStatus(BaseModel):
    job_id: str
    status: str = Field(..., description="queued, processing, finished, failed")
    progress: float = Field(0.0, description="0 to 100")
    error: Optional[str] = None