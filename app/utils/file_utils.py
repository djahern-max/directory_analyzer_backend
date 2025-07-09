import os
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import mimetypes

logger = logging.getLogger("app.utils.file_utils")


def get_file_hash(file_path: Path, algorithm: str = "md5") -> str:
   """
   Calculate hash of a file
   
   Args:
       file_path: Path to the file
       algorithm: Hash algorithm (md5, sha1, sha256)
       
   Returns:
       Hex digest of the file hash
   """
   hash_obj = hashlib.new(algorithm)
   
   try:
       with open(file_path, 'rb') as f:
           for chunk in iter(lambda: f.read(4096), b""):
               hash_obj.update(chunk)
       return hash_obj.hexdigest()
   except Exception as e:
       logger.error(f"Failed to calculate hash for {file_path}: {e}")
       raise


def get_file_mime_type(file_path: Path) -> str:
   """
   Get MIME type of a file
   
   Args:
       file_path: Path to the file
       
   Returns:
       MIME type string
   """
   mime_type, _ = mimetypes.guess_type(str(file_path))
   return mime_type or "application/octet-stream"


def format_file_size(size_bytes: int) -> str:
   """
   Format file size in human readable format
   
   Args:
       size_bytes: Size in bytes
       
   Returns:
       Formatted size string (e.g., "1.5 MB")
   """
   if size_bytes == 0:
       return "0 B"
   
   size_names = ["B", "KB", "MB", "GB", "TB"]
   import math
   i = int(math.floor(math.log(size_bytes, 1024)))
   p = math.pow(1024, i)
   s = round(size_bytes / p, 2)
   return f"{s} {size_names[i]}"


def is_pdf_file(file_path: Path) -> bool:
   """
   Check if a file is a PDF based on extension and MIME type
   
   Args:
       file_path: Path to the file
       
   Returns:
       True if file appears to be a PDF
   """
   # Check extension
   if file_path.suffix.lower() != '.pdf':
       return False
   
   # Check MIME type
   mime_type = get_file_mime_type(file_path)
   return mime_type == 'application/pdf'


def safe_filename(filename: str) -> str:
   """
   Create a safe filename by removing/replacing problematic characters
   
   Args:
       filename: Original filename
       
   Returns:
       Safe filename string
   """
   import re
   
   # Remove or replace problematic characters
   safe_name = re.sub(r'[<>:"/\\|?*]', '_', filename)
   
   # Remove leading/trailing whitespace and dots
   safe_name = safe_name.strip(' .')
   
   # Ensure filename is not empty
   if not safe_name:
       safe_name = "unnamed_file"
   
   # Limit length
   if len(safe_name) > 255:
       name_part, ext_part = os.path.splitext(safe_name)
       safe_name = name_part[:255-len(ext_part)] + ext_part
   
   return safe_name


def get_directory_size(directory_path: Path) -> Dict[str, Any]:
   """
   Calculate total size of a directory
   
   Args:
       directory_path: Path to the directory
       
   Returns:
       Dictionary with size information
   """
   total_size = 0
   file_count = 0
   dir_count = 0
   
   try:
       for item in directory_path.rglob('*'):
           if item.is_file():
               file_count += 1
               try:
                   total_size += item.stat().st_size
               except (OSError, IOError):
                   # Skip files we can't access
                   pass
           elif item.is_dir():
               dir_count += 1
       
       return {
           "total_size_bytes": total_size,
           "total_size_formatted": format_file_size(total_size),
           "file_count": file_count,
           "directory_count": dir_count
       }
       
   except Exception as e:
       logger.error(f"Failed to calculate directory size for {directory_path}: {e}")
       return {
           "total_size_bytes": 0,
           "total_size_formatted": "0 B",
           "file_count": 0,
           "directory_count": 0,
           "error": str(e)
       }


def find_files_by_pattern(directory_path: Path, pattern: str) -> List[Path]:
   """
   Find files matching a glob pattern
   
   Args:
       directory_path: Path to search in
       pattern: Glob pattern (e.g., "*.pdf")
       
   Returns:
       List of matching file paths
   """
   try:
       return list(directory_path.glob(pattern))
   except Exception as e:
       logger.error(f"Failed to find files with pattern '{pattern}' in {directory_path}: {e}")
       return []


def create_backup_filename(original_path: Path) -> Path:
   """
   Create a backup filename by adding timestamp
   
   Args:
       original_path: Original file path
       
   Returns:
       Backup file path
   """
   from datetime import datetime
   
   timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
   stem = original_path.stem
   suffix = original_path.suffix
   
   backup_name = f"{stem}_backup_{timestamp}{suffix}"
   return original_path.parent / backup_name


def ensure_directory_exists(directory_path: Path) -> bool:
   """
   Ensure a directory exists, create if it doesn't
   
   Args:
       directory_path: Path to the directory
       
   Returns:
       True if directory exists or was created successfully
   """
   try:
       directory_path.mkdir(parents=True, exist_ok=True)
       return True
   except Exception as e:
       logger.error(f"Failed to create directory {directory_path}: {e}")
       return False


def get_file_age_days(file_path: Path) -> float:
   """
   Get the age of a file in days
   
   Args:
       file_path: Path to the file
       
   Returns:
       Age in days (float)
   """
   try:
       import time
       file_mtime = file_path.stat().st_mtime
       current_time = time.time()
       age_seconds = current_time - file_mtime
       return age_seconds / (24 * 60 * 60)  # Convert to days
   except Exception as e:
       logger.error(f"Failed to get file age for {file_path}: {e}")
       return 0.0


def is_file_accessible(file_path: Path) -> Dict[str, bool]:
   """
   Check file accessibility permissions
   
   Args:
       file_path: Path to the file
       
   Returns:
       Dictionary with permission flags
   """
   return {
       "exists": file_path.exists(),
       "readable": os.access(file_path, os.R_OK) if file_path.exists() else False,
       "writable": os.access(file_path, os.W_OK) if file_path.exists() else False,
       "executable": os.access(file_path, os.X_OK) if file_path.exists() else False
   }


def compare_files(file1_path: Path, file2_path: Path) -> Dict[str, Any]:
   """
   Compare two files for basic equality
   
   Args:
       file1_path: Path to first file
       file2_path: Path to second file
       
   Returns:
       Comparison results dictionary
   """
   try:
       # Check if both files exist
       if not file1_path.exists() or not file2_path.exists():
           return {
               "files_exist": False,
               "are_identical": False,
               "error": "One or both files do not exist"
           }
       
       # Compare file sizes first (quick check)
       size1 = file1_path.stat().st_size
       size2 = file2_path.stat().st_size
       
       if size1 != size2:
           return {
               "files_exist": True,
               "are_identical": False,
               "size_match": False,
               "file1_size": size1,
               "file2_size": size2
           }
       
       # Compare hashes for identical size files
       hash1 = get_file_hash(file1_path)
       hash2 = get_file_hash(file2_path)
       
       return {
           "files_exist": True,
           "are_identical": hash1 == hash2,
           "size_match": True,
           "hash_match": hash1 == hash2,
           "file1_hash": hash1,
           "file2_hash": hash2,
           "file_size": size1
       }
       
   except Exception as e:
       logger.error(f"Failed to compare files {file1_path} and {file2_path}: {e}")
       return {
           "files_exist": False,
           "are_identical": False,
           "error": str(e)
       }
