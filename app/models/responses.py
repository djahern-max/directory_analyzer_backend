from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from app.models.base import BaseAPIModel, TimestampMixin
from app.models.directory import JobInfo, AnalysisStats
from app.models.document import RankedDocument, MainContractInfo, ClassificationSummary


class DirectoryAnalysisResponse(BaseAPIModel, TimestampMixin):
   """Complete directory analysis response"""
   
   success: bool = True
   message: str
   
   # Job information
   job_info: JobInfo
   
   # Main results
   main_contract: Optional[RankedDocument] = None
   ranked_documents: List[RankedDocument]
   
   # Analysis statistics
   stats: AnalysisStats
   
   # Classification summary
   classification_summary: ClassificationSummary
   
   # Failed files
   failed_files: List[str] = Field(
       default=[],
       description="List of files that couldn't be processed"
   )


class APIInfoResponse(BaseAPIModel):
   """API information response"""
   
   message: str
   version: str
   status: str
   endpoints: Dict[str, str]


class HealthCheckResponse(BaseAPIModel):
   """Health check response"""
   
   status: str
   timestamp: str
   service: str
   version: str
   environment: Optional[Dict[str, Any]] = None
   dependencies: Optional[Dict[str, Dict[str, str]]] = None


class ErrorDetailResponse(BaseAPIModel):
   """Detailed error response"""
   
   error: str
   message: str
   details: Dict[str, Any] = {}
   status_code: int
   timestamp: str = Field(default_factory=lambda: __import__('datetime').datetime.utcnow().isoformat())
   request_id: Optional[str] = None


class ValidationErrorResponse(BaseAPIModel):
   """Validation error response"""
   
   error: str = "ValidationError"
   message: str = "Request validation failed"
   details: List[Dict[str, Any]]
   status_code: int = 422
   timestamp: str = Field(default_factory=lambda: __import__('datetime').datetime.utcnow().isoformat())


class ProcessingStatusResponse(BaseAPIModel):
   """Processing status response for long-running operations"""
   
   status: str = Field(description="processing, completed, failed")
   message: str
   progress: Optional[float] = Field(None, description="Progress percentage (0-100)")
   current_step: Optional[str] = None
   estimated_completion: Optional[str] = None
   result: Optional[Dict[str, Any]] = None
