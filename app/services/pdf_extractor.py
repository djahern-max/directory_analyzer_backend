import logging
from pathlib import Path
from typing import Optional
import io

from app.core.exceptions import PDFExtractionError

logger = logging.getLogger("app.services.pdf_extractor")


class PDFExtractor:
   """Service for extracting text from PDF files"""
   
   def __init__(self):
       self.logger = logger
   
   def extract_text_from_file(self, file_path: Path) -> str:
       """
       Extract text from a PDF file
       
       Args:
           file_path: Path to the PDF file
           
       Returns:
           Extracted text content
           
       Raises:
           PDFExtractionError: If text extraction fails
       """
       try:
           import pdfplumber
           
           self.logger.debug(f"Extracting text from: {file_path}")
           
           text = ""
           with pdfplumber.open(file_path) as pdf:
               for page_num, page in enumerate(pdf.pages, 1):
                   try:
                       page_text = page.extract_text()
                       if page_text:
                           text += page_text + "\n"
                           self.logger.debug(f"Extracted {len(page_text)} chars from page {page_num}")
                   except Exception as e:
                       self.logger.warning(f"Failed to extract text from page {page_num}: {e}")
                       continue
           
           if not text.strip():
               raise PDFExtractionError(
                   f"No text could be extracted from {file_path.name}",
                   details={"file_path": str(file_path)}
               )
           
           self.logger.info(f"Successfully extracted {len(text)} characters from {file_path.name}")
           return text.strip()
           
       except ImportError:
           raise PDFExtractionError(
               "pdfplumber library is not installed",
               details={"required_library": "pdfplumber"}
           )
       except Exception as e:
           self.logger.error(f"PDF extraction failed for {file_path}: {e}")
           raise PDFExtractionError(
               f"Failed to extract text from {file_path.name}: {str(e)}",
               details={
                   "file_path": str(file_path),
                   "error_type": type(e).__name__,
                   "error_message": str(e)
               }
           )
   
   def extract_text_from_bytes(self, pdf_bytes: bytes, filename: str = "unknown.pdf") -> str:
       """
       Extract text from PDF bytes
       
       Args:
           pdf_bytes: PDF file content as bytes
           filename: Name of the file (for logging)
           
       Returns:
           Extracted text content
           
       Raises:
           PDFExtractionError: If text extraction fails
       """
       try:
           import pdfplumber
           
           self.logger.debug(f"Extracting text from bytes: {filename}")
           
           text = ""
           with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
               for page_num, page in enumerate(pdf.pages, 1):
                   try:
                       page_text = page.extract_text()
                       if page_text:
                           text += page_text + "\n"
                   except Exception as e:
                       self.logger.warning(f"Failed to extract text from page {page_num}: {e}")
                       continue
           
           if not text.strip():
               raise PDFExtractionError(
                   f"No text could be extracted from {filename}",
                   details={"filename": filename}
               )
           
           self.logger.info(f"Successfully extracted {len(text)} characters from {filename}")
           return text.strip()
           
       except ImportError:
           raise PDFExtractionError(
               "pdfplumber library is not installed",
               details={"required_library": "pdfplumber"}
           )
       except Exception as e:
           self.logger.error(f"PDF extraction failed for {filename}: {e}")
           raise PDFExtractionError(
               f"Failed to extract text from {filename}: {str(e)}",
               details={
                   "filename": filename,
                   "error_type": type(e).__name__,
                   "error_message": str(e)
               }
           )
   
   def validate_pdf_file(self, file_path: Path) -> bool:
       """
       Validate that a file is a readable PDF
       
       Args:
           file_path: Path to the file
           
       Returns:
           True if file is a valid PDF, False otherwise
       """
       try:
           import pdfplumber
           
           with pdfplumber.open(file_path) as pdf:
               # Try to access the first page
               if len(pdf.pages) > 0:
                   _ = pdf.pages[0]
                   return True
               return False
               
       except Exception as e:
           self.logger.warning(f"PDF validation failed for {file_path}: {e}")
           return False
   
   def get_pdf_info(self, file_path: Path) -> dict:
       """
       Get basic information about a PDF file
       
       Args:
           file_path: Path to the PDF file
           
       Returns:
           Dictionary with PDF information
       """
       try:
           import pdfplumber
           
           info = {
               "filename": file_path.name,
               "file_path": str(file_path),
               "page_count": 0,
               "is_valid": False,
               "has_text": False,
               "estimated_text_length": 0
           }
           
           with pdfplumber.open(file_path) as pdf:
               info["page_count"] = len(pdf.pages)
               info["is_valid"] = True
               
               # Check first few pages for text
               sample_text = ""
               max_pages_to_check = min(3, len(pdf.pages))
               
               for i in range(max_pages_to_check):
                   try:
                       page_text = pdf.pages[i].extract_text()
                       if page_text:
                           sample_text += page_text
                   except Exception:
                       continue
               
               if sample_text.strip():
                   info["has_text"] = True
                   # Estimate total text length based on sample
                   avg_text_per_page = len(sample_text) / max_pages_to_check
                   info["estimated_text_length"] = int(avg_text_per_page * info["page_count"])
           
           return info
           
       except Exception as e:
           self.logger.warning(f"Could not get PDF info for {file_path}: {e}")
           return {
               "filename": file_path.name,
               "file_path": str(file_path),
               "page_count": 0,
               "is_valid": False,
               "has_text": False,
               "estimated_text_length": 0,
               "error": str(e)
           }


# Global instance
pdf_extractor = PDFExtractor()
