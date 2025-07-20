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
