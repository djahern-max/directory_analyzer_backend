import re
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger("app.utils.validation")


def validate_directory_path(directory_path: str) -> Dict[str, Any]:
    """
    Validate directory path
    
    Args:
        directory_path: Path to validate
        
    Returns:
        Validation result dictionary
    """
    result = {
        "is_valid": False,
        "errors": [],
        "warnings": []
    }
    
    if not directory_path or not directory_path.strip():
        result["errors"].append("Directory path cannot be empty")
        return result
    
    try:
        path = Path(directory_path.strip())
        
        if not path.exists():
            result["errors"].append(f"Directory does not exist: {directory_path}")
            return result
        
        if not path.is_dir():
            result["errors"].append(f"Path is not a directory: {directory_path}")
            return result
        
        # Check if directory is readable
        try:
            list(path.iterdir())
        except PermissionError:
            result["errors"].append(f"Permission denied accessing directory: {directory_path}")
            return result
        
        result["is_valid"] = True
        
    except Exception as e:
        result["errors"].append(f"Error validating directory path: {str(e)}")
        logger.error(f"Directory path validation failed for {directory_path}: {e}")
    
    return result


def validate_file_path(file_path: str, max_size_mb: int = 50) -> Dict[str, Any]:
    """
    Validate file path and size
    
    Args:
        file_path: Path to file
        max_size_mb: Maximum file size in MB
        
    Returns:
        Validation result dictionary
    """
    result = {
        "is_valid": False,
        "errors": [],
        "warnings": []
    }
    
    if not file_path or not file_path.strip():
        result["errors"].append("File path cannot be empty")
        return result
    
    try:
        path = Path(file_path.strip())
        
        if not path.exists():
            result["errors"].append(f"File does not exist: {file_path}")
            return result
        
        if not path.is_file():
            result["errors"].append(f"Path is not a file: {file_path}")
            return result
        
        # Check file size
        file_size_bytes = path.stat().st_size
        file_size_mb = file_size_bytes / (1024 * 1024)
        
        if file_size_mb > max_size_mb:
            result["errors"].append(f"File too large: {file_size_mb:.1f}MB (max {max_size_mb}MB)")
            return result
        
        if file_size_mb > max_size_mb * 0.8:
            result["warnings"].append(f"File is quite large: {file_size_mb:.1f}MB")
        
        result["is_valid"] = True
        
    except Exception as e:
        result["errors"].append(f"Error checking file size: {str(e)}")
        logger.error(f"File size validation failed for {file_path}: {e}")
    
    return result


def validate_job_info(job_name: str, job_number: str) -> Dict[str, Any]:
    """
    Validate job information extracted from directory
    
    Args:
        job_name: Job name
        job_number: Job number
        
    Returns:
        Validation result dictionary
    """
    result = {
        "is_valid": False,
        "errors": [],
        "warnings": []
    }
    
    # Validate job name
    if not job_name or not job_name.strip():
        result["errors"].append("Job name cannot be empty")
    elif len(job_name) > 255:
        result["errors"].append("Job name is too long")
    
    # Validate job number
    if not job_number or job_number == "UNKNOWN":
        result["warnings"].append("Job number could not be determined")
    elif not re.match(r'^[A-Za-z0-9\-_]+$', job_number):
        result["warnings"].append("Job number contains unusual characters")
    
    if not result["errors"]:
        result["is_valid"] = True
    
    return result


def validate_analysis_request(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate complete analysis request
    
    Args:
        request_data: Request data dictionary
        
    Returns:
        Validation result dictionary
    """
    result = {
        "is_valid": False,
        "errors": [],
        "warnings": []
    }
    
    # Check required fields
    if "directory_path" not in request_data:
        result["errors"].append("Missing required field: directory_path")
        return result
    
    # Validate directory path
    dir_validation = validate_directory_path(request_data["directory_path"])
    if not dir_validation["is_valid"]:
        result["errors"].extend(dir_validation["errors"])
        result["warnings"].extend(dir_validation["warnings"])
    
    if not result["errors"]:
        result["is_valid"] = True
    
    return result
