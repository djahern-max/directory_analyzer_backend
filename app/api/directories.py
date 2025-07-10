from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
import logging
import traceback
from typing import Dict, Any

from app.models.directory import (
    DirectoryAnalysisRequest, 
    DirectoryListResponse,
    QuickIdentificationResponse
)
from app.models.responses import DirectoryAnalysisResponse
from app.services.directory_scanner import directory_scanner
from app.services.contract_intelligence import create_contract_intelligence_service
from app.utils.validation import validate_analysis_request
from app.core.exceptions import DirectoryAnalyzerException
from app.config import settings

router = APIRouter()
logger = logging.getLogger("app.api.directories")


@router.post("/list", response_model=DirectoryListResponse)
async def list_directory_files(
    request: DirectoryAnalysisRequest
) -> DirectoryListResponse:
    """List PDF files in a directory for preview before analysis"""
    logger.info(f"Listing files in directory: {request.directory_path}")
    
    try:
        validation = validate_analysis_request(request.dict())
        if not validation["is_valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request: {'; '.join(validation['errors'])}"
            )
        
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
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list directory files: {str(e)}"
        )


@router.post("/analyze")
async def analyze_directory(
    request: DirectoryAnalysisRequest
) -> Dict[str, Any]:  # Return raw dict instead of trying to fit into model
    """Analyze all PDFs in a directory"""
    logger.info(f"Starting complete directory analysis: {request.directory_path}")
    
    try:
        api_key = settings.anthropic_api_key
        
        validation = validate_analysis_request(request.dict())
        if not validation["is_valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request: {'; '.join(validation['errors'])}"
            )
        
        intelligence_service = create_contract_intelligence_service(api_key)
        analysis_result = intelligence_service.analyze_directory_complete(
            request.directory_path
        )
        
        # Return the result directly as a dict, don't try to convert to Pydantic model
        logger.info(
            f"Directory analysis completed successfully. "
            f"Main contract: {analysis_result.get('main_contract', {}).get('filename', 'Not identified')}"
        )
        
        return analysis_result
        
    except DirectoryAnalyzerException as e:
        logger.error(f"Directory analysis failed: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message
        )
        
    except Exception as e:
        logger.error(f"Unexpected error in directory analysis: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Directory analysis failed: {str(e)}"
        )


@router.post("/identify-main-contract", response_model=QuickIdentificationResponse)
async def identify_main_contract_only(
    request: DirectoryAnalysisRequest
) -> QuickIdentificationResponse:
    """Quick endpoint to identify just the main contract"""
    logger.info(f"Identifying main contract in: {request.directory_path}")
    
    try:
        api_key = settings.anthropic_api_key
        
        validation = validate_analysis_request(request.dict())
        if not validation["is_valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request: {'; '.join(validation['errors'])}"
            )
        
        intelligence_service = create_contract_intelligence_service(api_key)
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
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Main contract identification failed: {str(e)}"
        )


@router.get("/service-status")
async def get_service_status() -> Dict[str, Any]:
    """Get status of the directory analysis service"""
    try:
        api_key = settings.anthropic_api_key
        intelligence_service = create_contract_intelligence_service(api_key)
        status_info = intelligence_service.get_service_status()
        
        return {
            "status": "operational",
            "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
            "service_info": status_info
        }
        
    except Exception as e:
        logger.error(f"Error getting service status: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return {
            "status": "error",
            "timestamp": __import__('datetime').datetime.utcnow().isoformat(),
            "error": str(e)
        }
