from typing import Generator
import logging
from pathlib import Path

from app.config import settings
from app.core.exceptions import (
   DirectoryNotFoundError, 
   InvalidDirectoryPathError,
   DirectoryEmptyError
)

logger = logging.getLogger("app.deps")


def validate_anthropic_api_key() -> str:
   """Validate that Anthropic API key is configured"""
   
   if not settings.anthropic_api_key:
       raise ValueError("ANTHROPIC_API_KEY environment variable is required")
   
   if settings.anthropic_api_key == "your_actual_anthropic_api_key_here":
       raise ValueError("Please set a valid ANTHROPIC_API_KEY in your .env file")
   
   return settings.anthropic_api_key


def validate_directory_path(directory_path: str) -> Path:
   """Validate and return a directory path"""
   
   if not directory_path or not directory_path.strip():
       raise InvalidDirectoryPathError("Directory path cannot be empty")
   
   path = Path(directory_path.strip())
   
   if not path.exists():
       raise DirectoryNotFoundError(f"Directory not found: {directory_path}")
   
   if not path.is_dir():
       raise InvalidDirectoryPathError(f"Path is not a directory: {directory_path}")
   
   return path


def validate_pdf_files_exist(directory_path: Path) -> list[Path]:
   """Validate that PDF files exist in the directory"""
   
   pdf_files = list(directory_path.glob("*.pdf"))
   
   if not pdf_files:
       raise DirectoryEmptyError(f"No PDF files found in directory: {directory_path}")
   
   return pdf_files


def get_job_info_from_path(directory_path: Path) -> tuple[str, str]:
   """Extract job name and number from directory path"""
   
   job_name = directory_path.name
   
   # Try to extract job number from the beginning of the directory name
   job_number = job_name[:4] if len(job_name) >= 4 else "UNKNOWN"
   
   # More sophisticated job number extraction could be added here
   # For example, regex patterns for different naming conventions
   
   return job_name, job_number


def calculate_estimates(file_count: int) -> tuple[float, float]:
   """Calculate cost and time estimates for analysis"""
   
   estimated_cost = file_count * settings.estimated_cost_per_document
   estimated_time = file_count * settings.estimated_time_per_document
   
   return estimated_cost, estimated_time


def get_file_info(pdf_file: Path) -> dict:
   """Get file information dictionary"""
   
   try:
       file_stats = pdf_file.stat()
       file_size_bytes = file_stats.st_size
       file_size_kb = file_size_bytes // 1024
       file_size_mb = round(file_size_bytes / (1024 * 1024), 2)
       
       return {
           "filename": pdf_file.name,
           "file_path": str(pdf_file),
           "file_size_bytes": file_size_bytes,
           "file_size_kb": file_size_kb,
           "file_size_mb": file_size_mb,
       }
   except Exception as e:
       logger.warning(f"Could not get file stats for {pdf_file}: {e}")
       return {
           "filename": pdf_file.name,
           "file_path": str(pdf_file),
           "file_size_bytes": 0,
           "file_size_kb": 0,
           "file_size_mb": 0.0,
       }


class APIKeyDependency:
   """Dependency class for API key validation"""
   
   def __init__(self):
       self._api_key = None
   
   def __call__(self) -> str:
       if self._api_key is None:
           self._api_key = validate_anthropic_api_key()
       return self._api_key


# Dependency instances
get_api_key = APIKeyDependency()
