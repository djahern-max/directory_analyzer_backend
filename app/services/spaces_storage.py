# app/services/spaces_storage.py - Enhanced version with user/job/contract structure

import boto3
import logging
from typing import Dict, Any, Optional, BinaryIO, List
from pathlib import Path
import uuid
from datetime import datetime

from app.config import settings
from app.core.exceptions import DirectoryAnalyzerException

logger = logging.getLogger("app.services.spaces_storage")


class SpacesStorageService:
    """Service for managing file uploads to Digital Ocean Spaces with user/job/contract structure"""

    def __init__(self):
        self.logger = logger
        self.bucket_name = settings.spaces_bucket_name
        self.client = self._create_client()

    def _create_client(self):
        """Create and configure the boto3 client for DO Spaces"""
        try:
            # Validate required settings first
            if not all(
                [
                    settings.spaces_endpoint_url,
                    settings.spaces_region,
                    settings.spaces_bucket_name,
                    settings.spaces_access_key,
                    settings.spaces_secret_key,
                ]
            ):
                missing_settings = []
                if not settings.spaces_endpoint_url:
                    missing_settings.append("SPACES_ENDPOINT_URL")
                if not settings.spaces_region:
                    missing_settings.append("SPACES_REGION")
                if not settings.spaces_bucket_name:
                    missing_settings.append("SPACES_BUCKET_NAME")
                if not settings.spaces_access_key:
                    missing_settings.append("SPACES_ACCESS_KEY")
                if not settings.spaces_secret_key:
                    missing_settings.append("SPACES_SECRET_KEY")

                raise DirectoryAnalyzerException(
                    f"Missing Digital Ocean Spaces configuration: {', '.join(missing_settings)}",
                    details={"missing_settings": missing_settings},
                )

            client = boto3.client(
                "s3",
                endpoint_url=settings.spaces_endpoint_url,
                region_name=settings.spaces_region,
                aws_access_key_id=settings.spaces_access_key,
                aws_secret_access_key=settings.spaces_secret_key,
            )

            # Test the connection
            self._test_connection(client)
            return client

        except DirectoryAnalyzerException:
            raise
        except Exception as e:
            logger.error(f"Failed to create Spaces client: {e}")
            raise DirectoryAnalyzerException(
                "Failed to connect to Digital Ocean Spaces", details={"error": str(e)}
            )

    def _test_connection(self, client):
        """Test the connection to Spaces"""
        try:
            client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"Successfully connected to Spaces bucket: {self.bucket_name}")
        except Exception as e:
            logger.error(f"Failed to connect to bucket {self.bucket_name}: {e}")
            raise DirectoryAnalyzerException(
                f"Cannot access Spaces bucket: {self.bucket_name}",
                details={"error": str(e)},
            )

    def upload_contract_file(
        self,
        file_content: bytes,
        filename: str,
        user_id: str,
        job_number: str,
        job_name: str = None,
        contract_type: str = "unknown",
        is_main_contract: bool = False,
    ) -> Dict[str, Any]:
        """
        Upload a contract file with user/job/contract structure

        Args:
            file_content: The file content as bytes
            filename: Original filename
            user_id: User ID
            job_number: Job number (e.g., "2315", "CTDOT-456")
            job_name: Human-readable job name (optional)
            contract_type: Type of contract (main, amendment, change_order, etc.)
            is_main_contract: Whether this is the main contract

        Returns:
            Dictionary with file information and URLs
        """
        try:
            # Generate unique identifiers
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            file_id = str(uuid.uuid4())[:8]

            # Clean inputs
            safe_filename = self._clean_filename(filename)
            safe_job_number = self._clean_filename(job_number)
            safe_contract_type = self._clean_filename(contract_type)

            # Create hierarchical path: users/{user_id}/jobs/{job_number}/contracts/{contract_type}/{filename}
            file_key = (
                f"users/{user_id}/"
                f"jobs/{safe_job_number}/"
                f"contracts/{safe_contract_type}/"
                f"{timestamp}_{file_id}_{safe_filename}"
            )

            # Create comprehensive metadata
            metadata = {
                "original_filename": filename,
                "user_id": user_id,
                "job_number": job_number,
                "job_name": job_name or "",
                "contract_type": contract_type,
                "is_main_contract": str(is_main_contract).lower(),
                "upload_timestamp": timestamp,
                "file_id": file_id,
                "file_size": str(len(file_content)),
            }

            # Upload to Spaces
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=file_key,
                Body=file_content,
                ContentType=self._get_content_type(filename),
                Metadata=metadata,
                # Add tags for better organization
                Tagging=f"user_id={user_id}&job_number={safe_job_number}&contract_type={safe_contract_type}&main_contract={str(is_main_contract).lower()}",
            )

            # Generate URLs
            public_url = f"{settings.spaces_public_url}/{file_key}"
            spaces_url = f"{settings.spaces_endpoint_url}/{self.bucket_name}/{file_key}"

            logger.info(f"Successfully uploaded contract: {filename} -> {file_key}")

            return {
                "success": True,
                "file_key": file_key,
                "filename": safe_filename,
                "original_filename": filename,
                "size": len(file_content),
                "public_url": public_url,
                "spaces_url": spaces_url,
                "bucket": self.bucket_name,
                "user_id": user_id,
                "job_number": job_number,
                "job_name": job_name,
                "contract_type": contract_type,
                "is_main_contract": is_main_contract,
                "upload_timestamp": timestamp,
                "file_id": file_id,
                "structure": "user/job/contract",
            }

        except Exception as e:
            logger.error(f"Failed to upload contract {filename}: {e}")
            raise DirectoryAnalyzerException(
                f"Contract upload failed: {filename}",
                details={"error": str(e), "filename": filename},
            )

    def list_job_contracts(self, user_id: str, job_number: str) -> List[Dict[str, Any]]:
        """
        List all contracts for a specific job

        Args:
            user_id: User ID
            job_number: Job number

        Returns:
            List of contract information dictionaries
        """
        try:
            safe_job_number = self._clean_filename(job_number)
            prefix = f"users/{user_id}/jobs/{safe_job_number}/contracts/"

            response = self.client.list_objects_v2(
                Bucket=self.bucket_name, Prefix=prefix
            )

            contracts = []
            for obj in response.get("Contents", []):
                contract_info = {
                    "file_key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                    "public_url": f"{settings.spaces_public_url}/{obj['Key']}",
                }

                # Get metadata
                try:
                    head_response = self.client.head_object(
                        Bucket=self.bucket_name, Key=obj["Key"]
                    )
                    metadata = head_response.get("Metadata", {})
                    contract_info.update(
                        {
                            "original_filename": metadata.get("original_filename"),
                            "contract_type": metadata.get("contract_type"),
                            "is_main_contract": metadata.get("is_main_contract")
                            == "true",
                            "job_name": metadata.get("job_name"),
                            "upload_timestamp": metadata.get("upload_timestamp"),
                            "file_id": metadata.get("file_id"),
                        }
                    )
                except Exception as e:
                    logger.warning(f"Could not get metadata for {obj['Key']}: {e}")

                contracts.append(contract_info)

            # Sort contracts: main contract first, then by upload time
            contracts.sort(
                key=lambda x: (
                    not x.get("is_main_contract", False),  # Main contracts first
                    x.get("upload_timestamp", ""),  # Then by upload time
                )
            )

            return contracts

        except Exception as e:
            logger.error(f"Failed to list contracts for job {job_number}: {e}")
            raise DirectoryAnalyzerException(
                f"Failed to list contracts for job: {job_number}",
                details={"error": str(e)},
            )

    def list_user_jobs(self, user_id: str) -> List[Dict[str, Any]]:
        """
        List all jobs for a user

        Args:
            user_id: User ID

        Returns:
            List of job information dictionaries
        """
        try:
            prefix = f"users/{user_id}/jobs/"

            # Use delimiter to get "folder" structure
            response = self.client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                Delimiter="/",
            )

            jobs = []
            for common_prefix in response.get("CommonPrefixes", []):
                job_path = common_prefix["Prefix"]
                # Extract job number from path: users/{user_id}/jobs/{job_number}/
                job_number = job_path.rstrip("/").split("/")[-1]

                # Get job metadata by looking at contracts in this job
                contracts = self.list_job_contracts(user_id, job_number)

                # Extract job info from first contract's metadata
                job_info = {
                    "job_number": job_number,
                    "contract_count": len(contracts),
                    "main_contract": next(
                        (c for c in contracts if c.get("is_main_contract")), None
                    ),
                    "last_modified": max(
                        (c["last_modified"] for c in contracts), default=""
                    ),
                    "job_name": contracts[0].get("job_name") if contracts else "",
                }

                jobs.append(job_info)

            # Sort by last modified time (most recent first)
            jobs.sort(key=lambda x: x["last_modified"], reverse=True)

            return jobs

        except Exception as e:
            logger.error(f"Failed to list jobs for user {user_id}: {e}")
            raise DirectoryAnalyzerException(
                f"Failed to list jobs for user: {user_id}", details={"error": str(e)}
            )

    def get_main_contract(
        self, user_id: str, job_number: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get the main contract for a specific job

        Args:
            user_id: User ID
            job_number: Job number

        Returns:
            Main contract information or None if not found
        """
        try:
            contracts = self.list_job_contracts(user_id, job_number)
            main_contract = next(
                (c for c in contracts if c.get("is_main_contract")), None
            )

            if main_contract:
                logger.info(
                    f"Found main contract for job {job_number}: {main_contract['original_filename']}"
                )
            else:
                logger.warning(f"No main contract found for job {job_number}")

            return main_contract

        except Exception as e:
            logger.error(f"Failed to get main contract for job {job_number}: {e}")
            return None

    def download_file(self, file_key: str) -> bytes:
        """Download a file from Spaces"""
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=file_key)
            return response["Body"].read()
        except Exception as e:
            logger.error(f"Failed to download file {file_key}: {e}")
            raise DirectoryAnalyzerException(
                f"File download failed: {file_key}", details={"error": str(e)}
            )

    def delete_file(self, file_key: str) -> bool:
        """Delete a file from Spaces"""
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=file_key)
            logger.info(f"Successfully deleted file: {file_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete file {file_key}: {e}")
            return False

    def delete_job(self, user_id: str, job_number: str) -> bool:
        """
        Delete all contracts for a job

        Args:
            user_id: User ID
            job_number: Job number

        Returns:
            True if successful
        """
        try:
            contracts = self.list_job_contracts(user_id, job_number)

            # Delete all contracts
            for contract in contracts:
                self.delete_file(contract["file_key"])

            logger.info(
                f"Successfully deleted job {job_number} with {len(contracts)} contracts"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to delete job {job_number}: {e}")
            return False

    def _clean_filename(self, filename: str) -> str:
        """Clean filename for safe storage"""
        import re

        # Remove or replace problematic characters
        safe_name = re.sub(r'[<>:"/\\|?*]', "_", filename)
        safe_name = safe_name.strip(" .")

        if not safe_name:
            safe_name = "unnamed_file"

        # Limit length
        if len(safe_name) > 200:
            name_part, ext_part = Path(safe_name).stem, Path(safe_name).suffix
            safe_name = name_part[: 200 - len(ext_part)] + ext_part

        return safe_name

    def _get_content_type(self, filename: str) -> str:
        """Get content type based on file extension"""
        extension = Path(filename).suffix.lower()
        content_types = {
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".txt": "text/plain",
            ".xls": "application/vnd.ms-excel",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
        return content_types.get(extension, "application/octet-stream")


def get_spaces_storage():
    """Get a SpacesStorageService instance"""
    try:
        return SpacesStorageService()
    except DirectoryAnalyzerException as e:
        logger.error(f"Failed to initialize Spaces storage: {e.message}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error initializing Spaces storage: {e}")
        raise DirectoryAnalyzerException(
            "Failed to initialize file storage service", details={"error": str(e)}
        )
