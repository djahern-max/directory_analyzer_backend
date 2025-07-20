# app/api/directories.py
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from typing import List
import logging
from pathlib import Path
import tempfile
import shutil

from app.models.directory import DirectoryAnalysisRequest
from app.middleware.premium_check import verify_premium_subscription
from app.services.contract_intelligence import create_contract_intelligence_service
from app.services.spaces_storage import get_spaces_storage
from app.api.deps import get_api_key

router = APIRouter()
logger = logging.getLogger("app.api.directories")


@router.post("/upload")
async def upload_directory_files(
    files: List[UploadFile] = File(...),
    directory_name: str = Form(...),
    user: dict = Depends(verify_premium_subscription),
):
    """Upload files to Digital Ocean Spaces - PREMIUM ONLY"""
    try:
        logger.info(f"Uploading {len(files)} files for user {user['email']}")

        # Basic validation
        if len(files) > 50:  # Reasonable limit
            raise HTTPException(status_code=400, detail="Too many files (max 50)")

        # Initialize storage service
        storage = get_spaces_storage()

        uploaded_files = []

        for file in files:
            if not file.filename.lower().endswith(".pdf"):
                logger.warning(f"Skipping non-PDF file: {file.filename}")
                continue

            # Read file content
            content = await file.read()

            # Upload to Spaces with user/job structure
            upload_result = storage.upload_contract_file(
                file_content=content,
                filename=file.filename,
                user_id=user["id"],
                job_number=directory_name,  # Use directory name as job number
                job_name=directory_name,
                contract_type="unknown",  # Will be determined by analysis
                is_main_contract=False,  # Will be determined by analysis
            )

            uploaded_files.append(upload_result)

        logger.info(f"Successfully uploaded {len(uploaded_files)} files")

        return {
            "success": True,
            "uploaded_files": len(uploaded_files),
            "directory_path": directory_name,
            "files": uploaded_files,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/analyze")
async def analyze_directory(
    request: DirectoryAnalysisRequest,
    user: dict = Depends(verify_premium_subscription),
    api_key: str = Depends(get_api_key),
):
    """Analyze directory - PREMIUM ONLY"""
    try:
        logger.info(
            f"Starting directory analysis for user {user['email']}: {request.directory_path}"
        )

        # Create contract intelligence service
        service = create_contract_intelligence_service(api_key)

        # Run the analysis
        results = service.analyze_directory_complete(request.directory_path)

        logger.info(f"Analysis completed for user {user['email']}")
        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/service-status")
async def get_service_status():
    """Get service status - FREE endpoint for testing"""
    try:
        return {
            "service": "Directory Analyzer API",
            "status": "operational",
            "version": "1.0.0",
            "endpoints": {
                "upload": "/directories/upload (Premium)",
                "analyze": "/directories/analyze (Premium)",
                "service_status": "/directories/service-status (Free)",
            },
        }
    except Exception as e:
        logger.error(f"Service status check failed: {e}")
        raise HTTPException(status_code=500, detail="Service status unavailable")
