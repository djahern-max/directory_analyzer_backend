# app/api/directories.py
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from typing import List
import logging
from pathlib import Path
import tempfile
import shutil
from sqlalchemy.orm import Session

from app.models.directory import DirectoryAnalysisRequest
from app.models.database import Job, Contract
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


@router.get("/jobs")
async def get_user_jobs(
    current_user: dict = Depends(verify_premium_subscription),
    db: Session = Depends(get_db),
):
    """
    Get all jobs for the current user - PREMIUM ONLY
    """
    try:
        logger.info(f"Fetching jobs for user {current_user['email']}")

        # Initialize storage service
        storage = get_spaces_storage()

        # Get jobs from Digital Ocean Spaces
        try:
            spaces_jobs = storage.list_user_jobs(current_user["id"])
        except Exception as e:
            logger.error(f"Error fetching jobs from spaces: {e}")
            spaces_jobs = []

        # Get jobs from database for additional metadata
        db_jobs = db.query(Job).filter(Job.user_id == current_user["id"]).all()

        # Create a mapping of job numbers to database records
        db_jobs_map = {job.job_number: job for job in db_jobs}

        # Combine data from both sources
        combined_jobs = []

        # First, add jobs that exist in Spaces
        for spaces_job in spaces_jobs:
            job_number = spaces_job.get("job_number")
            db_job = db_jobs_map.get(job_number)

            # Get contracts for this job
            try:
                contracts = storage.list_job_contracts(current_user["id"], job_number)
                main_contract = next(
                    (c for c in contracts if c.get("is_main_contract")), None
                )
            except Exception as e:
                logger.warning(f"Could not fetch contracts for job {job_number}: {e}")
                contracts = []
                main_contract = None

            combined_job = {
                "id": str(db_job.id) if db_job else None,
                "job_number": job_number,
                "job_name": (
                    db_job.job_name
                    if db_job
                    else spaces_job.get("job_name", f"Job {job_number}")
                ),
                "client_name": db_job.client_name if db_job else None,
                "status": db_job.status if db_job else "active",
                "total_contracts": len(contracts),
                "main_contract_filename": (
                    main_contract.get("original_filename") if main_contract else None
                ),
                "created_at": (
                    db_job.created_at.isoformat()
                    if db_job and db_job.created_at
                    else None
                ),
                "updated_at": (
                    db_job.updated_at.isoformat()
                    if db_job and db_job.updated_at
                    else None
                ),
                "last_uploaded": spaces_job.get("last_modified"),
                "has_main_contract": main_contract is not None,
                "contract_types": list(
                    set([c.get("contract_type", "unknown") for c in contracts])
                ),
                "spaces_data": spaces_job,  # Include raw spaces data for debugging
            }

            combined_jobs.append(combined_job)

        # Also add any database jobs that don't exist in Spaces (edge case)
        spaces_job_numbers = {job.get("job_number") for job in spaces_jobs}
        for db_job in db_jobs:
            if db_job.job_number not in spaces_job_numbers:
                combined_job = {
                    "id": str(db_job.id),
                    "job_number": db_job.job_number,
                    "job_name": db_job.job_name or f"Job {db_job.job_number}",
                    "client_name": db_job.client_name,
                    "status": db_job.status,
                    "total_contracts": 0,  # No contracts in spaces
                    "main_contract_filename": None,
                    "created_at": (
                        db_job.created_at.isoformat() if db_job.created_at else None
                    ),
                    "updated_at": (
                        db_job.updated_at.isoformat() if db_job.updated_at else None
                    ),
                    "last_uploaded": None,
                    "has_main_contract": False,
                    "contract_types": [],
                    "spaces_data": None,
                }
                combined_jobs.append(combined_job)

        # Sort by most recently updated/uploaded
        combined_jobs.sort(
            key=lambda x: x.get("last_uploaded", x.get("updated_at", "")), reverse=True
        )

        logger.info(f"Found {len(combined_jobs)} jobs for user {current_user['email']}")

        return {
            "success": True,
            "jobs": combined_jobs,
            "total_jobs": len(combined_jobs),
        }

    except Exception as e:
        logger.error(
            f"Failed to fetch jobs for user {current_user.get('email', 'unknown')}: {e}"
        )
        raise HTTPException(status_code=500, detail=f"Failed to fetch jobs: {str(e)}")


@router.get("/jobs/{job_number}/contracts")
async def get_job_contracts(
    job_number: str,
    current_user: dict = Depends(verify_premium_subscription),
    db: Session = Depends(get_db),
):
    """
    Get all contracts for a specific job - PREMIUM ONLY
    """
    try:
        logger.info(
            f"Fetching contracts for job {job_number}, user {current_user['email']}"
        )

        # Initialize storage service
        storage = get_spaces_storage()

        # Get contracts from Digital Ocean Spaces
        try:
            contracts = storage.list_job_contracts(current_user["id"], job_number)
        except Exception as e:
            logger.error(f"Error fetching contracts from spaces: {e}")
            contracts = []

        # Get job info from database
        db_job = (
            db.query(Job)
            .filter(Job.user_id == current_user["id"], Job.job_number == job_number)
            .first()
        )

        # Format contracts for frontend
        formatted_contracts = []
        for contract in contracts:
            formatted_contract = {
                "id": contract.get("file_key"),  # Use file_key as unique identifier
                "filename": contract.get("original_filename"),
                "contract_type": contract.get("contract_type", "unknown"),
                "is_main_contract": contract.get("is_main_contract", False),
                "file_size": contract.get("size"),
                "upload_date": contract.get("upload_timestamp"),
                "public_url": contract.get("public_url"),
                "file_key": contract.get("file_key"),
                "status": "uploaded",  # You can enhance this based on analysis status
            }
            formatted_contracts.append(formatted_contract)

        # Sort: main contract first, then by upload date
        formatted_contracts.sort(
            key=lambda x: (
                not x.get("is_main_contract", False),
                x.get("upload_date", ""),
            )
        )

        response = {
            "success": True,
            "job_number": job_number,
            "job_name": db_job.job_name if db_job else f"Job {job_number}",
            "contracts": formatted_contracts,
            "total_contracts": len(formatted_contracts),
            "main_contract": next(
                (c for c in formatted_contracts if c.get("is_main_contract")), None
            ),
        }

        logger.info(f"Found {len(formatted_contracts)} contracts for job {job_number}")
        return response

    except Exception as e:
        logger.error(f"Failed to fetch contracts for job {job_number}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch contracts: {str(e)}"
        )


# Keep all your existing endpoints below this point
# (upload, analyze, etc.)


# Existing helper functions
def extract_job_number(directory_name: str) -> str:
    """Extract job number from directory name"""
    import re

    # Try to find a number at the beginning (e.g., "2506 - Washington St.")
    match = re.search(r"^(\d+)", directory_name.strip())
    if match:
        return match.group(1)

    # Try to find number after common prefixes
    prefixes = ["job", "project", "contract", "#"]
    for prefix in prefixes:
        pattern = rf"{prefix}\s*[#:\-]?\s*(\d+)"
        match = re.search(pattern, directory_name, re.IGNORECASE)
        if match:
            return match.group(1)

    # Fallback: return cleaned directory name
    cleaned = re.sub(r"[^\w\-]", "", directory_name)
    return cleaned[:20] if cleaned else "unknown"
