# app/services/spaces_storage.py - Fixed version
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
    """Service for managing file uploads to Digital Ocean Spaces"""

    def __init__(self):
        self.logger = logger
        # Set bucket_name BEFORE calling _create_client
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
            # Re-raise our custom exceptions
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

    def upload_file(
        self,
        file_content: bytes,
        filename: str,
        user_id: str,
        directory_name: str = None,
    ) -> Dict[str, Any]:
        """
        Upload a file to Digital Ocean Spaces

        Args:
            file_content: The file content as bytes
            filename: Original filename
            user_id: User ID for organizing files
            directory_name: Optional directory name for grouping

        Returns:
            Dictionary with file information and URLs
        """
        try:
            # Generate unique file path
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            file_id = str(uuid.uuid4())[:8]

            # Clean filename
            safe_filename = self._clean_filename(filename)

            # Create file path: users/{user_id}/{directory_name}/{timestamp}_{file_id}_{filename}
            path_parts = ["users", user_id]
            if directory_name:
                path_parts.append(self._clean_filename(directory_name))

            file_key = "/".join(path_parts) + f"/{timestamp}_{file_id}_{safe_filename}"

            # Upload to Spaces
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=file_key,
                Body=file_content,
                ContentType=self._get_content_type(filename),
                Metadata={
                    "original_filename": filename,
                    "user_id": user_id,
                    "upload_timestamp": timestamp,
                    "directory_name": directory_name or "",
                },
            )

            # Generate URLs
            public_url = f"{settings.spaces_public_url}/{file_key}"
            spaces_url = f"{settings.spaces_endpoint_url}/{self.bucket_name}/{file_key}"

            logger.info(f"Successfully uploaded file: {filename} -> {file_key}")

            return {
                "success": True,
                "file_key": file_key,
                "filename": safe_filename,
                "original_filename": filename,
                "size": len(file_content),
                "public_url": public_url,
                "spaces_url": spaces_url,
                "bucket": self.bucket_name,
                "upload_timestamp": timestamp,
                "file_id": file_id,
            }

        except Exception as e:
            logger.error(f"Failed to upload file {filename}: {e}")
            raise DirectoryAnalyzerException(
                f"File upload failed: {filename}",
                details={"error": str(e), "filename": filename},
            )

    def download_file(self, file_key: str) -> bytes:
        """
        Download a file from Spaces

        Args:
            file_key: The file key in Spaces

        Returns:
            File content as bytes
        """
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=file_key)
            return response["Body"].read()

        except Exception as e:
            logger.error(f"Failed to download file {file_key}: {e}")
            raise DirectoryAnalyzerException(
                f"File download failed: {file_key}", details={"error": str(e)}
            )

    def delete_file(self, file_key: str) -> bool:
        """
        Delete a file from Spaces

        Args:
            file_key: The file key in Spaces

        Returns:
            True if successful
        """
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=file_key)
            logger.info(f"Successfully deleted file: {file_key}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete file {file_key}: {e}")
            return False

    def list_user_files(
        self, user_id: str, directory_name: str = None
    ) -> List[Dict[str, Any]]:
        """
        List all files for a user

        Args:
            user_id: User ID
            directory_name: Optional directory filter

        Returns:
            List of file information dictionaries
        """
        try:
            prefix = f"users/{user_id}/"
            if directory_name:
                prefix += f"{self._clean_filename(directory_name)}/"

            response = self.client.list_objects_v2(
                Bucket=self.bucket_name, Prefix=prefix
            )

            files = []
            for obj in response.get("Contents", []):
                file_info = {
                    "file_key": obj["Key"],
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                    "public_url": f"{settings.spaces_public_url}/{obj['Key']}",
                }

                # Try to get metadata
                try:
                    head_response = self.client.head_object(
                        Bucket=self.bucket_name, Key=obj["Key"]
                    )
                    file_info.update(head_response.get("Metadata", {}))
                except:
                    pass

                files.append(file_info)

            return files

        except Exception as e:
            logger.error(f"Failed to list files for user {user_id}: {e}")
            raise DirectoryAnalyzerException(
                f"Failed to list files for user: {user_id}", details={"error": str(e)}
            )

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


# Create a function to get the service instance
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
