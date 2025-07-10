import logging
from pathlib import Path
from typing import Optional
import io

from app.core.exceptions import PDFExtractionError
from app.config import settings

logger = logging.getLogger("app.services.pdf_extractor")


class PDFExtractor:
    """Service for extracting text from PDF files with fallback to Google Vision"""
    
    def __init__(self):
        self.logger = logger
        self._google_extractor = None
    
    @property
    def google_extractor(self):
        """Lazy load Google Vision extractor"""
        if self._google_extractor is None and settings.use_google_vision_ocr:
            try:
                from app.services.google_vision_extractor import google_vision_extractor
                self._google_extractor = google_vision_extractor
                self.logger.info("Google Vision OCR enabled")
            except ImportError as e:
                self.logger.warning(f"Google Vision OCR not available: {e}")
        return self._google_extractor
    
    def extract_text_from_file(self, file_path: Path) -> str:
        """
        Extract text from a PDF file with fallback to Google Vision OCR
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Extracted text content
            
        Raises:
            PDFExtractionError: If text extraction fails
        """
        # First try pdfplumber (faster and cheaper)
        try:
            text = self._extract_with_pdfplumber(file_path)
            if text and len(text.strip()) > 50:  # Good text extraction
                self.logger.info(f"Successfully extracted text with pdfplumber: {file_path.name}")
                return text
            else:
                self.logger.warning(f"Poor text extraction with pdfplumber: {file_path.name} ({len(text)} chars)")
                
        except Exception as e:
            self.logger.warning(f"pdfplumber failed for {file_path.name}: {e}")
        
        # Fall back to Google Vision OCR if enabled
        if self.google_extractor:
            try:
                self.logger.info(f"Falling back to Google Vision OCR: {file_path.name}")
                text = self.google_extractor.extract_text_from_file(file_path)
                return text
            except Exception as e:
                self.logger.error(f"Google Vision OCR also failed for {file_path.name}: {e}")
        
        # If everything fails
        raise PDFExtractionError(
            f"All text extraction methods failed for {file_path.name}",
            details={
                "file_path": str(file_path),
                "pdfplumber_available": True,
                "google_vision_available": self.google_extractor is not None
            }
        )
    
    def _extract_with_pdfplumber(self, file_path: Path) -> str:
        """Extract text using pdfplumber"""
        try:
            import pdfplumber
            
            self.logger.debug(f"Extracting text with pdfplumber: {file_path}")
            
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
            
            return text.strip()
            
        except ImportError:
            raise PDFExtractionError(
                "pdfplumber library is not installed",
                details={"required_library": "pdfplumber"}
            )
        except Exception as e:
            raise PDFExtractionError(
                f"pdfplumber extraction failed: {str(e)}",
                details={"error": str(e)}
            )


# Global instance
pdf_extractor = PDFExtractor()