from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form, Depends
from fastapi.responses import JSONResponse
import logging
import traceback
import os
import tempfile
import shutil
import datetime
from typing import Dict, Any, List

from app.models.directory import (
    DirectoryAnalysisRequest,
    DirectoryListResponse,
    QuickIdentificationResponse,
)
from app.models.responses import DirectoryAnalysisResponse
from app.services.directory_scanner import directory_scanner
from app.services.contract_intelligence import create_contract_intelligence_service
from app.core.exceptions import DirectoryAnalyzerException
from app.config import settings
from app.middleware.premium_check import verify_premium_subscription, get_current_user

router = APIRouter()
logger = logging.getLogger("app.api.directories")


@router.post("/list", response_model=DirectoryListResponse)
async def list_directory_files(
    request: DirectoryAnalysisRequest,
) -> DirectoryListResponse:
    """List PDF files in a directory for preview before analysis"""
    logger.info(f"Listing files in directory: {request.directory_path}")

    try:
        # Remove validation block - scanner handles validation
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
                    "file_size_mb": file_info["file_size_mb"],
                }
                for file_info in scan_result["files"]
            ],
        )

        logger.info(f"Successfully listed {response.total_pdf_files} files")
        return response

    except DirectoryAnalyzerException as e:
        logger.error(f"Directory listing failed: {e.message}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
    except Exception as e:
        logger.error(f"Unexpected error listing directory: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list directory files: {str(e)}",
        )


@router.post("/upload")
async def upload_directory_files(
    files: List[UploadFile] = File(...),
    directory_name: str = Form(...),
    current_user: dict = Depends(
        verify_premium_subscription
    ),  # Fixed: Use dict instead of User
) -> Dict[str, Any]:
    """Upload files from browser and prepare them for analysis - PREMIUM ONLY"""
    logger.info(
        f"Premium user {current_user['email']} uploading {len(files)} files for: {directory_name}"
    )

    try:
        # Create a temporary directory for uploaded files
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        upload_dir = os.path.join(
            tempfile.gettempdir(), "contract_analysis", f"{directory_name}_{timestamp}"
        )

        # Create the directory
        os.makedirs(upload_dir, exist_ok=True)

        uploaded_files = []
        total_size = 0

        # Save each uploaded file
        for file in files:
            if file.filename and file.filename.lower().endswith(".pdf"):
                # Clean filename and ensure it's safe
                safe_filename = "".join(
                    c for c in file.filename if c.isalnum() or c in (" ", "-", "_", ".")
                ).rstrip()

                file_path = os.path.join(upload_dir, safe_filename)

                # Write file to disk
                content = await file.read()
                with open(file_path, "wb") as buffer:
                    buffer.write(content)
                    total_size += len(content)

                uploaded_files.append(
                    {
                        "filename": safe_filename,
                        "original_filename": file.filename,
                        "size": len(content),
                        "path": file_path,
                    }
                )

                logger.info(f"Saved file: {safe_filename} ({len(content)} bytes)")

        logger.info(
            f"Successfully uploaded {len(uploaded_files)} files to {upload_dir}"
        )

        return {
            "success": True,
            "directory_path": upload_dir,
            "directory_name": directory_name,
            "files_uploaded": len(uploaded_files),
            "total_size_bytes": total_size,
            "uploaded_files": uploaded_files,
            "message": f"Files uploaded successfully. Use directory_path '{upload_dir}' for analysis.",
            "user": current_user["email"],
        }

    except Exception as e:
        logger.error(f"File upload failed for user {current_user['email']}: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")

        # Clean up on error
        if "upload_dir" in locals() and os.path.exists(upload_dir):
            try:
                shutil.rmtree(upload_dir)
                logger.info(f"Cleaned up failed upload directory: {upload_dir}")
            except Exception as cleanup_error:
                logger.error(
                    f"Failed to cleanup directory {upload_dir}: {cleanup_error}"
                )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File upload failed: {str(e)}",
        )


@router.post("/analyze")
async def analyze_directory(
    request: DirectoryAnalysisRequest,
    current_user: dict = Depends(
        verify_premium_subscription
    ),  # Fixed: Use dict instead of User
) -> Dict[str, Any]:
    """Analyze directory - PREMIUM ONLY"""
    logger.info(
        f"Premium user {current_user['email']} analyzing: {request.directory_path}"
    )

    try:
        api_key = settings.anthropic_api_key

        # Remove validation block - intelligence service handles validation
        intelligence_service = create_contract_intelligence_service(api_key)
        analysis_result = intelligence_service.analyze_directory_complete(
            request.directory_path
        )

        # Add user info to result
        analysis_result["user"] = current_user["email"]
        analysis_result["timestamp"] = datetime.datetime.utcnow().isoformat()

        logger.info(
            f"Directory analysis completed for {current_user['email']}. "
            f"Main contract: {analysis_result.get('main_contract', {}).get('filename', 'Not identified')}"
        )

        return analysis_result

    except DirectoryAnalyzerException as e:
        logger.error(
            f"Directory analysis failed for {current_user['email']}: {e.message}"
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)

    except Exception as e:
        logger.error(
            f"Unexpected error in directory analysis for {current_user['email']}: {e}"
        )
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Directory analysis failed: {str(e)}",
        )


@router.post("/demo-analyze", response_model=QuickIdentificationResponse)
async def demo_analyze(
    request: DirectoryAnalysisRequest,
    current_user: dict = Depends(get_current_user),  # Just authenticated, not premium
) -> QuickIdentificationResponse:
    """Demo analysis with limited features - FREE"""
    logger.info(f"User {current_user['email']} starting demo analysis")

    try:
        api_key = settings.anthropic_api_key
        intelligence_service = create_contract_intelligence_service(api_key)

        # Use the existing identify_main_contract_only method for demo
        identification_result = intelligence_service.identify_main_contract_only(
            request.directory_path
        )

        # Add demo messaging
        identification_result["demo"] = True
        identification_result["message"] = (
            "This is a limited demo. Upgrade to premium for full analysis."
        )
        identification_result["upgrade_url"] = "/pricing"

        response = QuickIdentificationResponse(**identification_result)
        logger.info(f"Demo analysis completed for {current_user['email']}")

        return response

    except Exception as e:
        logger.error(f"Demo analysis failed for {current_user['email']}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Demo analysis failed: {str(e)}",
        )


@router.post("/identify-main-contract", response_model=QuickIdentificationResponse)
async def identify_main_contract_only(
    request: DirectoryAnalysisRequest,
) -> QuickIdentificationResponse:
    """Quick endpoint to identify just the main contract"""
    logger.info(f"Identifying main contract in: {request.directory_path}")

    try:
        api_key = settings.anthropic_api_key

        # Remove validation block - intelligence service handles validation
        intelligence_service = create_contract_intelligence_service(api_key)
        identification_result = intelligence_service.identify_main_contract_only(
            request.directory_path
        )

        response = QuickIdentificationResponse(**identification_result)

        if response.success:
            logger.info(
                f"Main contract identified: {response.main_contract['filename']}"
            )
        else:
            logger.warning(f"Main contract identification failed: {response.error}")

        return response

    except DirectoryAnalyzerException as e:
        logger.error(f"Main contract identification failed: {e.message}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)

    except Exception as e:
        logger.error(f"Unexpected error in main contract identification: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Main contract identification failed: {str(e)}",
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
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "service_info": status_info,
        }

    except Exception as e:
        logger.error(f"Error getting service status: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return {
            "status": "error",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "error": str(e),
        }
