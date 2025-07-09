from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any
from pathlib import Path

from app.models.base import BaseAPIModel


class DirectoryAnalysisRequest(BaseAPIModel):
   """Request model for directory analysis"""
   
   directory_path: str = Field(
       ...,
       description="Path to the directory containing PDF files",
       example="/path/to/construction/documents"
   )
   
   @validator('directory_path')
   def validate_directory_path(cls, v):
       if not v or not v.strip():
           raise ValueError("Directory path cannot be empty")
       return v.strip()


class FileInfo(BaseAPIModel):
   """Information about a single file"""
   
   filename: str
   file_path: str
   file_size_bytes: int
   file_size_kb: int
   file_size_mb: float


class DirectoryListResponse(BaseAPIModel):
   """Response model for directory file listing"""
   
   success: bool = True
   directory_path: str
   job_name: str
   job_number: str
   total_pdf_files: int
   estimated_scan_cost: float = Field(
       description="Estimated cost in USD for analyzing all files"
   )
   estimated_scan_time_seconds: float = Field(
       description="Estimated time in seconds for analyzing all files"
   )
   files: List[FileInfo]


class JobInfo(BaseAPIModel):
   """Job information extracted from directory"""
   
   job_name: str = Field(description="Job name extracted from directory name")
   job_number: str = Field(description="Job number extracted from directory name")
   directory_path: str = Field(description="Full path to the directory")


class AnalysisStats(BaseAPIModel):
   """Statistics from directory analysis"""
   
   total_documents: int
   successful_scans: int
   failed_scans: int
   success_rate: float = Field(description="Success rate as percentage")
   critical_documents: int
   primary_contracts: int
   executed_documents: int
   estimated_scan_cost: float
   scan_time_seconds: float


class QuickIdentificationResponse(BaseAPIModel):
   """Response for quick main contract identification"""
   
   success: bool
   job_name: str
   job_number: str
   directory_path: str
   main_contract: Dict[str, Any] = None
   total_documents: int
   scan_time_seconds: float
   confidence: str = Field(description="Confidence level: HIGH, MEDIUM, LOW")
   error: str = None
   suggestion: str = None
