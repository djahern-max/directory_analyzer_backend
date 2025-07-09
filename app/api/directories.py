from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
import logging
from typing import Dict, Any

from app.models.directory import (
    DirectoryAnalysisRequest, 
    DirectoryListResponse,
    QuickIdentificationResponse
)
from app.models.responses import DirectoryAnalysisResponse
from app.api.deps import get_api_key
from app.services.directory_scanner import directory_scanner
from app.services.contract_intelligence import create_contract_intelligence_service
from app.utils.validation import validate_analysis_request
from app.core.exceptions import DirectoryAnalyzerException

router = APIRouter()
logger = logging.getLogger("app.api.directories")


@router.post("/list", response_model=DirectoryListResponse)
async def list_directory_files(
    request: DirectoryAnalysisRequest,
    api_key: str = Depends(get_api_key)
) -> DirectoryListResponse:
    """
    List PDF files in a directory for preview before analysis
    
    Args:
        request: Directory analysis request
        api_key: Validated API key
        
    Returns:
        Directory listing with file information
        
    Raises:
        HTTPException: If directory listing fails
    """
    logger.info(f"Listing files in directory: {request.directory_path}")
    
    try:
        # Validate request
        validation = validate_analysis_request(request.dict())
        if not validation["is_valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request: {'; '.join(validation['errors'])}"
            )
        
        # Scan directory
        scan_result = directory_scanner.scan_directory(request.directory_path)
        
        response = DirectoryListResponse(
            success=scan_result["success"],
            directory_path=scan_result["directory_path"],
            job_name=scan_result["job_name"],
            job_number=scan_result["job_number"],
            total_pdf_files=scan_result["total_pdf_files"],
            estimated_scan_cost=scan_result["estimated_scan_cost"],
            estimated_scan_time_seconds=scan_result["estimated_scan_time_seconds"],
            files=[
                {
                    "filename": file_info["filename"],
                    "file_path": file_info["file_path"],
                    "file_size_bytes": file_info["file_size_bytes"],
                    "file_size_kb": file_info["file_size_kb"],
                    "file_size_mb": file_info["file_size_mb"]
                }
                for file_info in scan_result["files"]
            ]
        )
        
        logger.info(f"Successfully listed {response.total_pdf_files} files")
        return response
        
    except DirectoryAnalyzerException as e:
        logger.error(f"Directory listing failed: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message
        )
    except Exception as e:
        logger.error(f"Unexpected error listing directory: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list directory files: {str(e)}"
        )


@router.post("/analyze", response_model=DirectoryAnalysisResponse)
async def analyze_directory(
    request: DirectoryAnalysisRequest,
    api_key: str = Depends(get_api_key)
) -> DirectoryAnalysisResponse:
    """
    Analyze all PDFs in a directory to identify main contract and classify documents
    
    This endpoint:
    1. Scans directory for PDF files
    2. Extracts text from each PDF
    3. Uses AI to classify each document
    4. Identifies the main contract
    5. Ranks all documents by importance
    6. Returns comprehensive analysis
    
    Args:
        request: Directory analysis request
        api_key: Validated API key
        
    Returns:
        Complete directory analysis results
        
    Raises:
        HTTPException: If analysis fails
    """
    logger.info(f"Starting complete directory analysis: {request.directory_path}")
    
    try:
        # Validate request
        validation = validate_analysis_request(request.dict())
        if not validation["is_valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request: {'; '.join(validation['errors'])}"
            )
        
        # Create intelligence service
        intelligence_service = create_contract_intelligence_service(api_key)
        
        # Run complete analysis
        analysis_result = intelligence_service.analyze_directory_complete(
            request.directory_path
        )
        
        # Convert to response model
        response = DirectoryAnalysisResponse(
            success=analysis_result["success"],
            message=analysis_result["message"],
            job_info=analysis_result["job_info"],
            main_contract=analysis_result["main_contract"],
            ranked_documents=analysis_result["ranked_documents"],
            stats=analysis_result["stats"],
            classification_summary=analysis_result["classification_summary"],
            failed_files=analysis_result["failed_files"],
            timestamp=analysis_result["timestamp"]
        )
        
        logger.info(
            f"Directory analysis completed successfully. "
            f"Main contract: {response.main_contract.filename if response.main_contract else 'Not identified'}"
        )
        
        return response
        
    except DirectoryAnalyzerException as e:
        logger.error(f"Directory analysis failed: {e.message}")
        
        # Return appropriate HTTP status based on error type
        if "not found" in e.message.lower():
            status_code = status.HTTP_404_NOT_FOUND
        elif "permission" in e.message.lower():
            status_code = status.HTTP_403_FORBIDDEN
        elif "overloaded" in e.message.lower() or "rate limited" in e.message.lower():
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        else:
            status_code = status.HTTP_400_BAD_REQUEST
        
        raise HTTPException(
            status_code=status_code,
            detail=e.message
        )
        
    except Exception as e:
        logger.error(f"Unexpected error in directory analysis: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Directory analysis failed: {str(e)}"
        )


@router.post("/identify-main-contract", response_model=QuickIdentificationResponse)
async def identify_main_contract_only(
    request: DirectoryAnalysisRequest,
    api_key: str = Depends(get_api_key)
) -> QuickIdentificationResponse:
    """
    Quick endpoint to identify just the main contract from a directory
    
    Args:
        request: Directory analysis request
        api_key: Validated API key
        
    Returns:
        Main contract identification results
        
    Raises:
        HTTPException: If identification fails
    """
    logger.info(f"Identifying main contract in: {request.directory_path}")
    
    try:
        # Validate request
        validation = validate_analysis_request(request.dict())
        if not validation["is_valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request: {'; '.join(validation['errors'])}"
            )
        
        # Create intelligence service
        intelligence_service = create_contract_intelligence_service(api_key)
        
        # Run main contract identification
        identification_result = intelligence_service.identify_main_contract_only(
            request.directory_path
        )
        
        response = QuickIdentificationResponse(**identification_result)
        
        if response.success:
            logger.info(f"Main contract identified: {response.main_contract['filename']}")
        else:
            logger.warning(f"Main contract identification failed: {response.error}")
        
        return response
        
    except DirectoryAnalyzerException as e:
        logger.error(f"Main contract identification failed: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message
        )
        
    except Exception as e:
        logger.error(f"Unexpected error in main contract identification: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Main contract identification failed: {str(e)}"
        )


@router.get("/service-status")
async def get_service_status(
    api_key: str = Depends(get_api_key)
) -> Dict[str, Any]:
    """
    Get status of the directory analysis service
    
    Args:
        api_key: Validated API key
        
    Returns:
        Service status information
    """
    try:
        intelligence_service = create_contract_intelligence_service(api_key)
        status_info = intelligence_service.get_service_status()
        
        return {
            "status": "operational",
            "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
            "service_info": status_info
        }
        
    except Exception as e:
        logger.error(f"Error getting service status: {e}")
        return {
            "status": "error",
            "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
            "error": str(e)
        }
