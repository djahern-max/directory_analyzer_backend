# app/api/directories.py - Updated upload endpoint
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
    current_user: dict = Depends(verify_premium_subscription),
) -> Dict[str, Any]:
    """Upload files to Digital Ocean Spaces - PREMIUM ONLY"""
    logger.info(
        f"Premium user {current_user['email']} uploading {len(files)} files for: {directory_name}"
    )

    try:
        # Import and create spaces storage instance
        from app.services.spaces_storage import get_spaces_storage

        # Create storage service instance with proper error handling
        try:
            spaces_storage = get_spaces_storage()
        except DirectoryAnalyzerException as e:
            logger.error(f"Failed to initialize file storage: {e.message}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"File storage service unavailable: {e.message}",
            )

        uploaded_files = []
        failed_files = []
        total_size = 0

        # Process each uploaded file
        for file in files:
            try:
                if not file.filename:
                    failed_files.append(
                        {"filename": "unknown", "error": "No filename provided"}
                    )
                    continue

                # Read file content
                content = await file.read()
                total_size += len(content)

                # Upload to Spaces
                upload_result = spaces_storage.upload_file(
                    file_content=content,
                    filename=file.filename,
                    user_id=str(current_user["id"]),
                    directory_name=directory_name,
                )

                uploaded_files.append(
                    {
                        "filename": upload_result["filename"],
                        "original_filename": upload_result["original_filename"],
                        "size": upload_result["size"],
                        "file_key": upload_result["file_key"],
                        "public_url": upload_result["public_url"],
                        "file_id": upload_result["file_id"],
                    }
                )

                logger.info(f"Successfully uploaded: {file.filename}")

            except Exception as file_error:
                logger.error(f"Failed to upload {file.filename}: {file_error}")
                failed_files.append(
                    {"filename": file.filename, "error": str(file_error)}
                )

        # Check if any files were successfully uploaded
        if not uploaded_files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No files were successfully uploaded",
            )

        logger.info(
            f"Upload completed for {current_user['email']}: "
            f"{len(uploaded_files)} successful, {len(failed_files)} failed"
        )

        # Create a temporary directory path for analysis
        # We'll use a special format that indicates these are uploaded files
        analysis_directory_path = f"uploaded://{current_user['id']}/{directory_name}"

        return {
            "success": True,
            "directory_name": directory_name,
            "directory_path": analysis_directory_path,  # Add this for analysis
            "files_uploaded": len(uploaded_files),
            "files_failed": len(failed_files),
            "total_size_bytes": total_size,
            "uploaded_files": uploaded_files,
            "failed_files": failed_files,
            "message": f"Successfully uploaded {len(uploaded_files)} files to Digital Ocean Spaces",
            "user": current_user["email"],
            "upload_location": "digital_ocean_spaces",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"File upload failed for user {current_user['email']}: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File upload failed: {str(e)}",
        )


@router.post("/analyze")
async def analyze_directory(
    request: DirectoryAnalysisRequest,
    current_user: dict = Depends(verify_premium_subscription),
) -> Dict[str, Any]:
    """Analyze directory - PREMIUM ONLY"""
    logger.info(
        f"Premium user {current_user['email']} analyzing: {request.directory_path}"
    )

    try:
        api_key = settings.anthropic_api_key

        # Check if this is an uploaded files analysis
        if request.directory_path.startswith("uploaded://"):
            # For now, return a placeholder response
            # You'll need to implement uploaded file analysis later
            return {
                "success": False,
                "message": "Analysis of uploaded files not yet implemented",
                "directory_path": request.directory_path,
                "user": current_user["email"],
                "note": "This feature will be implemented to analyze files from Digital Ocean Spaces",
            }

        # For traditional directory paths, use the existing intelligence service
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
