# Create app/services/google_vision_extractor.py

import logging
import base64
from pathlib import Path
from typing import Optional
import json
import os

from app.core.exceptions import PDFExtractionError
from app.config import settings

logger = logging.getLogger("app.services.google_vision_extractor")


class GoogleVisionExtractor:
    """Service for extracting text from PDF files using Google Cloud Vision OCR"""
    
    def __init__(self):
        self.logger = logger
        self.credentials_path = settings.google_cloud_credentials_path
    
    def extract_text_from_file(self, file_path: Path) -> str:
        """
        Extract text from a PDF file using Google Cloud Vision OCR
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Extracted text content
            
        Raises:
            PDFExtractionError: If text extraction fails
        """
        try:
            from google.cloud import vision
            from google.oauth2 import service_account
            
            self.logger.debug(f"Extracting text using Google Vision: {file_path}")
            
            # Initialize the client with credentials
            if self.credentials_path and os.path.exists(self.credentials_path):
                credentials = service_account.Credentials.from_service_account_file(
                    self.credentials_path
                )
                client = vision.ImageAnnotatorClient(credentials=credentials)
            else:
                # Try to use default credentials or environment variable
                client = vision.ImageAnnotatorClient()
            
            # Read the PDF file as bytes
            with open(file_path, 'rb') as pdf_file:
                pdf_content = pdf_file.read()
            
            # Create vision document object for PDF
            input_config = vision.InputConfig(
                gcs_source=None,  # We're not using Google Cloud Storage
                content=pdf_content,
                mime_type='application/pdf'
            )
            
            # Configure output (we want text)
            output_config = vision.OutputConfig(
                gcs_destination=None,  # Output to response, not storage
                batch_size=1
            )
            
            # Create the request for document text detection
            features = [vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)]
            
            request = vision.AnnotateFileRequest(
                input_config=input_config,
                features=features,
                pages=None  # Process all pages
            )
            
            # Perform the text detection
            response = client.batch_annotate_files(requests=[request])
            
            # Extract text from all pages
            text = ""
            
            if response.responses:
                for page_response in response.responses[0].responses:
                    if page_response.full_text_annotation:
                        text += page_response.full_text_annotation.text + "\n"
                    
                    # Check for errors
                    if page_response.error.message:
                        raise PDFExtractionError(
                            f"Google Vision API error: {page_response.error.message}",
                            details={"file_path": str(file_path)}
                        )
            
            if not text.strip():
                raise PDFExtractionError(
                    f"No text could be extracted from {file_path.name} using Google Vision",
                    details={"file_path": str(file_path)}
                )
            
            self.logger.info(f"Successfully extracted {len(text)} characters using Google Vision: {file_path.name}")
            return text.strip()
            
        except ImportError as e:
            if "google.cloud" in str(e):
                raise PDFExtractionError(
                    "Google Cloud Vision library is not installed. Install with: pip install google-cloud-vision",
                    details={"required_library": "google-cloud-vision"}
                )
            else:
                raise PDFExtractionError(
                    f"Missing required library: {str(e)}",
                    details={"error": str(e)}
                )
                
        except Exception as e:
            self.logger.error(f"Google Vision extraction failed for {file_path}: {e}")
            raise PDFExtractionError(
                f"Failed to extract text from {file_path.name} using Google Vision: {str(e)}",
                details={
                    "file_path": str(file_path),
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )


# Global instance
google_vision_extractor = GoogleVisionExtractor()