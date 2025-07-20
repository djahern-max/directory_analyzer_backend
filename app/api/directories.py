# app/api/directories.py - Enhanced upload endpoint with user/job/contract structure

from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form, Depends
from fastapi.responses import JSONResponse
import logging
import traceback
from typing import Dict, Any, List, Optional

from app.models.directory import DirectoryAnalysisRequest
from app.services.contract_intelligence import create_contract_intelligence_service
from app.core.exceptions import DirectoryAnalyzerException
from app.config import settings
from app.middleware.premium_check import verify_premium_subscription

router = APIRouter()
logger = logging.getLogger("app.api.directories")


@router.post("/upload-contracts")
async def upload_contracts_for_job(
    files: List[UploadFile] = File(...),
    job_number: str = Form(...),
    job_name: str = Form(""),
    analyze_after_upload: bool = Form(True),
    current_user: dict = Depends(verify_premium_subscription),
) -> Dict[str, Any]:
    """
    Upload contract files for a specific job with user/job/contract structure
    """
    logger.info(
        f"Premium user {current_user['email']} uploading {len(files)} contracts for job: {job_number}"
    )

    try:
        from app.services.spaces_storage import get_spaces_storage

        # Create storage service instance
        try:
            spaces_storage = get_spaces_storage()
        except DirectoryAnalyzerException as e:
            logger.error(f"Failed to initialize file storage: {e.message}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"File storage service unavailable: {e.message}",
            )

        uploaded_contracts = []
        failed_files = []
        total_size = 0

        # First pass: Upload all files and classify them
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

                # Determine contract type from filename
                contract_type = _classify_contract_type_from_filename(file.filename)

                # Initially assume it's not the main contract
                is_main_contract = False

                # Upload to Spaces with enhanced structure
                upload_result = spaces_storage.upload_contract_file(
                    file_content=content,
                    filename=file.filename,
                    user_id=str(current_user["id"]),
                    job_number=job_number,
                    job_name=job_name,
                    contract_type=contract_type,
                    is_main_contract=is_main_contract,
                )

                uploaded_contracts.append(upload_result)
                logger.info(
                    f"Successfully uploaded: {file.filename} as {contract_type}"
                )

            except Exception as file_error:
                logger.error(f"Failed to upload {file.filename}: {file_error}")
                failed_files.append(
                    {"filename": file.filename, "error": str(file_error)}
                )

        # Check if any files were successfully uploaded
        if not uploaded_contracts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No files were successfully uploaded",
            )

        # Second pass: Analyze contracts to identify the main contract
        main_contract_identified = None
        analysis_results = None

        if analyze_after_upload and uploaded_contracts:
            try:
                analysis_results = await _analyze_uploaded_contracts(
                    uploaded_contracts,
                    current_user,
                    job_number,
                    job_name,
                    spaces_storage,
                )

                if analysis_results and analysis_results.get("main_contract"):
                    main_contract_filename = analysis_results["main_contract"][
                        "filename"
                    ]

                    # Update the main contract flag in storage
                    for contract in uploaded_contracts:
                        if contract["original_filename"] == main_contract_filename:
                            # Re-upload with main contract flag
                            await _update_main_contract_flag(
                                contract,
                                spaces_storage,
                                current_user["id"],
                                job_number,
                                job_name,
                            )
                            contract["is_main_contract"] = True
                            main_contract_identified = contract
                            break

            except Exception as analysis_error:
                logger.warning(
                    f"Analysis failed but upload succeeded: {analysis_error}"
                )
                # Don't fail the upload if analysis fails

        logger.info(
            f"Upload completed for {current_user['email']}: "
            f"{len(uploaded_contracts)} successful, {len(failed_files)} failed"
        )

        response = {
            "success": True,
            "job_number": job_number,
            "job_name": job_name,
            "contracts_uploaded": len(uploaded_contracts),
            "contracts_failed": len(failed_files),
            "total_size_bytes": total_size,
            "uploaded_contracts": uploaded_contracts,
            "failed_files": failed_files,
            "main_contract": main_contract_identified,
            "analysis_performed": analyze_after_upload,
            "user": current_user["email"],
            "storage_structure": "user/job/contract",
            "storage_location": "digital_ocean_spaces",
        }

        # Add analysis results if available
        if analysis_results:
            response["analysis_results"] = analysis_results

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Contract upload failed for user {current_user['email']}: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Contract upload failed: {str(e)}",
        )


@router.get("/jobs/{job_number}/contracts")
async def list_job_contracts(
    job_number: str,
    current_user: dict = Depends(verify_premium_subscription),
) -> Dict[str, Any]:
    """List all contracts for a specific job"""
    try:
        from app.services.spaces_storage import get_spaces_storage

        spaces_storage = get_spaces_storage()
        contracts = spaces_storage.list_job_contracts(
            user_id=str(current_user["id"]), job_number=job_number
        )

        return {
            "success": True,
            "job_number": job_number,
            "contract_count": len(contracts),
            "contracts": contracts,
            "user": current_user["email"],
        }

    except Exception as e:
        logger.error(f"Failed to list contracts for job {job_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list contracts: {str(e)}",
        )


