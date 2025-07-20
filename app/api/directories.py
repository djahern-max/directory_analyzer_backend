# app/api/directories.py
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from typing import List
import logging
from pathlib import Path
import tempfile
import shutil
from sqlalchemy.orm import Session

from app.models.directory import DirectoryAnalysisRequest
from app.middleware.premium_check import verify_premium_subscription
from app.services.contract_intelligence import create_contract_intelligence_service
from app.services.spaces_storage import get_spaces_storage
from app.api.deps import get_api_key
from app.core.database import get_db
from app.middleware.premium_check import verify_premium_subscription


router = APIRouter()
logger = logging.getLogger("app.api.directories")


@router.post("/upload")
async def upload_directory_files(
    files: List[UploadFile] = File(...),
    directory_name: str = Form(...),
    current_user: dict = Depends(verify_premium_subscription),
    db: Session = Depends(get_db),
):
    """
    Upload files to Digital Ocean Spaces - PREMIUM ONLY
    """
    try:
        logger.info(
            f"Starting file upload for user {current_user['email']}: {len(files)} files"
        )

        # Validate files
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")

        # Initialize storage service
        from app.services.spaces_storage import get_spaces_storage

        storage = get_spaces_storage()

        # Extract job info from directory name
        job_number = extract_job_number(directory_name)

        # Helper function to detect contract type from filename
        def detect_contract_type_from_filename(filename: str) -> tuple[str, bool]:
            """Detect contract type and if it's a main contract from filename patterns"""
            filename_lower = filename.lower()

            # Check for executed/signed contracts (likely main contracts)
            is_main = any(
                keyword in filename_lower
                for keyword in [
                    "executed",
                    "fully executed",
                    "signed",
                    "complete_with_docusign",
                ]
            )

            # Determine contract type
            if any(keyword in filename_lower for keyword in ["bond"]):
                return "bond", is_main
            elif any(keyword in filename_lower for keyword in ["cert_", "certificate"]):
                return "certificate", is_main
            elif any(keyword in filename_lower for keyword in ["amendment"]):
                return "amendment", is_main
            elif any(
                keyword in filename_lower
                for keyword in ["change_order", "change order"]
            ):
                return "change_order", is_main
            elif any(keyword in filename_lower for keyword in ["proposal"]):
                return "proposal", is_main
            elif any(keyword in filename_lower for keyword in ["exhibit"]):
                return "exhibit", is_main
            elif any(keyword in filename_lower for keyword in ["subcontract"]):
                return "subcontract", is_main
            elif any(keyword in filename_lower for keyword in ["affidavit"]):
                return "affidavit", is_main
            elif any(
                keyword in filename_lower
                for keyword in ["executed", "signed", "complete_with_docusign"]
            ):
                return "main_contract", True  # Definitely main if executed/signed
            else:
                return "general", is_main

        upload_results = []
        failed_uploads = []

        # Process each file
        for file in files:
            try:
                # Validate file type
                if not file.filename.lower().endswith(
                    (".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx")
                ):
                    failed_uploads.append(f"{file.filename}: Unsupported file type")
                    continue

                # Read file content
                file_content = await file.read()

                if len(file_content) == 0:
                    failed_uploads.append(f"{file.filename}: Empty file")
                    continue

                # Detect contract type and main contract status
                contract_type, is_main_contract = detect_contract_type_from_filename(
                    file.filename
                )

                logger.info(
                    f"Uploading {file.filename} as {contract_type} (main: {is_main_contract})"
                )

                # Upload to Spaces
                upload_result = storage.upload_contract_file(
                    file_content=file_content,
                    filename=file.filename,
                    user_id=current_user["id"],
                    job_number=job_number,
                    job_name=directory_name,
                    contract_type=contract_type,
                    is_main_contract=is_main_contract,
                )

                upload_results.append(
                    {
                        "filename": file.filename,
                        "contract_type": contract_type,
                        "is_main_contract": is_main_contract,
                        "file_key": upload_result["file_key"],
                        "public_url": upload_result["public_url"],
                        "size": upload_result["size"],
                    }
                )

                logger.info(
                    f"Successfully uploaded {file.filename} -> {upload_result['file_key']}"
                )

            except Exception as e:
                error_msg = f"{file.filename}: {str(e)}"
                failed_uploads.append(error_msg)
                logger.error(f"Failed to upload {file.filename}: {e}")

        # Prepare response
        response = {
            "success": True,
            "message": f"Uploaded {len(upload_results)} of {len(files)} files successfully",
            "directory_name": directory_name,
            "job_number": job_number,
            "directory_path": f"users/{current_user['id']}/jobs/{job_number}",  # For the analyze endpoint
            "uploaded_files": upload_results,
            "failed_uploads": failed_uploads,
            "total_files": len(files),
            "successful_uploads": len(upload_results),
            "failed_count": len(failed_uploads),
        }

        logger.info(
            f"Upload complete for user {current_user['email']}: {len(upload_results)} successful, {len(failed_uploads)} failed"
        )

        return response

    except Exception as e:
        logger.error(
            f"Upload failed for user {current_user.get('email', 'unknown')}: {e}"
        )
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


def extract_job_number(directory_name: str) -> str:
    """Extract job number from directory name"""
    import re

    # Try to find a number at the beginning (e.g., "2506 - Washington St.")
    match = re.match(r"^(\d+)", directory_name)
    if match:
        return match.group(1)

    # Try to find any 3-6 digit number
    match = re.search(r"\b(\d{3,6})\b", directory_name)
    if match:
        return match.group(1)

    # Fallback: use first word or "unknown"
    first_word = directory_name.split()[0] if directory_name.split() else "unknown"
    return re.sub(r"[^\w\-]", "", first_word)


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
