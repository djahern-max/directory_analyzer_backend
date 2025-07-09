import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple
import os

from app.config import settings
from app.core.exceptions import (
   DirectoryNotFoundError,
   DirectoryEmptyError,
   InvalidDirectoryPathError
)

logger = logging.getLogger("app.services.directory_scanner")


class DirectoryScanner:
   """Service for scanning directories and managing file operations"""
   
   def __init__(self):
       self.logger = logger
       self.allowed_extensions = [ext.lower() for ext in settings.allowed_file_extensions]
   
   def scan_directory(self, directory_path: str) -> Dict[str, Any]:
       """
       Scan a directory and return comprehensive information about PDF files
       
       Args:
           directory_path: Path to the directory to scan
           
       Returns:
           Dictionary containing directory information and file list
           
       Raises:
           DirectoryNotFoundError: If directory doesn't exist
           InvalidDirectoryPathError: If path is not a directory
           DirectoryEmptyError: If no PDF files found
       """
       # Validate and normalize path
       path = self._validate_directory_path(directory_path)
       
       # Find PDF files
       pdf_files = self._find_pdf_files(path)
       
       if not pdf_files:
           raise DirectoryEmptyError(f"No PDF files found in directory: {directory_path}")
       
       # Extract job information
       job_name, job_number = self._extract_job_info(path)
       
       # Get file information
       file_info_list = []
       total_size_bytes = 0
       
       for pdf_file in pdf_files:
           file_info = self._get_file_info(pdf_file)
           file_info_list.append(file_info)
           total_size_bytes += file_info["file_size_bytes"]
       
       # Sort files by name for consistent ordering
       file_info_list.sort(key=lambda x: x["filename"].lower())
       
       # Calculate estimates
       estimated_cost, estimated_time = self._calculate_estimates(len(pdf_files))
       
       scan_result = {
           "success": True,
           "directory_path": str(path),
           "job_name": job_name,
           "job_number": job_number,
           "total_pdf_files": len(pdf_files),
           "total_size_bytes": total_size_bytes,
           "total_size_mb": round(total_size_bytes / (1024 * 1024), 2),
           "estimated_scan_cost": estimated_cost,
           "estimated_scan_time_seconds": estimated_time,
           "files": file_info_list
       }
       
       self.logger.info(
           f"Scanned directory '{job_name}': {len(pdf_files)} PDF files, "
           f"{scan_result['total_size_mb']:.1f}MB total"
       )
       
       return scan_result
   
   def _validate_directory_path(self, directory_path: str) -> Path:
       """Validate and return a Path object for the directory"""
       
       if not directory_path or not directory_path.strip():
           raise InvalidDirectoryPathError("Directory path cannot be empty")
       
       path = Path(directory_path.strip())
       
       if not path.exists():
           raise DirectoryNotFoundError(f"Directory not found: {directory_path}")
       
       if not path.is_dir():
           raise InvalidDirectoryPathError(f"Path is not a directory: {directory_path}")
       
       # Check if directory is readable
       try:
           list(path.iterdir())
       except PermissionError:
           raise InvalidDirectoryPathError(f"Permission denied accessing directory: {directory_path}")
       except OSError as e:
           raise InvalidDirectoryPathError(f"Cannot access directory: {directory_path} - {str(e)}")
       
       return path
   
   def _find_pdf_files(self, directory_path: Path) -> List[Path]:
       """Find all PDF files in the directory"""
       
       pdf_files = []
       
       try:
           # Use glob to find PDF files (case insensitive)
           for extension in self.allowed_extensions:
               pattern = f"*.{extension}"
               pdf_files.extend(directory_path.glob(pattern))
           
           # Remove duplicates (in case of case variations)
           unique_files = []
           seen_names = set()
           
           for file_path in pdf_files:
               if file_path.name.lower() not in seen_names:
                   unique_files.append(file_path)
                   seen_names.add(file_path.name.lower())
           
           self.logger.debug(f"Found {len(unique_files)} PDF files in {directory_path}")
           return unique_files
           
       except Exception as e:
           self.logger.error(f"Error finding PDF files in {directory_path}: {e}")
           raise DirectoryAnalyzerException(
               f"Failed to scan directory for PDF files: {str(e)}",
               details={"directory_path": str(directory_path)}
           )
   
   def _extract_job_info(self, directory_path: Path) -> Tuple[str, str]:
       """Extract job name and number from directory path"""
       
       job_name = directory_path.name
       
       # Try to extract job number from various patterns
       job_number = "UNKNOWN"
       
       # Pattern 1: First 4 characters (e.g., "2315 - Project Name")
       if len(job_name) >= 4 and job_name[:4].isdigit():
           job_number = job_name[:4]
       
       # Pattern 2: Find first sequence of 3-6 digits
       import re
       digit_match = re.search(r'\b(\d{3,6})\b', job_name)
       if digit_match:
           job_number = digit_match.group(1)
       
       # Pattern 3: Job number after common prefixes
       job_prefixes = ['job', 'project', 'contract', 'ctdot']
       for prefix in job_prefixes:
           pattern = rf'{prefix}[-_\s]*(\d+)'
           match = re.search(pattern, job_name.lower())
           if match:
               job_number = match.group(1)
               break
       
       self.logger.debug(f"Extracted job info: name='{job_name}', number='{job_number}'")
       return job_name, job_number
   
   def _get_file_info(self, pdf_file: Path) -> Dict[str, Any]:
       """Get comprehensive file information"""
       
       try:
           file_stats = pdf_file.stat()
           file_size_bytes = file_stats.st_size
           
           file_info = {
               "filename": pdf_file.name,
               "file_path": str(pdf_file),
               "file_size_bytes": file_size_bytes,
               "file_size_kb": file_size_bytes // 1024,
               "file_size_mb": round(file_size_bytes / (1024 * 1024), 2),
               "created_time": file_stats.st_ctime,
               "modified_time": file_stats.st_mtime,
               "is_readable": os.access(pdf_file, os.R_OK)
           }
           
           # Add file classification hints based on filename
           file_info["filename_hints"] = self._analyze_filename(pdf_file.name)
           
           return file_info
           
       except Exception as e:
           self.logger.warning(f"Could not get complete file stats for {pdf_file}: {e}")
           return {
               "filename": pdf_file.name,
               "file_path": str(pdf_file),
               "file_size_bytes": 0,
               "file_size_kb": 0,
               "file_size_mb": 0.0,
               "created_time": 0,
               "modified_time": 0,
               "is_readable": False,
               "error": str(e),
               "filename_hints": self._analyze_filename(pdf_file.name)
           }
   
   def _analyze_filename(self, filename: str) -> Dict[str, Any]:
       """Analyze filename for classification hints"""
       
       filename_lower = filename.lower()
       
       hints = {
           "likely_main_contract": False,
           "likely_executed": False,
           "likely_draft": False,
           "has_version": False,
           "contract_indicators": [],
           "status_indicators": [],
           "version_indicators": []
       }
       
       # Main contract indicators
       main_indicators = ["executed", "signed", "final", "clean", "fully executed"]
       hints["contract_indicators"] = [ind for ind in main_indicators if ind in filename_lower]
       hints["likely_main_contract"] = len(hints["contract_indicators"]) > 0
       
       # Execution status indicators
       execution_indicators = ["executed", "signed", "fully executed"]
       hints["status_indicators"] = [ind for ind in execution_indicators if ind in filename_lower]
       hints["likely_executed"] = len(hints["status_indicators"]) > 0
       
       # Draft indicators
       draft_indicators = ["draft", "markup", "redline", "comments", "review"]
       draft_found = [ind for ind in draft_indicators if ind in filename_lower]
       hints["likely_draft"] = len(draft_found) > 0
       
       # Version indicators
       import re
       version_patterns = [
           r'r\d+', r'rev\d+', r'revision\s*\d+', r'v\d+', r'version\s*\d+'
       ]
       
       for pattern in version_patterns:
           matches = re.findall(pattern, filename_lower)
           if matches:
               hints["version_indicators"].extend(matches)
       
       hints["has_version"] = len(hints["version_indicators"]) > 0
       
       return hints
   
   def _calculate_estimates(self, file_count: int) -> Tuple[float, float]:
       """Calculate cost and time estimates for processing"""
       
       estimated_cost = file_count * settings.estimated_cost_per_document
       estimated_time = file_count * settings.estimated_time_per_document
       
       return estimated_cost, estimated_time
   
   def validate_file_access(self, file_path: Path) -> bool:
       """Validate that a file can be accessed and read"""
       
       try:
           if not file_path.exists():
               return False
           
           if not file_path.is_file():
               return False
           
           if not os.access(file_path, os.R_OK):
               return False
           
           # Try to open the file briefly
           with open(file_path, 'rb') as f:
               f.read(1)  # Read just one byte to test access
           
           return True
           
       except Exception as e:
           self.logger.warning(f"File access validation failed for {file_path}: {e}")
           return False
   
   def get_directory_summary(self, directory_path: str) -> Dict[str, Any]:
       """Get a quick summary of directory contents without full scanning"""
       
       try:
           path = self._validate_directory_path(directory_path)
           pdf_files = self._find_pdf_files(path)
           job_name, job_number = self._extract_job_info(path)
           
           return {
               "directory_path": str(path),
               "job_name": job_name,
               "job_number": job_number,
               "pdf_file_count": len(pdf_files),
               "is_valid": True
           }
           
       except Exception as e:
           return {
               "directory_path": directory_path,
               "job_name": "Unknown",
               "job_number": "Unknown",
               "pdf_file_count": 0,
               "is_valid": False,
               "error": str(e)
           }


# Global instance
directory_scanner = DirectoryScanner()