@router.get("/jobs")
async def list_user_jobs(
    current_user: dict = Depends(verify_premium_subscription),
) -> Dict[str, Any]:
    """List all jobs for the current user"""
    try:
        from app.services.spaces_storage import get_spaces_storage

        spaces_storage = get_spaces_storage()
        jobs = spaces_storage.list_user_jobs(user_id=str(current_user["id"]))

        return {
            "success": True,
            "job_count": len(jobs),
            "jobs": jobs,
            "user": current_user["email"],
        }

    except Exception as e:
        logger.error(f"Failed to list jobs for user {current_user['email']}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list jobs: {str(e)}",
        )


@router.get("/jobs/{job_number}/main-contract")
async def get_main_contract(
    job_number: str,
    current_user: dict = Depends(verify_premium_subscription),
) -> Dict[str, Any]:
    """Get the main contract for a specific job"""
    try:
        from app.services.spaces_storage import get_spaces_storage

        spaces_storage = get_spaces_storage()
        main_contract = spaces_storage.get_main_contract(
            user_id=str(current_user["id"]), job_number=job_number
        )

        if not main_contract:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No main contract found for job {job_number}",
            )

        return {
            "success": True,
            "job_number": job_number,
            "main_contract": main_contract,
            "user": current_user["email"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get main contract for job {job_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get main contract: {str(e)}",
        )


# Helper functions


def _classify_contract_type_from_filename(filename: str) -> str:
    """Classify contract type based on filename"""
    filename_lower = filename.lower()

    if any(word in filename_lower for word in ["executed", "signed", "final", "main"]):
        return "main"
    elif any(word in filename_lower for word in ["amendment", "amend"]):
        return "amendment"
    elif any(word in filename_lower for word in ["change", "order", "co"]):
        return "change_order"
    elif any(word in filename_lower for word in ["proposal", "bid"]):
        return "proposal"
    elif any(word in filename_lower for word in ["schedule", "sched"]):
        return "schedule"
    elif any(word in filename_lower for word in ["insurance", "bond"]):
        return "insurance"
    else:
        return "unknown"


async def _analyze_uploaded_contracts(
    uploaded_contracts: List[Dict[str, Any]],
    current_user: dict,
    job_number: str,
    job_name: str,
    spaces_storage,
) -> Optional[Dict[str, Any]]:
    """Analyze uploaded contracts to identify the main contract"""
    try:
        # Create a temporary analysis structure that mimics directory analysis
        api_key = settings.anthropic_api_key
        intelligence_service = create_contract_intelligence_service(api_key)

        # Download and analyze each contract
        classifications = []

        for contract in uploaded_contracts:
            try:
                # Download file content
                file_content = spaces_storage.download_file(contract["file_key"])

                # Extract text (you'll need to implement this for uploaded files)
                # For now, this is a placeholder
                document_text = f"Contract: {contract['original_filename']}"

                # Classify the document
                classification = intelligence_service.ai_classifier.classify_document(
                    document_text=document_text,
                    filename=contract["original_filename"],
                    job_name=job_name,
                )

                classification["file_key"] = contract["file_key"]
                classifications.append(classification)

            except Exception as e:
                logger.warning(
                    f"Failed to analyze {contract['original_filename']}: {e}"
                )
                continue

        if classifications:
            # Use document analyzer to identify main contract
            main_contract = (
                intelligence_service.document_analyzer.identify_main_contract(
                    classifications
                )
            )
            ranked_documents = intelligence_service.document_analyzer.rank_documents(
                classifications
            )

            return {
                "main_contract": main_contract,
                "ranked_documents": ranked_documents,
                "total_analyzed": len(classifications),
                "job_number": job_number,
                "job_name": job_name,
            }

        return None

    except Exception as e:
        logger.error(f"Contract analysis failed: {e}")
        return None


async def _update_main_contract_flag(
    contract: Dict[str, Any],
    spaces_storage,
    user_id: str,
    job_number: str,
    job_name: str,
) -> None:
    """Update the main contract flag by re-uploading with updated metadata"""
    try:
        # Download the current file
        file_content = spaces_storage.download_file(contract["file_key"])

        # Delete the old file
        spaces_storage.delete_file(contract["file_key"])

        # Re-upload with main contract flag
        updated_contract = spaces_storage.upload_contract_file(
            file_content=file_content,
            filename=contract["original_filename"],
            user_id=user_id,
            job_number=job_number,
            job_name=job_name,
            contract_type=contract["contract_type"],
            is_main_contract=True,
        )

        # Update the contract info
        contract.update(updated_contract)

    except Exception as e:
        logger.error(f"Failed to update main contract flag: {e}")
        raise
